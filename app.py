# app.py -- Helsinki Taxi AI -- Tuotantoversio
from __future__ import annotations

import asyncio
import os
import sys
import logging
import time
from datetime import datetime
import pytz

import streamlit as st

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

st.set_page_config(
    page_title="Helsinki Taxi AI",
    page_icon="taxi",
    layout="wide",
    initial_sidebar_state="collapsed",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("taxiapp.app")

_missing = []
for _key in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
    if not os.environ.get(_key):
        _missing.append(_key)
if _missing:
    st.info("Supabase ei ole konfiguroitu -- sovellus toimii ilman tietokantaa.")

if "initialized" not in st.session_state:
    st.session_state.update({
        "initialized":     True,
        "driver_id":       None,
        "driver_weights":  None,
        "app_settings":    {},
        "hotspot_cache":   None,
        "hotspot_ts":      0.0,
        "last_ocr_result": None,
        "slippery_news":   [],
    })

REFRESH_SECONDS = 30


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=30)
        return loop.run_until_complete(coro)
    except Exception:
        return asyncio.run(coro)


def _run_ceo():
    now = time.time()
    last_ts = st.session_state.get("hotspot_ts", 0.0)
    if (now - last_ts) < REFRESH_SECONDS and st.session_state.get("hotspot_cache"):
        return

    try:
        from src.taxiapp.ceo import TaxiCEOAgent, build_agents
        agents = build_agents()
        ceo = TaxiCEOAgent(agents=agents)
        hotspots, results = _run_async(ceo.run())
        st.session_state["hotspot_cache"] = (hotspots, results)
        st.session_state["hotspot_ts"] = now
        logger.info("CEO: %d hotspottia, %d agenttia", len(hotspots), len(results))
    except Exception as e:
        logger.error("CEO ajo epaonnistui: %s", e)


with st.spinner("Paivitetaan tietoja..."):
    _run_ceo()

with st.sidebar:
    st.markdown("### Helsinki Taxi AI")
    st.markdown("---")

    driver_input = st.text_input(
        "Kuljettajan tunnus",
        value=st.session_state.get("driver_id") or "",
        placeholder="UUID tai nimi",
        key="sidebar_driver_id",
    )
    if driver_input and driver_input != st.session_state.get("driver_id"):
        st.session_state["driver_id"] = driver_input.strip() or None
        for k in ("hotspot_cache", "hotspot_ts", "driver_weights"):
            st.session_state.pop(k, None)
        st.rerun()

    st.markdown("---")
    lat = st.session_state.get("driver_lat")
    lon = st.session_state.get("driver_lon")
    if lat and lon:
        st.caption("Sijainti: " + str(round(lat, 4)) + ", " + str(round(lon, 4)))
    else:
        st.caption("GPS ei aktiivinen")

    with st.expander("Aseta sijainti kasin", expanded=False):
        mlat = st.number_input("Lat", value=60.1718, format="%.4f", key="manual_lat")
        mlon = st.number_input("Lon", value=24.9414, format="%.4f", key="manual_lon")
        if st.button("Aseta sijainti", key="btn_set_loc"):
            st.session_state["driver_lat"] = float(mlat)
            st.session_state["driver_lon"] = float(mlon)
            st.session_state.pop("hotspot_cache", None)
            st.session_state.pop("hotspot_ts", None)
            st.rerun()

    st.markdown("---")
    tz_hki = pytz.timezone("Europe/Helsinki")
    now_hki = datetime.now(tz_hki)
    st.caption("v1.0 - " + now_hki.strftime("%H:%M HKI"))

TABS = ["Kojelauta", "Tapahtumat", "Linkit", "Tilastot", "Asetukset", "Yllapito"]
tabs = st.tabs(TABS)

cached   = st.session_state.get("hotspot_cache")
hotspots = cached[0] if cached else []
results  = cached[1] if cached else []

with tabs[0]:
    try:
        from src.taxiapp.ui.dashboard import render_dashboard
        render_dashboard(hotspots=hotspots, agent_results=results)
    except Exception as e:
        logger.exception("Dashboard virhe")
        st.error("Kojelauta virhe: " + str(e))
        st.code(str(e))

with tabs[1]:
    try:
        from src.taxiapp.ui.events_tab import render_events_tab
        render_events_tab(results)
    except Exception as e:
        logger.exception("Tapahtumat virhe")
        st.error("Tapahtumat virhe: " + str(e))

with tabs[2]:
    try:
        from src.taxiapp.ui.links_tab import render_links_tab
        render_links_tab(results)
    except Exception as e:
        logger.exception("Linkit virhe")
        st.error("Linkit virhe: " + str(e))

with tabs[3]:
    try:
        from src.taxiapp.ui.stats_tab import render_stats_tab
        render_stats_tab(results, driver_id=st.session_state.get("driver_id"))
    except Exception as e:
        logger.exception("Tilastot virhe")
        st.error("Tilastot virhe: " + str(e))

with tabs[4]:
    try:
        from src.taxiapp.ui.settings_tab import render_settings_tab
        render_settings_tab(driver_id=st.session_state.get("driver_id"))
    except Exception as e:
        logger.exception("Asetukset virhe")
        st.error("Asetukset virhe: " + str(e))

with tabs[5]:
    try:
        from src.taxiapp.ui.admin_tab import render_admin_tab
        render_admin_tab(driver_id=st.session_state.get("driver_id"))
    except Exception as e:
        logger.exception("Yllapito virhe")
        st.error("Yllapito virhe: " + str(e))

refresh_secs = int(st.session_state.get("app_settings", {}).get("refresh_seconds", 30))
st.markdown(
    "<script>setTimeout(function(){window.location.reload();}, "
    + str(refresh_secs * 1000) + ");</script>",
    unsafe_allow_html=True,
)
