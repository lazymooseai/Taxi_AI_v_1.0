"""
dashboard.py -- Kojelauta v2.1
Helsinki Taxi AI

KORJAUKSET v2.1:
  - Kortit koko ruudun levyisia, allekkain
  - Top 3 korkein prioriteetti ylimmaisena
  - Jokaisessa kortissa 1-5 seuraavaa tapahtumaa
  - Liikennevalineet: 2h ikkuna, muut: paivan tapahtumat
  - Oikeat suomenkieliset merkit (ae, oe HTML-entiteeteilla)
  - Isommat fontit, nopeasti luettavissa
  - Saa-animaatio ylapalkkiin
  - Linkkipainikkeet jokaisessa kortissa
  - Scrollaus ja swaippaus toimii (ei position:fixed CSStae)
  - Ooppera avautuu kalenterinakymaan
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

import streamlit as st

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

HKI_TZ = ZoneInfo("Europe/Helsinki")


# ---------------------------------------------------------------------------
# 8 KATEGORIAA
# ---------------------------------------------------------------------------

CARD_CATEGORIES: list[dict] = [
    {
        "id": "trains",
        "name": "Junat",
        "icon_html": "&#128642;",
        "agents": ["TrainAgent"],
        "sub": "Helsinki, Pasila, Tikkurila",
        "color": "#3B82F6",
        "bg": "#0f1d30",
        "border": "#3B82F644",
        "lookahead_hours": 2,
    },
    {
        "id": "ferries",
        "name": "Satamat",
        "icon_html": "&#9875;",
        "agents": ["FerryAgent"],
        "sub": "Olympiaterminaali, Katajanokka, L\u00e4nsisatama, Hansaterminaali",
        "color": "#06B6D4",
        "bg": "#0c2d3a",
        "border": "#06B6D444",
        "lookahead_hours": 2,
    },
    {
        "id": "culture",
        "name": "Kulttuuri ja musiikki",
        "icon_html": "&#127917;",
        "agents": ["EventsAgent"],
        "filter_category": "culture",
        "sub": "Musiikkitalo, Ooppera, Kansallisteatteri, Tavastia",
        "color": "#A855F7",
        "bg": "#1e1035",
        "border": "#A855F744",
        "lookahead_hours": 24,
    },
    {
        "id": "airport",
        "name": "Lentoasema",
        "icon_html": "&#9992;&#65039;",
        "agents": ["FlightAgent"],
        "sub": "Helsinki-Vantaa EFHK",
        "color": "#F59E0B",
        "bg": "#2e1e05",
        "border": "#F59E0B44",
        "lookahead_hours": 2,
    },
    {
        "id": "sports",
        "name": "Urheilu",
        "icon_html": "&#9917;",
        "agents": ["EventsAgent"],
        "filter_category": "sports",
        "sub": "Nordis, Bolt Arena, Olympiastadion",
        "color": "#22C55E",
        "bg": "#0a2916",
        "border": "#22C55E44",
        "lookahead_hours": 24,
    },
    {
        "id": "politics",
        "name": "Politiikka",
        "icon_html": "&#127963;&#65039;",
        "agents": ["SocialMediaAgent"],
        "sub": "Eduskunta, S\u00e4\u00e4tytalo",
        "color": "#EF4444",
        "bg": "#2e0d0d",
        "border": "#EF444444",
        "lookahead_hours": 24,
    },
    {
        "id": "disruptions",
        "name": "Liikenneh\u00e4iri\u00f6t",
        "icon_html": "&#9888;&#65039;",
        "agents": ["DisruptionAgent"],
        "sub": "HSL, VR, Metro, Raitiovaunu",
        "color": "#FF6B6B",
        "bg": "#250808",
        "border": "#FF6B6B44",
        "lookahead_hours": 2,
    },
    {
        "id": "weather",
        "name": "S\u00e4\u00e4",
        "icon_html": "&#9925;",
        "agents": ["WeatherAgent"],
        "sub": "FMI Helsinki, Sadetutka",
        "color": "#38BDF8",
        "bg": "#0f1d30",
        "border": "#38BDF844",
        "lookahead_hours": 24,
    },
]


# ---------------------------------------------------------------------------
# CSS - v2.1 korjattu
# ---------------------------------------------------------------------------

DASHBOARD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #0e1117 !important;
    font-family: 'Inter', sans-serif !important;
    color: #FAFAFA !important;
}

/* Tab-palkki alhaalla - sticky, ei fixed */
[data-baseweb="tab-list"] {
    position: sticky !important;
    bottom: 0 !important;
    z-index: 999 !important;
    background: #12151f !important;
    border-top: 1px solid #2a2d3d !important;
    padding: 6px 0 !important;
    justify-content: space-around !important;
    box-shadow: 0 -4px 20px rgba(0,0,0,0.4) !important;
}

[data-baseweb="tab"] {
    font-size: 0.8rem !important;
    padding: 10px 14px !important;
    color: #888899 !important;
    border: none !important;
    background: transparent !important;
}

[data-baseweb="tab"][aria-selected="true"] {
    color: #00B4D8 !important;
    background: rgba(0,180,216,0.1) !important;
    border-radius: 8px !important;
}

/* Yl\u00e4palkki */
.top-bar {
    background: linear-gradient(135deg, #12151f 0%, #1a1d27 100%);
    border: 1px solid #2a2d3d;
    border-radius: 16px;
    padding: 16px 20px;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.top-bar-clock {
    font-size: 2.8rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: #FAFAFA;
    font-variant-numeric: tabular-nums;
}
.top-bar-right { text-align: right; }
.top-bar-weather {
    font-size: 1.15rem;
    font-weight: 600;
    color: #CCCCDD;
}
.top-bar-location {
    font-size: 0.85rem;
    color: #00B4D8;
    margin-top: 2px;
}

/* S\u00e4\u00e4-animaatio */
@keyframes weather-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}
.weather-anim {
    display: inline-block;
    font-size: 2.2rem;
    animation: weather-pulse 3s ease-in-out infinite;
    margin-right: 8px;
    vertical-align: middle;
}

/* H\u00e4iri\u00f6banneri */
.disruption-banner {
    background: linear-gradient(90deg, #2d0a0a, #1a0505);
    border: 1px solid #FF4B4B66;
    border-radius: 12px;
    padding: 12px 18px;
    margin-bottom: 12px;
    font-size: 1.0rem;
    font-weight: 600;
    color: #FF6B6B;
}

/* KORTIT - koko leveys, allekkain */
.taxi-card {
    width: 100%;
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 14px;
    position: relative;
    overflow: hidden;
    -webkit-overflow-scrolling: touch;
}
.taxi-card-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
}
.taxi-card-icon {
    font-size: 2.0rem;
}
.taxi-card-title {
    font-size: 1.3rem;
    font-weight: 800;
    color: #FAFAFA;
    letter-spacing: -0.01em;
}
.taxi-card-sub {
    font-size: 0.8rem;
    color: #999;
    margin-left: auto;
}
.taxi-card-badge {
    position: absolute;
    top: 14px;
    right: 16px;
    font-size: 0.75rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 12px;
}

/* Signaalirivi kortissa */
.sig-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 0;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    font-size: 1.0rem;
    line-height: 1.4;
    color: #e0e0e0;
}
.sig-row:last-child { border-bottom: none; }
.sig-time {
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    min-width: 50px;
    color: #FAFAFA;
    font-size: 1.05rem;
}
.sig-text {
    flex: 1;
    font-size: 0.95rem;
}
.sig-urgency-high { color: #FF6B6B; }
.sig-urgency-mid { color: #FFD700; }
.sig-urgency-low { color: #21C55D; }

/* Tyhj\u00e4 kortti */
.sig-empty {
    font-size: 0.9rem;
    color: #666;
    padding: 6px 0;
    font-style: italic;
}

/* Agenttipisteet */
.agent-dots { display:flex; gap:6px; flex-wrap:wrap; margin:8px 0; }
.agent-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
.dot-ok { background:#21C55D; }
.dot-error { background:#FF4B4B; }

/* Streamlit button overrides */
.stButton > button {
    background: #1a1d27 !important;
    border: 1px solid #2a2d3d !important;
    color: #FAFAFA !important;
    border-radius: 12px !important;
    font-size: 0.95rem !important;
    font-weight: 600 !important;
}
.stLinkButton > a {
    background: rgba(0,180,216,0.1) !important;
    border: 1px solid #00B4D844 !important;
    color: #00B4D8 !important;
    border-radius: 12px !important;
    font-size: 0.9rem !important;
    padding: 8px 16px !important;
    text-decoration: none !important;
    font-weight: 600 !important;
}
div[data-testid="column"] { padding: 0 4px !important; }
.block-container {
    padding-top: 0.8rem !important;
    padding-bottom: 20px !important;
    max-width: 800px !important;
}
</style>
"""


