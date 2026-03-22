# ferries.py — KORJAUKSET
# =====================================================
# KOHTA #5: Averio 404 + Digitransit 401
# =====================================================

# KORJAUS 1: Averio URL-muutos
# VANHA: "https://www.averio.fi/aikataulu"  -> 404
# UUSI:  testaa seuraavaa
AVERIOSCHEDULE = "https://www.averio.fi/en/schedule"  # tai /fi/aikataulu

# KORJAUS 2: Digitransit GraphQL vaatii subscription-avaimen
# Rekisteröidy: https://digitransit.fi/en/developers/
# Lisää avaimen config.py:hin:

# config.py lisäys:
# DIGITRANSIT_KEY = "your_subscription_key_here"

# ferries.py:
# async def _fetch_suomenlinna(self, client: httpx.AsyncClient):
#     headers = {
#         "Content-Type": "application/json",
#         "digitransit-subscription-1-api-key": config.digitransit_key,  # ← KORJAUS
#     }
#     resp = await client.post(HSLAPIURL, json={"query": query}, headers=headers)

import httpx
from src.taxiapp.config import config  # pitää olla digitransit_key

# Esimerkki _fetch_suomenlinna:
async def _fetch_suomenlinna_fixed(self, client: httpx.AsyncClient):
    """Hae Suomenlinna-lautan seuraavat lähdetyt HSL Reittiopas APIsta.
    
    KORJAUS: Digitransit vaatii subscription-avaimen 2024 alkaen.
    """
    query = {
        "query": """
        {
          stop(id: "HSL:1020452") {
            name
            stoptimesWithoutPatterns(numberOfDepartures: 6) {
              scheduledArrival
              realtimeArrival
              serviceDay
              trip {
                route {
                  shortName
                  longName
                }
              }
            }
          }
        }
        """
    }
    
    headers = {
        "Content-Type": "application/json",
        "digitransit-subscription-1-api-key": config.digitransit_key,  # ← KORJAUS
    }
    
    try:
        resp = await client.post(
            "https://api.digitransit.fi/routing/v1/routers/hsl/index/graphql",
            json=query,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        arrivals = parse_hsl_suomenlinna(data)
        return arrivals, None
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return [], "HSL API: Digitransit API-avain puuttuu tai virheellinen (401)"
        return [], f"HSL API HTTP {e.response.status_code}"
    except Exception as e:
        return [], f"HSL API virhe: {e}"
