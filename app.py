# app.py — Helsinki Taxi AI — Tuotantoversio
# Python 3.12 | Streamlit Cloud
#
# Korjaukset v1.1:
#   - _run_async(): ThreadPoolExecutor + uusi event loop per ajo
#     → estää "RuntimeError: This event loop is already running" Streamlit Cloudissa
#   - Autorefresh: <meta http-equiv="refresh"> älykkäällä ajastuksella
#     → JS setTimeout ei toimi Streamlitin HTML-sanitoinnin takia
#   - Kuljettajan painot välitetään CEO:lle session_statesta
#   - st.toast() virheilmoituksiin loggauksen lisäksi

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import sys
import time
from datetime import datetime

import streamlit as st

# ── Varmista että src/ löytyy Python-polusta ──────────────────────────────
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Sivukonfiguraatio — ENSIMMÄISENÄ ennen muita st-kutsuja ──────────────
st.set_page_config(
    page_title="Helsinki Taxi AI",
    page_icon="🚕",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Lokitus ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("taxiapp.app")

# Vaimenna Streamlitin omat thread-varoitukset:
# "missing ScriptRunContext" tulee joka kerta kun CEO-threadi käynnistyy.
# Tämä on odotettua käytöstä (ThreadPoolExecutor + asyncio) eikä osoita virhettä.
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(
    logging.ERROR
)
logging.getLogger("streamlit").setLevel(logging.WARNING)

# ── Supabase-tarkistus (ei-blokkaava) ────────────────────────────────────
_missing_keys = [k for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY") if not os.environ.get(k)]
if _missing_keys:
    st.info("ℹ️ Supabase ei konfiguroitu — sovellus toimii ilman tietokantaa.", icon="ℹ️")

# ── Session state -alustus ────────────────────────────────────────────────
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
        # GPS-kentät (täytetään location.py:stä)
        "driver_lat":      None,
        "driver_lon":      None,
        "driver_accuracy": None,
        "driver_speed":    None,
    })

# ── Vakiot ────────────────────────────────────────────────────────────────
REFRESH_SECONDS: int = int(
    st.session_state.get("app_settings", {}).get("refresh_seconds", 30)
)


# ══════════════════════════════════════════════════════════════════════════
# ASYNCIO-AJURI — luotettava Streamlit Cloud -ympäristössä
# ══════════════════════════════════════════════════════════════════════════

