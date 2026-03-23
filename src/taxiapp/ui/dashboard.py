# dashboard.py -- Kojelauta-valilehti
# Helsinki Taxi AI
#
# Muutokset v1.1:
#   - Navigaatio kiinnitetty alaosaan JS-injektiolla
#   - Kortit: link_button per signaali (source_url)
#   - Reaaliaikainen sijaintiboosteri (streamlit-geolocation)
#   - Junat: vain saapuvat kaukojunat + VR-linkki suodatettuna
#   - EventsAgent: toimivat lahteet, tayttöaste nakyy kortissa

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st

# Sijaintipalvelu -- valinnainen
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

logger = logging.getLogger("taxiapp.dashboard")

# ---------------------------------------------------------------------------
# VARIT
# ---------------------------------------------------------------------------

COLOR_RED    = "#FF4B4B"
COLOR_GOLD   = "#FFD700"
COLOR_BLUE   = "#00B4D8"
COLOR_MUTED  = "#888899"
COLOR_BG     = "#0e1117"
COLOR_CARD   = "#1a1d27"
COLOR_BORDER = "#2a2d3d"

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

DASHBOARD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #0e1117 !important;
    font-family: 'Inter', sans-serif !important;
    color: #FAFAFA !important;
}

/* Kiintea alapalkki */
[data-baseweb="tab-list"] {
    position: fixed !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 9999 !important;
    background: #12151f !important;
    border-top: 1px solid #2a2d3d !important;
    padding: 4px 0 !important;
    margin: 0 !important;
    width: 100% !important;
    justify-content: space-around !important;
    box-shadow: 0 -4px 20px rgba(0,0,0,0.4) !important;
}

[data-baseweb="tab"] {
    font-size: 0.75rem !important;
    padding: 8px 12px !important;
    color: #888899 !important;
    border: none !important;
    background: transparent !important;
    min-width: 56px !important;
}

[data-baseweb="tab"][aria-selected="true"] {
    color: #00B4D8 !important;
    background: rgba(0,180,216,0.1) !important;
}

/* Ylapalkki */
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

/* Kortit */
.hotspot-card {
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 12px;
    position: relative;
    overflow: hidden;
}

