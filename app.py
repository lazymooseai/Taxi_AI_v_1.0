# app.py - Helsinki Taxi AI - Tuotantoversio
# Streamlit Cloud kaynistystiedosto

import os
import sys
import logging
from datetime import datetime
import pytz

import streamlit as st

# sys.path-korjaus Streamlit Cloudille
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Sivun asetukset
st.set_page_config(
    page_title='Helsinki Taxi AI',
    page_icon='taxi',
    layout='wide',
    initial_sidebar_state='collapsed',
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger('taxiapp.app')

# Pakolliset ymparistomuuttujat
_missing = []
for _key in ('SUPABASE_URL', 'SUPABASE_ANON_KEY'):
    if not os.environ.get(_key):
        _missing.append(_key)

if _missing:
    st.warning(
        'Supabase ei ole konfiguroitu: ' + str(_missing) + '. '
        'Sovellus toimii ilman tietokantaa.'
    )

# Session state
if 'initialized' not in st.session_state:
    st.session_state.update({
        'initialized':    True,
        'driver_id':      None,
        'driver_weights': None,
        'app_settings':   {},
        'hotspot_cache':  None,
        'hotspot_ts':     0.0,
        'last_ocr_result': None,
        'slippery_news':  [],
    })

# Sivupalkki
with st.sidebar:
    st.markdown('### Helsinki Taxi AI')
    st.markdown('---')

    driver_input = st.text_input(
        'Kuljettajan tunnus',
        value=st.session_state.get('driver_id') or '',
        placeholder='UUID tai nimi',
        key='sidebar_driver_id',
    )
    if driver_input and driver_input != st.session_state.get('driver_id'):
        st.session_state['driver_id'] = driver_input.strip() or None
        for k in ('hotspot_cache', 'hotspot_ts', 'driver_weights'):
            st.session_state.pop(k, None)
        st.rerun()

    st.markdown('---')

    # GPS-sijainti
    lat = st.session_state.get('driver_lat')
    lon = st.session_state.get('driver_lon')
    if lat and lon:
        st.caption('Sijainti: ' + str(round(lat, 4)) + ', ' + str(round(lon, 4)))
    else:
        st.caption('GPS ei aktiivinen')

    with st.expander('Aseta sijainti kasin', expanded=False):
        mlat = st.number_input('Lat', value=60.1718, format='%.4f', key='manual_lat')
        mlon = st.number_input('Lon', value=24.9414, format='%.4f', key='manual_lon')
        if st.button('Aseta sijainti', key='btn_set_loc'):
            try:
                from src.taxiapp.location import update_driver_location
                update_driver_location(float(mlat), float(mlon))
                st.session_state.pop('hotspot_cache', None)
                st.session_state.pop('hotspot_ts', None)
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.markdown('---')
    # Helsinki-aika
    tz_hki = pytz.timezone('Europe/Helsinki')
    now_hki = datetime.now(tz_hki)
    st.caption('v1.0 - ' + now_hki.strftime('%H:%M HKI'))

# Valilehdet
TABS = [
    'Kojelauta',
    'Tapahtumat',
    'Linkit',
    'Tilastot',
    'Asetukset',
    'Yllapito',
]
tabs = st.tabs(TABS)

# TAB 0 - KOJELAUTA
with tabs[0]:
    try:
        from src.taxiapp.ui.dashboard import render_dashboard
        render_dashboard()
    except Exception as e:
        logger.exception('Dashboard virhe')
        st.error('Kojelauta virhe: ' + str(e))
        st.code(str(e))

# TAB 1 - TAPAHTUMAT
with tabs[1]:
    try:
        from src.taxiapp.ui.events_tab import render_events_tab
        cached = st.session_state.get('hotspot_cache')
        results = cached[1] if cached else []
        render_events_tab(results)
    except Exception as e:
        logger.exception('Tapahtumat virhe')
        st.error('Tapahtumat virhe: ' + str(e))

# TAB 2 - LINKIT
with tabs[2]:
    try:
        from src.taxiapp.ui.links_tab import render_links_tab
        cached = st.session_state.get('hotspot_cache')
        results = cached[1] if cached else []
        render_links_tab(results)
    except Exception as e:
        logger.exception('Linkit virhe')
        st.error('Linkit virhe: ' + str(e))

# TAB 3 - TILASTOT
with tabs[3]:
    try:
        from src.taxiapp.ui.stats_tab import render_stats_tab
        cached = st.session_state.get('hotspot_cache')
        results = cached[1] if cached else []
        render_stats_tab(results, driver_id=st.session_state.get('driver_id'))
    except Exception as e:
        logger.exception('Tilastot virhe')
        st.error('Tilastot virhe: ' + str(e))

# TAB 4 - ASETUKSET
with tabs[4]:
    try:
        from src.taxiapp.ui.settings_tab import render_settings_tab
        render_settings_tab(driver_id=st.session_state.get('driver_id'))
    except Exception as e:
        logger.exception('Asetukset virhe')
        st.error('Asetukset virhe: ' + str(e))

# TAB 5 - YLLAPITO
with tabs[5]:
    try:
        from src.taxiapp.ui.admin_tab import render_admin_tab
        render_admin_tab(driver_id=st.session_state.get('driver_id'))
    except Exception as e:
        logger.exception('Yllapito virhe')
        st.error('Yllapito virhe: ' + str(e))
