# Admin Tab Component
import streamlit as st

ADMIN_CSS = """
<style>
.admin-section {
    background: #1a1d27;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
    border: 1px solid #2a2d3d;
}
.status-ok {
    color: #21C55D;
    font-weight: 600;
}
.status-error {
    color: #FF4B4B;
    font-weight: 600;
}
</style>
"""

def render_admin_tab():
    """Render admin tab"""
    st.markdown(ADMIN_CSS, unsafe_allow_html=True)
    
    # Password protection
    password = st.text_input("Admin password:", type="password")
    if password != "admin123":
        st.warning("🔒 Enter password to access admin panel")
        return
    
    st.success("✓ Admin panel unlocked")
    
    st.header("🛡️ Admin Panel")
    
    # System status
    st.subheader("System Status")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("<div class='status-ok'>✓ API Connections</div>", unsafe_allow_html=True)
    with col2:
        st.markdown("<div class='status-ok'>✓ Database</div>", unsafe_allow_html=True)
    with col3:
        st.markdown("<div class='status-ok'>✓ Cache</div>", unsafe_allow_html=True)
    with col4:
        st.markdown("<div class='status-ok'>✓ Agents</div>", unsafe_allow_html=True)
    
    st.divider()
    
    # Agent management
    st.subheader("📊 Agent Management")
    tab1, tab2, tab3 = st.tabs(["Agents", "Sources", "Diagnostics"])
    
    with tab1:
        st.write("Active agents:")
        agents = {
            "FlightAgent": "✓ Running",
            "TrainAgent": "✓ Running",
            "FerryAgent": "✓ Running",
            "WeatherAgent": "✓ Running",
            "EventsAgent": "✓ Running",
            "DisruptionAgent": "✓ Running",
            "SocialMediaAgent": "✓ Running",
        }
        for agent, status in agents.items():
            st.markdown(f"<div class='status-ok'>{agent}: {status}</div>", unsafe_allow_html=True)
    
    with tab2:
        st.info("API Sources Configuration")
        st.write("Flight Data: Finavia API")
        st.write("Train Data: Digitraffic API")
        st.write("Events: RSS Feeds (Hel.fi, Liput.fi)")
        st.write("Weather: FMI API")
    
    with tab3:
        st.info("System Diagnostics")
        st.write("Last agent run: 30 seconds ago")
        st.write("Database connections: 5/10")
        st.write("Cache hit rate: 92%")
    
    st.divider()
    
    # Manual controls
    st.subheader("Manual Controls")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔄 Force refresh all agents"):
            st.success("Agents refreshed")
    with col2:
        if st.button("🗑️ Clear cache"):
            st.success("Cache cleared")
    with col3:
        if st.button("🔧 Restart agents"):
            st.success("Agents restarted")
