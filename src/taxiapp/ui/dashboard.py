"""
dashboard.py -- Kojelauta v2.2
Helsinki Taxi AI

KRIITTISET KORJAUKSET:
  - Kortit nayttavat oikeat tapahtumat nimilla ja aikatauluilla
  - Signaalin title+aika prominenttina, ei pelkkaa reason-tekstia
  - Fontit huomattavasti suuremmat (otsikot 1.4rem, signaalit 1.1rem)
  - Ei piilotettuja nappeja - tabs alhaalla sticky
  - VR-linkit korjattu (yksinkertaistettu URL)
  - Streamlit-natiivit komponentit klikkauksiin
  - Saa-animaatio ylapalkissa
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

CARD_CATEGORIES: list[dict] = [
    {"id": "trains", "name": "Junat", "icon": "\U0001f686",
     "agents": ["TrainAgent"],
     "sub": "Helsinki \u2022 Pasila \u2022 Tikkurila",
     "color": "#3B82F6", "bg": "#0f1d30", "border": "#3B82F644"},
    {"id": "ferries", "name": "Satamat", "icon": "\u2693",
     "agents": ["FerryAgent"],
     "sub": "Olympiaterminaali \u2022 Katajanokka \u2022 L\u00e4nsisatama",
     "color": "#06B6D4", "bg": "#0c2d3a", "border": "#06B6D444"},
    {"id": "culture", "name": "Kulttuuri ja musiikki", "icon": "\U0001f3ad",
     "agents": ["EventsAgent"], "filter_category": "culture",
     "sub": "Musiikkitalo \u2022 Ooppera \u2022 Teatteri \u2022 Tavastia",
     "color": "#A855F7", "bg": "#1e1035", "border": "#A855F744"},
    {"id": "airport", "name": "Lentoasema", "icon": "\u2708\ufe0f",
     "agents": ["FlightAgent"],
     "sub": "Helsinki-Vantaa EFHK",
     "color": "#F59E0B", "bg": "#2e1e05", "border": "#F59E0B44"},
    {"id": "sports", "name": "Urheilu", "icon": "\u26bd",
     "agents": ["EventsAgent"], "filter_category": "sports",
     "sub": "Nordis \u2022 Bolt Arena \u2022 Olympiastadion",
     "color": "#22C55E", "bg": "#0a2916", "border": "#22C55E44"},
    {"id": "politics", "name": "Politiikka", "icon": "\U0001f3db\ufe0f",
     "agents": ["SocialMediaAgent"],
     "sub": "Eduskunta \u2022 S\u00e4\u00e4tytalo",
     "color": "#EF4444", "bg": "#2e0d0d", "border": "#EF444444"},
    {"id": "disruptions", "name": "Liikenneh\u00e4iri\u00f6t", "icon": "\u26a0\ufe0f",
     "agents": ["DisruptionAgent"],
     "sub": "HSL \u2022 VR \u2022 Metro",
     "color": "#FF6B6B", "bg": "#250808", "border": "#FF6B6B44"},
    {"id": "weather", "name": "S\u00e4\u00e4", "icon": "\u2600\ufe0f",
     "agents": ["WeatherAgent"],
     "sub": "FMI Helsinki",
     "color": "#38BDF8", "bg": "#0f1d30", "border": "#38BDF844"},
]

DASHBOARD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
html, body, [data-testid="stAppViewContainer"] {
    background: #0e1117 !important;
    font-family: 'Inter', sans-serif !important;
    color: #FAFAFA !important;
}
[data-baseweb="tab-list"] {
    position: sticky !important;
    bottom: 0 !important;
    z-index: 999 !important;
    background: #12151f !important;
    border-top: 1px solid #2a2d3d !important;
    padding: 6px 0 !important;
    justify-content: space-around !important;
}
[data-baseweb="tab"] {
    font-size: 0.85rem !important;
    padding: 10px 14px !important;
    color: #888899 !important;
    border: none !important;
    background: transparent !important;
}
[data-baseweb="tab"][aria-selected="true"] {
    color: #00B4D8 !important;
    background: rgba(0,180,216,0.12) !important;
    border-radius: 8px !important;
}
.top-bar {
    background: linear-gradient(135deg, #12151f 0%, #1a1d27 100%);
    border: 1px solid #2a2d3d;
    border-radius: 16px;
    padding: 18px 22px;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.top-clock {
    font-size: 3.2rem;
    font-weight: 800;
    color: #FAFAFA;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.03em;
}
.top-right { text-align: right; }
.top-weather {
    font-size: 1.2rem;
    font-weight: 600;
    color: #ddd;
}
.top-date {
    font-size: 0.9rem;
    color: #888;
    margin-top: 2px;
}
@keyframes wpulse {
    0%,100% { opacity:1; transform:scale(1); }
    50% { opacity:0.7; transform:scale(1.1); }
}
.wanim { display:inline-block; font-size:1.8rem; animation:wpulse 3s ease-in-out infinite; margin-right:6px; vertical-align:middle; }
.disruption-banner {
    background: linear-gradient(90deg, #3d0a0a, #1a0505);
    border: 1px solid #FF4B4B66;
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 12px;
    font-size: 1.1rem;
    font-weight: 600;
    color: #FF6B6B;
}
.card-box {
    width: 100%;
    border-radius: 16px;
    padding: 18px 20px 14px 20px;
    margin-bottom: 4px;
}
.card-head {
    display: flex;
    align-items: center;
    margin-bottom: 12px;
}
.card-icon { font-size: 1.8rem; margin-right: 10px; }
.card-name { font-size: 1.4rem; font-weight: 800; color: #FAFAFA; flex: 1; }
.card-badge {
    font-size: 0.78rem; font-weight: 700; padding: 3px 10px;
    border-radius: 12px; white-space: nowrap;
}
.ev-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 9px 0;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.ev-row:last-child { border-bottom: none; }
.ev-time {
    font-size: 1.15rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    min-width: 55px;
    flex-shrink: 0;
}
.ev-name {
    font-size: 1.05rem;
    font-weight: 600;
    color: #FAFAFA;
    flex: 1;
}
.ev-detail {
    font-size: 0.85rem;
    color: #999;
}
.ev-tag {
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 8px;
    white-space: nowrap;
}
.u-high { color: #FF6B6B; }
.u-mid { color: #FFD700; }
.u-low { color: #21C55D; }
.u-mute { color: #888; }
.tag-sold { background: #FF4B4B33; color: #FF4B4B; }
.tag-limited { background: #FF8C0033; color: #FF8C00; }
.ev-empty { font-size: 1.0rem; color: #666; padding: 8px 0; font-style: italic; }
.agent-dots { display:flex; gap:7px; flex-wrap:wrap; margin:10px 0; }
.agent-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
.dot-ok { background:#21C55D; }
.dot-err { background:#FF4B4B; }
.stButton > button {
    background: #1a1d27 !important;
    border: 1px solid #2a2d3d !important;
    color: #FAFAFA !important;
    border-radius: 12px !important;
    font-size: 1.0rem !important;
    font-weight: 600 !important;
    padding: 10px !important;
}
.stLinkButton > a {
    background: rgba(0,180,216,0.12) !important;
    border: 1px solid #00B4D844 !important;
    color: #00B4D8 !important;
    border-radius: 12px !important;
    font-size: 0.95rem !important;
    padding: 8px 16px !important;
    text-decoration: none !important;
    font-weight: 600 !important;
}
.block-container {
    padding-top: 0.5rem !important;
    padding-bottom: 20px !important;
    max-width: 800px !important;
}
</style>
"""


