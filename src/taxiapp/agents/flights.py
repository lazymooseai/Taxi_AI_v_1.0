async def fetch_finavia_flights() -> List[FlightArrival]:
    """
    Hakee saapuvat lennot Finavian API:sta.
    Jos API-avainta ei ole, palauttaa testidataa Streamlit-kehitystä varten.
    """
    app_id = os.getenv("FINAVIA_APP_ID")
    app_key = os.getenv("FINAVIA_APP_KEY")
    
    # 1. TESTITILA: Jos avaimia ei ole, annetaan Streamlitille testidataa
    if not app_id or not app_key:
        logger.info("Finavia API-avaimia ei löydetty. Palautetaan testidataa Streamlitia varten.")
        return [
            make_test_flight("AY123", eta_minutes=15, delay_minutes=0, origin_city="Oulu"),
            make_test_flight("AY456", eta_minutes=45, delay_minutes=35, origin_city="Lontoo"), # Tämä on myöhässä!
            make_test_flight("D8700", eta_minutes=90, delay_minutes=0, origin_city="Tukholma")
        ]

    # 2. TUOTANTOTILA: Haetaan aito data
    url = "https://api.finavia.fi/flights/public/v0/airport/EFHK/arr"
    headers = {
        "app_id": app_id,
        "app_key": app_key
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            flights = []
            # Finavian API:n datan rakenne vaihtelee, oletetaan lista lennoista
            flight_list = data.get('arr', data) if isinstance(data, dict) else data
            
            for item in flight_list:
                try:
                    # Parsitaan päivämäärät (Finavia käyttää ISO 8601 muotoa)
                    sdt_str = item.get("sdt", "") # Scheduled Departure/Arrival Time
                    scheduled = datetime.fromisoformat(sdt_str.replace("Z", "+00:00")) if sdt_str else datetime.now(timezone.utc)
                    
                    eta_str = item.get("eta", "") # Estimated Time of Arrival
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
                    logger.warning(f"Virhe yksittäisen lennon parsinnassa: {e}")
                    continue

            logger.info(f"Haettiin ja parsittiin {len(flights)} aitoa lentoa Finavialta.")
            return flights
            
    except Exception as e:
        logger.error(f"Virhe Finavia-rajapinnassa: {e}")
        return []
