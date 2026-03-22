"""
flights.py - Lentoliikenteen agentti (Helsinki-Vantaa, HEL)
Helsinki Taxi AI | Päivittyy 3 min välein (ttl=180)
Käyttää FlightRadar24 API + fallback staattiseen dataan
"""
from __future__ import annotations
import logging, json, re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger(__name__)

# Helsinki-Vantaa ICAO/IATA koodit
AIRPORT_CODES = {
    "EFHK": "Helsinki-Vantaa",  # ICAO
    "HEL": "Helsinki-Vantaa",   # IATA
}

# FlightRadar24 API-endpointit
FR24_BASE = "https://api.flightradar24.com/common/v1"
FR24_AIRPORT = f"{FR24_BASE}/airport/activity"
FR24_FLIGHTS = f"{FR24_BASE}/flight"

# Fallback URL
FR24_WEB = "https://www.flightradar24.com/data/flights"

@dataclass
class FlightArrival:
    callsign: str           # Lentoyhtiön koodi + numero (AY123)
    aircraft: str          # Koneen tyyppi (A320, B787, etc)
    origin: str            # Lähtökaupunki
    scheduled_at: datetime # Aikataulussa saapuu
    estimated_at: Optional[datetime] = None  # Todennäköinen saapumisaika
    airline: str = ""      # Lentoyhtiö (Finnair, SAS, etc)
    status: str = "scheduled"  # scheduled, boarding, landed, cancelled
    source: str = ""

    @property
    def area(self):
        return "Lentokenttä"  # Helsinki-Vantaan alue

    @property
    def effective_at(self):
        return self.estimated_at or self.scheduled_at

    @property
    def minutes_until_arrival(self):
        return (self.effective_at - datetime.now(timezone.utc)).total_seconds() / 60

    def short_info(self):
        eta = self.minutes_until_arrival
        status_emoji = "✈️" if eta > 0 else "🛬"
        if eta < 0:
            return f"{status_emoji} {self.callsign} ({self.airline}) LASKEUTUNUT"
        return f"{status_emoji} {self.callsign} ({self.airline}) {self.origin} -> ~{max(0,int(eta))}min"

def _parse_flightradar24_api(data):
    """Jäsennä FlightRadar24 API-vastaus."""
    arrivals = []

    try:
        # Yleinen FlightRadar24-formaatti
        for item in data if isinstance(data, list) else data.get("data", []):
            if isinstance(item, dict):
                try:
                    callsign = (item.get("identification", {}).get("callsign") or
                               item.get("callsign") or "").upper().strip()
                    airline = (item.get("airline", {}).get("name") or
                              item.get("airline") or "Unknown").strip()
                    aircraft = (item.get("aircraft", {}).get("model") or
                               item.get("aircraft") or "Unknown").strip()

                    origin = (item.get("trail", [{}])[-1].get("origin") or
                             item.get("origin") or "Unknown").strip()

                    status = (item.get("status", {}).get("text") or
                             item.get("status") or "scheduled").lower()

                    # Aika UTC:ssa
                    scheduled_ts = item.get("time", {}).get("scheduled", {}).get("arrival") or item.get("eta")
                    if isinstance(scheduled_ts, (int, float)):
                        scheduled = datetime.fromtimestamp(scheduled_ts, tz=timezone.utc)
                    else:
                        continue

                    estimated_ts = item.get("time", {}).get("real", {}).get("arrival")
                    estimated = None
                    if isinstance(estimated_ts, (int, float)):
                        estimated = datetime.fromtimestamp(estimated_ts, tz=timezone.utc)

                    if callsign and airline and scheduled:
                        arrivals.append(FlightArrival(
                            callsign=callsign, aircraft=aircraft, origin=origin,
                            scheduled_at=scheduled, estimated_at=estimated,
                            airline=airline, status=status, source="fr24_api"))
                except:
                    pass
    except Exception as e:
        logger.debug(f"FR24 API jäsennys epäonnistui: {e}")

    return arrivals

def _static_flights_fallback():
    """Staattinen lentoliikenteen aikataulufallback."""
    now = datetime.now(timezone.utc)

    _STATIC = [
        ("AY031", "Finnair", "A350", "Helsinki", 6, 45, "scheduled"),
        ("AY027", "Finnair", "A321", "Stockholm", 7, 15, "scheduled"),
        ("LH910", "Lufthansa", "A320", "Munich", 8, 0, "scheduled"),
        ("BA956", "British Airways", "B787", "London", 8, 30, "scheduled"),
        ("SQ022", "Singapore Airlines", "A380", "Singapore", 9, 0, "scheduled"),
        ("BA950", "British Airways", "A321", "London", 10, 15, "scheduled"),
        ("AY105", "Finnair", "A320", "Berlin", 11, 0, "scheduled"),
        ("SU301", "Aeroflot", "A320", "Moscow", 12, 0, "scheduled"),
    ]

    arrivals = []
    for callsign, airline, aircraft, origin, h, m, status in _STATIC:
        sched = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if sched < now - timedelta(minutes=5):
            sched += timedelta(days=1)

        arrivals.append(FlightArrival(
            callsign=callsign, aircraft=aircraft, origin=origin,
            scheduled_at=sched, airline=airline, status=status,
            source="static_fallback"))

    return arrivals