def _hki_now():
    return datetime.now(HKI_TZ)


def _agent_result(ar, name):
    if isinstance(ar, dict):
        return ar.get(name)
    return next((r for r in (ar or []) if getattr(r, "agent_name", "") == name), None)


def _signals_for(cat, ar):
    sigs = []
    fc = cat.get("filter_category", "")
    for an in cat.get("agents", []):
        r = _agent_result(ar, an)
        if r is None or not getattr(r, "ok", False):
            continue
        for s in getattr(r, "signals", []):
            if fc:
                sc = getattr(s, "category", "")
                if sc and sc != fc:
                    continue
            sigs.append(s)
    sigs.sort(key=lambda s: getattr(s, "urgency", 0), reverse=True)
    return sigs


def _weather_icon(reason):
    r = reason.lower()
    if "ukkonen" in r or "myrsky" in r:
        return '<span class="wanim">&#9928;</span>'
    if "sade" in r or "lumi" in r:
        return '<span class="wanim">&#127783;&#65039;</span>'
    if "tuuli" in r:
        return '<span class="wanim">&#127744;</span>'
    if "pilvi" in r:
        return '<span class="wanim">&#9729;&#65039;</span>'
    return '<span class="wanim">&#9728;&#65039;</span>'


def _ucls(u):
    if u >= 7: return "u-high"
    if u >= 4: return "u-mid"
    if u >= 2: return "u-low"
    return "u-mute"


