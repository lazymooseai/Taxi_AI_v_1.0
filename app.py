import os
import sys
import streamlit as st

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

st.set_page_config(page_title='Helsinki Taxi AI', page_icon='taxi')
st.title('Helsinki Taxi AI')

try:
    from src.taxiapp.hello import get_message
    st.success(get_message())
except Exception as e:
    st.error(str(e))

