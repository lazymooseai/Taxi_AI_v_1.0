import os
import sys
import streamlit as st

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

st.set_page_config(page_title='Helsinki Taxi AI', page_icon='taxi')
st.title('Helsinki Taxi AI')

try:
    from src.taxiapp.ceo import build_agents
    agents = build_agents()
    st.success('Vaihe 4 OK - CEO ladattu')
    st.info('Agentteja: ' + str(len(agents)) + '/7')
    if len(agents) < 7:
        import importlib, traceback
        st.warning('Puuttuvat agentit - diagnostiikka:')
        for mod, cls in [
            ('src.taxiapp.agents.disruptions', 'DisruptionAgent'),
            ('src.taxiapp.agents.weather', 'WeatherAgent'),
            ('src.taxiapp.agents.trains', 'TrainAgent'),
            ('src.taxiapp.agents.flights', 'FlightAgent'),
            ('src.taxiapp.agents.ferries', 'FerryAgent'),
            ('src.taxiapp.agents.events', 'EventsAgent'),
            ('src.taxiapp.agents.social_media', 'SocialMediaAgent'),
        ]:
            try:
                m = importlib.import_module(mod)
                getattr(m, cls)
                st.success(cls + ' OK')
            except Exception as e:
                st.error(cls + ': ' + str(e))
except Exception as e:
    st.error(str(e))