.card-red  {
    background: linear-gradient(135deg, #2d0a0a 0%, #1a0505 100%);
    border: 1px solid #FF4B4B44;
}

.card-gold {
    background: linear-gradient(135deg, #2d2200 0%, #1a1500 100%);
    border: 1px solid #FFD70044;
}

.card-blue {
    background: linear-gradient(135deg, #00162a 0%, #000d1a 100%);
    border: 1px solid #00B4D844;
}

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

.reason-item {
    display: block;
    padding: 3px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}

.reason-item:last-child { border-bottom: none; }

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

/* Hairiosbanneri */
.disruption-banner {
    background: linear-gradient(90deg, #2d0a0a, #1a0505);
    border: 1px solid #FF4B4B66;
    border-radius: 10px;
    padding: 10px 16px;
    margin-bottom: 12px;
    font-size: 0.88rem;
    color: #FF6B6B;
}

/* Agent-pisteet */
.agent-dots {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin: 8px 0;
}

.agent-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
}

.dot-ok    { background: #21C55D; }
.dot-error { background: #FF4B4B; }
.dot-off   { background: #444455; }

/* Streamlit-overridet */
.stButton > button {
    background: #1a1d27 !important;
    border: 1px solid #2a2d3d !important;
    color: #FAFAFA !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
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
    padding-bottom: 80px !important;
    max-width: 1200px !important;
}
</style>
"""

# ---------------------------------------------------------------------------
# APUFUNKTIOT
# ---------------------------------------------------------------------------

def _helsinki_time() -> datetime:
    """Palauta Helsingin paikallisaika (EET/EEST)."""
    import time as _t
    offset = 3 if _t.daylight else 2
    return datetime.now(timezone.utc) + timedelta(hours=offset)


def _fill_rate_badge(fill_rate: Optional[float]) -> str:
    """Palauta HTML-badge tayttöasteen mukaan."""
    if fill_rate is None:
        return ""
    if fill_rate >= 1.0:
        return '<span class="fill-badge fill-sold-out">LOPPUUNMYYTY</span>'
    if fill_rate >= 0.85:
        return '<span class="fill-badge fill-limited">Viimeiset liput</span>'
    if fill_rate >= 0.5:
        return '<span class="fill-badge fill-normal">Lippuja</span>'
    return ""


def _urgency_label(urgency: int) -> str:
    """Palauta kiireellisyyden tekstinimi."""
    if urgency >= 9:
        return "OVERRIDE"
    if urgency >= 7:
        return "KRIITTINEN"
    if urgency >= 5:
        return "KORKEA"
    if urgency >= 3:
        return "NORMAALI"
    return "PERUS"


def _card_classes(idx: int, urgency: int) -> tuple[str, str]:
    """Palauta (card_css_class, badge_css_class)."""
    if urgency >= 9 or idx == 0:
        return "card-red", "badge-red"
    if idx == 1:
        return "card-gold", "badge-gold"
    return "card-blue", "badge-blue"


# ---------------------------------------------------------------------------
# KORTTIEN RENDEROINTI
# ---------------------------------------------------------------------------

def _render_hotspot_card(hotspot: object, idx: int) -> None:
    """
    Renderoi yksi hotspot-kortti linkkipainikkeineen.

    Rakenne:
      [BADGE]
      [OTSIKKO]
      [pisteet]
      [syyt + tayttöasteet]
      [link_button per signaali jolla source_url]
    """
    card_cls, badge_cls = _card_classes(idx, getattr(hotspot, "urgency", 2))
    urgency_label = _urgency_label(getattr(hotspot, "urgency", 2))
    score = getattr(hotspot, "score", 0.0)
    area_id = getattr(hotspot, "area", "?")
    title = area_id.replace("_", " ").title()
    signals = getattr(hotspot, "signals", [])

    # Syyt HTML
    reasons_html = ""
    for sig in signals[:5]:
        desc = getattr(sig, "description", "")
        fill_rate = (getattr(sig, "extra", {}) or {}).get("fill_rate")
        fill_badge = _fill_rate_badge(fill_rate)
        if desc:
            reasons_html += (
                '<span class="reason-item">'
                + desc
                + fill_badge
                + "</span>"
            )

    st.markdown(
        "<div class=\"hotspot-card " + card_cls + "\">"
        + "<div class=\"card-badge " + badge_cls + "\">" + urgency_label + "</div>"
        + "<div class=\"card-title\">Sijainti: " + title + "</div>"
        + "<div class=\"card-score\">Pisteet: " + str(round(score, 1)) + "</div>"
        + "<div class=\"card-reason\">" + reasons_html + "</div>"
        + "</div>",
        unsafe_allow_html=True,
    )

    # Linkkipainikkeet -- max 3 per kortti
    seen_urls: set[str] = set()
    link_buttons: list[tuple[str, str]] = []

    for sig in signals:
        url = getattr(sig, "source_url", None)
        if not url or url in seen_urls:
            continue
        if not url.startswith("http"):
            continue
        seen_urls.add(url)

        label_raw = getattr(sig, "title", "")
        # Siisti label: poista tunnettuja prefikseja
        for prefix in [
            "Juna saapuu: ", "Tapahtuma: ", "Hairio: ",
            "Lautta: ", "Lento: ", "Saa: ",
        ]:
            label_raw = label_raw.replace(prefix, "")
        label_raw = label_raw.strip()
        if len(label_raw) > 35:
            label_raw = label_raw[:32] + "..."
        if not label_raw:
            label_raw = "Avaa"

        link_buttons.append((label_raw, url))

    if link_buttons:
        cols = st.columns(min(len(link_buttons), 3))
        for i, (label, url) in enumerate(link_buttons[:3]):
            with cols[i % len(cols)]:
                st.link_button("-> " + label, url, use_container_width=True)


# ---------------------------------------------------------------------------
# YLAPALKKI
# ---------------------------------------------------------------------------

def _render_top_bar(agent_results: dict) -> None:
    """Renderoi ylapalkki: kello, saa, sijaintisuositus."""
    now = _helsinki_time()
    time_str = now.strftime("%H:%M")

    weather_html = ""
    weather_result = agent_results.get("WeatherAgent")
    if weather_result and getattr(weather_result, "ok", False):
        sigs = getattr(weather_result, "signals", [])
        if sigs:
            weather_html = (
                '<div class="top-bar-weather">'
                + getattr(sigs[0], "description", "")
                + "</div>"
            )

    location_html = ""
    if LOCATION_AVAILABLE:
        loc = get_location_from_session()
        if loc and loc.nearest_area:
            hotspots = st.session_state.get("ceo_hotspots", [])
            rec_text = get_smart_recommendation_text(
                loc.lat, loc.lon, hotspots
            )
            location_html = (
                '<div class="top-bar-location">'
                + rec_text
                + "</div>"
            )

    st.markdown(
        "<div class=\"top-bar\">"
        + "<div class=\"top-bar-clock\">" + time_str + "</div>"
        + "<div>" + weather_html + location_html + "</div>"
        + "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# PAARUNKTIO
# ---------------------------------------------------------------------------

def render_dashboard(
    hotspots: list,
    agent_results: dict,
    refresh_callback=None,
) -> None:
    """
    Renderoi koko kojelauta-nakyma.

    Parametrit:
        hotspots:         CEO:n palauttama Hotspot-lista (max 3)
        agent_results:    dict[str, AgentResult] kaikilta agenteilta
        refresh_callback: Callable jota kutsutaan Paivita-napista
    """
    # CSS
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)

    # Sijaintiboosteri
    if LOCATION_AVAILABLE:
        loc = get_location_from_session()
        if loc:
            hotspots = apply_location_boost(
                hotspots,
                driver_lat=loc.lat,
                driver_lon=loc.lon,
            )

    # Ylapalkki
    _render_top_bar(agent_results)

    # Hairiosbanneri urgency >= 7
    disruption_result = agent_results.get("DisruptionAgent")
    if disruption_result and getattr(disruption_result, "ok", False):
        for sig in getattr(disruption_result, "signals", [])[:2]:
            if getattr(sig, "urgency", 0) >= 7:
                st.markdown(
                    "<div class=\"disruption-banner\">"
                    + "!! "
                    + getattr(sig, "description", "")
                    + "</div>",
                    unsafe_allow_html=True,
                )

    # Sijainti-expander
    if LOCATION_AVAILABLE:
        with st.expander("Sijainti (GPS)", expanded=False):
            render_location_widget()

    # Kortit
    if not hotspots:
        st.info("Ladataan agentteja...")
        return

    st.session_state["ceo_hotspots"] = hotspots

    for idx, hotspot in enumerate(hotspots[:3]):
        _render_hotspot_card(hotspot, idx)

    # Agenttistatus-pisteet
    dots_html = "<div class=\"agent-dots\">"
    for name, result in agent_results.items():
        if result is None:
            continue
        ok = getattr(result, "ok", False)
        count = len(getattr(result, "signals", []))
        dot_cls = "dot-ok" if ok else "dot-error"
        dots_html += (
            "<span title=\""
            + name
            + ": "
            + str(count)
            + " signaalia\" class=\"agent-dot "
            + dot_cls
            + "\"></span>"
        )
    dots_html += "</div>"
    st.markdown(dots_html, unsafe_allow_html=True)

    # Paivita-nappi
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button("Paivita nyt", use_container_width=True):
            if refresh_callback:
                refresh_callback()
            else:
                st.cache_resource.clear()
                st.rerun()
