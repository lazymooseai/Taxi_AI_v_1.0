“””
dashboard.py — Kojelauta-välilehti
Helsinki Taxi AI

Muutokset v1.1:
✅ Navigaatio kiinnitetty ALAOSAAN (ei enää piiloudu scrollatessa)
✅ Jokainen kortti: “Avaa →” link_button suoraan tapahtuman sivulle
✅ Jokainen signaali kortissa: oma linkkinappi source_url:iin
✅ Reaaliaikainen sijaintiboosteri (streamlit-geolocation)
✅ Junat: näytetään vain saapuvat kaukojunat + VR-linkki suodatettuna
✅ EventsAgent: toimivat lähteet, täyttöaste näkyvissä
“””

from **future** import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st

# Sijaintipalvelu

try:
from src.taxiapp.location_service import (
get_location_from_session,
render_location_widget,
apply_location_boost,
get_smart_recommendation_text,
)
LOCATION_AVAILABLE = True
except ImportError:
LOCATION_AVAILABLE = False

logger = logging.getLogger(“taxiapp.dashboard”)

# ── Värit ──────────────────────────────────────────────────────────────────

COLOR_RED   = “#FF4B4B”
COLOR_GOLD  = “#FFD700”
COLOR_BLUE  = “#00B4D8”
COLOR_MUTED = “#888899”
COLOR_BG    = “#0e1117”
COLOR_CARD  = “#1a1d27”
COLOR_BORDER = “#2a2d3d”

# ── CSS ────────────────────────────────────────────────────────────────────

DASHBOARD_CSS = “””

<style>
/* ── Perusta ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [data-testid="stAppViewContainer"] {
    background: #0e1117 !important;
    font-family: 'Inter', sans-serif !important;
    color: #FAFAFA !important;
}

/* ── KIINTEÄ ALAPALKKI (navigaatio) ── */
.bottom-nav {
    position: fixed !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 9999 !important;
    background: #12151f !important;
    border-top: 1px solid #2a2d3d !important;
    padding: 8px 16px !important;
    display: flex !important;
    justify-content: space-around !important;
    align-items: center !important;
}
.nav-btn {
    background: transparent !important;
    border: none !important;
    color: #888899 !important;
    font-size: 0.75rem !important;
    text-align: center !important;
    cursor: pointer !important;
    padding: 4px 12px !important;
    border-radius: 8px !important;
    transition: all 0.15s !important;
    min-width: 60px !important;
}
.nav-btn.active {
    color: #00B4D8 !important;
    background: rgba(0,180,216,0.12) !important;
}

/* Lisää tilaa alapalkille ettei sisältö jää sen alle */
.main-content-wrapper {
    padding-bottom: 72px !important;
}

