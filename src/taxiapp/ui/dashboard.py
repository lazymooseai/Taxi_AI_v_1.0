"""
dashboard.py -- Kojelauta v2.3
Helsinki Taxi AI

v2.3 muutokset:
  - Saa-kortti poistettu (naytetaan vain ylapalkissa + FMI-linkki)
  - Junakortti: asemavalitsin (Helsinki/Pasila/Tikkurila)
  - Politiikka: suodatettu Helsinki-relevantteihin uutisiin
  - Saa-signaalien deduplikointi (ei 5x toistoa)
  - Ylaosa: padding-top Streamlit-nappien alle
  - Fontit suuremmat tapahtumissa
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

# 7 kategoriaa (Saa poistettu - naytetaan ylapalkissa)
CARD_CATEGORIES: list[dict] = [
    {"id": "trains", "name": "Junat", "icon": "\U0001f686",
     "agents": ["TrainAgent"],
     "sub": "Helsinki \u2022 Pasila \u2022 Tikkurila",
     "color": "#3B82F6", "bg": "#0f1d30", "border": "#3B82F644",
     "has_station_filter": True},
    {"id": "ferries", "name": "Satamat", "icon": "\u2693",
     "agents": ["FerryAgent"],
     "sub": "Olympiaterminaali \u2022 Katajanokka \u2022 L\u00e4nsisatama",
     "color": "#06B6D4", "bg": "#0c2d3a", "border": "#06B6D444"},
    {"id": "culture", "name": "Kulttuuri ja musiikki", "icon": "\U0001f3ad",
     "agents": ["EventsAgent"], "filter_category": "culture",
     "sub": "Musiikkitalo \u2022 Ooppera \u2022 Teatteri",
     "color": "#A855F7", "bg": "#1e1035", "border": "#A855F744"},
    {"id": "airport", "name": "Lentoasema", "icon": "\u2708\ufe0f",
     "agents": ["FlightAgent"],
     "sub": "Helsinki-Vantaa EFHK",
     "color": "#F59E0B", "bg": "#2e1e05", "border": "#F59E0B44"},
    {"id": "sports", "name": "Urheilu", "icon": "\u26bd",
     "agents": ["EventsAgent"], "filter_category": "sports",
     "sub": "Nordis \u2022 Bolt Arena \u2022 Olympiastadion",
     "color": "#22C55E", "bg": "#0a2916", "border": "#22C55E44"},
    {"id": "helsinki_news", "name": "Helsinki-uutiset", "icon": "\U0001f3db\ufe0f",
     "agents": ["SocialMediaAgent"],
     "sub": "Liikenne \u2022 H\u00e4iri\u00f6t \u2022 Tapahtumat",
     "color": "#EF4444", "bg": "#2e0d0d", "border": "#EF444444"},
    {"id": "disruptions", "name": "Liikenneh\u00e4iri\u00f6t", "icon": "\u26a0\ufe0f",
     "agents": ["DisruptionAgent"],
     "sub": "HSL \u2022 VR \u2022 Metro",
     "color": "#FF6B6B", "bg": "#250808", "border": "#FF6B6B44"},
]

# Helsinki-avainsanat politiikka/uutiset -suodatukseen
HELSINKI_KEYWORDS = frozenset({
    "helsinki", "espoo", "vantaa", "metro", "raitiovaunu",
    "liikenne", "onnettomuus", "mielenosoitus", "lakko",
    "poliisi", "suljettu", "hairio", "h\u00e4iri\u00f6",
    "eduskunta", "s\u00e4\u00e4tytalo", "kaupunginvaltuusto",
    "tuomioistuin", "palolaitos", "pelastuslaitos",
    "hsl", "taksi", "linja-auto", "bussi", "juna",
    "rautatieasema", "pasila", "it\u00e4keskus",
    "kamppi", "kallio", "s\u00f6rn\u00e4inen",
})

# Asemasuodattimet junakortille
TRAIN_STATIONS = {
    "Kaikki": None,
    "Helsinki": "Rautatieasema",
    "Pasila": "Pasila",
    "Tikkurila": "Tikkurila",
}

FMI_URL = "https://www.ilmatieteenlaitos.fi/sade-ja-pilvialueet?area=etela-suomi"

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
    font-size: 1.15rem;
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
    50% { opacity:0.7; transform:scale(1.15); }
}
.wanim {
    display:inline-block; font-size:2.0rem;
    animation:wpulse 3s ease-in-out infinite;
    margin-right:8px; vertical-align:middle;
}
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
    margin-bottom: 10px;
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
    padding: 10px 0;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.ev-row:last-child { border-bottom: none; }
.ev-time {
    font-size: 1.2rem;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
    min-width: 58px;
    flex-shrink: 0;
}
.ev-name {
    font-size: 1.15rem;
    font-weight: 700;
    color: #FAFAFA;
    flex: 1;
}
.ev-detail {
    font-size: 0.88rem;
    color: #999;
    margin-top: 1px;
}
.ev-tag {
    font-size: 0.72rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 8px;
    white-space: nowrap;
    margin-left: 6px;
}
.u-high { color: #FF6B6B; }
.u-mid { color: #FFD700; }
.u-low { color: #21C55D; }
.u-mute { color: #888; }
.tag-sold { background: #FF4B4B33; color: #FF4B4B; }
.tag-ltd { background: #FF8C0033; color: #FF8C00; }
.ev-empty { font-size: 1.05rem; color: #666; padding: 10px 0; font-style: italic; }
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
    padding-top: 3.5rem !important;
    padding-bottom: 20px !important;
    max-width: 800px !important;
}
</style>
"""


