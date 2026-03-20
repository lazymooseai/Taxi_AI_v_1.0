# Statistics Tab Component
import streamlit as st
from datetime import datetime, timezone
import random

STATS_CSS = """
<style>
.stat-card {
    background: #1a1d27;
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 12px;
    border: 1px solid #2a2d3d;
}
.kpi-box {
    background: #1a1d27;
    border-radius: 12px;
    padding: 14px;
    border: 1px solid #2a2d3d;
    text-align: center;
}
.kpi-value {
    font-size: 1.9rem;
    font-weight: 700;
}
.kpi-label {
    font-size: 0.7rem;
    color: #888899;
    text-transform: uppercase;
}
</style>
"""

def render_stats_tab():
    """Render statistics tab"""
    st.markdown(STATS_CSS, unsafe_allow_html=True)
    
    st.header("📈 Driver Statistics")
    
    # KPI Row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("""
        <div class="kpi-box">
            <div class="kpi-value" style="color: #00B4D8;">247</div>
            <div class="kpi-label">Total Rides</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="kpi-box">
            <div class="kpi-value" style="color: #21C55D;">€1,842</div>
            <div class="kpi-label">Total Earnings</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="kpi-box">
            <div class="kpi-value" style="color: #FFD700;">€7.45</div>
            <div class="kpi-label">Avg Fare</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown("""
        <div class="kpi-box">
            <div class="kpi-value" style="color: #A78BFA;">4.8/5.0</div>
            <div class="kpi-label">Rating</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    # Charts
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📍 Rides by Area (Last 7 days)")
        rides_by_area = {
            "Airport": 32,
            "Central Station": 28,
            "Pasila": 22,
            "Kallio": 18,
            "Katajanokka": 15,
        }
        st.bar_chart(rides_by_area)
    
    with col2:
        st.subheader("💰 Earnings Trend")
        earnings = {
            "Mon": 240,
            "Tue": 190,
            "Wed": 210,
            "Thu": 185,
            "Fri": 320,
            "Sat": 410,
            "Sun": 280,
        }
        st.line_chart(earnings)
    
    st.divider()
    
    # ML Data
    st.subheader("🤖 AI Learning Metrics")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Model Accuracy", "82.5%", "+2.1%")
    with col2:
        st.metric("Training Samples", "1,247", "+45")
    with col3:
        st.metric("MAE Error", "0.32", "-0.05")
