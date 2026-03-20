# Helsinki Taxi AI - Main Streamlit Application
# Orchestrates all tabs and agent results

import streamlit as st
import asyncio
import time
from datetime import datetime

st.set_page_config(
    page_title="Taxi AI Dashboard",
    page_icon="🚕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Import UI components
try:
    from dashboard import render_dashboard
    from events import render_events_tab
    from links_tab import render_links_tab
    from stats_tab import render_stats_tab
    from settings_tab import render_settings_tab
    from amin_tab import render_admin_tab
except ImportError as e:
    st.error(f"UI modules import failed: {e}")
    st.info("Make sure all tab modules are in the same directory as app.py")
    st.stop()

def fetch_all_data():
    """Fetch data from all agents and prepare state for UI"""
    # Placeholder for agent execution
    # This would run FlightAgent, EventsAgent, TrainAgent, etc. in production
    return {
        "flights": [],
        "events": [],
        "trains": [],
        "weather": {},
        "agents": [],
        "last_updated": datetime.now().strftime("%H:%M:%S")
    }

def main():
    st.title("🚕 Helsinki Taxi AI - Operational Dashboard")
    
    # Fetch data
    with st.spinner("Updating situation from agents..."):
        state = fetch_all_data()
    
    st.caption(f"Last updated: {state['last_updated']}")
    
    # Create tabs
    tabs = st.tabs([
        "📊 Dashboard",
        "🎭 Events",
        "🔗 Links",
        "📈 Stats",
        "⚙️ Settings",
        "🛡️ Admin"
    ])
    
    # Render each tab
    with tabs[0]:
        render_dashboard()
    with tabs[1]:
        render_events_tab()
    with tabs[2]:
        render_links_tab()
    with tabs[3]:
        render_stats_tab()
    with tabs[4]:
        render_settings_tab()
    with tabs[5]:
        render_admin_tab()

if __name__ == "__main__":
    main()
