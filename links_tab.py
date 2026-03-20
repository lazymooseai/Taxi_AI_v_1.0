# Links Tab Component
import streamlit as st

LINKS_CSS = """
<style>
.agent-section {
    background: #1a1d27;
    border-radius: 16px;
    padding: 16px;
    border: 1px solid #2a2d3d;
    margin-bottom: 14px;
}
.agent-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #2a2d3d;
    padding-bottom: 8px;
    margin-bottom: 12px;
}
.link-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 8px;
}
.link-card {
    background: #12151e;
    border: 1px solid #2a2d3d;
    border-radius: 10px;
    padding: 10px;
    text-decoration: none;
    color: #FAFAFA;
}
.link-card:hover {
    border-color: #00B4D8;
    background: #1e2130;
}
</style>
"""

def render_links_tab():
    """Render links tab"""
    st.markdown(LINKS_CSS, unsafe_allow_html=True)
    
    st.header("🔗 Quick Links & Agent Status")
    
    # Agent summary
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Agents", "7", status="running")
    with col2:
        st.metric("OK", "6", status="running")
    with col3:
        st.metric("Cached", "1", status="off")
    with col4:
        st.metric("Errors", "0", status="off")
    
    st.divider()
    
    # Agent sections
    agents = [
        {
            "name": "🚆 Trains (Digitraffic)",
            "status": "✓ OK",
            "links": [
                {"label": "Live Trains", "url": "https://rata.digitraffic.fi"},
                {"label": "HKI Station", "url": "https://rata.digitraffic.fi/stationHKI"},
                {"label": "VR Timetables", "url": "https://www.vr.fi"},
            ]
        },
        {
            "name": "✈️ Flights (Finavia)",
            "status": "✓ OK",
            "links": [
                {"label": "Helsinki Flights", "url": "https://www.finavia.fi"},
                {"label": "Arrivals", "url": "https://www.finavia.fi/en"},
                {"label": "Flightradar24", "url": "https://www.flightradar24.com/EFHK"},
            ]
        },
        {
            "name": "⛴️ Ferries (Averio)",
            "status": "✓ OK",
            "links": [
                {"label": "Averio Timetable", "url": "https://www.averio.fi"},
                {"label": "Viking Line", "url": "https://www.vikingline.com"},
                {"label": "Suomenlinna Ferry", "url": "https://www.hsl.fi"},
            ]
        },
        {
            "name": "🌤️ Weather (FMI)",
            "status": "✓ OK",
            "links": [
                {"label": "FMI Helsinki", "url": "https://www.ilmatieteenlaitos.fi/saa/helsinki"},
                {"label": "Radar", "url": "https://www.ilmatieteenlaitos.fi/saa/kartta"},
                {"label": "Forecast", "url": "https://www.ilmatieteenlaitos.fi"},
            ]
        },
    ]
    
    for agent in agents:
        st.markdown(f"<div class='agent-section'><div class='agent-header'><strong>{agent['name']}</strong><span>{agent['status']}</span></div>", unsafe_allow_html=True)
        
        cols = st.columns(len(agent['links']))
        for col, link in zip(cols, agent['links']):
            with col:
                st.markdown(f"[{link['label']}]({link['url']})")
        
        st.markdown("</div>", unsafe_allow_html=True)
