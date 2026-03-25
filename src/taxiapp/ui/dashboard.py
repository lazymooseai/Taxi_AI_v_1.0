# dashboard.py -- Helsinki Taxi AI v1.4
# KRIITTINEN KORJAUS:
#   - st.markdown() EI aja <script>-tageja Streamlitissa
#   - Karuselli nyt st.components.v1.html() -> oma iframe -> JS toimii
#   - Tab-CSS position:fixed poistettu -> valilehdet toimivat taas
#   - Ferries-aluksen nimi + matkustajat nakyvat kortilla

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

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
# CSS -- EI position:fixed tab-listille (rikkoi valilehdet)
# ---------------------------------------------------------------------------

DASHBOARD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #0a0c14 !important;
    font-family: 'Inter', sans-serif !important;
    color: #FAFAFA !important;
}

.top-bar {
    background: linear-gradient(135deg, #0e1019 0%, #141827 100%);
    border: 1px solid #1e2235;
    border-radius: 16px;
    padding: 16px 22px;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.top-bar-clock {
    font-size: 2.8rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: #FFFFFF;
    font-variant-numeric: tabular-nums;
    line-height: 1;
}
.top-bar-right { text-align: right; }
.top-bar-weather { font-size: 1.05rem; font-weight: 500; color: #CCDDEE; }
.top-bar-location { font-size: 0.8rem; color: #00C8F0; margin-top: 4px; }

.disruption-banner {
    background: linear-gradient(90deg, #200808, #140303);
    border: 1px solid rgba(255,75,75,0.4);
    border-radius: 12px;
    padding: 10px 16px;
    margin-bottom: 12px;
    font-size: 0.9rem;
    font-weight: 500;
    color: #FF8080;
    line-height: 1.4;
}
.agent-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    padding: 8px 4px;
    margin-top: 4px;
}
.agent-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.72rem;
    padding: 3px 9px;
    border-radius: 20px;
    font-weight: 600;
}
.chip-ok    { background: rgba(33,197,93,0.12);  color: #21C55D; border: 1px solid rgba(33,197,93,0.2); }
.chip-error { background: rgba(255,75,75,0.12);  color: #FF6B6B; border: 1px solid rgba(255,75,75,0.2); }
.chip-dot   { width: 6px; height: 6px; border-radius: 50%; }
.cdot-ok  { background: #21C55D; }
.cdot-err { background: #FF6B6B; }

.stButton > button {
    background: #141827 !important;
    border: 1px solid #1e2235 !important;
    color: #CCDDEE !important;
    border-radius: 12px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
}
.stButton > button:hover { border-color: #00C8F0 !important; color: #00C8F0 !important; }
.stLinkButton > a {
    background: rgba(0,200,240,0.08) !important;
    border: 1px solid rgba(0,200,240,0.25) !important;
    color: #00C8F0 !important;
    border-radius: 12px !important;
    font-size: 0.84rem !important;
    font-weight: 600 !important;
    padding: 6px 14px !important;
    text-decoration: none !important;
}
.stLinkButton > a:hover { background: rgba(0,200,240,0.16) !important; }
div[data-testid="column"] { padding: 0 4px !important; }
.block-container {
    padding-top: 0.8rem !important;
    padding-bottom: 90px !important;
    max-width: 680px !important;
}

/* TAB-PALKKI: kiinteä alaosaan, klikattava */
[data-baseweb="tab-list"] {
    position: fixed !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 99999 !important;
    background: #0a0c14 !important;
    border-top: 1px solid #1e2235 !important;
    padding: 6px 0 env(safe-area-inset-bottom, 0px) !important;
    margin: 0 !important;
    width: 100% !important;
    display: flex !important;
    justify-content: space-around !important;
    box-shadow: 0 -4px 20px rgba(0,0,0,0.6) !important;
    pointer-events: auto !important;
}
[data-baseweb="tab"] {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    padding: 6px 8px !important;
    color: #445566 !important;
    border: none !important;
    background: transparent !important;
    min-width: 48px !important;
    cursor: pointer !important;
    pointer-events: auto !important;
    -webkit-tap-highlight-color: transparent !important;
    touch-action: manipulation !important;
}
[data-baseweb="tab"][aria-selected="true"] {
    color: #00C8F0 !important;
    background: rgba(0,200,240,0.08) !important;
    border-radius: 10px !important;
}
[data-baseweb="tab"]:hover {
    color: #00C8F0 !important;
}
/* Varmista ettei iframe peitä tableja */
iframe {
    pointer-events: auto !important;
}
</style>
"""

# ---------------------------------------------------------------------------
# KARUSELLI HTML + JS -- renderoidaan st.components.v1.html():lla
# JS toimii vain iframessa, ei st.markdown():ssa
# ---------------------------------------------------------------------------

def _build_carousel_html(cards: list[dict]) -> str:
    """
    Rakenna koko karusellikomponentti yhtenä HTML-merkkijonona.
    Renderoidaan st.components.v1.html():lla jotta JS toimii.

    cards = [{"html": "...", "color": "#FF4B4B", "links": [...]}]
    """
    n = len(cards)
    if n == 0:
        return "<p style='color:#888;padding:20px'>Ei dataa</p>"

    dot_colors = ["#FF4B4B", "#FFD700", "#00C8F0"]

    slides_html = ""
    for i, card in enumerate(cards):
        slides_html += f'<div class="slide">{card["html"]}</div>\n'

    dots_html = ""
    for i in range(n):
        col = dot_colors[i] if i < 3 else "#00C8F0"
        dots_html += f'<div class="dot" id="dot{i}" style="background:{col};opacity:0.3" onclick="goTo({i})"></div>\n'

    return f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    background: #0a0c14;
    font-family: 'Inter', -apple-system, sans-serif;
    color: #FAFAFA;
    overflow-x: hidden;
}}
.carousel {{
    position: relative;
    overflow: hidden;
    width: 100%;
    touch-action: pan-y;
    user-select: none;
}}
.track {{
    display: flex;
    transition: transform .35s cubic-bezier(.25,.46,.45,.94);
    will-change: transform;
}}
.slide {{
    flex: 0 0 100%;
    width: 100%;
    padding: 4px 6px;
    box-sizing: border-box;
}}
.card {{
    border-radius: 16px;
    padding: 20px 22px 18px;
    overflow: hidden;
}}
.card-red  {{ background: linear-gradient(145deg,#2a0808,#180303); border: 1px solid rgba(255,75,75,0.35); box-shadow: 0 4px 20px rgba(255,75,75,0.1); }}
.card-gold {{ background: linear-gradient(145deg,#261c00,#140e00); border: 1px solid rgba(255,215,0,0.35); box-shadow: 0 4px 20px rgba(255,215,0,0.08); }}
.card-blue {{ background: linear-gradient(145deg,#001826,#000c14); border: 1px solid rgba(0,200,240,0.25); box-shadow: 0 4px 20px rgba(0,200,240,0.07); }}
.rank {{
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 0.7rem; font-weight: 800; letter-spacing: 0.1em;
    padding: 3px 11px; border-radius: 20px; margin-bottom: 12px;
    text-transform: uppercase;
}}
.rank-red  {{ background: rgba(255,75,75,0.15);  color: #FF6B6B; border: 1px solid rgba(255,75,75,0.3); }}
.rank-gold {{ background: rgba(255,215,0,0.15);  color: #FFD700; border: 1px solid rgba(255,215,0,0.3); }}
.rank-blue {{ background: rgba(0,200,240,0.12);  color: #00C8F0; border: 1px solid rgba(0,200,240,0.25); }}
.area {{
    font-size: 2.0rem; font-weight: 800; line-height: 1.1;
    margin-bottom: 6px; letter-spacing: -0.02em; color: #FFFFFF;
}}
.meta {{
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 12px; flex-wrap: wrap;
}}
.score {{ font-size: 0.8rem; color: #667788; }}
.pax {{
    font-size: 0.78rem; font-weight: 700;
    padding: 2px 9px; border-radius: 12px;
    background: rgba(255,255,255,0.06); color: #AABBCC;
    border: 1px solid rgba(255,255,255,0.1);
}}
.signals {{ display: flex; flex-direction: column; gap: 3px; }}
.sig-row {{
    display: flex; align-items: flex-start; gap: 7px;
    font-size: 0.93rem; color: #D0DDEE; line-height: 1.4;
    padding: 4px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}}
.sig-row:last-child {{ border-bottom: none; }}
.sig-dot {{
    width: 6px; height: 6px; border-radius: 50%;
    margin-top: 6px; flex-shrink: 0;
}}
/* Dots */
.dots {{
    display: flex; justify-content: center;
    gap: 8px; padding: 12px 0 4px;
}}
.dot {{
    width: 9px; height: 9px; border-radius: 50%;
    cursor: pointer; transition: all .2s;
}}
.dot.active {{ opacity: 1 !important; transform: scale(1.35); }}
/* Arrows */
.arrow {{
    position: absolute; top: 50%; transform: translateY(-50%);
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 50%; width: 34px; height: 34px;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; z-index: 5; color: #AABBCC; font-size: 1.1rem;
    transition: background .2s;
}}
.arrow:hover {{ background: rgba(255,255,255,0.12); }}
.arrow.left  {{ left: 4px; }}
.arrow.right {{ right: 4px; }}
</style>
</head>
<body>
<div class="carousel" id="car">
    <div class="track" id="track">
        {slides_html}
    </div>
    <div class="arrow left"  onclick="goTo(cur-1)">&#8249;</div>
    <div class="arrow right" onclick="goTo(cur+1)">&#8250;</div>
</div>
<div class="dots" id="dots">
    {dots_html}
</div>
<script>
const N={n}, track=document.getElementById('track');
const dots=document.querySelectorAll('.dot');
let cur=0, sx=0, sy=0, st=0, dx=0, active=false;

function goTo(i, smooth=true) {{
    i = Math.max(0, Math.min(N-1, i));
    cur = i;
    track.style.transition = smooth ? 'transform .35s cubic-bezier(.25,.46,.45,.94)' : 'none';
    track.style.transform = 'translateX(-' + (i*100) + '%)';
    dots.forEach((d,j) => d.classList.toggle('active', j===i));
}}

const car = document.getElementById('car');
car.addEventListener('touchstart', e=>{{
    sx=e.touches[0].clientX; sy=e.touches[0].clientY;
    st=Date.now(); dx=0; active=true;
    track.style.transition='none';
}},{{passive:true}});
car.addEventListener('touchmove', e=>{{
    if(!active) return;
    dx=e.touches[0].clientX-sx;
    const dy=e.touches[0].clientY-sy;
    if(Math.abs(dy)>Math.abs(dx)){{ active=false; return; }}
    const r=(cur===0&&dx>0)||(cur===N-1&&dx<0)?0.25:1;
    track.style.transform='translateX(calc(-'+(cur*100)+'% + '+(dx*r)+'px))';
}},{{passive:true}});
car.addEventListener('touchend', ()=>{{
    if(!active) return; active=false;
    const v=Math.abs(dx)/(Date.now()-st);
    const w=car.offsetWidth;
    if(dx<-w*0.2||(v>0.35&&dx<0)) goTo(cur+1);
    else if(dx>w*0.2||(v>0.35&&dx>0)) goTo(cur-1);
    else goTo(cur);
}});
document.addEventListener('keydown', e=>{{
    if(e.key==='ArrowRight') goTo(cur+1);
    if(e.key==='ArrowLeft')  goTo(cur-1);
}});
goTo(0, false);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# APUFUNKTIOT
# ---------------------------------------------------------------------------

def _helsinki_time() -> datetime:
    import time as _t
    offset = 3 if _t.daylight else 2
    return datetime.now(timezone.utc) + timedelta(hours=offset)


def _urgency_label(urgency: int, idx: int) -> str:
    if urgency >= 9: return "YLIKIRJOITUS"
    if urgency >= 7: return "KRIITTINEN"
    return ["KORKEIN", "KULTAKOHDE", "ENNAKOIVA"][idx] if idx < 3 else "HOTSPOT"


def _card_cls(idx: int, urgency: int) -> tuple[str, str]:
    if urgency >= 9 or idx == 0: return "card-red",  "rank-red"
    if idx == 1:                  return "card-gold", "rank-gold"
    return                               "card-blue", "rank-blue"


def _dot_color(urgency: int) -> str:
    if urgency >= 7: return "#FF6B6B"
    if urgency >= 5: return "#FFD700"
    if urgency >= 3: return "#00C8F0"
    return "#445566"


def _extract_pax(signals: list, reasons: list) -> Optional[int]:
    texts = [str(getattr(s, "reason", "") or "") + str(getattr(s, "description", "") or "") for s in signals]
    texts += [str(r) for r in reasons]
    for t in texts:
        m = re.search(r'(\d{3,5})\s*(?:matkustajaa|hlöä|pax)', t)
        if m:
            return int(m.group(1))
    return None


def _build_card_html(hotspot: object, idx: int) -> str:
    """Rakenna yhden hotspot-kortin HTML (menee karusellin slideen)."""
    card_cls, rank_cls = _card_cls(idx, getattr(hotspot, "urgency", 2))
    urgency = getattr(hotspot, "urgency", 2)
    score   = getattr(hotspot, "score", 0.0)
    area    = getattr(hotspot, "area", "?").replace("_", " ").title()
    signals = getattr(hotspot, "signals", [])
    reasons = getattr(hotspot, "reasons", [])

    rank_icons = ["", "", ""]
    rank_lbl = rank_icons[idx] if idx < 3 else ""
    rank_lbl += " " + _urgency_label(urgency, idx)
    if urgency >= 9: rank_lbl = " " + _urgency_label(urgency, idx)
    if urgency >= 7 and urgency < 9: rank_lbl = " " + _urgency_label(urgency, idx)

    pax = _extract_pax(signals, reasons)
    pax_html = f'<span class="pax"> {pax:,} matkustajaa</span>'.replace(",", "\u202f") if pax and pax > 100 else ""

    rows = ""
    if reasons:
        for r in reasons[:5]:
            rows += f'<div class="sig-row"><span class="sig-dot" style="background:#557788"></span><span>{str(r)[:110]}</span></div>'
    else:
        for sig in signals[:5]:
            txt = str(getattr(sig, "reason", "") or getattr(sig, "description", "") or "")[:110]
            urg = getattr(sig, "urgency", 2)
            if txt:
                rows += f'<div class="sig-row"><span class="sig-dot" style="background:{_dot_color(urg)}"></span><span>{txt}</span></div>'

    return (
        f'<div class="card {card_cls}">'
        f'<div class="rank {rank_cls}">{rank_lbl}</div>'
        f'<div class="area">{area}</div>'
        f'<div class="meta"><span class="score">Pisteet {round(score,1)}</span>{pax_html}</div>'
        f'<div class="signals">{rows}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# YLAPALKKI
# ---------------------------------------------------------------------------

def _render_top_bar(agent_results) -> None:
    now_str = _helsinki_time().strftime("%H:%M")
    weather_html = ""
    if isinstance(agent_results, dict):
        wr = agent_results.get("WeatherAgent")
    else:
        wr = next((r for r in (agent_results or []) if getattr(r, "agent_name", "") == "WeatherAgent"), None)
    if wr and getattr(wr, "ok", False):
        sigs = getattr(wr, "signals", [])
        if sigs:
            desc = str(getattr(sigs[0], "reason", "") or getattr(sigs[0], "description", ""))
            weather_html = f'<div class="top-bar-weather">{desc}</div>'
    location_html = ""
    if LOCATION_AVAILABLE:
        loc = get_location_from_session()
        if loc and getattr(loc, "nearest_area", None):
            rec = get_smart_recommendation_text(loc.lat, loc.lon, st.session_state.get("ceo_hotspots", []))
            location_html = f'<div class="top-bar-location">{rec}</div>'
    st.markdown(
        f'<div class="top-bar">'
        f'<div class="top-bar-clock">{now_str}</div>'
        f'<div class="top-bar-right">{weather_html}{location_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# AGENTTISTATUS
# ---------------------------------------------------------------------------

def _render_agent_status(agent_results) -> None:
    items = (
        agent_results.items() if isinstance(agent_results, dict)
        else [(getattr(r, "agent_name", "?"), r) for r in (agent_results or [])]
    )
    short = {
        "TrainAgent": "Junat", "FlightAgent": "Lennot", "FerryAgent": "Lautat",
        "WeatherAgent": "Saa", "EventsAgent": "Tapahtumat",
        "DisruptionAgent": "Hairiot", "SocialMediaAgent": "Uutiset",
    }
    chips = ""
    for name, result in items:
        if result is None: continue
        ok  = getattr(result, "ok", False)
        n   = len(getattr(result, "signals", []))
        lbl = short.get(str(name), str(name)[:8])
        cls = "chip-ok" if ok else "chip-error"
        dot = "cdot-ok"  if ok else "cdot-err"
        chips += f'<span class="agent-chip {cls}"><span class="chip-dot {dot}"></span>{lbl} {n}</span>'
    st.markdown(f'<div class="agent-bar">{chips}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# PAARUNKTIO
# ---------------------------------------------------------------------------

def render_dashboard(hotspots=None, agent_results=None, refresh_callback=None) -> None:
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)

    # Hae data
    if hotspots is None or agent_results is None:
        cache = st.session_state.get("hotspot_cache")
        if cache and isinstance(cache, (tuple, list)) and len(cache) >= 2:
            hotspots      = cache[0] if hotspots is None else hotspots
            agent_results = cache[1] if agent_results is None else agent_results
        else:
            hotspots      = hotspots or []
            agent_results = agent_results or []

    # Sijaintiboosteri
    if LOCATION_AVAILABLE and hotspots:
        loc = get_location_from_session()
        if loc:
            hotspots = apply_location_boost(hotspots, driver_lat=loc.lat, driver_lon=loc.lon)

    # Ylapalkki
    _render_top_bar(agent_results)

    # Hairiosbanneri
    if isinstance(agent_results, dict):
        dr = agent_results.get("DisruptionAgent")
    else:
        dr = next((r for r in (agent_results or []) if getattr(r, "agent_name", "") == "DisruptionAgent"), None)
    if dr and getattr(dr, "ok", False):
        for sig in getattr(dr, "signals", [])[:2]:
            if getattr(sig, "urgency", 0) >= 7:
                reason = str(getattr(sig, "reason", "") or getattr(sig, "description", ""))
                st.markdown(f'<div class="disruption-banner"> {reason}</div>', unsafe_allow_html=True)

    # GPS
    if LOCATION_AVAILABLE:
        with st.expander(" Sijainti (GPS)", expanded=False):
            render_location_widget()

    if hotspots:
        st.session_state["ceo_hotspots"] = hotspots

    # Karuselli -- st.components.v1.html() jotta JS toimii
    n = min(len(hotspots), 3)
    if n == 0:
        st.info("Ladataan agentteja...")
    else:
        cards = [
            {"html": _build_card_html(h, i), "color": ["#FF4B4B","#FFD700","#00C8F0"][i]}
            for i, h in enumerate(hotspots[:n])
        ]
        carousel_html = _build_carousel_html(cards)
        # Korkeus: approx 320px kortille + 50px dotsille
        components.html(carousel_html, height=390, scrolling=False)

        # Linkit Streamlit-komponentteina karusellin alla
        for i, hotspot in enumerate(hotspots[:n]):
            signals = getattr(hotspot, "signals", [])
            seen: set[str] = set()
            links = []
            for sig in signals:
                url = getattr(sig, "source_url", None)
                if url and url.startswith("http") and url not in seen:
                    seen.add(url)
                    lbl = str(getattr(sig, "reason", "") or "")[:24].strip() or "Avaa"
                    links.append((lbl, url))
            if links:
                area = getattr(hotspot, "area", "").replace("_"," ").title()
                with st.expander(f" Linkit -- {area}", expanded=False):
                    cols = st.columns(min(len(links), 3))
                    for j, (lbl, url) in enumerate(links[:3]):
                        with cols[j % len(cols)]:
                            st.link_button("-> " + lbl[:20], url, use_container_width=True)

    # Agenttistatus
    _render_agent_status(agent_results)

    # Paivita-nappi
    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        if st.button(" Paivita nyt", use_container_width=True):
            for k in ("hotspot_cache", "hotspot_ts"):
                st.session_state.pop(k, None)
            st.rerun()
