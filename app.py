import os
import sys
import streamlit as st

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

st.set_page_config(page_title='Helsinki Taxi AI', page_icon='taxi')
st.title('Helsinki Taxi AI')

try:
    from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal
    from src.taxiapp.areas import AREAS
    st.success('Vaihe 3 OK - BaseAgent ja AREAS ladattu')
    st.info('Alueita: ' + str(len(AREAS)))
except Exception as e:
    st.error(str(e))