# ---------------------------------------------------------------------------
# APUFUNKTIOT
# ---------------------------------------------------------------------------

def _hki_now() -> datetime:
    return datetime.now(HKI_TZ)


def _get_agent_result(agent_results, agent_name: str):
    if isinstance(agent_results, dict):
        return agent_results.get(agent_name)
    return next(
        (r for r in (agent_results or [])
         if getattr(r, "agent_name", "") == agent_name),
        None,
    )


def _collect_signals(cat: dict, agent_results) -> list:
    signals = []
    filter_cat = cat.get("filter_category", "")
    for agent_name in cat.get("agents", []):
        result = _get_agent_result(agent_results, agent_name)
        if result is None or not getattr(result, "ok", False):
            continue
        for sig in getattr(result, "signals", []):
            if filter_cat:
                sig_cat = getattr(sig, "category", "")
                if sig_cat and sig_cat != filter_cat:
                    continue
            signals.append(sig)
    signals.sort(key=lambda s: getattr(s, "urgency", 0), reverse=True)
    return signals


def _weather_icon_html(reason: str) -> str:
    r = reason.lower()
    if "ukkonen" in r or "myrsky" in r:
        return '<span class="weather-anim">&#9928;</span>'
    if "sade" in r or "lumi" in r:
        return '<span class="weather-anim">&#127783;&#65039;</span>'
    if "tuuli" in r:
        return '<span class="weather-anim">&#127744;</span>'
    if "pilvi" in r:
        return '<span class="weather-anim">&#9729;&#65039;</span>'
    # Aurinkoinen / normaali
    return '<span class="weather-anim">&#9728;&#65039;</span>'


