"""
flights.py - Finavia EFHK lentoagentti
Helsinki Taxi AI

Hakee saapuvat lennot Helsinki-Vantaan lentokentalita.
Aikaikkuna: seuraavat 2h
Maksimi: 7 lentoa
ttl = 300s (5 min)

API: Finavia FlightAPI v0
  GET /flights/public/v0/airport/{icao}/arr
  ICAO: EFHK (Helsinki-Vantaa)
  Headers: app_id + app_key (Finavia developer portal)

Fallback: Jos Finavia API ei saatavilla -> scrape Finavia-sivulta
  https://www.finavia.fi/fi/lentokentat/helsinki-vantaa/lennot/saapuvat-lennot

Signaalit (CEO prioriteetti):
  Taso 4 KRIITTINEN (urgency 8): lento >60min myohassa
  Taso 3 KORKEA    (urgency 6): lento saapuu 0-10min
  Taso 2 NORMAALI  (urgency 5): lento saapuu 10-30min, iso kone
  Taso 1 PERUS     (urgency 3): lento saapuu 30-60min
  Myohassa >30min  (urgency 7): kriittinen myohastyminen
  Myohassa >15min  (urgency 5): kohtalainen myohastyminen
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger(__name__)
from src.taxiapp.config import config


# ==============================================================
# VAKIOT
# ==============================================================

EFHK_ICAO        = "EFHK"
AREA             = "Lentokentta"
TIKKURILA_AREA   = "Tikkurila"   # Tikkurila on gateway lentokentalle
MAX_FLIGHTS      = 7
LOOKAHEAD_HOURS  = 2

FINAVIA_API_BASE = "https://api.finavia.fi/flights/public/v0"
FINAVIA_FLIGHT_INFO_URL = (
    "https://www.finavia.fi/fi/lentokentat/helsinki-vantaa/lennot/saapuvat-lennot"
)

# OpenSky Network — avoin ilmailutietokanta, ei API-avainta tarvita
# Dokumentaatio: https://openskynetwork.github.io/opensky-api/rest.html
OPENSKY_ARRIVALS_URL = "https://opensky-network.org/api/flights/arrival"
OPENSKY_STATES_URL   = "https://opensky-network.org/api/states/all"
EFHK_BOX = {          # Helsinki-Vantaa bounding box
    "lamin": 60.28, "lamax": 60.37,
    "lomin": 24.88, "lomax": 25.05,
}

# Finavia uusi avoin lentodata-API (ei avaimia)
FINAVIA_OPEN_URL = "https://www.finavia.fi/api/flights/arrivals?airport=HEL"

# Lentokoneiden kapasiteettiluokat (ICAO type -> matkustajat)
AIRCRAFT_CAPACITY: dict[str, int] = {
    # Suuret (>300 pax)
    "A380": 525, "B748": 410, "A342": 380, "A343": 370,
    "A345": 400, "A346": 380, "B744": 420, "B773": 350,
    "B77W": 370, "B77L": 350, "B788": 250, "B789": 290,
    "B78X": 320, "A359": 314, "A35K": 369, "A333": 300,
    "A332": 290, "A339": 300,
    # Keskikokoiset (150-300 pax)
    "B738": 189, "B737": 149, "B739": 215, "A320": 180,
    "A321": 220, "A319": 140, "A20N": 180, "A21N": 220,
    "B38M": 178, "B39M": 204, "A318": 107,
    # Pienet (<150 pax)
    "AT75": 70,  "AT72": 68,  "AT73": 68,  "DH8D": 78,
    "E190": 100, "E195": 120, "E170": 76,  "E175": 80,
    "CRJ9": 90,  "CRJ7": 70,
}

def _estimate_pax(aircraft_type: str) -> int:
    """Arvioi matkustajamäärä konetyypin perusteella."""
    if not aircraft_type:
        return 150  # Oletusarvo
    t = aircraft_type.upper().strip()
    return AIRCRAFT_CAPACITY.get(t, 150)


# ==============================================================
# LENTO-DATACLASS
# ==============================================================

@dataclass
class FlightArrival:
    """Yksittaisen lennon saapumistiedot EFHK:lle."""
    flight_no:      str
    airline:        str
    origin:         str
    origin_city:    str
    scheduled_at:   datetime
    estimated_at:   Optional[datetime] = None
    actual_at:      Optional[datetime] = None
    status:         str = "scheduled"
    aircraft_type:  str = ""
    terminal:       str = "T2"
    gate:           str = ""
    belt:           str = ""
    cancelled:      bool = False

    @property
    def effective_at(self) -> datetime:
        return self.actual_at or self.estimated_at or self.scheduled_at

    @property
    def delay_minutes(self) -> int:
        best = self.estimated_at or self.actual_at
        if best is None:
            return 0
        delta = (best - self.scheduled_at).total_seconds() / 60
        return max(0, int(delta))

    @property
    def minutes_until_arrival(self) -> float:
        return (self.effective_at - datetime.now(timezone.utc)).total_seconds() / 60

    @property
    def estimated_pax(self) -> int:
        return _estimate_pax(self.aircraft_type)

    def is_large_aircraft(self) -> bool:
        return self.estimated_pax >= 250

    def is_arriving_soon(self, minutes: float = 30) -> bool:
        eta = self.minutes_until_arrival
        return -5 <= eta <= minutes

    def delay_label(self) -> str:
        d = self.delay_minutes
        if d == 0:  return "ajallaan"
        return f"+{d} min myohassa"

    def label(self) -> str:
        return f"{self.flight_no} {self.origin_city or self.origin}"

    def short_info(self) -> str:
        d = self.delay_label()
        return (
            f"{self.flight_no} {self.origin_city or self.origin} "
            f"-> T{self.terminal} | {d}"
        )


# ==============================================================
# LENTOKENTTAAGENTTI
# ==============================================================

class FlightAgent(BaseAgent):
    """
    Hakee saapuvat lennot EFHK:lle.
    Yritysjärjestys: Finavia API -> HTML-scrape.
    Paivittyy 5 min valein (ttl=300).
    """

    name = "FlightAgent"
    ttl  = 300

    async def fetch(self) -> AgentResult:
        flights: list[FlightArrival] = []
        source_used = "none"
        error_msg: Optional[str] = None

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={
                "User-Agent": "HelsinkiTaxiAI/1.0 (+https://github.com)",
                "Accept":     "application/json",
            },
            follow_redirects=True,
        ) as client:

            # == 1. Yrita Finavia API =========================
            if config.finavia_app_id and config.finavia_app_key:
                flights, err = await self._fetch_finavia_api(client)
                if err:
                    self.logger.warning(f"Finavia API: {err}")
                    error_msg = err
                else:
                    source_used = "finavia_api"

            # == 2. Fallback: HTML-scrape ======================
            if not flights:
                flights, err2 = await self._fetch_html_fallback(client)
                if err2:
                    self.logger.warning(f"HTML-scrape: {err2}")
                    if error_msg:
                        error_msg = f"{error_msg} | {err2}"
                    else:
                        error_msg = err2
                else:
                    source_used = "html_scrape"

        if not flights:
            return self._error(
                f"EFHK ei saatavilla: {error_msg or 'tuntematon virhe'}"
            )

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=LOOKAHEAD_HOURS)
        arriving = [
            f for f in flights
            if not f.cancelled
            and f.effective_at >= now - timedelta(minutes=5)
            and f.effective_at <= cutoff
        ]
        arriving.sort(key=lambda f: f.effective_at)
        arriving = arriving[:MAX_FLIGHTS]

        signals = self._build_signals(arriving)
        signals.sort(key=lambda s: s.urgency, reverse=True)

        raw = {
            "airport":       EFHK_ICAO,
            "source":        source_used,
            "total_flights": len(arriving),
            "flights": [
                {
                    "flight":    f.flight_no,
                    "origin":    f.origin_city or f.origin,
                    "scheduled": f.scheduled_at.isoformat(),
                    "estimated": f.estimated_at.isoformat()
                                 if f.estimated_at else None,
                    "delay_min": f.delay_minutes,
                    "eta_min":   round(f.minutes_until_arrival, 1),
                    "status":    f.status,
                    "terminal":  f.terminal,
                    "aircraft":  f.aircraft_type,
                    "pax_est":   f.estimated_pax,
                }
                for f in arriving
            ],
            "error": error_msg,
        }

        self.logger.info(
            f"FlightAgent: {len(arriving)} lentoa ({source_used}) "
            f"-> {len(signals)} signaalia"
        )
        return self._ok(signals, raw_data=raw)

    # == Finavia REST API =======================================

    async def _fetch_finavia_api(
        self, client: httpx.AsyncClient
    ) -> tuple[list[FlightArrival], Optional[str]]:
        """Hae saapuvat lennot Finavia API:sta."""
        url = f"{FINAVIA_API_BASE}/airport/{EFHK_ICAO}/arr"
        headers = {
            "app_id":  config.finavia_app_id or "",
            "app_key": config.finavia_app_key or "",
            "Accept":  "application/json",
        }
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            flights = _parse_finavia_json(data)
            self.logger.debug(f"Finavia API: {len(flights)} lentoa")
            return flights, None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return [], "Finavia API: virheelliset tunnukset (401)"
            if e.response.status_code == 403:
                return [], "Finavia API: ei oikeuksia (403)"
            return [], f"Finavia API HTTP {e.response.status_code}"
        except httpx.RequestError as e:
            return [], f"Finavia API verkkovirhe: {e}"
        except Exception as e:
            return [], f"Finavia API virhe: {e}"

    # == OpenSky fallback ======================================

    async def _fetch_html_fallback(
        self, client: httpx.AsyncClient
    ) -> tuple[list[FlightArrival], Optional[str]]:
        """
        Fallback-ketju kun Finavia API ei ole käytössä:
          1. OpenSky Network /flights/arrival — avoin, ei avaimia
          2. OpenSky Network /states/all     — bounding box EFHK
          3. Tyhjä lista + virheviesti

        OpenSky rajoitukset:
          - Anonyymi: 400 pyyntöä / päivä, max 10s historia-ikkuna
          - Rekisteröitynyt: 4000 pyyntöä / päivä
          - 5s TTL riittää koska FlightAgent.ttl = 300s
        """
        # Yritys 1: OpenSky arrivals endpoint
        flights, err = await self._fetch_opensky_arrivals(client)
        if flights:
            self.logger.info(f"OpenSky arrivals: {len(flights)} lentoa")
            return flights, None

        # Yritys 2: OpenSky states bounding box (reaaliaikainen sijainti)
        flights2, err2 = await self._fetch_opensky_states(client)
        if flights2:
            self.logger.info(f"OpenSky states: {len(flights2)} lentoa")
            return flights2, None

        combined_err = " | ".join(filter(None, [err, err2]))
        return [], combined_err or "OpenSky: ei lentoja"

    async def _fetch_opensky_arrivals(
        self, client: httpx.AsyncClient
    ) -> tuple[list[FlightArrival], Optional[str]]:
        """
        OpenSky Network /flights/arrival
        Hakee viimeisen 2h saapuvat lennot EFHK:lle.
        Dokumentaatio: https://openskynetwork.github.io/opensky-api/rest.html
        """
        import time as _t
        now_ts   = int(_t.time())
        begin_ts = now_ts - 7200   # 2h taaksepäin
        try:
            resp = await client.get(
                OPENSKY_ARRIVALS_URL,
                params={
                    "airport": EFHK_ICAO,
                    "begin":   begin_ts,
                    "end":     now_ts,
                },
                headers={
                    "Accept": "application/json",
                    # User-Agent pakollinen OpenSky:lle
                    "User-Agent": "HelsinkiTaxiAI/1.1 (opensource; contact@example.com)",
                },
                timeout=httpx.Timeout(12.0),
            )
            resp.raise_for_status()
            data = resp.json()
            flights = _parse_opensky_arrivals(data)
            return flights, None
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 429:
                return [], "OpenSky arrivals: rate limit (429)"
            if code == 503:
                return [], "OpenSky arrivals: ei saatavilla (503)"
            return [], f"OpenSky arrivals HTTP {code}"
        except Exception as e:
            return [], f"OpenSky arrivals virhe: {e}"

    async def _fetch_opensky_states(
        self, client: httpx.AsyncClient
    ) -> tuple[list[FlightArrival], Optional[str]]:
        """
        OpenSky Network /states/all bounding box.
        Palauttaa reaaliaikaiset lennot EFHK:n lähialueella.
        Laskeutumisessa olevat koneet tunnistetaan matalasta korkeudesta.
        """
        try:
            resp = await client.get(
                OPENSKY_STATES_URL,
                params=EFHK_BOX,
                headers={
                    "Accept":     "application/json",
                    "User-Agent": "HelsinkiTaxiAI/1.1",
                },
                timeout=httpx.Timeout(10.0),
            )
            resp.raise_for_status()
            data = resp.json()
            flights = _parse_opensky_states(data)
            return flights, None
        except httpx.HTTPStatusError as e:
            return [], f"OpenSky states HTTP {e.response.status_code}"
        except Exception as e:
            return [], f"OpenSky states virhe: {e}"

    # == Signaalien rakentaminen ================================

    def _build_signals(
        self, flights: list[FlightArrival]
    ) -> list[Signal]:
        """
        Muunna saapuvat lennot signaaleiksi.
        Lentokentta + Tikkurila (juna-yhteys) saavat signaalit.
        Pisteet skaalautuvat matkustajamäärän mukaan.
        """
        signals: list[Signal] = []

        for flight in flights:
            for area in [AREA, TIKKURILA_AREA]:
                sig = self._flight_to_signal(flight, area)
                if sig:
                    signals.append(sig)

        return _dedup_signals(signals)

    def _flight_to_signal(
        self, flight: FlightArrival, area: str
    ) -> Optional[Signal]:
        eta    = flight.minutes_until_arrival
        delay  = flight.delay_minutes
        pax    = flight.estimated_pax

        if eta < -5 or eta > 120:
            return None

        score_base = max(5.0, pax / 10.0)

        if area == TIKKURILA_AREA:
            score_base *= 0.4

        # == Myohastymisbonus ==================================
        delay_urgency = 1
        delay_bonus   = 0.0
        delay_reason  = None

        if delay >= 60:
            delay_urgency = 8
            delay_bonus   = 30.0
            delay_reason  = (
                f"\U0001F6A8 {flight.flight_no} MYOHASSA {delay}min "
                f"({flight.origin_city or flight.origin})"
            )
        elif delay >= 30:
            delay_urgency = 7
            delay_bonus   = 18.0
            delay_reason  = (
                f"\u26a0 {flight.flight_no} myohassa {delay}min "
                f"({flight.origin_city or flight.origin})"
            )
        elif delay >= 15:
            delay_urgency = 5
            delay_bonus   = 8.0
            delay_reason  = (
                f"\u23f0 {flight.flight_no} +{delay}min "
                f"({flight.origin_city or flight.origin})"
            )

        # == ETA-urgency =======================================
        if 0 <= eta <= 10:
            eta_urgency = 6
            eta_score   = score_base * 1.5
            eta_reason  = (
                f"\u2708 {flight.flight_no} laskeutuu ~{max(0,int(eta))}min "
                f"({flight.origin_city or flight.origin})"
            )
        elif 10 < eta <= 30:
            eta_urgency = 5 if flight.is_large_aircraft() else 4
            eta_score   = score_base * 1.2
            eta_reason  = (
                f"\u2708 {flight.flight_no} saapuu {int(eta)}min paasta "
                f"({flight.origin_city or flight.origin})"
            )
        elif 30 < eta <= 60:
            eta_urgency = 3
            eta_score   = score_base
            eta_reason  = (
                f"\u2708 {flight.flight_no} saapuu {int(eta)}min paasta"
            )
        else:
            eta_urgency = 2
            eta_score   = score_base * 0.6
            eta_reason  = (
                f"\u2708 {flight.flight_no} saapuu {int(eta)}min paasta"
            )

        final_urgency = max(delay_urgency, eta_urgency)
        final_score   = round(eta_score + delay_bonus, 1)
        reason        = delay_reason or eta_reason

        expires = flight.effective_at + timedelta(minutes=20)

        return Signal(
            area=area,
            score_delta=final_score,
            reason=reason,
            urgency=final_urgency,
            expires_at=expires,
            source_url=f"https://www.finavia.fi/lennot/{flight.flight_no}",
        )


# ==============================================================
# FINAVIA JSON -JASENNIN
# ==============================================================

def _parse_finavia_json(data: dict | list) -> list[FlightArrival]:
    """
    Jasenna Finavia API JSON -> lista FlightArrival-olioita.
    Finavia API palauttaa rakenteen:
      { "body": { "flights": { "flight": [...] } } }
    tai suoraan listan.
    """
    flights: list[FlightArrival] = []

    if isinstance(data, dict):
        body = data.get("body", data)
        if isinstance(body, dict):
            inner = body.get("flights", body)
            if isinstance(inner, dict):
                raw_list = inner.get("flight", [])
            else:
                raw_list = inner if isinstance(inner, list) else []
        else:
            raw_list = body if isinstance(body, list) else []
    elif isinstance(data, list):
        raw_list = data
    else:
        return flights

    if isinstance(raw_list, dict):
        raw_list = [raw_list]

    for item in raw_list:
        if not isinstance(item, dict):
            continue
        try:
            flight = _parse_finavia_item(item)
            if flight:
                flights.append(flight)
        except Exception:
            continue

    return flights


def _parse_finavia_item(item: dict) -> Optional[FlightArrival]:
    """Jasenna yksi Finavia JSON-lentoalkio."""
    flight_no   = (item.get("fltnr") or item.get("flightno") or
                   item.get("flight_no") or "").strip()
    if not flight_no:
        return None

    airline     = (item.get("airline") or item.get("al") or
                   item.get("airlinename") or "").strip()
    origin      = (item.get("orig") or item.get("origin") or
                   item.get("dep_iata") or "").strip()
    origin_city = (item.get("orig_name") or item.get("origin_name") or
                   item.get("dep_city") or origin).strip()
    aircraft    = (item.get("actype") or item.get("aircraft_type") or
                   item.get("ac_type") or "").strip()
    terminal    = str(item.get("terminal") or item.get("term") or "2")
    gate        = str(item.get("gate") or "")
    belt        = str(item.get("belt") or item.get("baggage_belt") or "")
    status_raw  = (item.get("status") or item.get("flt_status") or
                   "scheduled").lower()

    sched_str = (item.get("sched") or item.get("scheduled") or
                 item.get("std") or item.get("sta") or "")
    estim_str = (item.get("estimate") or item.get("estimated") or
                 item.get("etd") or item.get("eta") or "")
    actual_str = (item.get("actual") or item.get("atd") or
                  item.get("ata") or "")

    scheduled = _parse_dt_flex(sched_str)
    if scheduled is None:
        return None

    estimated = _parse_dt_flex(estim_str)
    actual    = _parse_dt_flex(actual_str)
    cancelled = "cancel" in status_raw or status_raw == "c"

    return FlightArrival(
        flight_no=flight_no,
        airline=airline,
        origin=origin,
        origin_city=origin_city,
        scheduled_at=scheduled,
        estimated_at=estimated,
        actual_at=actual,
        status=status_raw,
        aircraft_type=aircraft,
        terminal=terminal,
        gate=gate,
        belt=belt,
        cancelled=cancelled,
    )


# ==============================================================
# OPENSKY NETWORK -JÄSENTIMET
# ==============================================================

def _parse_opensky_arrivals(data: list) -> list[FlightArrival]:
    """
    Jäsennä OpenSky /flights/arrival -vastaus.

    OpenSky palauttaa listan dictionaryja:
      {icao24, firstSeen, estDepartureAirport, lastSeen,
       estArrivalAirport, callsign, estDepartureAirportHorizDistance, ...}

    Muunna FlightArrival-olioiksi — käytetään saapumisaikana lastSeen.
    """
    if not isinstance(data, list):
        return []

    flights: list[FlightArrival] = []
    now = datetime.now(timezone.utc)

    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            callsign = (item.get("callsign") or "").strip()
            if not callsign:
                continue

            # lastSeen = viimeisin havaintoaika (Unix timestamp)
            last_seen_ts = item.get("lastSeen") or item.get("firstSeen")
            if not last_seen_ts:
                continue

            arrival_dt = datetime.fromtimestamp(
                int(last_seen_ts), tz=timezone.utc
            )

            # Suodata: vain viimeisen 2h saapuneet tai seuraavan 1h saapuvat
            delta_min = (arrival_dt - now).total_seconds() / 60
            if delta_min < -120 or delta_min > 60:
                continue

            origin_icao = (
                item.get("estDepartureAirport") or ""
            ).strip()

            flights.append(FlightArrival(
                flight_no    = callsign[:8],
                airline      = callsign[:2],
                origin       = origin_icao,
                origin_city  = _icao_to_city(origin_icao),
                scheduled_at = arrival_dt,
                estimated_at = arrival_dt,
                status       = "landed" if delta_min < 0 else "scheduled",
            ))
        except Exception:
            continue

    return flights[:MAX_FLIGHTS]


def _parse_opensky_states(data: dict) -> list[FlightArrival]:
    """
    Jäsennä OpenSky /states/all bounding box -vastaus.

    Kentät per state vector (indeksit):
      0:icao24, 1:callsign, 2:origin_country, 3:time_position,
      4:last_contact, 5:longitude, 6:latitude, 7:baro_altitude,
      8:on_ground, 9:velocity, 10:true_track, 11:vertical_rate,
      12:sensors, 13:geo_altitude, 14:squawk, 15:spi, 16:position_source

    Tunnistetaan lähestyvät koneet: on_ground=False, baro_altitude < 3000m,
    vertical_rate < 0 (laskeutuminen).
    """
    if not isinstance(data, dict):
        return []

    states = data.get("states") or []
    flights: list[FlightArrival] = []
    now = datetime.now(timezone.utc)

    for state in states:
        if not isinstance(state, (list, tuple)) or len(state) < 12:
            continue
        try:
            callsign       = str(state[1] or "").strip()
            on_ground      = bool(state[8])
            baro_altitude  = state[7]   # metrit (None jos ei saatavilla)
            vertical_rate  = state[11]  # m/s (negatiivinen = laskee)
            last_contact   = state[4]   # Unix timestamp

            if not callsign:
                continue

            # Suodata: vain ilmassa olevat, matalalla, laskeutumassa
            if on_ground:
                continue
            if baro_altitude is not None and baro_altitude > 4000:
                continue
            if vertical_rate is not None and vertical_rate > 2:
                continue  # Nousee tai tasalento

            # Arvioi saapumisaika: korkeus / laskeutumisnopeus
            eta_min = 5.0   # Oletus: 5 min
            if baro_altitude and vertical_rate and vertical_rate < -1:
                eta_sec = abs(baro_altitude / vertical_rate)
                eta_min = max(1.0, min(30.0, eta_sec / 60))

            arrival_dt = now + timedelta(minutes=eta_min)

            flights.append(FlightArrival(
                flight_no    = callsign[:8],
                airline      = callsign[:2],
                origin       = "",
                origin_city  = "",
                scheduled_at = arrival_dt,
                estimated_at = arrival_dt,
                status       = "approaching",
            ))
        except Exception:
            continue

    return flights[:MAX_FLIGHTS]


# ICAO-lentokenttäkoodi → kaupungin nimi (yleisimmät reitit EFHK:lle)
_ICAO_CITIES: dict[str, str] = {
    "EFHK": "Helsinki",   "ESSA": "Tukholma",  "EKCH": "Kööpenhamina",
    "ENGM": "Oslo",       "EFTU": "Turku",      "EFTP": "Tampere",
    "EGLL": "Lontoo",     "EHAM": "Amsterdam",  "EDDF": "Frankfurt",
    "LFPG": "Pariisi",    "LEMD": "Madrid",     "LIRF": "Rooma",
    "UUEE": "Moskova",    "LTFM": "Istanbul",   "VHHH": "Hongkong",
    "RJTT": "Tokio",      "OMDB": "Dubai",      "ZBAA": "Peking",
    "KJFK": "New York",   "CYYZ": "Toronto",    "WMKK": "Kuala Lumpur",
    "WSSS": "Singapore",  "OTHH": "Doha",       "OERK": "Riad",
}


def _icao_to_city(icao: str) -> str:
    """Muunna ICAO-lentokenttäkoodi kaupungin nimeksi."""
    return _ICAO_CITIES.get(icao.upper(), icao)


# ==============================================================
# FINAVIA HTML-SCRAPER (säilytetään legacy-fallbackina)
# ==============================================================

def _parse_finavia_html(html: str) -> list[FlightArrival]:
    """
    Scrape Finavia.fi saapuvat-lennot-sivulta.
    Sivu kayttaa JavaScript-renderointia, joten etsitaan
    mahdollisia data-attribuutteja tai JSON-blokkeja.
    """
    flights: list[FlightArrival] = []

    json_blocks = re.findall(
        r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE
    )
    for block in json_blocks:
        try:
            import json
            data = json.loads(block.strip())
            parsed = _parse_finavia_json(data)
            if parsed:
                flights.extend(parsed)
        except Exception:
            continue

    if not flights:
        state_match = re.search(
            r'(?:window\.__(?:INITIAL_STATE|DATA|FLIGHTS)__|var flights)\s*=\s*(\{.*?\});',
            html, re.DOTALL
        )
        if state_match:
            try:
                import json
                data = json.loads(state_match.group(1))
                flights.extend(_parse_finavia_json(data))
            except Exception as e:
                logger.debug(f"Finavia HTML JSON-parsinta epaonnistui: {e}")
    if not flights:
        flights = _scrape_html_table(html)

    return flights


def _scrape_html_table(html: str) -> list[FlightArrival]:
    """
    Etsi lentotaulukkorivit HTML:sta regex-pohjaisesti.
    Toimii Finavia-sivun taulukkorakenteen kanssa.
    """
    flights: list[FlightArrival] = []
    now     = datetime.now(timezone.utc)

    pattern = re.compile(
        r'([A-Z]{2}\d{1,4})\D+?'
        r'(\d{2}:\d{2})',
        re.IGNORECASE
    )
    for m in pattern.finditer(html):
        flight_no = m.group(1).upper()
        time_str  = m.group(2)
        try:
            h, mins = map(int, time_str.split(":"))
            sched = now.replace(hour=h, minute=mins, second=0, microsecond=0)
            if sched < now - timedelta(hours=1):
                sched += timedelta(days=1)
            flights.append(FlightArrival(
                flight_no=flight_no,
                airline="",
                origin="",
                origin_city="",
                scheduled_at=sched,
            ))
        except Exception:
            continue

    seen: set[str] = set()
    unique: list[FlightArrival] = []
    for f in flights:
        key = f"{f.flight_no}_{f.scheduled_at.strftime('%H:%M')}"
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique[:MAX_FLIGHTS * 2]


# ==============================================================
# APUFUNKTIOT
# ==============================================================

def _parse_dt_flex(s: str) -> Optional[datetime]:
    """
    Joustava aikaleiman jasennin - tukee useita muotoja.
    Finavia kayttaa seka ISO 8601 etta dd.MM.yyyy HH:mm -muotoja.
    """
    if not s:
        return None
    s = s.strip()

    try:
        return datetime.fromisoformat(
            s.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except ValueError:
        pass

    for fmt in [
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M",
    ]:
        try:
            dt = datetime.strptime(s, fmt)
            import time as _time
            offset = 3 if _time.daylight else 2
            return (dt - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    m = re.match(r'^(\d{2}):(\d{2})$', s)
    if m:
        now = datetime.now(timezone.utc)
        h, mins = int(m.group(1)), int(m.group(2))
        dt = now.replace(hour=h, minute=mins, second=0, microsecond=0)
        if dt < now - timedelta(hours=1):
            dt += timedelta(days=1)
        return dt

    return None


def _dedup_signals(signals: list[Signal]) -> list[Signal]:
    """
    Poista signaaliduplikaatit per alue.
    Sama alue -> summaa pisteet, pida korkein urgency.
    """
    by_area: dict[str, Signal] = {}
    for sig in signals:
        if sig.area not in by_area:
            by_area[sig.area] = sig
        else:
            ex = by_area[sig.area]
            if sig.urgency >= ex.urgency:
                by_area[sig.area] = Signal(
                    area=sig.area,
                    score_delta=round(ex.score_delta + sig.score_delta, 1),
                    reason=sig.reason,
                    urgency=sig.urgency,
                    expires_at=max(sig.expires_at, ex.expires_at),
                    source_url=sig.source_url,
                )
            else:
                by_area[sig.area] = Signal(
                    area=ex.area,
                    score_delta=round(ex.score_delta + sig.score_delta, 1),
                    reason=ex.reason,
                    urgency=ex.urgency,
                    expires_at=max(sig.expires_at, ex.expires_at),
                    source_url=ex.source_url,
                )
    return list(by_area.values())


# ==============================================================
# TESTIAPU
# ==============================================================

def make_test_flight(
    flight_no: str = "AY123",
    eta_minutes: float = 15.0,
    delay_minutes: int = 0,
    aircraft_type: str = "B738",
    origin_city: str = "London",
    cancelled: bool = False,
) -> FlightArrival:
    """Luo testilentoliitos annetuilla parametreilla."""
    now = datetime.now(timezone.utc)
    scheduled = now + timedelta(minutes=eta_minutes)
    estimated = (
        now + timedelta(minutes=eta_minutes + delay_minutes)
        if delay_minutes > 0 else None
    )
    return FlightArrival(
        flight_no=flight_no,
        airline="Test Air",
        origin="LHR",
        origin_city=origin_city,
        scheduled_at=scheduled,
        estimated_at=estimated,
        aircraft_type=aircraft_type,
        cancelled=cancelled,
    )