def _dedup_flight_signals(signals):
    """Deduplicoi per alue."""
    by_area = {}
    for sig in signals:
        if sig.area not in by_area:
            by_area[sig.area] = sig
        else:
            ex = by_area[sig.area]
            if sig.urgency >= ex.urgency:
                by_area[sig.area] = Signal(
                    area=sig.area, score_delta=round(ex.score_delta + sig.score_delta, 1),
                    reason=sig.reason, urgency=sig.urgency,
                    expires_at=max(sig.expires_at, ex.expires_at),
                    source_url=sig.source_url)
    return list(by_area.values())

class FlightsAgent(BaseAgent):
    """Lentoliikenteen agentti - hakee saapuvat lennot HEL:iin."""
    name = "FlightAgent"
    ttl = 180

    async def fetch(self) -> AgentResult:
        all_arrivals = []
        errors = []

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            headers={"User-Agent": "HelsinkiTaxiAI/1.0"},
            follow_redirects=True) as client:

            # Yritä FlightRadar24 API:ta
            try:
                # FR24 publinen API (ei auth required)
                resp = await client.get(
                    f"{FR24_AIRPORT}",
                    params={"airport": "HEL"},
                    follow_redirects=True,
                    timeout=httpx.Timeout(8.0))
                resp.raise_for_status()
                data = resp.json()
                arrivals = _parse_flightradar24_api(data)
                if arrivals:
                    all_arrivals.extend(arrivals)
                    logger.debug(f"FlightRadar24: {len(arrivals)} lentoa")
            except Exception as e:
                errors.append(f"FlightRadar24 API: {str(e)[:50]}")
                logger.debug(f"FR24 API epäonnistui: {e}")

            # Yritä web-scrape FlightRadar24:stä (fallback)
            if not all_arrivals:
                try:
                    resp = await client.get(FR24_WEB, follow_redirects=True)
                    resp.raise_for_status()
                    # Etsi JSON-dataa sivusta
                    for m in re.finditer(r'"(AY|BA|LH|SU|SK|AF|KL)\d{3,4}"', resp.text[:50000]):
                        pass  # Fallback pois käytöstä - liian kompleksi scrape
                    logger.debug("FlightRadar24 web: ei dataa")
                except:
                    pass

        # Fallback staattiseen aikatauluun
        if not all_arrivals:
            all_arrivals = _static_flights_fallback()
            errors.append("Käytetään staattista lentoaikataulua")
            logger.info("FlightsAgent: käytetään staattista aikataulua")

        # Suodata seuraavat 2h
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=2)
        arriving = [f for f in all_arrivals
                   if f.status != "cancelled"
                   and f.effective_at >= now - timedelta(minutes=10)
                   and f.effective_at <= cutoff]
        arriving.sort(key=lambda f: f.effective_at)

        signals = []
        for flight in arriving:
            eta = flight.minutes_until_arrival

            if eta < -10 or eta > 120:
                continue

            score = 8.0  # Lentoliikenne on aina merkitsevää

            if eta < 0:
                reason = f" {flight.callsign} ({flight.airline}) LASKEUTUNUT {flight.origin}sta"
                urgency = 1
                score = 3.0
            elif 0 <= eta <= 10:
                reason = f" {flight.callsign} ({flight.airline}) LASKEUTUU {max(0,int(eta))}min ({flight.origin})"
                urgency = 7
                score = 15.0
            elif 10 < eta <= 30:
                reason = f" {flight.callsign} ({flight.airline}) saapuu {int(eta)}min ({flight.origin})"
                urgency = 6
                score = 12.0
            elif 30 < eta <= 60:
                reason = f" {flight.callsign} ({flight.airline}) {int(eta)}min päästä ({flight.origin})"
                urgency = 5
                score = 10.0
            else:
                reason = f" {flight.callsign} ({flight.airline}) {int(eta)}min päästä"
                urgency = 3
                score = 6.0

            signals.append(Signal(
                area=flight.area, score_delta=round(score, 1),
                reason=reason, urgency=urgency,
                expires_at=flight.effective_at + timedelta(minutes=30),
                source_url=FR24_WEB))

        signals = _dedup_flight_signals(signals)
        signals.sort(key=lambda s: s.urgency, reverse=True)

        raw = {
            "airport": "HEL (Helsinki-Vantaa)",
            "total_flights": len(arriving),
            "signals": len(signals),
            "errors": errors,
            "arrivals": [
                {"callsign": f.callsign, "airline": f.airline,
                 "origin": f.origin, "eta_min": round(f.minutes_until_arrival, 1),
                 "status": f.status, "source": f.source}
                for f in arriving[:8]
            ]
        }

        logger.info(f"FlightsAgent: {len(arriving)} lentoa -> {len(signals)} signaalia")
        return self._ok(signals, raw_data=raw)