def _urgency_css(urgency: int) -> str:
    if urgency >= 7:
        return "sig-urgency-high"
    if urgency >= 4:
        return "sig-urgency-mid"
    return "sig-urgency-low"


def _signal_time_str(sig) -> str:
    """Hae signaalin aikaleima naytettavaksi."""
    extra = getattr(sig, "extra", {}) or {}
    # Junat: minutes_away
    mins = extra.get("minutes_away")
    if mins is not None:
        return f"{mins}min"
    # Tapahtumat: hours_until
    hours = extra.get("hours_until")
    if hours is not None:
        if hours < 1:
            return f"{int(hours*60)}min"
        return f"{hours:.0f}h"
    # Paattymisaika
    mins_end = extra.get("minutes_to_end")
    if mins_end is not None:
        return f"-{mins_end}min"
    return ""


# ---------------------------------------------------------------------------
# YLAPALKKI + SAAANIMAATIO
# ---------------------------------------------------------------------------

def _render_top_bar(agent_results) -> None:
    now_str = _hki_now().strftime("%H:%M")
    date_str = _hki_now().strftime("%d.%m.%Y")

    weather_html = ""
    weather_icon = '<span class="weather-anim">&#9728;&#65039;</span>'
    wr = _get_agent_result(agent_results, "WeatherAgent")
    if wr and getattr(wr, "ok", False):
        sigs = getattr(wr, "signals", [])
        if sigs:
            reason = getattr(sigs[0], "reason", "")
            weather_icon = _weather_icon_html(reason)
            weather_html = (
                '<div class="top-bar-weather">'
                + reason[:60] + "</div>"
            )

    location_html = ""
    if LOCATION_AVAILABLE:
        try:
            loc = get_location_from_session()
            if loc and loc.nearest_area:
                hotspots = st.session_state.get("ceo_hotspots", [])
                rec = get_smart_recommendation_text(loc.lat, loc.lon, hotspots)
                location_html = '<div class="top-bar-location">' + rec + "</div>"
        except Exception:
            pass

    st.markdown(
        '<div class="top-bar">'
        '<div>' + weather_icon
        + '<span class="top-bar-clock">' + now_str + "</span>"
        + "</div>"
        + '<div class="top-bar-right">'
        + '<div style="font-size:0.85rem;color:#888">' + date_str + "</div>"
        + weather_html + location_html
        + "</div></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# HAIRIOBANNERI
# ---------------------------------------------------------------------------

def _render_disruption_banner(agent_results) -> None:
    dr = _get_agent_result(agent_results, "DisruptionAgent")
    if dr and getattr(dr, "ok", False):
        for sig in getattr(dr, "signals", [])[:2]:
            if getattr(sig, "urgency", 0) >= 7:
                reason = getattr(sig, "reason", "")
                st.markdown(
                    '<div class="disruption-banner">&#9888; '
                    + str(reason)[:140] + "</div>",
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# KATEGORIAKORTIT - koko leveys, allekkain, prioriteettijärjestyksessä
# ---------------------------------------------------------------------------

def _render_cards(agent_results) -> None:
    # Laske prioriteetti per kategoria
    cat_priority: list[tuple[int, int, dict]] = []
    for idx, cat in enumerate(CARD_CATEGORIES):
        signals = _collect_signals(cat, agent_results)
        max_urg = 0
        count = len(signals)
        if signals:
            max_urg = max(getattr(s, "urgency", 0) for s in signals)
        cat_priority.append((max_urg, count, cat))

    # Jarjesta: korkein urgency + eniten signaaleja ylimmaiseksi
    cat_priority.sort(key=lambda x: (x[0], x[1]), reverse=True)

    for max_urg, count, cat in cat_priority:
        signals = _collect_signals(cat, agent_results)

        # Urgency-vari badgelle
        if max_urg >= 7:
            badge_bg = "rgba(255,75,75,0.3)"
            badge_color = "#FF4B4B"
            badge_text = "KRIITTINEN"
        elif max_urg >= 5:
            badge_bg = "rgba(255,215,0,0.3)"
            badge_color = "#FFD700"
            badge_text = "KORKEA"
        elif count > 0:
            badge_bg = "rgba(255,255,255,0.12)"
            badge_color = cat["color"]
            badge_text = str(count) + " signaalia"
        else:
            badge_bg = "rgba(255,255,255,0.05)"
            badge_color = "#666"
            badge_text = "Ei dataa"

        # Kortin HTML
        card_html = (
            '<div class="taxi-card" style="background:'
            + cat["bg"] + ';border:1px solid ' + cat["border"] + '">'
            + '<div class="taxi-card-badge" style="background:'
            + badge_bg + ';color:' + badge_color + '">'
            + badge_text + "</div>"
            + '<div class="taxi-card-header">'
            + '<span class="taxi-card-icon">' + cat["icon_html"] + "</span>"
            + '<span class="taxi-card-title">' + cat["name"] + "</span>"
            + "</div>"
        )

        # Signaalit kortissa: max 5
        if signals:
            for sig in signals[:5]:
                urg = getattr(sig, "urgency", 0)
                reason = getattr(sig, "reason", "")
                time_str = _signal_time_str(sig)
                urg_cls = _urgency_css(urg)

                card_html += (
                    '<div class="sig-row">'
                    + '<span class="sig-time ' + urg_cls + '">'
                    + time_str + "</span>"
                    + '<span class="sig-text">'
                    + reason[:100] + "</span>"
                    + "</div>"
                )
        else:
            card_html += (
                '<div class="sig-empty">'
                "Ei aktiivisia signaaleja</div>"
            )

        card_html += "</div>"
        st.markdown(card_html, unsafe_allow_html=True)

        # Linkkipainikkeet (Streamlit natiivi - toimii klikkaus)
        links: list[tuple[str, str]] = []
        seen: set[str] = set()
        for sig in signals[:5]:
            url = getattr(sig, "source_url", "")
            if not url or not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            lbl = getattr(sig, "title", "") or getattr(sig, "reason", "")
            for prefix in [
                "Juna saapuu: ", "Tapahtuma: ",
                "Hairio: ", "Lautta: ", "Paattyy pian: ",
            ]:
                lbl = lbl.replace(prefix, "")
            lbl = lbl[:35] or "Avaa"
            links.append((lbl, url))

        if links:
            cols = st.columns(min(len(links), 3))
            for i, (lbl, url) in enumerate(links[:3]):
                with cols[i]:
                    st.link_button(lbl, url, use_container_width=True)


# ---------------------------------------------------------------------------
# AGENTTISTATUS
# ---------------------------------------------------------------------------

def _render_agent_dots(agent_results) -> None:
    items = (
        agent_results.items() if isinstance(agent_results, dict)
        else [(getattr(r, "agent_name", "?"), r) for r in (agent_results or [])]
    )
    dots_html = '<div class="agent-dots">'
    for name, result in items:
        if result is None:
            continue
        ok = getattr(result, "ok", False)
        count = len(getattr(result, "signals", []))
        cls = "dot-ok" if ok else "dot-error"
        dots_html += (
            '<span title="' + str(name) + ": " + str(count)
            + ' signaalia" class="agent-dot ' + cls + '"></span>'
        )
    dots_html += "</div>"
    st.markdown(dots_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# PAARUNKTIO
# ---------------------------------------------------------------------------

def render_dashboard(
    hotspots=None, agent_results=None, refresh_callback=None,
) -> None:
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)

    if hotspots is None or agent_results is None:
        cache = st.session_state.get("hotspot_cache")
        if cache and isinstance(cache, (tuple, list)) and len(cache) >= 2:
            hotspots = cache[0] if hotspots is None else hotspots
            agent_results = cache[1] if agent_results is None else agent_results
        else:
            hotspots = hotspots or []
            agent_results = agent_results or {}

    if LOCATION_AVAILABLE and hotspots:
        try:
            loc = get_location_from_session()
            if loc:
                hotspots = apply_location_boost(
                    hotspots, driver_lat=loc.lat, driver_lon=loc.lon
                )
        except Exception:
            pass

    # Yl\u00e4palkki + s\u00e4\u00e4animaatio
    _render_top_bar(agent_results)

    # H\u00e4iri\u00f6banneri
    _render_disruption_banner(agent_results)

    # Sijainti
    if LOCATION_AVAILABLE:
        with st.expander("Sijainti (GPS)", expanded=False):
            render_location_widget()

    if not agent_results:
        st.info("Ladataan agentteja...")
        return

    st.session_state["ceo_hotspots"] = hotspots

    # 8 kategoriakorttinakyma - prioriteettijarjestyksessa
    _render_cards(agent_results)

    # Agenttistatus
    _render_agent_dots(agent_results)

    # P\u00e4ivit\u00e4-nappi
    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        if st.button("P\u00e4ivit\u00e4 nyt", use_container_width=True):
            if refresh_callback:
                refresh_callback()
            else:
                st.cache_resource.clear()
                st.rerun()