/* ── Yläpalkki ── */
.top-bar {
    background: linear-gradient(135deg, #12151f 0%, #1a1d27 100%);
    border: 1px solid #2a2d3d;
    border-radius: 14px;
    padding: 14px 20px;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.top-bar-clock {
    font-size: 2.4rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: #FAFAFA;
    font-variant-numeric: tabular-nums;
}
.top-bar-weather {
    font-size: 1.0rem;
    color: #CCCCDD;
    text-align: right;
}
.top-bar-location {
    font-size: 0.78rem;
    color: #00B4D8;
    margin-top: 2px;
}

/* ── Kortit ── */
.hotspot-card {
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 12px;
    position: relative;
    overflow: hidden;
    transition: transform 0.12s ease;
}
.hotspot-card:hover { transform: translateY(-2px); }

.card-red  { background: linear-gradient(135deg, #2d0a0a 0%, #1a0505 100%); border: 1px solid #FF4B4B44; }
.card-gold { background: linear-gradient(135deg, #2d2200 0%, #1a1500 100%); border: 1px solid #FFD70044; }
.card-blue { background: linear-gradient(135deg, #00162a 0%, #000d1a 100%); border: 1px solid #00B4D844; }

.card-badge {
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 8px;
    text-transform: uppercase;
}
.badge-red  { background: #FF4B4B22; color: #FF4B4B; border: 1px solid #FF4B4B44; }
.badge-gold { background: #FFD70022; color: #FFD700; border: 1px solid #FFD70044; }
.badge-blue { background: #00B4D822; color: #00B4D8; border: 1px solid #00B4D844; }

.card-title {
    font-size: 1.45rem;
    font-weight: 700;
    line-height: 1.2;
    margin-bottom: 6px;
    color: #FAFAFA;
}
.card-score {
    font-size: 0.8rem;
    color: #888899;
    margin-bottom: 10px;
}
.card-reason {
    font-size: 0.82rem;
    color: #CCCCDD;
    line-height: 1.5;
}
.card-reason .reason-item {
    display: block;
    padding: 3px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.card-reason .reason-item:last-child { border-bottom: none; }

/* Pienikokoinen täyttöaste-merkki */
.fill-badge {
    display: inline-block;
    font-size: 0.7rem;
    padding: 1px 7px;
    border-radius: 10px;
    margin-left: 6px;
    vertical-align: middle;
}
.fill-sold-out { background: #FF4B4B33; color: #FF4B4B; }
.fill-limited  { background: #FF8C0033; color: #FF8C00; }
.fill-normal   { background: #21C55D22; color: #21C55D; }

/* ── Häiriöbanneri ── */
.disruption-banner {
    background: linear-gradient(90deg, #2d0a0a, #1a0505);
    border: 1px solid #FF4B4B66;
    border-radius: 10px;
    padding: 10px 16px;
    margin-bottom: 12px;
    font-size: 0.88rem;
    color: #FF6B6B;
    animation: pulse-border 2s infinite;
}
@keyframes pulse-border {
    0%, 100% { border-color: #FF4B4B66; }
    50%       { border-color: #FF4B4Bcc; }
}

/* ── Sää-widget ── */
.weather-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 0.85rem;
    margin: 4px 4px 4px 0;
}

/* ── Agent-statuspisteet ── */
.agent-dots {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin: 8px 0;
}
.agent-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
}
.dot-ok    { background: #21C55D; }
.dot-error { background: #FF4B4B; }
.dot-off   { background: #444455; }

/* ── Streamlit-overridet ── */
.stButton > button {
    background: #1a1d27 !important;
    border: 1px solid #2a2d3d !important;
    color: #FAFAFA !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    padding: 6px 14px !important;
}
.stButton > button:hover {
    border-color: #00B4D8 !important;
    color: #00B4D8 !important;
    background: rgba(0,180,216,0.08) !important;
}
.stLinkButton > a {
    background: rgba(0,180,216,0.1) !important;
    border: 1px solid #00B4D844 !important;
    color: #00B4D8 !important;
    border-radius: 10px !important;
    font-size: 0.82rem !important;
    padding: 5px 14px !important;
    text-decoration: none !important;
    font-weight: 500 !important;
}
.stLinkButton > a:hover {
    background: rgba(0,180,216,0.2) !important;
    border-color: #00B4D8 !important;
}
div[data-testid="column"] { padding: 0 5px !important; }
.block-container {
    padding-top: 0.8rem !important;
    padding-bottom: 80px !important;   /* tilaa alapalkille */
    max-width: 1200px !important;
}
h1, h2, h3 { font-family: 'Inter', sans-serif !important; }
</style>

“””

# ── Alapalkki JavaScript-injektio ─────────────────────────────────────────

# Injektoi kiinteän alapalkin Streamlit-sovellukseen.

# st.tabs() sijaitsee liian ylhäällä → korvataan kiinteällä JS-navigaatiolla.

BOTTOM_NAV_JS = “””

<script>
// Kiinteä alapalkki — ajetaan kerran sivun latauksen jälkeen
(function injectBottomNav() {
    const tabs = window.parent.document.querySelectorAll('[data-baseweb="tab"]');
    if (!tabs.length) {
        setTimeout(injectBottomNav, 300);
        return;
    }
    const tabBar = tabs[0].closest('[data-baseweb="tab-list"]');
    if (!tabBar) { setTimeout(injectBottomNav, 300); return; }

    // Siirrä tab-bar kiinteäksi alapalkiksi
    tabBar.style.cssText = `
        position: fixed !important;
        bottom: 0 !important;
        left: 0 !important;
        right: 0 !important;
        z-index: 9999 !important;
        background: #12151f !important;
        border-top: 1px solid #2a2d3d !important;
        padding: 4px 0 env(safe-area-inset-bottom, 0) !important;
        margin: 0 !important;
        width: 100% !important;
        justify-content: space-around !important;
        box-shadow: 0 -4px 20px rgba(0,0,0,0.4) !important;
    `;

    // Tyylitä yksittäiset tabnapit
    tabs.forEach(tab => {
        tab.style.cssText = `
            font-size: 0.75rem !important;
            padding: 8px 12px !important;
            color: #888899 !important;
            border: none !important;
            background: transparent !important;
            min-width: 56px !important;
        `;
    });
})();
</script>

“””

# ══════════════════════════════════════════════════════════════

# APUFUNKTIOT

# ══════════════════════════════════════════════════════════════

def _helsinki_time() -> datetime:
“”“Palauta Helsingin paikallisaika (EET/EEST).”””
import time as _t
offset = 3 if _t.daylight else 2
return datetime.now(timezone.utc) + timedelta(hours=offset)

def _fill_rate_badge(fill_rate: Optional[float]) -> str:
if fill_rate is None:
return “”
if fill_rate >= 1.0:
return ‘<span class="fill-badge fill-sold-out">🔴 LOPPUUNMYYTY</span>’
if fill_rate >= 0.85:
return ‘<span class="fill-badge fill-limited">🟠 Viim. liput</span>’
if fill_rate >= 0.5:
return ‘<span class="fill-badge fill-normal">🟢 Lippuja</span>’
return “”

def _urgency_label(urgency: int) -> str:
if urgency >= 9: return “⛔ OVERRIDE”
if urgency >= 7: return “🔴 KRIITTINEN”
if urgency >= 5: return “🟠 KORKEA”
if urgency >= 3: return “🟡 NORMAALI”
return “⚪ PERUS”

def _card_classes(idx: int, urgency: int) -> tuple[str, str]:
“”“Palauta (card_css_class, badge_css_class) kortin indeksin mukaan.”””
if urgency >= 9 or idx == 0:
return “card-red”, “badge-red”
if idx == 1:
return “card-gold”, “badge-gold”
return “card-blue”, “badge-blue”

# ══════════════════════════════════════════════════════════════

# KORTTIEN RENDEROINTI

# ══════════════════════════════════════════════════════════════

def _render_hotspot_card(hotspot, idx: int) -> None:
“””
Renderöi yksi hotspot-kortti.

```
Kortin rakenne:
  [BADGE] [TITLE]
  [pisteet] [agenttien kuvaukset syinä]
  [Avaa → link_button per signaali jolla source_url]

Parametrit:
    hotspot: Hotspot-objekti (CEO:lta)
    idx: Järjestysnumero (0=punainen, 1=kulta, 2=sininen)
"""
card_cls, badge_cls = _card_classes(idx, getattr(hotspot, "urgency", 2))
urgency_label = _urgency_label(getattr(hotspot, "urgency", 2))
score = getattr(hotspot, "score", 0.0)
title = getattr(hotspot, "area", "?").replace("_", " ").title()
signals = getattr(hotspot, "signals", [])

# ── Syyt HTML ─────────────────────────────────────────────
reasons_html = ""
for sig in signals[:5]:
    desc = getattr(sig, "description", "")
    fill_rate = (getattr(sig, "extra", {}) or {}).get("fill_rate")
    fill_badge = _fill_rate_badge(fill_rate)
    if desc:
        reasons_html += (
            f'<span class="reason-item">'
            f'{desc}{fill_badge}'
            f'</span>'
        )

# ── Kortti HTML ────────────────────────────────────────────
st.markdown(
    f"""
    <div class="hotspot-card {card_cls}">
        <div class="card-badge {badge_cls}">{urgency_label}</div>
        <div class="card-title">📍 {title}</div>
        <div class="card-score">Pisteet: {score:.1f}</div>
        <div class="card-reason">{reasons_html}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Linkkipainikkeet per signaali ──────────────────────────
# Kerää uniikit URLt
seen_urls: set[str] = set()
link_buttons: list[tuple[str, str]] = []  # (label, url)

for sig in signals:
    url = getattr(sig, "source_url", None)
    if not url or url in seen_urls:
        continue
    if not url.startswith("http"):
        continue
    seen_urls.add(url)

    # Laadi lyhyt nappi-teksti
    title_raw = getattr(sig, "title", "")
    # Siisti: poista emoji-prefix, leikkaa max 35 merkkiä
    label = title_raw.lstrip("📅🚆✈️⛴️🌤️⚠️📰🔴🟠🟡🟢🏒⛔ ").strip()
    if len(label) > 35:
        label = label[:32] + "…"
    if not label:
        label = "Avaa"

    link_buttons.append((label, url))

if link_buttons:
    # Max 3 linkkiä per kortti, rinnakkain
    cols = st.columns(min(len(link_buttons), 3))
    for i, (label, url) in enumerate(link_buttons[:3]):
        with cols[i % len(cols)]:
            st.link_button(f"→ {label}", url, use_container_width=True)
```

# ══════════════════════════════════════════════════════════════

# YLÄPALKKI

# ══════════════════════════════════════════════════════════════

def _render_top_bar(agent_results: dict) -> None:
“”“Renderöi yläpalkki: kello, sää, sijainti.”””
now = _helsinki_time()
time_str = now.strftime(”%H:%M”)

```
# Sää WeatherAgentilta
weather_html = ""
weather_result = agent_results.get("WeatherAgent")
if weather_result and weather_result.ok and weather_result.signals:
    sig = weather_result.signals[0]
    weather_html = f'<div class="top-bar-weather">{sig.description}</div>'

# Sijaintisuositus
location_html = ""
if LOCATION_AVAILABLE:
    loc = get_location_from_session()
    if loc and loc.nearest_area:
        hotspots = st.session_state.get("ceo_hotspots", [])
        rec_text = get_smart_recommendation_text(
            loc.lat, loc.lon, hotspots
        )
        location_html = f'<div class="top-bar-location">{rec_text}</div>'

st.markdown(
    f"""
    <div class="top-bar">
        <div class="top-bar-clock">{time_str}</div>
        <div>
            {weather_html}
            {location_html}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
```

# ══════════════════════════════════════════════════════════════

# PÄÄFUNKTIO

# ══════════════════════════════════════════════════════════════

def render_dashboard(
hotspots: list,
agent_results: dict,
refresh_callback: callable | None = None,
) -> None:
“””
Renderöi koko kojelauta-näkymä.

```
Parametrit:
    hotspots: CEO:n palauttama Hotspot-lista (max 3)
    agent_results: dict[str, AgentResult] kaikilta agenteilta
    refresh_callback: Callable jota kutsutaan kun käyttäjä painaa Päivitä
"""
# ── CSS + JS ──────────────────────────────────────────────
st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)
st.markdown(BOTTOM_NAV_JS, unsafe_allow_html=True)

# ── Sijaintiboosteri ───────────────────────────────────────
# Jos GPS-sijainti on saatavilla, boostataan lähellä olevia hotspotteja
if LOCATION_AVAILABLE:
    loc = get_location_from_session()
    if loc:
        hotspots = apply_location_boost(
            hotspots,
            driver_lat=loc.lat,
            driver_lon=loc.lon,
        )

# ── Yläpalkki ─────────────────────────────────────────────
_render_top_bar(agent_results)

# ── Häiriöbanneri (taso >= 7) ──────────────────────────────
disruption_result = agent_results.get("DisruptionAgent")
if disruption_result and disruption_result.ok:
    critical_signals = [
        s for s in disruption_result.signals
        if getattr(s, "urgency", 0) >= 7
    ]
    for sig in critical_signals[:2]:
        st.markdown(
            f'<div class="disruption-banner">⚡ {sig.description}</div>',
            unsafe_allow_html=True,
        )

# ── Sijaintinappi (kompakti) ───────────────────────────────
if LOCATION_AVAILABLE:
    with st.expander("📍 Sijainti", expanded=False):
        render_location_widget()

# ── 3 hotspot-korttia ─────────────────────────────────────
if not hotspots:
    st.info("⏳ Ladataan agentteja…")
    return

# Tallenna session stateen sijaintiboosteria varten
st.session_state["ceo_hotspots"] = hotspots

for idx, hotspot in enumerate(hotspots[:3]):
    _render_hotspot_card(hotspot, idx)

# ── Agenttistatusrivi ──────────────────────────────────────
dots_html = '<div class="agent-dots">'
for name, result in agent_results.items():
    if result is None:
        continue
    dot_cls = "dot-ok" if getattr(result, "ok", False) else "dot-error"
    count = len(getattr(result, "signals", []))
    dots_html += (
        f'<span title="{name}: {count} signaalia" '
        f'class="agent-dot {dot_cls}"></span>'
    )
dots_html += "</div>"
st.markdown(dots_html, unsafe_allow_html=True)

# ── Päivitä-nappi ──────────────────────────────────────────
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("🔄 Päivitä nyt", use_container_width=True):
        if refresh_callback:
            refresh_callback()
        else:
            st.cache_resource.clear()
            st.rerun()
```
