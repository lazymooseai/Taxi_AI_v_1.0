# Settings Tab Component
import streamlit as st

SETTINGS_CSS = """
<style>
.settings-section {
    background: #1a1d27;
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
    border: 1px solid #2a2d3d;
}
.weight-row {
    margin-bottom: 12px;
}
.weight-label {
    display: flex;
    justify-content: space-between;
    margin-bottom: 4px;
    font-size: 0.9rem;
}
</style>
"""

def render_settings_tab():
    """Render settings tab"""
    st.markdown(SETTINGS_CSS, unsafe_allow_html=True)
    
    st.header("⚙️ Driver Preferences")
    
    # Category weights
    st.subheader("Demand Model Weights (0-3.0)")
    st.caption("Adjust how much each factor influences taxi demand predictions")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.slider("🚆 Trains", 0.0, 3.0, 1.0, 0.1)
        st.slider("✈️ Flights", 0.0, 3.0, 1.0, 0.1)
        st.slider("⛴️ Ferries", 0.0, 3.0, 1.0, 0.1)
        st.slider("🎭 Events", 0.0, 3.0, 1.0, 0.1)
    
    with col2:
        st.slider("🌤️ Weather", 0.0, 3.0, 1.0, 0.1)
        st.slider("🎪 Nightlife", 0.0, 3.0, 0.8, 0.1)
        st.slider("⚽ Sports", 0.0, 3.0, 1.0, 0.1)
        st.slider("💼 Business", 0.0, 3.0, 1.0, 0.1)
    
    st.divider()
    
    # Voice settings
    st.subheader("🔊 Voice Settings")
    voice_enabled = st.toggle("Enable voice alerts", True)
    if voice_enabled:
        st.radio("Voice provider:", ["Web Speech (Free)", "OpenAI TTS (Premium)"])
    
    st.divider()
    
    # General settings
    st.subheader("General Settings")
    col1, col2 = st.columns(2)
    with col1:
        st.select_slider("Refresh interval (seconds)", options=[5, 10, 15, 30, 60])
    with col2:
        st.select_slider("Alert threshold", options=[3, 5, 7, 9])
    
    # Dark theme
    st.toggle("Dark theme", True)
    st.toggle("Show hotspot map", False)
    
    st.divider()
    
    # Save button
    if st.button("💾 Save Settings", type="primary"):
        st.success("✓ Settings saved!")
        st.toast("Preferences updated", icon="✓")
