import os
import sys
import streamlit as st

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

st.set_page_config(page_title='Helsinki Taxi AI', page_icon='taxi')
st.title('Helsinki Taxi AI')

try:
    from src.taxiapp.ceo import build_ceo, build_agents
    agents = build_agents()
    st.success('Vaihe 4 OK - CEO ja agentit ladattu')
    st.info('Agentteja: ' + str(len(agents)) + '/7')
except Exception as e:
    st.error(str(e))
