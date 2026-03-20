"""
app.py - Helsinki Taxi AI
Pääohjelma ja käyttöliittymän orkestrointi (Vaihe 6)
"""

import streamlit as st
import asyncio
import time
from datetime import datetime

# 1. Sivun perusasetukset (pitää olla tiedoston ensimmäinen Streamlit-komento)
st.set_page_config(
    page_title="Taxi AI Dashboard", 
    page_icon="🚖", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Tuodaan ydinmoottori (Agentit)
try:
    from src.taxiapp.agents.flights import FlightAgent
except ImportError:
    st.error("🚨 Agenttien tuonti epäonnistui! Varmista, että 'src/taxiapp/agents/flights.py' on olemassa ja että kansioissa on '__init__.py'.")
    st.stop()
    
# 3. Tuodaan UI-välilehdet
try:
    from src.taxiapp.ui.dashboard import render_dashboard
    from src.taxiapp.ui.events_tab import render_events_tab
    from src.taxiapp.ui.links_tab import render_links_tab
    from src.taxiapp.ui.stats_tab import render_stats_tab
    from src.taxiapp.ui.settings_tab import render_settings_tab
    from src.taxiapp.ui.admin_tab import render_admin_tab
except ImportError as e:
    st.error(f"🚨 UI-moduulien tuonti epäonnistui: {e}")
    st.info("Varmista, että loit kansion 'src/taxiapp/ui/', sen sisällä on '__init__.py', ja tiedostojen nimet ovat oikein (esim. links_tab.py ilman välilyöntejä).")
    st.stop()

# ==============================================================
# DATANHAKU JA ORKESTROINTI
# ==============================================================

@st.cache_data(ttl=60) # Haetaan data max kerran minuutissa (säästää API-kutsuja)
def fetch_all_data():
    """Suorittaa agentit ja kokoaa sovelluksen yhteisen tilan (state)."""
    async def run_agents():
        start_time = time.time()
        
        # Alustetaan agentit
        flight_agent = FlightAgent()
        
        # Tulevaisuudessa ajamme täällä rinnakkain myös juna- ja sää-agentit asyncio.gatherilla.
        # Nyt suoritetaan vasta valmis lentoagentti.
        flight_data = await flight_agent.execute()
        
        exec_time = time.time() - start_time
        
        # Kootaan järjestelmän tila (State), jota UI-välilehdet osaavat lukea
        return {
            "flights": flight_data.get("flights", []),
            "signals": flight_data.get("signals", []),
            # Placeholderit tuleville agenteille, jotta UI ei kaadu:
            "trains": [], 
            "weather": {},
            "cruises": [],
            "events": [],
            "traffic": [],
            
            "agent_stats": {
                "flights_time": round(exec_time, 2),
                "total_time": round(exec_time, 2)
            },
            "last_updated": datetime.now().strftime("%H:%M:%S")
        }
        
    return asyncio.run(run_agents())

# ==============================================================
# PÄÄKÄYTTÖLIITTYMÄ (UI)
# ==============================================================

def main():
    st.title("🚖 Helsinki Taxi AI - Operatiivinen Kojelauta")
    
    # Haetaan tilannekuva
    with st.spinner("Päivitetään tilannekuvaa agenteilta..."):
        state = fetch_all_data()
        
    st.caption(f"Viimeksi päivitetty: {state['last_updated']}")
    
    # Luodaan välilehdet modulaarisen rakenteen mukaisesti
    tabs = st.tabs([
        "📊 Kojelauta", 
        "📅 Tapahtumat", 
        "🔗 Pikalinkit", 
        "📈 Tilastot", 
        "⚙️ Asetukset", 
        "🛠️ Hallinta"
    ])
    
    # Renderöidään jokainen välilehti omalla tuodulla funktiollaan
    with tabs[0]: render_dashboard(state)
    with tabs[1]: render_events_tab(state)
    with tabs[2]: render_links_tab()
    with tabs[3]: render_stats_tab(state)
    with tabs[4]: render_settings_tab()
    with tabs[5]: render_admin_tab(state)

if __name__ == "__main__":
    main()
