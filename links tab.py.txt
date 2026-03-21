# links_tab.py — Helsinki Taxi AI
# Linkit-välilehti: agenttistatus ja pikakäyttölinkit

from __future__ import annotations
from datetime import datetime, timezone
import streamlit as st

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
LINKS_CSS = """
<style>
.agent-section {
    background: #1a1d27;
    border-radius: 16px;
    padding: 0;
    margin-bottom: 14px;
    border: 1px solid #2a2d3d;
    overflow: hidden;
}
.agent-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #2a2d3d;
    padding: 14px 18px 10px;
}
.agent-name { font-size: 1.05rem; font-weight: 700; }
.agent-desc { font-size: 0.75rem; color: #888899; margin-top: 2px; }
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
}
.status-ok       { background: #21C55D22; color: #21C55D; }
.status-cached   { background: #88889922; color: #888899; border: 1px solid #888899; }
.status-error    { background: #FF4B4B22; color: #FF4B4B; }
.status-disabled { background: #2a2d3d;   color: #888899; }
.link-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 8px;
    padding: 14px 18px;
}
.link-card {
    background: #12151e;
    border-radius: 10px;
    padding: 10px 14px;
    border: 1px solid #2a2d3d;
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: border-color 0.15s, background 0.15s;
}
.link-card:hover { background: #1e2130; border-color: #00B4D8; }
.link-icon { font-size: 1.3rem; flex-shrink: 0; }
.link-text {
    font-size: 0.82rem;
    color: #FAFAFA;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
</style>
"""

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
AGENTS = [
    {
        "name": "🚆 Trains (Digitraffic)",
        "color": "#6C9FD4",
        "status": "ok",
        "links": [
            {"icon": "🚆", "label": "Digitraffic live-junat",  "url": "https://rata.digitraffic.fi"},
            {"icon": "🗺️", "label": "VR aikataulut",           "url": "https://www.vr.fi"},
            {"icon": "⚠️", "label": "Junahäiriöt",             "url": "https://www.vr.fi/asiakaspalvelu/hairiot"},
        ],
    },
    {
        "name": "✈️ Flights (Finavia)",
        "color": "#7EC8E3",
        "status": "ok",
        "links": [
            {"icon": "✈️", "label": "Finavia — saapuvat",      "url": "https://www.finavia.fi/fi/lentokentat/helsinki-vantaa/lennot/saapuvat"},
            {"icon": "📡", "label": "Flightradar24 EFHK",      "url": "https://www.flightradar24.com/EFHK"},
            {"icon": "🛠️", "label": "Finavia API docs",        "url": "https://developer.finavia.fi"},
        ],
    },
    {
        "name": "⛴️ Ferries (Averio)",
        "color": "#5BA4CF",
        "status": "ok",
        "links": [
            {"icon": "⛴️", "label": "Averio aikataulu",        "url": "https://www.averio.fi/aikataulu"},
            {"icon": "🚢", "label": "Viking Line HKI",         "url": "https://www.vikingline.com/fi"},
            {"icon": "🛳️", "label": "Tallink Silja",           "url": "https://www.tallinksilja.fi"},
            {"icon": "🏝️", "label": "Suomenlinna-lautta HSL",  "url": "https://www.hsl.fi/reitit/suomenlinna"},
        ],
    },
    {
        "name": "🌤️ Weather (FMI)",
        "color": "#89CFF0",
        "status": "ok",
        "links": [
            {"icon": "🌤️", "label": "FMI Sää Helsinki",        "url": "https://www.ilmatieteenlaitos.fi/saa/helsinki"},
            {"icon": "🌧️", "label": "Sadetutka (animaatio)",   "url": "https://www.ilmatieteenlaitos.fi/saa/kartta/suomi/sateen-intensiteetti"},
            {"icon": "💨", "label": "Tuulikartta",              "url": "https://www.ilmatieteenlaitos.fi/saa/kartta/suomi/tuulet"},
        ],
    },
    {
        "name": "⚠️ Disruptions (HSL/Fintraffic)",
        "color": "#FF8C00",
        "status": "ok",
        "links": [
            {"icon": "🚌", "label": "HSL häiriötiedotteet",    "url": "https://www.hsl.fi/fi/hairiot"},
            {"icon": "🚦", "label": "Fintraffic liikennetil.", "url": "https://liikennetilanne.fintraffic.fi"},
            {"icon": "🗺️", "label": "HSL reittiopas",         "url": "https://reittiopas.hsl.fi"},
        ],
    },
    {
        "name": "🎭 Events (Hel.fi / Liput.fi)",
        "color": "#A78BFA",
        "status": "ok",
        "links": [
            {"icon": "🎭", "label": "Hel.fi tapahtumat",       "url": "https://www.hel.fi/fi/tapahtumat"},
            {"icon": "🎟️", "label": "Liput.fi",               "url": "https://www.liput.fi"},
            {"icon": "🎫", "label": "Ticketmaster FI",         "url": "https://www.ticketmaster.fi"},
        ],
    },
    {
        "name": "📰 News (YLE / IS)",
        "color": "#34D399",
        "status": "ok",
        "links": [
            {"icon": "📺", "label": "Yle Uutiset Helsinki",    "url": "https://yle.fi/uutiset/osasto/helsinki"},
            {"icon": "📱", "label": "MTV Uutiset",             "url": "https://www.mtvuutiset.fi"},
            {"icon": "📰", "label": "Ilta-Sanomat",            "url": "https://www.is.fi"},
        ],
    },
]