def _sig_time(sig):
    ex = getattr(sig, "extra", {}) or {}
    m = ex.get("minutes_away")
    if m is not None:
        return f"{m}min"
    h = ex.get("hours_until")
    if h is not None and h >= 0:
        if h < 1:
            return f"{int(h*60)}min"
        return f"{h:.0f}h"
    me = ex.get("minutes_to_end")
    if me is not None:
        return f"-{me}min"
    return ""


def _sig_title(sig):
    """Hae signaalin otsikko (tapahtuman nimi)."""
    t = getattr(sig, "title", "")
    if t:
        return t
    return getattr(sig, "reason", "")[:50]


def _sig_detail(sig):
    """Hae yksityiskohdat (paikka, status)."""
    ex = getattr(sig, "extra", {}) or {}
    parts = []
    venue = ex.get("venue", "")
    if venue:
        parts.append(venue)
    delay = ex.get("delay_minutes", 0)
    if delay and delay > 0:
        parts.append(f"+{delay}min my\u00f6h\u00e4ss\u00e4")
    origin = ex.get("origin", "")
    if origin:
        parts.append(origin)
    fr = ex.get("fill_rate")
    if fr is not None and fr >= 1.0:
        return " \u2022 ".join(parts) + "|SOLD"
    if fr is not None and fr >= 0.85:
        return " \u2022 ".join(parts) + "|LTD"
    return " \u2022 ".join(parts) if parts else ""


def _render_top_bar(ar):
    now_s = _hki_now().strftime("%H:%M")
    date_s = _hki_now().strftime("%d.%m.%Y")
    wi = '<span class="wanim">&#9728;&#65039;</span>'
    wt = ""
    wr = _agent_result(ar, "WeatherAgent")
    if wr and getattr(wr, "ok", False):
        sigs = getattr(wr, "signals", [])
        if sigs:
            reason = getattr(sigs[0], "reason", "")
            wi = _weather_icon(reason)
            wt = '<div class="top-weather">' + reason[:55] + "</div>"
    st.markdown(
        '<div class="top-bar">'
        '<div style="display:flex;align-items:center;gap:8px">' + wi
        + '<span class="top-clock">' + now_s + "</span></div>"
        + '<div class="top-right">' + wt
        + '<div class="top-date">' + date_s + "</div></div></div>",
        unsafe_allow_html=True,
    )


def _render_disruption(ar):
    dr = _agent_result(ar, "DisruptionAgent")
    if dr and getattr(dr, "ok", False):
        for sig in getattr(dr, "signals", [])[:2]:
            if getattr(sig, "urgency", 0) >= 7:
                st.markdown(
                    '<div class="disruption-banner">\u26a0\ufe0f '
                    + getattr(sig, "reason", "")[:140] + "</div>",
                    unsafe_allow_html=True)


