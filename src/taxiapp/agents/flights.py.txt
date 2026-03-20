"""
flights.py - Finavia & Flightradar24 lentoagentti
Helsinki Taxi AI

Korjattu versio (Vaihe 5):
- typing.List importoitu (korjaa NameErrorin)
- Ei testidataa. Vain aito, reaaliaikainen data.
- Ensisijainen lähde: Finavia API v0
- Varalähde (Fallback): Flightradar24 API (Helsinki-Vantaa saapuvat)
- LISÄTTY: FlightAgent-luokka palauttamaan data oikeassa dict-muodossa UI:lle.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any

import httpx

# Asetetaan lokitus
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================================
# DATALUOKAT
# ==============================================================

@dataclass
class FlightArrival:
    flight_no: str
    airline: str
    origin: str
    origin_city: str
    scheduled_arrival: datetime
    estimated_arrival: Optional[datetime] = None
    status: str = "Scheduled"
    aircraft_type: str = "Unknown"
    
@dataclass
class Signal:
    area: str
    score_delta: float
    reason: str
    urgency: int
    expires_at: datetime
    source_url: str

# ==============================================================
# VARAJÄRJESTELMÄ: FLIGHTRADAR24
# ==============================================================

async def fetch_flightradar24_fallback() -> List[FlightArrival]:
    """
    Hakee reaaliaikaiset saapuvat lennot Flightradar24-palvelusta.
    Käytetään, jos Finavian API ei ole saatavilla tai avaimet puuttuvat.
    """
    logger.info("Haetaan reaaliaikaista lentodataa varajärjestelmästä (Flightradar24)...")
    
    url = "https://api.flightradar24.com/common/v1/airport.json?code=hel&plugin[]=schedule&plugin-setting[schedule][mode]=arrivals&limit=15"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    flights: List[FlightArrival] = []
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # Puretaan FR24 JSON-rakenne
            arrivals = data.get("result", {}).get("response", {}).get("airport", {}).get("pluginData", {}).get("schedule", {}).get("arrivals", {}).get("data", [])
            
            for item in arrivals:
                try:
                    flight_info = item.get("flight", {})
                    
                    # Tunnisteet
                    ident = flight_info.get("identification", {}).get("number", {}).get("default", "N/A")
                    airline = flight_info.get("airline", {}).get("name", "N/A")
                    
                    # Lähtöpaikka
                    airport_origin = flight_info.get("airport", {}).get("origin", {})
                    origin_city = airport_origin.get("position", {}).get("region", {}).get("city", "N/A") if airport_origin else "N/A"
                    origin_code = airport_origin.get("code", {}).get("iata", "N/A") if airport_origin else "N/A"
                    
                    # Aikataulut (UNIX timestamp -> datetime)
                    time_info = flight_info.get("time", {})
                    scheduled_ts = time_info.get("scheduled", {}).get("arrival")
                    estimated_ts = time_info.get("estimated", {}).get("arrival")
                    
                    if scheduled_ts:
                        scheduled_arrival = datetime.fromtimestamp(scheduled_ts, tz=timezone.utc)
                    else:
                        scheduled_arrival = datetime.now(timezone.utc)
                        
                    estimated_arrival = datetime.fromtimestamp(estimated_ts, tz=timezone.utc) if estimated_ts else None
                    
                    # Tila ja kalusto
                    status = flight_info.get("status", {}).get("text", "Scheduled")
                    aircraft_type = flight_info.get("aircraft", {}).get("model", {}).get("code", "Unknown")
                    
                    flights.append(FlightArrival(
                        flight_no=ident,
                        airline=airline,
                        origin=origin_code,
                        origin_city=origin_city,
                        scheduled_arrival=scheduled_arrival,
                        estimated_arrival=estimated_arrival,
                        status=status,
                        aircraft_type=aircraft_type
                    ))
                except Exception as e:
                    logger.warning(f"Virhe yksittäisen FR24-lennon parsinnassa: {e}")
                    continue
                    
            logger.info(f"Haettiin onnistuneesti {len(flights)} aitoa lentoa Flightradar24:stä.")
            return flights

    except Exception as e:
        logger.error(f"Kriittinen virhe: Myös Flightradar24-varajärjestelmä epäonnistui: {e}")
        return []

# ==============================================================
# YDINLOGIIKKA (FINAVIA API)
# ==============================================================

async def fetch_finavia_flights() -> List[FlightArrival]:
    """
    Hakee saapuvat lennot Finavian API:sta asynkronisesti.
    Jos epäonnistuu, siirtyy FR24-varajärjestelmään.
    """
    app_key = os.getenv("FINAVIA_APP_KEY")
    
    # 1. Tarkistetaan avaimet
    if not app_key:
        logger.warning("FINAVIA_APP_KEY puuttuu. Siirrytään Flightradar24-varajärjestelmään.")
        return await fetch_flightradar24_fallback()

    # 2. Aito rajapintapyyntö Finavialle
    url = "https://apigw.finavia.fi/flights/public/v0/flights/arr/EFHK"
    headers = {
        "app_key": app_key,
        "Accept": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            flights: List[FlightArrival] = []
            flight_list = data if isinstance(data, list) else data.get('flights', [])
            if not isinstance(flight_list, list):
                flight_list = []
            
            for item in flight_list:
                try:
                    sdt_str = item.get("sdt", "") 
                    scheduled = datetime.fromisoformat(sdt_str.replace("Z", "+00:00")) if sdt_str else datetime.now(timezone.utc)
                    
                    eta_str = item.get("eta", "")
                    estimated = datetime.fromisoformat(eta_str.replace("Z", "+00:00")) if eta_str else None
                    
                    flights.append(FlightArrival(
                        flight_no=item.get("flt", "Tuntematon"),
                        airline=item.get("actn", "Tuntematon"),
                        origin=item.get("rout", "Tuntematon"),
                        origin_city=item.get("route_n_en", "Tuntematon"),
                        scheduled_arrival=scheduled,
                        estimated_arrival=estimated,
                        status=item.get("stat", "Scheduled"),
                        aircraft_type=item.get("ac", "Unknown")
                    ))
                except Exception as e:
                    continue

            logger.info(f"Haettiin onnistuneesti {len(flights)} aitoa lentoa Finavialta.")
            return flights[:15] 
            
    except Exception as e:
        logger.error(f"Virhe Finavia-rajapinnassa ({e}). Siirrytään Flightradar24-varajärjestelmään.")
        return await fetch_flightradar24_fallback()

def generate_signals(flights: List[FlightArrival]) -> List[Signal]:
    """Analysoi lennot ja luo hälytykset taksikuskille (esim. myöhästymiset)."""
    by_area: Dict[str, Signal] = {}
    
    for flight in flights:
        if flight.estimated_arrival and flight.scheduled_arrival:
            delay_minutes = (flight.estimated_arrival - flight.scheduled_arrival).total_seconds() / 60.0
            
            if delay_minutes > 15: 
                sig = Signal(
                    area="EFHK",
                    score_delta=2.0,
                    reason=f"Lento {flight.flight_no} ({flight.origin_city}) myöhässä {int(delay_minutes)} min",
                    urgency=7 if delay_minutes > 30 else 5,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    source_url="finavia.fi/flightradar24"
                )
                
                if sig.area in by_area:
                    ex = by_area[sig.area]
                    by_area[sig.area] = Signal(
                        area=ex.area,
                        score_delta=round(ex.score_delta + sig.score_delta, 1),
                        reason=ex.reason,
                        urgency=max(ex.urgency, sig.urgency),
                        expires_at=max(sig.expires_at, ex.expires_at),
                        source_url=ex.source_url,
                    )
                else:
                    by_area[sig.area] = sig

    return list(by_area.values())


# ==============================================================
# AGENTTILUOKKA KÄYTTÖLIITTYMÄÄ VARTEN (KORJAA TYPEERRORIN)
# ==============================================================

class FlightAgent:
    """
    Käärii logiikan agenttiluokaksi.
    Palauttaa datan Streamlit-käyttöliittymälle sanakirjana,
    jotta kutsu data["flights"] toimii oikein.
    """
    async def get_data(self) -> Dict[str, Any]:
        # Haetaan asynkronisesti lista FlightArrival-olioita
        flights_list = await fetch_finavia_flights()
        
        # Generoidaan signaalit
        signals_list = generate_signals(flights_list)
        
        # Muutetaan oliot sisäisiksi sanakirjoiksi (dict),
        # jotta UI voi operoida niillä turvallisesti ilman subscriptable-virheitä
        return {
            "flights": [f.__dict__ for f in flights_list],
            "signals": [s.__dict__ for s in signals_list]
        }
    
    # Alias siltä varalta, että app.py kutsuu agenttia nimellä .execute()
    async def execute(self, *args, **kwargs) -> Dict[str, Any]:
        return await self.get_data()
