# Main Dashboard Component for Helsinki Taxi AI
import streamlit as st
from datetime import datetime, timezone

DASHBOARD_CSS = """
<style>
.hotspot-card {
    background: #1a1d27;
    border-radius: 16px;
    padding: 20px;
    border-left: 5px solid;
    min-height: 180px;
    margin-bottom: 12px;
}
.card-red { border-left-color: #FF4B4B; }
.card-gold { border-left-color: #FFD700; }
.card-blue { border-left-color: #00B4D8; }
.card-area {
    font-size: 1.6rem;
    font-weight: 700;
    margin-bottom: 8px;
}
.taxi-header {
    background: linear-gradient(135deg, #0e1117 0%, #1a1d27 100%);
    border-bottom: 2px solid #2a2d3d;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.taxi-clock {
    font-size: 2.8rem;
    font-weight: 700;
    color: #FAFAFA;
}
</style>
"""

def render_dashboard():
    """Render main dashboard tab"""
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)
    
    # Header with clock and weather
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(f"### 🚕 Real-time Hotspots", unsafe_allow_html=True)
    with col2:
        st.metric("Status", "Active", "✓")
    with col3:
        now = datetime.now(timezone.utc).strftime("%H:%M")
        st.metric("Time", now)
    
    st.divider()
    
    # Three hotspot cards
    cols = st.columns(3, gap="medium")
    
    hotspots = [
        {"area": "Airport", "score": 8.5, "label": "CRITICAL", "color": "red", "emoji": "🔴"},
        {"area": "Central Station", "score": 6.2, "label": "HIGH", "color": "gold", "emoji": "🟡"},
        {"area": "Pasila Events", "score": 4.8, "label": "PREDICTIVE", "color": "blue", "emoji": "🔵"},
    ]
    
    for col, hotspot in zip(cols, hotspots):
        with col:
            st.markdown(f"""
            <div class="hotspot-card card-{hotspot['color']}">
                <div style="font-size: 0.7rem; opacity: 0.7; margin-bottom: 4px;">{hotspot['emoji']} {hotspot['label']}</div>
                <div class="card-area" style="color: #FAFAFA;">{hotspot['area']}</div>
                <div style="font-size: 0.9rem; opacity: 0.6;">Score: {hotspot['score']}</div>
                <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 10px; margin-top: 10px; font-size: 0.85rem;">
                    Real-time demand from multiple agents
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    st.divider()
    
    # News and events sections
    left, right = st.columns(2, gap="medium")
    
    with left:
        st.subheader("📰 Latest News")
        st.info("🚕 Heavy traffic at Airport - 45 min delays expected")
        st.info("🎭 Concert at Tavastia tonight - Event hotspot activated")
        st.info("🌧️ Rain expected in 30 minutes - Demand likely to increase")
    
    with right:
        st.subheader("📅 Upcoming Events (Next 3h)")
        st.info("🎪 17:30 - Concert at Tavastia Club")
        st.info("⚽ 19:00 - HJK match at Olympic Stadium")
        st.info("🎭 20:30 - Theater play at Linteatteri")
    
    st.divider()
    
    # Refresh info
    st.caption("🔄 Dashboard refreshes every 30 seconds | Data from 7 agents | Last update: Now")