def _hki_now():
    return datetime.now(HKI_TZ)


def _ar(agent_results, name):
    if isinstance(agent_results, dict):
        return agent_results.get(name)
    return next((r for r in (agent_results or []) if getattr(r, "agent_name", "") == name), None)


def _signals_for(cat, ar):
    sigs = []
    fc = cat.get("filter_category", "")
    for an in cat.get("agents", []):
        r = _ar(ar, an)
        if r is None or not getattr(r, "ok", False):
            continue
        for s in getattr(r, "signals", []):
            if fc:
                sc = getattr(s, "category", "")
                if sc and sc != fc:
                    continue
            sigs.append(s)
    sigs.sort(key=lambda s: getattr(s, "urgency", 0), reverse=True)
    # Deduplikointi: sama reason naytetaan vain kerran
    seen_reasons = set()
    unique = []
    for s in sigs:
        reason = getattr(s, "reason", "")
        if reason not in seen_reasons:
            seen_reasons.add(reason)
            unique.append(s)
    return unique


def _filter_helsinki_news(sigs):
    """Suodata vain Helsinki-relevantit uutiset."""
    filtered = []
    for s in sigs:
        text = (getattr(s, "reason", "") + " " + getattr(s, "title", "")).lower()
        if any(kw in text for kw in HELSINKI_KEYWORDS):
            filtered.append(s)
    return filtered if filtered else sigs[:2]  # Fallback: 2 tuoreinta


def _filter_train_station(sigs, station_area):
    """Suodata junasignaalit aseman mukaan."""
    if station_area is None:
        return sigs
    return [s for s in sigs if getattr(s, "area", "") == station_area]


def _weather_icon(reason):
    r = reason.lower()
    if "ukkonen" in r or "myrsky" in r:
        return '<span class="wanim">&#9928;</span>'
    if "sade" in r or "lumi" in r:
        return '<span class="wanim">&#127783;&#65039;</span>'
    if "tuuli" in r and ("kova" in r or "voimakas" in r):
        return '<span class="wanim">&#127744;</span>'
    if "pilvi" in r:
        return '<span class="wanim">&#9729;&#65039;</span>'
    if "nakyvyys" in r or "n\u00e4kyvyys" in r:
        return '<span class="wanim">&#127787;&#65039;</span>'
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
        if h < 1: return f"{int(h*60)}min"
        return f"{h:.0f}h"
    at = ex.get("arrival_time")
    if at: return at
    me = ex.get("minutes_to_end")
    if me is not None: return f"-{me}min"
    return ""


def _sig_title(sig):
    t = getattr(sig, "title", "")
    return t if t else getattr(sig, "reason", "")[:55]


def _sig_detail(sig):
    ex = getattr(sig, "extra", {}) or {}
    parts = []
    v = ex.get("venue")
    if v: parts.append(v)
    d = ex.get("delay_minutes", 0)
    if d and d > 0: parts.append(f"+{d}min")
    o = ex.get("origin")
    if o: parts.append(o)
    fr = ex.get("fill_rate")
    tag = ""
    if fr is not None and fr >= 1.0: tag = "|SOLD"
    elif fr is not None and fr >= 0.85: tag = "|LTD"
    return (" \u2022 ".join(parts) + tag) if parts else ""


# --- YLAPALKKI ---

def _render_top_bar(ar):
    now_s = _hki_now().strftime("%H:%M")
    date_s = _hki_now().strftime("%d.%m.%Y")
    wi = '<span class="wanim">&#9728;&#65039;</span>'
    wt = ""
    wr = _ar(ar, "WeatherAgent")
    if wr and getattr(wr, "ok", False):
        sigs = getattr(wr, "signals", [])
        if sigs:
            reason = getattr(sigs[0], "reason", "")
            wi = _weather_icon(reason)
            # Nayta vain uniikki tieto
            wt = '<div class="top-weather">' + reason[:55] + "</div>"

    st.markdown(
        '<div class="top-bar">'
        '<div style="display:flex;align-items:center;gap:8px">' + wi
        + '<span class="top-clock">' + now_s + "</span></div>"
        + '<div class="top-right">' + wt
        + '<div class="top-date">' + date_s + "</div></div></div>",
        unsafe_allow_html=True,
    )
    # FMI-linkki saan alle
    st.link_button("\u2600\ufe0f S\u00e4\u00e4tutka ja ennuste (FMI)", FMI_URL,
                   use_container_width=True)


# --- HAIRIOBANNERI ---

