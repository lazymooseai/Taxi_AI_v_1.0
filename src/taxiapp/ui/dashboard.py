# dashboard.py -- Kojelauta-valilehti
# Helsinki Taxi AI v1.2
#
# KORJAUKSET:
#   - render_dashboard() ei vaadi parametreja -- lukee hotspot_cache session_statesta
#   - 0 erikoismerkkia -- vain ASCII + aaoo
#   - Navigaatio kiinnitetty CSS:lla alaosaan
#   - Kortit: link_button per signaali (source_url)
#   - Sijaintiboosteri (streamlit-geolocation, valinnainen)

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st

# Sijaintipalvelu -- valinnainen riippuvuus
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
# CSS -- navigaatio kiinnitetty alaosaan
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
.top-bar-right {
    text-align: right;
}
.top-bar-weather {
    font-size: 1.0rem;
    color: #CCCCDD;
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
    overflow: hidden;
}
.card-red  { background: linear-gradient(135deg,#2d0a0a,#1a0505); border:1px solid #FF4B4B44; }
.card-gold { background: linear-gradient(135deg,#2d2200,#1a1500); border:1px solid #FFD70044; }
.card-blue { background: linear-gradient(135deg,#00162a,#000d1a); border:1px solid #00B4D844; }

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
.badge-red  { background:#FF4B4B22; color:#FF4B4B; border:1px solid #FF4B4B44; }
.badge-gold { background:#FFD70022; color:#FFD700; border:1px solid #FFD70044; }
.badge-blue { background:#00B4D822; color:#00B4D8; border:1px solid #00B4D844; }

.card-title  { font-size:1.45rem; font-weight:700; line-height:1.2; margin-bottom:6px; color:#FAFAFA; }
.card-score  { font-size:0.8rem; color:#888899; margin-bottom:10px; }
.card-reason { font-size:0.82rem; color:#CCCCDD; line-height:1.5; }
.reason-item { display:block; padding:3px 0; border-bottom:1px solid rgba(255,255,255,0.05); }
.reason-item:last-child { border-bottom:none; }

.fill-badge   { display:inline-block; font-size:0.7rem; padding:1px 7px; border-radius:10px; margin-left:6px; }
.fill-soldout { background:#FF4B4B33; color:#FF4B4B; }
.fill-limited { background:#FF8C0033; color:#FF8C00; }
.fill-normal  { background:#21C55D22; color:#21C55D; }

/* Hairiosbanneri */
.disruption-banner {
    background: linear-gradient(90deg,#2d0a0a,#1a0505);
    border: 1px solid #FF4B4B66;
    border-radius: 10px;
    padding: 10px 16px;
    margin-bottom: 12px;
    font-size: 0.88rem;
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
    font-family: 'Inter', sans-serif !important;
    font-size: 0.85rem !important;
}
.stButton > button:hover {
    border-color: #00B4D8 !important;
    color: #00B4D8 !important;
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
    """Helsingin aika -- zoneinfo."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Helsinki"))
    except Exception:
        utc_now = datetime.now(timezone.utc)
        year = utc_now.year
        mar_last = datetime(year, 3, 31, tzinfo=timezone.utc)
        while mar_last.weekday() != 6:
            mar_last -= timedelta(days=1)
        dst_start = mar_last.replace(hour=1)
        oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
        while oct_last.weekday() != 6:
            oct_last -= timedelta(days=1)
        dst_end = oct_last.replace(hour=1)
        offset = 3 if dst_start <= utc_now < dst_end else 2
        return utc_now + timedelta(hours=offset)


def _fill_badge(fill_rate: Optional[float]) -> str:
    if fill_rate is None:
        return ""
    if fill_rate >= 1.0:
        return '<span class="fill-badge fill-soldout">LOPPUUNMYYTY</span>'
    if fill_rate >= 0.85:
        return '<span class="fill-badge fill-limited">Viimeiset liput</span>'
    if fill_rate >= 0.5:
        return '<span class="fill-badge fill-normal">Lippuja</span>'
    return ""


def _urgency_label(urgency: int) -> str:
    if urgency >= 9: return "OVERRIDE"
    if urgency >= 7: return "KRIITTINEN"
    if urgency >= 5: return "KORKEA"
    if urgency >= 3: return "NORMAALI"
    return "PERUS"


def _card_cls(idx: int, urgency: int) -> tuple[str, str]:
    if urgency >= 9 or idx == 0: return "card-red",  "badge-red"
    if idx == 1:                  return "card-gold", "badge-gold"
    return                               "card-blue", "badge-blue"


# ---------------------------------------------------------------------------
# KORTTI
# ---------------------------------------------------------------------------

def _render_card(hotspot: object, idx: int) -> None:
    """Renderoi yksi hotspot-kortti linkkipainikkeineen."""
    card_cls, badge_cls = _card_cls(idx, getattr(hotspot, "urgency", 2))
    urgency  = getattr(hotspot, "urgency", 2)
    score    = getattr(hotspot, "score", 0.0)
    area     = getattr(hotspot, "area", "?").replace("_", " ").title()
    signals  = getattr(hotspot, "signals", [])

    # Yhteensopivuus: vanha dashboard kayttaa hotspot.reasons (list[str])
    reasons_list = getattr(hotspot, "reasons", [])
    if reasons_list:
        reasons_html = "".join(
            '<span class="reason-item">' + str(r)[:90] + "</span>"
            for r in reasons_list[:4]
        )
    else:
        # Uusi rakenne: signals-lista
        reasons_html = ""
        for sig in signals[:4]:
            desc = getattr(sig, "description", "")
            fill = _fill_badge((getattr(sig, "extra", {}) or {}).get("fill_rate"))
            if desc:
                reasons_html += '<span class="reason-item">' + desc + fill + "</span>"

    st.markdown(
        "<div class=\"hotspot-card " + card_cls + "\">"
        + "<div class=\"card-badge " + badge_cls + "\">" + _urgency_label(urgency) + "</div>"
        + "<div class=\"card-title\">" + area + "</div>"
        + "<div class=\"card-score\">Pisteet: " + str(round(score, 1)) + "</div>"
        + "<div class=\"card-reason\">" + reasons_html + "</div>"
        + "</div>",
        unsafe_allow_html=True,
    )

    # Linkkipainikkeet -- keraa uniikit URLt signaaleista
    seen: set[str] = set()
    links: list[tuple[str, str]] = []

    for sig in signals:
        url = getattr(sig, "source_url", None)
        if not url or not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        lbl = getattr(sig, "title", "").strip()
        for prefix in ["Juna saapuu: ", "Tapahtuma: ", "Hairio: ", "Lautta: "]:
            lbl = lbl.replace(prefix, "")
        lbl = lbl[:32] or "Avaa"
        links.append((lbl, url))

    if links:
        cols = st.columns(min(len(links), 3))
        for i, (lbl, url) in enumerate(links[:3]):
            with cols[i % len(cols)]:
                st.link_button("-> " + lbl, url, use_container_width=True)


# ---------------------------------------------------------------------------
# YLAPALKKI
# ---------------------------------------------------------------------------

def _render_top_bar(agent_results: list | dict) -> None:
    now_str = _helsinki_time().strftime("%H:%M")

    weather_html = ""
    # Tukee seka lista- etta dict-muotoa
    if isinstance(agent_results, dict):
        wr = agent_results.get("WeatherAgent")
    else:
        wr = next(
            (r for r in (agent_results or []) if getattr(r, "agent_name", "") == "WeatherAgent"),
            None,
        )
    if wr and getattr(wr, "ok", False):
        sigs = getattr(wr, "signals", [])
        if sigs:
            weather_html = (
                '<div class="top-bar-weather">'
                + str(getattr(sigs[0], "description", ""))
                + "</div>"
            )

    location_html = ""
    if LOCATION_AVAILABLE:
        loc = get_location_from_session()
        if loc and loc.nearest_area:
            hotspots = st.session_state.get("ceo_hotspots", [])
            rec = get_smart_recommendation_text(loc.lat, loc.lon, hotspots)
            location_html = '<div class="top-bar-location">' + rec + "</div>"

    st.markdown(
        "<div class=\"top-bar\">"
        + "<div class=\"top-bar-clock\">" + now_str + "</div>"
        + "<div class=\"top-bar-right\">" + weather_html + location_html + "</div>"
        + "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# PAARUNKTIO -- yhteensopiva alkuperaisen app.py:n kanssa
# ---------------------------------------------------------------------------

def render_dashboard(
    hotspots: list | None = None,
    agent_results: list | dict | None = None,
    refresh_callback=None,
) -> None:
    """
    Renderoi kojelauta-nakyma.

    Yhteensopiva molempien kutsumuotojen kanssa:
      render_dashboard()                         -- lukee session_statesta
      render_dashboard(hotspots, agent_results)  -- kayttaa suoraan

    app.py kutsuu: render_dashboard()
    session_state["hotspot_cache"] = (hotspots, results)
    """
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)

    # --- Hae data session_statesta jos ei annettu parametrina ---
    if hotspots is None or agent_results is None:
        cache = st.session_state.get("hotspot_cache")
        if cache and isinstance(cache, (tuple, list)) and len(cache) >= 2:
            hotspots      = cache[0] if hotspots is None else hotspots
            agent_results = cache[1] if agent_results is None else agent_results
        else:
            hotspots      = hotspots or []
            agent_results = agent_results or {}

    # --- Sijaintiboosteri ---
    if LOCATION_AVAILABLE and hotspots:
        loc = get_location_from_session()
        if loc:
            hotspots = apply_location_boost(
                hotspots, driver_lat=loc.lat, driver_lon=loc.lon
            )

    # --- Ylapalkki ---
    _render_top_bar(agent_results)

    # --- Hairiosbanneri urgency >= 7 ---
    if isinstance(agent_results, dict):
        dr = agent_results.get("DisruptionAgent")
    else:
        dr = next(
            (r for r in (agent_results or []) if getattr(r, "agent_name", "") == "DisruptionAgent"),
            None,
        )
    if dr and getattr(dr, "ok", False):
        for sig in getattr(dr, "signals", [])[:2]:
            if getattr(sig, "urgency", 0) >= 7:
                st.markdown(
                    "<div class=\"disruption-banner\">!! "
                    + str(getattr(sig, "description", ""))
                    + "</div>",
                    unsafe_allow_html=True,
                )

    # --- Sijainti-expander ---
    if LOCATION_AVAILABLE:
        with st.expander("Sijainti (GPS)", expanded=False):
            render_location_widget()

    # --- 3 hotspot-korttia ---
    if not hotspots:
        st.info("Ladataan agentteja...")
        return

    st.session_state["ceo_hotspots"] = hotspots

    for idx, hotspot in enumerate(hotspots[:3]):
        _render_card(hotspot, idx)

    # --- Agenttistatus-pisteet ---
    items = agent_results.items() if isinstance(agent_results, dict) else [
        (getattr(r, "agent_name", "?"), r) for r in (agent_results or [])
    ]
    dots_html = "<div class=\"agent-dots\">"
    for name, result in items:
        if result is None:
            continue
        ok    = getattr(result, "ok", False)
        count = len(getattr(result, "signals", []))
        cls   = "dot-ok" if ok else "dot-error"
        dots_html += (
            "<span title=\"" + str(name) + ": " + str(count)
            + " signaalia\" class=\"agent-dot " + cls + "\"></span>"
        )
    dots_html += "</div>"
    st.markdown(dots_html, unsafe_allow_html=True)

    # --- Paivita-nappi ---
    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        if st.button("Paivita nyt", use_container_width=True):
            if refresh_callback:
                refresh_callback()
            else:
                st.cache_resource.clear()
                st.rerun()