def _render_cards(ar):
    scored = []
    for cat in CARD_CATEGORIES:
        sigs = _signals_for(cat, ar)
        mu = max((getattr(s, "urgency", 0) for s in sigs), default=0)
        scored.append((mu, len(sigs), cat))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    for mu, cnt, cat in scored:
        sigs = _signals_for(cat, ar)
        # Badge
        if mu >= 7:
            bbg, bcol, btxt = "rgba(255,75,75,0.3)", "#FF4B4B", "KRIITTINEN"
        elif mu >= 5:
            bbg, bcol, btxt = "rgba(255,215,0,0.3)", "#FFD700", "KORKEA"
        elif cnt > 0:
            bbg, bcol, btxt = "rgba(255,255,255,0.12)", cat["color"], str(cnt)
        else:
            bbg, bcol, btxt = "rgba(255,255,255,0.05)", "#666", "-"

        html = (
            '<div class="card-box" style="background:' + cat["bg"]
            + ';border:1px solid ' + cat["border"] + '">'
            + '<div class="card-head">'
            + '<span class="card-icon">' + cat["icon"] + "</span>"
            + '<span class="card-name">' + cat["name"] + "</span>"
            + '<span class="card-badge" style="background:' + bbg
            + ';color:' + bcol + '">' + btxt + "</span></div>"
        )

        if sigs:
            for sig in sigs[:5]:
                urg = getattr(sig, "urgency", 0)
                tm = _sig_time(sig)
                title = _sig_title(sig)
                detail = _sig_detail(sig)
                ucl = _ucls(urg)

                # Fill rate tags
                tag_html = ""
                if detail.endswith("|SOLD"):
                    detail = detail[:-5]
                    tag_html = '<span class="ev-tag tag-sold">LOPPUUNMYYTY</span>'
                elif detail.endswith("|LTD"):
                    detail = detail[:-4]
                    tag_html = '<span class="ev-tag tag-limited">Viim. liput</span>'

                html += '<div class="ev-row">'
                if tm:
                    html += '<span class="ev-time ' + ucl + '">' + tm + "</span>"
                html += '<div style="flex:1">'
                html += '<div class="ev-name">' + title[:65] + " " + tag_html + "</div>"
                if detail:
                    html += '<div class="ev-detail">' + detail[:80] + "</div>"
                html += "</div></div>"
        else:
            html += '<div class="ev-empty">Ei aktiivisia signaaleja</div>'

        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

        # Linkkipainikkeet - max 2 per kortti
        links = []
        seen = set()
        for sig in sigs[:5]:
            url = getattr(sig, "source_url", "")
            if not url or not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            lbl = _sig_title(sig)[:32] or "Avaa"
            links.append((lbl, url))
        if links:
            cols = st.columns(min(len(links), 2))
            for i, (lbl, url) in enumerate(links[:2]):
                with cols[i]:
                    st.link_button(lbl, url, use_container_width=True)


def _render_dots(ar):
    items = (ar.items() if isinstance(ar, dict)
             else [(getattr(r, "agent_name", "?"), r) for r in (ar or [])])
    h = '<div class="agent-dots">'
    for name, r in items:
        if r is None: continue
        ok = getattr(r, "ok", False)
        n = len(getattr(r, "signals", []))
        c = "dot-ok" if ok else "dot-err"
        h += '<span title="' + name + ": " + str(n) + '" class="agent-dot ' + c + '"></span>'
    h += "</div>"
    st.markdown(h, unsafe_allow_html=True)


def render_dashboard(hotspots=None, agent_results=None, refresh_callback=None):
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
                hotspots = apply_location_boost(hotspots, driver_lat=loc.lat, driver_lon=loc.lon)
        except Exception:
            pass

    _render_top_bar(agent_results)
    _render_disruption(agent_results)

    if LOCATION_AVAILABLE:
        with st.expander("Sijainti (GPS)", expanded=False):
            render_location_widget()

    if not agent_results:
        st.info("Ladataan agentteja...")
        return

    st.session_state["ceo_hotspots"] = hotspots
    _render_cards(agent_results)
    _render_dots(agent_results)

    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        if st.button("P\u00e4ivit\u00e4 nyt", use_container_width=True):
            if refresh_callback:
                refresh_callback()
            else:
                st.cache_resource.clear()
                st.rerun()