def _run_async(coro) -> object:
    """
    Aja asyncio-koroutiini Streamlit Cloudissa turvallisesti.

    Ongelma: Streamlit ajaa koodia Tornado-palvelimen event loopin
    sisällä. asyncio.get_event_loop().run_until_complete() kaatuu:
      RuntimeError: This event loop is already running

    Ratkaisu: Aja koroutiini erillisessä threadissa jolla on
    oma, puhdas event loop. ThreadPoolExecutor takaa säieturvallisuuden.

    Args:
        coro: asyncio-koroutiini (await-kutsu)

    Returns:
        Koroutiinin palautusarvo

    Raises:
        TimeoutError: jos ajo kestää yli 45 sekuntia
        Exception:    kaikki muut virheet välitetään ylöspäin
    """
    def _thread_runner(c):
        """Suorittaa koroutiinin omassa event loopissa omassa threadissa."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(c)
        finally:
            # Sulje loop siististi — estää resurssivuodot
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            finally:
                loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_thread_runner, coro)
        return future.result(timeout=45)


# ══════════════════════════════════════════════════════════════════════════
# CEO-AJO — agenttidatan haku
# ══════════════════════════════════════════════════════════════════════════

def _run_ceo() -> None:
    """
    Aja CEO-orkestraattori ja päivitä hotspot_cache session_stateen.

    Välimuistilogiikka: jos edellisestä ajosta on kulunut alle
    REFRESH_SECONDS, ei tehdä uutta hakua.

    Välittää kuljettajan painot ja sijainnin CEO:lle jos saatavilla.
    Virhe yhdessä agentissa ei kaada muita (CEO hoitaa).
    """
    now      = time.time()
    last_ts  = st.session_state.get("hotspot_ts", 0.0)
    cache    = st.session_state.get("hotspot_cache")

    # Välimuistiosuma — ei uutta hakua
    if cache and (now - last_ts) < REFRESH_SECONDS:
        return

    try:
        from src.taxiapp.ceo import TaxiCEOAgent, build_agents

        # Hae kuljettajan painot
        weights = st.session_state.get("driver_weights") or {}

        # Hae kuljettajan sijainti
        lat = st.session_state.get("driver_lat")
        lon = st.session_state.get("driver_lon")
        location = (float(lat), float(lon)) if lat and lon else None

        agents   = build_agents()
        ceo      = TaxiCEOAgent(
            agents    = agents,
            weights   = weights or None,
            driver_id = st.session_state.get("driver_id"),
            location  = location,
        )

        hotspots, results = _run_async(ceo.run())

        st.session_state["hotspot_cache"] = (hotspots, results)
        st.session_state["hotspot_ts"]    = now

        logger.info(
            "CEO: %d hotspottia | %d agenttia | sijainti: %s",
            len(hotspots),
            len(results),
            f"{lat:.4f},{lon:.4f}" if location else "ei",
        )

    except Exception as exc:
        logger.error("CEO ajo epäonnistui: %s", exc, exc_info=True)
        # Näytä käyttäjälle toast mutta älä kaada sovellusta
        st.toast(f"⚠️ Datan päivitys epäonnistui: {exc}", icon="⚠️")


# ══════════════════════════════════════════════════════════════════════════
# ENSIMMÄINEN AJO
# ══════════════════════════════════════════════════════════════════════════

with st.spinner("⏳ Päivitetään tietoja..."):
    _run_ceo()


# ══════════════════════════════════════════════════════════════════════════
# SIVUPALKKI
# ══════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### 🚕 Helsinki Taxi AI")
    st.markdown("---")

    # Kuljettajan tunnus
    driver_input = st.text_input(
        "Kuljettajan tunnus",
        value=st.session_state.get("driver_id") or "",
        placeholder="UUID tai nimi",
        key="sidebar_driver_id",
    )
    if driver_input != (st.session_state.get("driver_id") or ""):
        new_id = driver_input.strip() or None
        if new_id != st.session_state.get("driver_id"):
            st.session_state["driver_id"] = new_id
            for k in ("hotspot_cache", "hotspot_ts", "driver_weights"):
                st.session_state.pop(k, None)
            st.rerun()

    st.markdown("---")

    # GPS-tila
    lat = st.session_state.get("driver_lat")
    lon = st.session_state.get("driver_lon")
    if lat and lon:
        st.caption(f"📍 {round(lat, 4)}, {round(lon, 4)}")
    else:
        st.caption("⊙ GPS ei aktiivinen")

    # Manuaalinen sijaintiasetus
    with st.expander("📌 Aseta sijainti käsin", expanded=False):
        mlat = st.number_input("Lat", value=60.1718, format="%.4f", key="manual_lat")
        mlon = st.number_input("Lon", value=24.9414, format="%.4f", key="manual_lon")
        if st.button("Aseta sijainti", key="btn_set_loc"):
            st.session_state["driver_lat"] = float(mlat)
            st.session_state["driver_lon"] = float(mlon)
            for k in ("hotspot_cache", "hotspot_ts"):
                st.session_state.pop(k, None)
            st.rerun()

    st.markdown("---")

    # Kello
    try:
        import pytz
        tz_hki   = pytz.timezone("Europe/Helsinki")
        now_hki  = datetime.now(tz_hki)
        time_str = now_hki.strftime("%H:%M")
    except ImportError:
        import time as _t
        offset   = 3 if _t.daylight else 2
        from datetime import timezone, timedelta
        now_hki  = datetime.now(timezone.utc) + timedelta(hours=offset)
        time_str = now_hki.strftime("%H:%M")

    st.caption(f"v1.1 · {time_str} HKI")

    # Manuaalinen päivitys
    if st.button("🔄 Päivitä nyt", use_container_width=True, key="sidebar_refresh"):
        for k in ("hotspot_cache", "hotspot_ts"):
            st.session_state.pop(k, None)
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# PÄÄVÄLILEHDET
# ══════════════════════════════════════════════════════════════════════════

TABS = [
    "🗺️ Kojelauta",
    "🎭 Tapahtumat",
    "🔗 Linkit",
    "📊 Tilastot",
    "⚙️ Asetukset",
    "🔧 Ylläpito",
]
tabs = st.tabs(TABS)

# Hae data session_statesta
_cache    = st.session_state.get("hotspot_cache")
hotspots  = _cache[0] if _cache else []
results   = _cache[1] if _cache else []


# ── Kojelauta ─────────────────────────────────────────────────────────────
with tabs[0]:
    try:
        from src.taxiapp.ui.dashboard import render_dashboard
        render_dashboard(hotspots=hotspots, agent_results=results)
    except Exception as exc:
        logger.exception("Dashboard virhe")
        st.error(f"Kojelauta virhe: {exc}")
        with st.expander("Tekninen virhe"):
            st.code(str(exc))

# ── Tapahtumat ────────────────────────────────────────────────────────────
with tabs[1]:
    try:
        from src.taxiapp.ui.events_tab import render_events_tab
        render_events_tab(results)
    except Exception as exc:
        logger.exception("Tapahtumat virhe")
        st.error(f"Tapahtumat virhe: {exc}")

# ── Linkit ────────────────────────────────────────────────────────────────
with tabs[2]:
    try:
        from src.taxiapp.ui.links_tab import render_links_tab
        render_links_tab(results)
    except Exception as exc:
        logger.exception("Linkit virhe")
        st.error(f"Linkit virhe: {exc}")

# ── Tilastot ──────────────────────────────────────────────────────────────
with tabs[3]:
    try:
        from src.taxiapp.ui.stats_tab import render_stats_tab
        render_stats_tab(results, driver_id=st.session_state.get("driver_id"))
    except Exception as exc:
        logger.exception("Tilastot virhe")
        st.error(f"Tilastot virhe: {exc}")

# ── Asetukset ─────────────────────────────────────────────────────────────
with tabs[4]:
    try:
        from src.taxiapp.ui.settings_tab import render_settings_tab
        render_settings_tab(driver_id=st.session_state.get("driver_id"))
    except Exception as exc:
        logger.exception("Asetukset virhe")
        st.error(f"Asetukset virhe: {exc}")

# ── Ylläpito ──────────────────────────────────────────────────────────────
with tabs[5]:
    try:
        from src.taxiapp.ui.admin_tab import render_admin_tab
        render_admin_tab(driver_id=st.session_state.get("driver_id"))
    except Exception as exc:
        logger.exception("Ylläpito virhe")
        st.error(f"Ylläpito virhe: {exc}")


# ══════════════════════════════════════════════════════════════════════════
# AUTOREFRESH — luotettava meta-refresh
# ══════════════════════════════════════════════════════════════════════════
#
# <meta http-equiv="refresh"> on selaimen natiivi ominaisuus.
# Se toimii ilman JavaScriptiä ja Streamlitin HTML-sanitoijaa.
# Älykäs ajoitus: lasketaan milloin data vanhentuu ja asetetaan
# refresh juuri sille hetkelle — ei turhia latauksia.
#
_now_ts      = time.time()
_last_ts     = st.session_state.get("hotspot_ts", 0.0)
_elapsed     = _now_ts - _last_ts
_refresh_in  = max(5, int(REFRESH_SECONDS - _elapsed))

st.markdown(
    f'<meta http-equiv="refresh" content="{_refresh_in}">',
    unsafe_allow_html=True,
)