def _render_disruption(ar):
    dr = _ar(ar, "DisruptionAgent")
    if dr and getattr(dr, "ok", False):
        for sig in getattr(dr, "signals", [])[:2]:
            if getattr(sig, "urgency", 0) >= 7:
                st.markdown(
                    '<div class="disruption-banner">\u26a0\ufe0f '
                    + getattr(sig, "reason", "")[:140] + "</div>",
                    unsafe_allow_html=True)


# --- KORTTIEN RENDEROYS ---

def _render_cards(ar):
    scored = []
    for cat in CARD_CATEGORIES:
        sigs = _signals_for(cat, ar)
        # Helsinki-suodatus uutisille
        if cat["id"] == "helsinki_news":
            sigs = _filter_helsinki_news(sigs)
        mu = max((getattr(s, "urgency", 0) for s in sigs), default=0)
        scored.append((mu, len(sigs), cat))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    for mu, cnt, cat in scored:
        sigs = _signals_for(cat, ar)
        if cat["id"] == "helsinki_news":
            sigs = _filter_helsinki_news(sigs)

        # Junakortilla asemavalitsin
        if cat.get("has_station_filter"):
            sigs = _render_train_card(cat, sigs, mu, cnt)
            continue

        _render_single_card(cat, sigs, mu, cnt)


def _render_train_card(cat, sigs, mu, cnt):
    """Junakortti asemavalitsimella."""
    # Badge
    bbg, bcol, btxt = _badge(mu, cnt, cat)

    html = (
        '<div class="card-box" style="background:' + cat["bg"]
        + ';border:1px solid ' + cat["border"] + '">'
        + '<div class="card-head">'
        + '<span class="card-icon">' + cat["icon"] + "</span>"
        + '<span class="card-name">' + cat["name"] + "</span>"
        + '<span class="card-badge" style="background:' + bbg
        + ';color:' + bcol + '">' + btxt + "</span></div></div>"
    )
    st.markdown(html, unsafe_allow_html=True)

    # Asemavalitsin
    station = st.radio(
        "Asema",
        list(TRAIN_STATIONS.keys()),
        horizontal=True,
        key="train_station_filter",
        label_visibility="collapsed",
    )
    area_filter = TRAIN_STATIONS.get(station)
    filtered = _filter_train_station(sigs, area_filter)

    if filtered:
        for sig in filtered[:5]:
            _render_signal_row(sig)
    else:
        st.markdown('<div class="ev-empty">Ei junia t\u00e4ll\u00e4 hetkell\u00e4</div>',
                    unsafe_allow_html=True)

    # VR-linkki
    st.link_button("VR radalla - saapuvat junat", "https://www.vr.fi/radalla",
                   use_container_width=True)
    return filtered


def _render_single_card(cat, sigs, mu, cnt):
    """Tavallinen tapahtumakortti."""
    bbg, bcol, btxt = _badge(mu, cnt, cat)

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
            tag_html = ""
            if detail.endswith("|SOLD"):
                detail = detail[:-5]
                tag_html = '<span class="ev-tag tag-sold">LOPPUUNMYYTY</span>'
            elif detail.endswith("|LTD"):
                detail = detail[:-4]
                tag_html = '<span class="ev-tag tag-ltd">Viim. liput</span>'
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

    # Linkit
    links = []
    seen = set()
    for sig in sigs[:5]:
        url = getattr(sig, "source_url", "")
        if not url or not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        lbl = _sig_title(sig)[:30] or "Avaa"
        links.append((lbl, url))
    if links:
        cols = st.columns(min(len(links), 2))
        for i, (lbl, url) in enumerate(links[:2]):
            with cols[i]:
                st.link_button(lbl, url, use_container_width=True)


def _render_signal_row(sig):
    """Renderoi yksi signaalirivi Streamlit-natiivina."""
    urg = getattr(sig, "urgency", 0)
    tm = _sig_time(sig)
    title = _sig_title(sig)
    detail = _sig_detail(sig)
    ucl = _ucls(urg)
    tag_html = ""
    if detail.endswith("|SOLD"):
        detail = detail[:-5]
        tag_html = '<span class="ev-tag tag-sold">LOPPUUNMYYTY</span>'
    elif detail.endswith("|LTD"):
        detail = detail[:-4]
        tag_html = '<span class="ev-tag tag-ltd">Viim. liput</span>'
    html = '<div class="ev-row">'
    if tm:
        html += '<span class="ev-time ' + ucl + '">' + tm + "</span>"
    html += '<div style="flex:1">'
    html += '<div class="ev-name">' + title[:65] + " " + tag_html + "</div>"
    if detail:
        html += '<div class="ev-detail">' + detail[:80] + "</div>"
    html += "</div></div>"
    st.markdown(html, unsafe_allow_html=True)


def _badge(mu, cnt, cat):
    if mu >= 7:
        return "rgba(255,75,75,0.3)", "#FF4B4B", "KRIITTINEN"
    if mu >= 5:
        return "rgba(255,215,0,0.3)", "#FFD700", "KORKEA"
    if cnt > 0:
        return "rgba(255,255,255,0.12)", cat["color"], str(cnt)
    return "rgba(255,255,255,0.05)", "#666", "-"


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