# ---------------------------------------------------------------------------
# Apufunktiot
# ---------------------------------------------------------------------------
def _status_pill(status: str) -> str:
    cfg = {
        "ok":       ("status-ok",       "✓ OK"),
        "cached":   ("status-cached",   "⟳ Välimuisti"),
        "error":    ("status-error",    "✗ Virhe"),
        "disabled": ("status-disabled", "– Pois"),
    }
    cls, label = cfg.get(status, ("status-disabled", status))
    return f"<span class='status-pill {cls}'>{label}</span>"


def _render_agent_section(agent: dict) -> None:
    color = agent["color"]
    html_header = (
        f"<div class='agent-section' style='border-left:4px solid {color}'>"
        f"  <div class='agent-header'>"
        f"    <div><div class='agent-name'>{agent['name']}</div></div>"
        f"    {_status_pill(agent['status'])}"
        f"  </div>"
    )
    st.markdown(html_header, unsafe_allow_html=True)

    links_html = "<div class='link-grid'>"
    for lnk in agent["links"]:
        links_html += (
            f"<a class='link-card' href='{lnk['url']}' target='_blank'>"
            f"<span class='link-icon'>{lnk['icon']}</span>"
            f"<span class='link-text'>{lnk['label']}</span></a>"
        )
    links_html += "</div></div>"
    st.markdown(links_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Pääfunktio
# ---------------------------------------------------------------------------
def render_links_tab() -> None:
    """Linkit-välilehden pääfunktio. Kutsutaan app.py:stä."""
    st.markdown(LINKS_CSS, unsafe_allow_html=True)

    st.header("🔗 Quick Links & Agent Status")

    # KORJATTU: st.metric() ei hyväksy status=-parametria — poistettu kokonaan
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Agentit", len(AGENTS))
    with col2:
        st.metric("OK", len(AGENTS))
    with col3:
        st.metric("Välimuisti", 0)
    with col4:
        st.metric("Virheet", 0)

    st.divider()

    # Agenttiosiot
    for agent in AGENTS:
        _render_agent_section(agent)

    # Aikaleima
    now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
    st.markdown(
        f"<div style='font-size:0.72rem;color:#888899;text-align:right;margin-top:8px'>"
        f"Viimeisin päivitys: {now_str}</div>",
        unsafe_allow_html=True,
    )
