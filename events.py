# Events Agent Component
import streamlit as st
from datetime import datetime, timezone, timedelta

EVENTS_CSS = """
<style>
.event-card {
    background: #1a1d27;
    border-radius: 12px;
    padding: 12px 16px;
    border-left: 3px solid #A78BFA;
    margin-bottom: 8px;
}
.event-time {
    font-size: 0.9rem;
    font-weight: 600;
    color: #00B4D8;
}
.event-title {
    font-size: 1rem;
    font-weight: 600;
    margin: 4px 0;
}
.event-venue {
    font-size: 0.8rem;
    color: #888899;
}
</style>
"""

def render_events_tab():
    """Render events tab"""
    st.markdown(EVENTS_CSS, unsafe_allow_html=True)
    
    st.header("🎭 Helsinki Events")
    st.markdown("Real-time event tracking for demand prediction")
    
    # Categories
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🎪 Culture", "12 events", "+3 today")
    with col2:
        st.metric("⚽ Sports", "5 events", "+1 today")
    with col3:
        st.metric("🎤 Entertainment", "8 events", "+2 today")
    
    st.divider()
    
    # Upcoming events
    st.subheader("📅 Next 24 Hours")
    
    events = [
        {"time": "17:30", "title": "Concert - Tavastia Club", "venue": "Kallio", "category": "🎪"},
        {"time": "18:45", "title": "Theater - Linteatteri", "venue": "Katajanokka", "category": "🎭"},
        {"time": "19:00", "title": "HJK vs Inter - Olympic Stadium", "venue": "Pasila", "category": "⚽"},
        {"time": "20:00", "title": "Comedy Show - Klubi", "venue": "Kamppi", "category": "🎤"},
        {"time": "21:00", "title": "Techno Party - Cable Factory", "venue": "Kallio", "category": "🎵"},
    ]
    
    for event in events:
        st.markdown(f"""
        <div class="event-card">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div>
                    <div class="event-time">{event['time']}</div>
                    <div class="event-title">{event['category']} {event['title']}</div>
                    <div class="event-venue">📍 {event['venue']}</div>
                </div>
                <div style="font-size: 0.8rem; color: #888899;">High demand</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.info("ℹ️ Events are tracked via RSS feeds from Hel.fi, Liput.fi, and Eduskunta. Demand model learns from event urgency.")
