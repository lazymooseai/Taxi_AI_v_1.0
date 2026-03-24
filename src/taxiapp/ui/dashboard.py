# dashboard.py -- Helsinki Taxi AI v1.3
# Muutokset:
#   - Isommat fontit (alue 2.1rem, signaalit 0.95rem, kello 3.0rem)
#   - Swipe-karuselli kumpaankin suuntaan + piste-navigaatio + nuolet
#   - Matkustajamäärät näkyvissä (pax-badge)
#   - Selkeämpi korttien rakenne
#   - Tummempi, kontrastisempi tausta

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
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

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

DASHBOARD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #0a0c14 !important;
    font-family: 'Inter', sans-serif !important;
    color: #FAFAFA !important;
}

[data-baseweb="tab-list"] {
    position: fixed !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 9999 !important;
    background: #0e1019 !important;
    border-top: 1px solid #1e2235 !important;
    padding: 6px 0 !important;
    margin: 0 !important;
    width: 100% !important;
    justify-content: space-around !important;
    box-shadow: 0 -6px 24px rgba(0,0,0,0.5) !important;
}
[data-baseweb="tab"] {
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    padding: 8px 10px !important;
    color: #555577 !important;
    border: none !important;
    background: transparent !important;
    min-width: 52px !important;
}
[data-baseweb="tab"][aria-selected="true"] {
    color: #00C8F0 !important;
    background: rgba(0,200,240,0.08) !important;
    border-radius: 10px !important;
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
    font-size: 3.0rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: #FFFFFF;
    font-variant-numeric: tabular-nums;
    line-height: 1;
}
.top-bar-right { text-align: right; }
.top-bar-weather { font-size: 1.1rem; font-weight: 500; color: #CCDDEE; margin-bottom: 2px; }
.top-bar-location { font-size: 0.82rem; color: #00C8F0; margin-top: 4px; }

/* Karuselli */
.carousel-wrapper {
    position: relative;
    overflow: hidden;
    touch-action: pan-y;
    user-select: none;
    margin-bottom: 4px;
}
.carousel-track {
    display: flex;
    will-change: transform;
}
.carousel-slide {
    flex: 0 0 100%;
    width: 100%;
    padding: 0 2px;
    box-sizing: border-box;
}
.carousel-dots {
    display: flex;
    justify-content: center;
    gap: 8px;
    margin: 10px 0 4px;
}
.carousel-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #2a2d3d;
    cursor: pointer;
    transition: all 0.2s;
}
.carousel-dot.active { transform: scale(1.4); }
.dot-red  { background: #FF4B4B; }
.dot-gold { background: #FFD700; }
.dot-blue { background: #00C8F0; }
.carousel-arrow {
    position: absolute;
    top: 50%; transform: translateY(-50%);
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 50%;
    width: 36px; height: 36px;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; z-index: 10;
    font-size: 1.2rem; color: #AABBCC;
    transition: background 0.2s;
}
.carousel-arrow:hover { background: rgba(255,255,255,0.14); color: #fff; }
.carousel-arrow.left  { left: 6px; }
.carousel-arrow.right { right: 6px; }

/* Kortit */
.hotspot-card {
    border-radius: 18px;
    padding: 20px 22px 18px;
    overflow: hidden;
}
.card-red  { background: linear-gradient(145deg,#2a0808,#180303); border: 1px solid rgba(255,75,75,0.3); box-shadow: 0 4px 24px rgba(255,75,75,0.1); }
.card-gold { background: linear-gradient(145deg,#261c00,#140e00); border: 1px solid rgba(255,215,0,0.3); box-shadow: 0 4px 24px rgba(255,215,0,0.08); }
.card-blue { background: linear-gradient(145deg,#001826,#000c14); border: 1px solid rgba(0,200,240,0.25); box-shadow: 0 4px 24px rgba(0,200,240,0.07); }

.card-rank {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 0.72rem; font-weight: 800; letter-spacing: 0.1em;
    padding: 4px 12px; border-radius: 20px; margin-bottom: 12px;
    text-transform: uppercase;
}
.rank-red  { background: rgba(255,75,75,0.15);  color: #FF6B6B; border: 1px solid rgba(255,75,75,0.3); }
.rank-gold { background: rgba(255,215,0,0.15);  color: #FFD700; border: 1px solid rgba(255,215,0,0.3); }
.rank-blue { background: rgba(0,200,240,0.12);  color: #00C8F0; border: 1px solid rgba(0,200,240,0.25); }

.card-area {
    font-size: 2.1rem; font-weight: 800; line-height: 1.1;
    margin-bottom: 6px; letter-spacing: -0.02em; color: #FFFFFF;
}
.card-meta {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 14px; flex-wrap: wrap;
}
.card-score { font-size: 0.82rem; color: #667788; font-variant-numeric: tabular-nums; }
.pax-badge {
    font-size: 0.8rem; font-weight: 700;
    padding: 2px 10px; border-radius: 12px;
    background: rgba(255,255,255,0.06); color: #AABBCC;
    border: 1px solid rgba(255,255,255,0.1);
}
.card-signals { display: flex; flex-direction: column; gap: 4px; }
.signal-row {
    display: flex; align-items: flex-start; gap: 8px;
    font-size: 0.95rem; color: #D0DDEE; line-height: 1.45;
    padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.04);
}
.signal-row:last-child { border-bottom: none; }
.signal-dot { width: 6px; height: 6px; border-radius: 50%; margin-top: 7px; flex-shrink: 0; }

.disruption-banner {
    background: linear-gradient(90deg,#200808,#140303);
    border: 1px solid rgba(255,75,75,0.4);
    border-radius: 12px; padding: 10px 16px; margin-bottom: 12px;
    font-size: 0.9rem; font-weight: 500; color: #FF8080; line-height: 1.4;
}

.agent-bar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 10px 4px; margin-top: 4px; }
.agent-chip {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 0.72rem; padding: 3px 9px; border-radius: 20px; font-weight: 600;
}
.chip-ok    { background: rgba(33,197,93,0.12);  color: #21C55D; border: 1px solid rgba(33,197,93,0.2); }
.chip-error { background: rgba(255,75,75,0.12);  color: #FF6B6B; border: 1px solid rgba(255,75,75,0.2); }
.chip-dot   { width: 6px; height: 6px; border-radius: 50%; }
.cdot-ok  { background: #21C55D; }
.cdot-err { background: #FF6B6B; }

.stButton > button {
    background: #141827 !important; border: 1px solid #1e2235 !important;
    color: #CCDDEE !important; border-radius: 12px !important;
    font-family: 'Inter', sans-serif !important; font-size: 0.88rem !important;
    font-weight: 600 !important; padding: 8px 16px !important;
}
.stButton > button:hover { border-color: #00C8F0 !important; color: #00C8F0 !important; }
.stLinkButton > a {
    background: rgba(0,200,240,0.08) !important; border: 1px solid rgba(0,200,240,0.25) !important;
    color: #00C8F0 !important; border-radius: 12px !important;
    font-size: 0.84rem !important; font-weight: 600 !important;
    padding: 6px 14px !important; text-decoration: none !important;
}
.stLinkButton > a:hover { background: rgba(0,200,240,0.16) !important; }
div[data-testid="column"] { padding: 0 4px !important; }
.block-container {
    padding-top: 0.8rem !important;
    padding-bottom: 90px !important;
    max-width: 680px !important;
}
</style>
"""

# ---------------------------------------------------------------------------
# SWIPE JS
# ---------------------------------------------------------------------------

def _swipe_js(n: int) -> str:
    dot_colors = ["dot-red", "dot-gold", "dot-blue"]
    colors_js = str([dot_colors[i] if i < 3 else "dot-blue" for i in range(n)])
    return f"""
<script>
(function(){{
    const N={n}, COLORS={colors_js};
    let cur=0, sx=0, sy=0, st=0, drag=false, dx=0;
    const track=document.getElementById('tc-track');
    const dots=document.querySelectorAll('.c-dot');
    const la=document.getElementById('tc-left');
    const ra=document.getElementById('tc-right');
    if(!track)return;

    function goTo(i,smooth=true){{
        i=Math.max(0,Math.min(N-1,i)); cur=i;
        track.style.transition=smooth?'transform .35s cubic-bezier(.25,.46,.45,.94)':'none';
        track.style.transform=`translateX(-${{i*100}}%)`;
        dots.forEach((d,j)=>{{
            d.className='carousel-dot c-dot'+(j===i?' active '+COLORS[j]:'');
        }});
        if(la)la.style.opacity=i===0?'0.2':'1';
        if(ra)ra.style.opacity=i===N-1?'0.2':'1';
    }}

    const wrap=track.parentElement;
    wrap.addEventListener('touchstart',e=>{{
        sx=e.touches[0].clientX; sy=e.touches[0].clientY;
        st=Date.now(); drag=true; dx=0;
        track.style.transition='none';
    }},{{passive:true}});
    wrap.addEventListener('touchmove',e=>{{
        if(!drag)return;
        dx=e.touches[0].clientX-sx;
        const dy=e.touches[0].clientY-sy;
        if(Math.abs(dy)>Math.abs(dx)){{drag=false;return;}}
        const resist=(cur===0&&dx>0)||(cur===N-1&&dx<0)?0.28:1;
        track.style.transform=`translateX(calc(-${{cur*100}}% + ${{dx*resist}}px))`;
    }},{{passive:true}});
    wrap.addEventListener('touchend',()=>{{
        if(!drag)return; drag=false;
        const v=Math.abs(dx)/(Date.now()-st);
        const w=wrap.offsetWidth;
        const fast=v>0.35&&Math.abs(dx)>30;
        if(dx<-w*0.2||( fast&&dx<0))goTo(cur+1);
        else if(dx>w*0.2||(fast&&dx>0))goTo(cur-1);
        else goTo(cur);
        dx=0;
    }});
    document.addEventListener('keydown',e=>{{
        if(e.key==='ArrowRight')goTo(cur+1);
        if(e.key==='ArrowLeft') goTo(cur-1);
    }});
    if(la)la.addEventListener('click',()=>goTo(cur-1));
    if(ra)ra.addEventListener('click',()=>goTo(cur+1));
    dots.forEach((d,i)=>d.addEventListener('click',()=>goTo(i)));
    goTo(0,false);
}})();
</script>
"""

# ---------------------------------------------------------------------------
# APUFUNKTIOT
# ---------------------------------------------------------------------------

def _helsinki_time() -> datetime:
    import time as _t
    offset = 3 if _t.daylight else 2
    return datetime.now(timezone.utc) + timedelta(hours=offset)


def _urgency_label(urgency: int, idx: int) -> str:
    if urgency >= 9: return "🚨 YLIKIRJOITUS"
    if urgency >= 7: return "⚡ KRIITTINEN"
    labels = ["🔴 KORKEIN", "🥇 KULTAKOHDE", "🔵 ENNAKOIVA"]
    return labels[idx] if idx < 3 else "📍 HOTSPOT"


def _card_cls(idx: int, urgency: int) -> tuple[str, str]:
    if urgency >= 9 or idx == 0: return "card-red",  "rank-red"
    if idx == 1:                  return "card-gold", "rank-gold"
    return                               "card-blue", "rank-blue"


def _extract_pax(signals: list, reasons: list) -> Optional[int]:
    """Poimi matkustajamäärä reason/description-teksteistä."""
    texts = []
    for sig in signals:
        texts.append(str(getattr(sig, "reason", "") or ""))
        texts.append(str(getattr(sig, "description", "") or ""))
    for r in reasons:
        texts.append(str(r))
    for t in texts:
        m = re.search(r'(\d{3,5})\s*(?:matkustajaa|hlöä|pax|passengers)', t)
        if m:
            return int(m.group(1))
    return None


def _dot_color(urgency: int) -> str:
    if urgency >= 7: return "#FF6B6B"
    if urgency >= 5: return "#FFD700"
    if urgency >= 3: return "#00C8F0"
    return "#445566"


# ---------------------------------------------------------------------------
# KORTTIEN HTML
# ---------------------------------------------------------------------------

def _card_html(hotspot: object, idx: int) -> str:
    card_cls, rank_cls = _card_cls(idx, getattr(hotspot, "urgency", 2))
    urgency = getattr(hotspot, "urgency", 2)
    score   = getattr(hotspot, "score", 0.0)
    area    = getattr(hotspot, "area", "?").replace("_", " ").title()
    signals = getattr(hotspot, "signals", [])
    reasons = getattr(hotspot, "reasons", [])

    pax = _extract_pax(signals, reasons)
    pax_html = f'<span class="pax-badge">👥 {pax:,} matkustajaa</span>'.replace(",", "\u202f") if pax and pax > 100 else ""

    # Signaalit tai reasons
    rows = ""
    if reasons:
        for r in reasons[:5]:
            rows += f'<div class="signal-row"><span class="signal-dot" style="background:#557788"></span><span>{str(r)[:100]}</span></div>'
    else:
        for sig in signals[:5]:
            txt = str(getattr(sig, "reason", "") or getattr(sig, "description", "") or "")[:100]
            urg = getattr(sig, "urgency", 2)
            if txt:
                rows += f'<div class="signal-row"><span class="signal-dot" style="background:{_dot_color(urg)}"></span><span>{txt}</span></div>'

    rank_lbl = _urgency_label(urgency, idx)
    return (
        f'<div class="hotspot-card {card_cls}">'
        f'<div class="card-rank {rank_cls}">{rank_lbl}</div>'
        f'<div class="card-area">{area}</div>'
        f'<div class="card-meta"><span class="card-score">Pisteet {round(score,1)}</span>{pax_html}</div>'
        f'<div class="card-signals">{rows}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# KARUSELLI
# ---------------------------------------------------------------------------

def _render_carousel(hotspots: list) -> None:
    n = min(len(hotspots), 3)
    if n == 0:
        st.info("Ladataan agentteja...")
        return

    slides = "".join(
        f'<div class="carousel-slide">{_card_html(h, i)}</div>'
        for i, h in enumerate(hotspots[:n])
    )
    dots = "".join(
        f'<div class="carousel-dot c-dot" id="cdot-{i}"></div>'
        for i in range(n)
    )

    st.markdown(
        f'<div class="carousel-wrapper">'
        f'  <div class="carousel-track" id="tc-track">{slides}</div>'
        f'  <div class="carousel-arrow left" id="tc-left">&#8249;</div>'
        f'  <div class="carousel-arrow right" id="tc-right">&#8250;</div>'
        f'</div>'
        f'<div class="carousel-dots">{dots}</div>'
        + _swipe_js(n),
        unsafe_allow_html=True,
    )

    # Linkit expander-muodossa
    for i, hotspot in enumerate(hotspots[:n]):
        signals = getattr(hotspot, "signals", [])
        seen: set[str] = set()
        links: list[tuple[str, str]] = []
        for sig in signals:
            url = getattr(sig, "source_url", None)
            if url and url.startswith("http") and url not in seen:
                seen.add(url)
                lbl = str(getattr(sig, "reason", "") or "")[:26].strip() or "Avaa"
                links.append((lbl, url))
        if links:
            area = getattr(hotspot, "area", "").replace("_", " ").title()
            with st.expander(f"🔗 Linkit — {area}", expanded=False):
                cols = st.columns(min(len(links), 3))
                for j, (lbl, url) in enumerate(links[:3]):
                    with cols[j % len(cols)]:
                        st.link_button("→ " + lbl[:22], url, use_container_width=True)


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
        if loc and loc.nearest_area:
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
    short = {"TrainAgent":"Junat","FlightAgent":"Lennot","FerryAgent":"Lautat",
             "WeatherAgent":"Sää","EventsAgent":"Tapahtumat",
             "DisruptionAgent":"Häiriöt","SocialMediaAgent":"Uutiset"}
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

    if hotspots is None or agent_results is None:
        cache = st.session_state.get("hotspot_cache")
        if cache and isinstance(cache, (tuple, list)) and len(cache) >= 2:
            hotspots      = cache[0] if hotspots is None else hotspots
            agent_results = cache[1] if agent_results is None else agent_results
        else:
            hotspots      = hotspots or []
            agent_results = agent_results or []

    if LOCATION_AVAILABLE and hotspots:
        loc = get_location_from_session()
        if loc:
            hotspots = apply_location_boost(hotspots, driver_lat=loc.lat, driver_lon=loc.lon)

    _render_top_bar(agent_results)

    if isinstance(agent_results, dict):
        dr = agent_results.get("DisruptionAgent")
    else:
        dr = next((r for r in (agent_results or []) if getattr(r, "agent_name", "") == "DisruptionAgent"), None)
    if dr and getattr(dr, "ok", False):
        for sig in getattr(dr, "signals", [])[:2]:
            if getattr(sig, "urgency", 0) >= 7:
                reason = str(getattr(sig, "reason", "") or getattr(sig, "description", ""))
                st.markdown(f'<div class="disruption-banner">⚠️ {reason}</div>', unsafe_allow_html=True)

    if LOCATION_AVAILABLE:
        with st.expander("📍 Sijainti (GPS)", expanded=False):
            render_location_widget()

    if hotspots:
        st.session_state["ceo_hotspots"] = hotspots

    _render_carousel(hotspots)
    _render_agent_status(agent_results)

    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        if st.button("🔄 Päivitä nyt", use_container_width=True):
            for k in ("hotspot_cache", "hotspot_ts"):
                st.session_state.pop(k, None)
            st.rerun()
