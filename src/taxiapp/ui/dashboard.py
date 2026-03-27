"""
dashboard.py -- Kojelauta v2.0
Helsinki Taxi AI

8 dynaamista ja alykasta tapahtumakorttia:
  1. Junat (Helsinki, Pasila, Tikkurila)
  2. Satamat (Olympiaterminaali, Katajanokka, Laensisatama, Hansaterm., Suomenlinna)
  3. Kulttuuri ja musiikki
  4. Lentoasema
  5. Urheilu
  6. Politiikka
  7. Liikennehaeirioet
  8. Saa

Kortit ovat scrollattavia ja swaipattavia (mobiili-optimoitu).
Aika: Suomen aika (Europe/Helsinki) - korjattu v2.0

KORJAUKSET:
  - Kellonaika korjattu: zoneinfo.ZoneInfo("Europe/Helsinki")
  - 8 kategoriakorttinakyma korvaa vanhat 3 korttia
  - pointer-events fix CSS:lle
  - Ei emojeja Python-koodissa (HTML-entiteetit naytossa)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
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

# Helsinki aikavyohyke
HKI_TZ = ZoneInfo("Europe/Helsinki")


# ---------------------------------------------------------------------------
# 8 KATEGORIAA
# ---------------------------------------------------------------------------

CARD_CATEGORIES: list[dict] = [
    {
        "id": "trains",
        "name": "Junat",
        "icon": "&#128642;",
        "agents": ["TrainAgent"],
        "sub": "Helsinki, Pasila, Tikkurila",
        "color": "#3B82F6",
        "gradient": "linear-gradient(135deg, #1e3a5f, #0f1d30)",
        "border": "#3B82F644",
    },
    {
        "id": "ferries",
        "name": "Satamat",
        "icon": "&#9875;",
        "agents": ["FerryAgent"],
        "sub": "Olympiat., Katajanokka, Laensisat., Hansaterm., Suomenlinna",
        "color": "#06B6D4",
        "gradient": "linear-gradient(135deg, #164e63, #0c2d3a)",
        "border": "#06B6D444",
    },
    {
        "id": "culture",
        "name": "Kulttuuri",
        "icon": "&#127917;",
        "agents": ["EventsAgent"],
        "filter_category": "culture",
        "sub": "Musiikkitalo, Ooppera, Tavastia...",
        "color": "#A855F7",
        "gradient": "linear-gradient(135deg, #3b1f5e, #1e1035)",
        "border": "#A855F744",
    },
    {
        "id": "airport",
        "name": "Lentoasema",
        "icon": "&#9992;",
        "agents": ["FlightAgent"],
        "sub": "Helsinki-Vantaa EFHK",
        "color": "#F59E0B",
        "gradient": "linear-gradient(135deg, #5c3d0a, #2e1e05)",
        "border": "#F59E0B44",
    },
    {
        "id": "sports",
        "name": "Urheilu",
        "icon": "&#9917;",
        "agents": ["EventsAgent"],
        "filter_category": "sports",
        "sub": "Nordis, Bolt Arena, Olympiastadion",
        "color": "#22C55E",
        "gradient": "linear-gradient(135deg, #14532d, #0a2916)",
        "border": "#22C55E44",
    },
    {
        "id": "politics",
        "name": "Politiikka",
        "icon": "&#127963;",
        "agents": ["SocialMediaAgent", "EventsAgent"],
        "filter_category": "politics",
        "sub": "Eduskunta, Saeatyetalo",
        "color": "#EF4444",
        "gradient": "linear-gradient(135deg, #5c1a1a, #2e0d0d)",
        "border": "#EF444444",
    },
    {
        "id": "disruptions",
        "name": "Haeirioet",
        "icon": "&#9888;",
        "agents": ["DisruptionAgent"],
        "sub": "HSL, VR, Metro, Raitiovaunu",
        "color": "#FF6B6B",
        "gradient": "linear-gradient(135deg, #4a1010, #250808)",
        "border": "#FF6B6B44",
    },
    {
        "id": "weather",
        "name": "Saa",
        "icon": "&#9925;",
        "agents": ["WeatherAgent"],
        "sub": "FMI Helsinki, Sadetutka",
        "color": "#38BDF8",
        "gradient": "linear-gradient(135deg, #1e3a5f, #0f1d30)",
        "border": "#38BDF844",
    },
]


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

/* Kiintea tab-palkki alaosaan */
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
    pointer-events: auto !important;
}

[data-baseweb="tab"] {
    font-size: 0.75rem !important;
    padding: 8px 12px !important;
    color: #888899 !important;
    border: none !important;
    background: transparent !important;
    min-width: 56px !important;
    pointer-events: auto !important;
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
    margin-bottom: 12px;
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
.top-bar-right { text-align: right; }
.top-bar-weather { font-size: 1.0rem; color: #CCCCDD; }
.top-bar-location { font-size: 0.78rem; color: #00B4D8; margin-top: 2px; }

/* Kategoriakortit - 2-sarakkeinen gridi */
.cat-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    padding-bottom: 80px;
}
.cat-card {
    border-radius: 14px;
    padding: 14px 16px;
    min-height: 110px;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    -webkit-tap-highlight-color: transparent;
    position: relative;
    overflow: hidden;
}
.cat-card:active { transform: scale(0.97); }
.cat-card-icon {
    font-size: 1.6rem;
    margin-bottom: 6px;
    display: block;
}
.cat-card-name {
    font-size: 0.95rem;
    font-weight: 700;
    color: #FAFAFA;
    margin-bottom: 2px;
}
.cat-card-sub {
    font-size: 0.65rem;
    color: #999;
    margin-bottom: 6px;
    line-height: 1.3;
}
.cat-card-count {
    position: absolute;
    top: 12px;
    right: 12px;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 10px;
    background: rgba(255,255,255,0.1);
}
.cat-card-signal {
    font-size: 0.72rem;
    color: #ddd;
    line-height: 1.4;
    max-height: 3.0em;
    overflow: hidden;
}

/* Hairiobanneri */
.disruption-banner {
    background: linear-gradient(90deg, #2d0a0a, #1a0505);
    border: 1px solid #FF4B4B66;
    border-radius: 10px;
    padding: 10px 16px;
    margin-bottom: 10px;
    font-size: 0.85rem;
    color: #FF6B6B;
}

/* Agenttipisteet */
.agent-dots { display:flex; gap:6px; flex-wrap:wrap; margin:8px 0; }
.agent-dot  { width:8px; height:8px; border-radius:50%; display:inline-block; }
.dot-ok     { background:#21C55D; }
.dot-error  { background:#FF4B4B; }

/* Streamlit-overridet */
.stButton > button {
    background: #1a1d27 !important;
    border: 1px solid #2a2d3d !important;
    color: #FAFAFA !important;
    border-radius: 10px !important;
    font-size: 0.85rem !important;
}
.stLinkButton > a {
    background: rgba(0,180,216,0.1) !important;
    border: 1px solid #00B4D844 !important;
    color: #00B4D8 !important;
    border-radius: 10px !important;
    font-size: 0.82rem !important;
    padding: 5px 14px !important;
    text-decoration: none !important;
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
    """Palauta Suomen aika (Europe/Helsinki) oikein."""
    return datetime.now(HKI_TZ)


def _get_agent_result(
    agent_results: list | dict,
    agent_name: str,
) -> object:
    """Hae agentin tulos nimella."""
    if isinstance(agent_results, dict):
        return agent_results.get(agent_name)
    return next(
        (r for r in (agent_results or [])
         if getattr(r, "agent_name", "") == agent_name),
        None,
    )


def _collect_signals_for_category(
    cat: dict,
    agent_results: list | dict,
) -> list:
    """Keraa kategoriaan kuuluvat signaalit."""
    signals = []
    filter_cat = cat.get("filter_category", "")

    for agent_name in cat.get("agents", []):
        result = _get_agent_result(agent_results, agent_name)
        if result is None or not getattr(result, "ok", False):
            continue
        for sig in getattr(result, "signals", []):
            # Jos kategoria-suodatin maaritelty, suodata
            if filter_cat:
                sig_cat = getattr(sig, "category", "")
                if sig_cat and sig_cat != filter_cat:
                    continue
            signals.append(sig)

    # Jarjesta urgency mukaan
    signals.sort(key=lambda s: getattr(s, "urgency", 0), reverse=True)
    return signals


# ---------------------------------------------------------------------------
# YLAPALKKI
# ---------------------------------------------------------------------------

def _render_top_bar(agent_results: list | dict) -> None:
    """Renderoi ylapalkki kellolla ja saatiedolla."""
    now_str = _helsinki_time().strftime("%H:%M")

    weather_html = ""
    wr = _get_agent_result(agent_results, "WeatherAgent")
    if wr and getattr(wr, "ok", False):
        sigs = getattr(wr, "signals", [])
        if sigs:
            desc = getattr(sigs[0], "reason", "")
            if desc:
                weather_html = (
                    '<div class="top-bar-weather">' + desc[:60] + "</div>"
                )

    location_html = ""
    if LOCATION_AVAILABLE:
        loc = get_location_from_session()
        if loc and loc.nearest_area:
            hotspots = st.session_state.get("ceo_hotspots", [])
            rec = get_smart_recommendation_text(loc.lat, loc.lon, hotspots)
            location_html = (
                '<div class="top-bar-location">' + rec + "</div>"
            )

    st.markdown(
        '<div class="top-bar">'
        + '<div class="top-bar-clock">' + now_str + "</div>"
        + '<div class="top-bar-right">' + weather_html + location_html
        + "</div></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# HAIRIOBANNERI
# ---------------------------------------------------------------------------

def _render_disruption_banner(agent_results: list | dict) -> None:
    """Nayta hairiot urgency >= 7."""
    dr = _get_agent_result(agent_results, "DisruptionAgent")
    if dr and getattr(dr, "ok", False):
        for sig in getattr(dr, "signals", [])[:2]:
            if getattr(sig, "urgency", 0) >= 7:
                reason = getattr(sig, "reason", "")
                st.markdown(
                    '<div class="disruption-banner">!! '
                    + str(reason)[:120]
                    + "</div>",
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# 8 KATEGORIAKORTIT
# ---------------------------------------------------------------------------

def _render_category_cards(agent_results: list | dict) -> None:
    """Renderoi 8 dynaamista tapahtumakorttia 2-sarakkeisessa gridissa."""
    cards_html = '<div class="cat-grid">'

    for cat in CARD_CATEGORIES:
        signals = _collect_signals_for_category(cat, agent_results)
        count = len(signals)

        # Korkein urgency maaraa kortin varin intensiteetin
        max_urgency = 0
        top_signal_text = cat["sub"]
        if signals:
            max_urgency = max(
                getattr(s, "urgency", 0) for s in signals
            )
            top = signals[0]
            top_signal_text = getattr(top, "reason", "")[:80]

        # Urgency-vari countille
        if max_urgency >= 7:
            count_bg = "rgba(255,75,75,0.3)"
            count_color = "#FF4B4B"
        elif max_urgency >= 5:
            count_bg = "rgba(255,215,0,0.3)"
            count_color = "#FFD700"
        elif count > 0:
            count_bg = "rgba(255,255,255,0.15)"
            count_color = cat["color"]
        else:
            count_bg = "rgba(255,255,255,0.07)"
            count_color = "#666"

        cards_html += (
            '<div class="cat-card" '
            f'style="background:{cat["gradient"]}; '
            f'border:1px solid {cat["border"]}">'
            f'<span class="cat-card-icon">{cat["icon"]}</span>'
            f'<div class="cat-card-name">{cat["name"]}</div>'
            f'<div class="cat-card-sub">{cat["sub"]}</div>'
            f'<div class="cat-card-count" '
            f'style="background:{count_bg};color:{count_color}">'
            f'{count}</div>'
            f'<div class="cat-card-signal">{top_signal_text}</div>'
            "</div>"
        )

    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)

    # Linkkipainikkeet per kategoria (Streamlit-natiivi)
    for cat in CARD_CATEGORIES:
        signals = _collect_signals_for_category(cat, agent_results)
        links: list[tuple[str, str]] = []
        seen: set[str] = set()

        for sig in signals[:3]:
            url = getattr(sig, "source_url", "")
            if not url or not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            lbl = getattr(sig, "title", "")
            if not lbl:
                lbl = getattr(sig, "reason", "")[:30]
            # Siivoa otsikkoa
            for prefix in [
                "Juna saapuu: ", "Tapahtuma: ",
                "Hairio: ", "Lautta: ", "Paattyy pian: ",
            ]:
                lbl = lbl.replace(prefix, "")
            lbl = lbl[:28] or "Avaa"
            links.append((lbl, url))

        if links:
            with st.expander(cat["name"] + " linkit", expanded=False):
                for lbl, url in links:
                    st.link_button(
                        lbl, url, use_container_width=True
                    )


# ---------------------------------------------------------------------------
# AGENTTISTATUS
# ---------------------------------------------------------------------------

def _render_agent_dots(agent_results: list | dict) -> None:
    """Nayta agenttien tila pisteineen."""
    items = (
        agent_results.items()
        if isinstance(agent_results, dict)
        else [
            (getattr(r, "agent_name", "?"), r)
            for r in (agent_results or [])
        ]
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
    hotspots: list | None = None,
    agent_results: list | dict | None = None,
    refresh_callback=None,
) -> None:
    """
    Renderoi kojelauta-nakyma v2.0.

    8 dynaamista tapahtumakorttia kategorioittain.
    """
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)

    # Hae data session_statesta jos ei annettu parametrina
    if hotspots is None or agent_results is None:
        cache = st.session_state.get("hotspot_cache")
        if cache and isinstance(cache, (tuple, list)) and len(cache) >= 2:
            hotspots = cache[0] if hotspots is None else hotspots
            agent_results = cache[1] if agent_results is None else agent_results
        else:
            hotspots = hotspots or []
            agent_results = agent_results or {}

    # Sijaintiboosteri
    if LOCATION_AVAILABLE and hotspots:
        loc = get_location_from_session()
        if loc:
            hotspots = apply_location_boost(
                hotspots, driver_lat=loc.lat, driver_lon=loc.lon
            )

    # Ylapalkki
    _render_top_bar(agent_results)

    # Hairiobanneri
    _render_disruption_banner(agent_results)

    # Sijainti-expander
    if LOCATION_AVAILABLE:
        with st.expander("Sijainti (GPS)", expanded=False):
            render_location_widget()

    # 8 kategoriakorttinakyma
    if not agent_results:
        st.info("Ladataan agentteja...")
        return

    st.session_state["ceo_hotspots"] = hotspots
    _render_category_cards(agent_results)

    # Agenttistatus
    _render_agent_dots(agent_results)

    # Paivita-nappi
    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        if st.button("Paivita nyt", use_container_width=True):
            if refresh_callback:
                refresh_callback()
            else:
                st.cache_resource.clear()
                st.rerun()
