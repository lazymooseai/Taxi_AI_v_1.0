"""
flights.py - Finavia EFHK lentoagentti
Helsinki Taxi AI

Hakee saapuvat lennot Helsinki-Vantaan lentokentalita.
Aikaikkuna: seuraavat 2h | Maksimi: 7 lentoa | ttl = 300s

API-ketju:
  1. Finavia REST API (jos app_id+app_key konfiguroitu)
  2. Finavia HTML scrape (useita URL-vaihtoehtoja)
  3. Flightradar24 (JSON tai HTML)

KORJAUKSET (bugfix_8):
  - FR24-parseri uudelleenkirjoitettu: yrittaa JSON-parsintaa ensin
    (FR24 /data/airports/hel/arrivals palauttaa JSON-rakenteen)
  - Finavia HTML-fallback: useita URL-vaihtoehtoja (vanha ?tab=arr antoi 404)
  - json-moduuli importattu eksplisiittisesti
"""

from __future__ import annotations

import json as _json
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

EFHK_ICAO      = "EFHK"
AREA           = "Lentokenttä"  # KORJATTU: vastaa areas.py AREAS-avainta
TIKKURILA_AREA = "Tikkurila"
MAX_FLIGHTS    = 7
LOOKAHEAD_HOURS = 2

FINAVIA_API_BASE = "https://api.finavia.fi/flights/public/v0"

# Useita URL-vaihtoehtoja -- kokeillataan jarjestyksessa (vanha ?tab=arr antoi 404)
FINAVIA_HTML_URLS: list[str] = [
    "https://www.finavia.fi/fi/lentokentat/helsinki-vantaa/lennot/saapuvat",
    "https://www.finavia.fi/fi/helsinki-vantaa/lennot",
    "https://www.finavia.fi/fi/lentokentat/helsinki-vantaa/lennot",
    "https://www.finavia.fi/fi/lentokentat/helsinki-vantaa",
]

FR24_URL = "https://www.flightradar24.com/data/airports/hel/arrivals"

# Lentokoneiden kapasiteettiluokat (ICAO type -> matkustajat)
AIRCRAFT_CAPACITY: dict[str, int] = {
    "A380": 525, "B748": 410, "A342": 380, "A343": 370,
    "A345": 400, "A346": 380, "B744": 420, "B773": 350,
    "B77W": 370, "B77L": 350, "B788": 250, "B789": 290,
    "B78X": 320, "A359": 314, "A35K": 369, "A333": 300,
    "A332": 290, "A339": 300,
    "B738": 189, "B737": 149, "B739": 215, "A320": 180,
    "A321": 220, "A319": 140, "A20N": 180, "A21N": 220,
    "B38M": 178, "B39M": 204, "A318": 107,
    "AT75": 70,  "AT72": 68,  "AT73": 68,  "DH8D": 78,
    "E190": 100, "E195": 120, "E170": 76,  "E175": 80,
    "CRJ9": 90,  "CRJ7": 70,
}


def _estimate_pax(aircraft_type: str) -> int:
    """Arvioi matkustajamaeaerae konetyypin perusteella."""
    if not aircraft_type:
        return 150
    t = aircraft_type.upper().strip()
    return AIRCRAFT_CAPACITY.get(t, 150)


# ==============================================================
# LENTO-DATACLASS
# ==============================================================

@dataclass
class FlightArrival:
    """Yksittaisen lennon saapumistiedot EFHK:lle."""
    flight_no:     str
    airline:       str
    origin:        str
    origin_city:   str
    scheduled_at:  datetime
    estimated_at:  Optional[datetime] = None
    actual_at:     Optional[datetime] = None
    status:        str = "scheduled"
    aircraft_type: str = ""
    terminal:      str = "T2"
    gate:          str = ""
    belt:          str = ""
    cancelled:     bool = False

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
        return (
            self.effective_at - datetime.now(timezone.utc)
        ).total_seconds() / 60

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
        if d == 0:
            return "ajallaan"
        return f"+{d} min myohassa"

    def label(self) -> str:
        return f"{self.flight_no} {self.origin_city or self.origin}"


# ==============================================================
# FLIGHTAGENT
# ==============================================================

class FlightAgent(BaseAgent):
    """
    Hakee saapuvat lennot EFHK:lle.
    Yritysjärjestys: Finavia API -> HTML scrape -> Flightradar24.
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
                "Accept":     "application/json, text/html",
            },
            follow_redirects=True,
        ) as client:

            # == 1. Finavia REST API ==========================
            if config.finavia_app_id and config.finavia_app_key:
                flights, err = await self._fetch_finavia_api(client)
                if err:
                    self.logger.warning(f"Finavia API: {err}")
                    error_msg = err
                else:
                    source_used = "finavia_api"

            # == 2. Finavia HTML fallback =====================
            if not flights:
                flights, err2 = await self._fetch_html_fallback(client)
                if err2:
                    self.logger.warning(f"HTML-scrape: {err2}")
                    error_msg = (error_msg + " | " + err2) if error_msg else err2
                else:
                    source_used = "html_scrape"

            # == 3. Flightradar24 fallback ====================
            if not flights:
                flights, err3 = await self._fetch_fr24(client)
                if err3:
                    self.logger.warning(f"FR24: {err3}")
                    error_msg = (error_msg + " | " + err3) if error_msg else err3
                else:
                    source_used = "flightradar24"

        if not flights:
            return self._error(
                f"EFHK ei saatavilla: {error_msg or 'tuntematon virhe'}"
            )

        now    = datetime.now(timezone.utc)
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
                    "estimated": (
                        f.estimated_at.isoformat() if f.estimated_at else None
                    ),
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

    # == HTML-scrape fallback ===================================

    async def _fetch_html_fallback(
        self, client: httpx.AsyncClient
    ) -> tuple[list[FlightArrival], Optional[str]]:
        """
        Fallback: kokeillaan useita Finavia.fi URL-vaihtoehtoja.
        Vanha ?tab=arr URL antoi 404 -- nyt loop useiden URL:ien yli.
        """
        last_err: Optional[str] = None
        for url in FINAVIA_HTML_URLS:
            try:
                resp = await client.get(
                    url, headers={"Accept": "text/html"}
                )
                if resp.status_code == 404:
                    last_err = f"HTML-scrape HTTP 404: {url}"
                    continue
                resp.raise_for_status()
                flights = _parse_finavia_html(resp.text)
                self.logger.debug(
                    f"HTML-scrape ({url}): {len(flights)} lentoa"
                )
                if not flights:
                    last_err = f"HTML-scrape: ei lentoja loydetty ({url})"
                    continue
                return flights, None
            except httpx.HTTPStatusError as e:
                last_err = f"HTML-scrape HTTP {e.response.status_code}"
                continue
            except httpx.RequestError as e:
                last_err = f"HTML-scrape verkkovirhe: {e}"
                continue
            except Exception as e:
                last_err = f"HTML-scrape virhe: {e}"
                continue
        return [], last_err or "HTML-scrape: kaikki URL:t epaonnistuivat"

    # == Flightradar24 fallback ================================

    async def _fetch_fr24(
        self, client: httpx.AsyncClient
    ) -> tuple[list["FlightArrival"], Optional[str]]:
        """
        Hae saapuvat lennot Flightradar24:sta.
        FR24 palauttaa JSON-rakenteen /data/airports/hel/arrivals -endpointissa.
        Parsinta: JSON ensin, sen jalkeen HTML regex.
        """
        try:
            resp = await client.get(
                FR24_URL,
                headers={
                    "Accept": "application/json, text/html",
                    "User-Agent": (
                        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
                    ),
                },
            )
            resp.raise_for_status()
            flights = _parse_fr24_response(resp.text)
            if not flights:
                return [], "FR24: ei lentoja loydetty"
            self.logger.info(f"FR24: {len(flights)} lentoa")
            return flights, None
        except httpx.HTTPStatusError as e:
            return [], f"FR24 HTTP {e.response.status_code}"
        except Exception as e:
            return [], f"FR24 virhe: {e}"

    # == Signaalien rakentaminen ================================

    def _build_signals(
        self, flights: list[FlightArrival]
    ) -> list[Signal]:
        """
        Muunna saapuvat lennot signaaleiksi.
        Lentokentta + Tikkurila saavat signaalit.
        Pisteet skaalautuvat matkustajamaeaeraen mukaan.
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
        eta   = flight.minutes_until_arrival
        delay = flight.delay_minutes
        pax   = flight.estimated_pax

        if eta < -5 or eta > 120:
            return None

        score_base = max(5.0, pax / 10.0)
        if area == TIKKURILA_AREA:
            score_base *= 0.4

        # Myoehastymisbonus
        delay_urgency = 1
        delay_bonus   = 0.0
        delay_reason  = None

        if delay >= 60:
            delay_urgency = 8
            delay_bonus   = 30.0
            delay_reason  = (
                f"\U0001f6a8 {flight.flight_no} MYOHASSA {delay}min "
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

        # ETA-urgency
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
        expires       = flight.effective_at + timedelta(minutes=20)

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
    flights: list[FlightArrival] = []

    if isinstance(data, dict):
        body = data.get("body", data)
        if isinstance(body, dict):
            inner = body.get("flights", body)
            raw_list = (
                inner.get("flight", [])
                if isinstance(inner, dict)
                else (inner if isinstance(inner, list) else [])
            )
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
    flight_no = (
        item.get("fltnr") or item.get("flightno") or
        item.get("flight_no") or ""
    ).strip()
    if not flight_no:
        return None

    airline     = (item.get("airline") or item.get("al") or "").strip()
    origin      = (item.get("orig") or item.get("origin") or
                   item.get("dep_iata") or "").strip()
    origin_city = (item.get("orig_name") or item.get("origin_name") or
                   item.get("dep_city") or origin).strip()
    aircraft    = (item.get("actype") or item.get("aircraft_type") or "").strip()
    terminal    = str(item.get("terminal") or item.get("term") or "2")
    status_raw  = (item.get("status") or "scheduled").lower()

    sched_str  = (item.get("sched") or item.get("scheduled") or
                  item.get("std") or item.get("sta") or "")
    estim_str  = (item.get("estimate") or item.get("estimated") or
                  item.get("eta") or "")
    actual_str = (item.get("actual") or item.get("ata") or "")

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
        cancelled=cancelled,
    )


# ==============================================================
# HTML-SCRAPER (Finavia.fi fallback)
# ==============================================================

def _parse_finavia_html(html: str) -> list[FlightArrival]:
    flights: list[FlightArrival] = []

    # Etsi JSON-blokkeja
    for block in re.findall(
        r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE
    ):
        try:
            data = _json.loads(block.strip())
            parsed = _parse_finavia_json(data)
            if parsed:
                flights.extend(parsed)
        except Exception:
            continue

    if not flights:
        m = re.search(
            r'(?:window\.__(?:INITIAL_STATE|DATA|FLIGHTS)__|var flights)\s*=\s*(\{.*?\});',
            html, re.DOTALL
        )
        if m:
            try:
                data = _json.loads(m.group(1))
                flights.extend(_parse_finavia_json(data))
            except Exception:
                pass

    if not flights:
        flights = _scrape_html_table(html)

    return flights


def _scrape_html_table(html: str) -> list[FlightArrival]:
    flights: list[FlightArrival] = []
    now = datetime.now(timezone.utc)

    for m in re.finditer(
        r'([A-Z]{2}\d{3,4})\D{0,30}?(\d{2}:\d{2})',
        html, re.IGNORECASE
    ):
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
# FR24 PARSERI (uudelleenkirjoitettu bugfix_8)
# ==============================================================

def _parse_fr24_response(raw: str) -> list[FlightArrival]:
    """
    Parsii Flightradar24-vastauksen.
    FR24 /data/airports/hel/arrivals palauttaa JSON-rakenteen.

    Rakenteen muoto:
      { "arrivals": { "data": [ {...}, ... ] } }
    tai
      { "data": [ {...}, ... ] }

    Jokainen kohde voi sisaltaa:
      "flight"    : "AY1234"
      "Ident"     : "AY1234"
      "callsign"  : "AY1234"
      "time"      : 1234567890  (Unix timestamp)
      "eta"       : 1234567890
      "from"      : "LHR"
      "From"      : "London Heathrow"
      "origin"    : "LHR"
    """
    flights: list[FlightArrival] = []
    now = datetime.now(timezone.utc)

    # -- 1. Yrita suora JSON-parsinta ---------------------------
    try:
        data = _json.loads(raw)

        # Etsi flights-lista useista mahdollisista paikoista
        candidates: list = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            # "arrivals" -> "data"
            arr = data.get("arrivals", data)
            if isinstance(arr, dict):
                candidates = arr.get("data", arr.get("flights", []))
            elif isinstance(arr, list):
                candidates = arr
            if not candidates:
                candidates = data.get("data", data.get("flights", []))

        for item in candidates[:MAX_FLIGHTS * 4]:
            if not isinstance(item, dict):
                continue
            flight_no = (
                item.get("flight") or item.get("Ident") or
                item.get("callsign") or item.get("IATA") or ""
            )
            if not flight_no:
                continue
            flight_no = str(flight_no).strip().upper()
            # Validoi lentotunnus: 2 kirjainta + 2-4 numeroa
            if not re.match(r'^[A-Z]{1,3}\d{1,4}$', flight_no):
                continue

            # Aikaleima
            ts = item.get("time") or item.get("eta") or item.get("Time") or 0
            if isinstance(ts, dict):
                ts = ts.get("scheduled") or ts.get("real") or 0
            sched: Optional[datetime] = None
            if isinstance(ts, (int, float)) and ts > 1_000_000_000:
                try:
                    sched = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                except Exception:
                    pass
            elif isinstance(ts, str):
                sched = _parse_dt_flex(ts)

            if sched is None:
                sched = now + timedelta(hours=1)

            origin = str(
                item.get("from") or item.get("From") or
                item.get("origin") or item.get("Origin") or ""
            ).strip()
            origin_city = str(
                item.get("fromCity") or item.get("origin_city") or origin
            ).strip()

            aircraft = str(
                item.get("aircraft") or item.get("type") or ""
            ).strip()

            flights.append(FlightArrival(
                flight_no=flight_no,
                airline="",
                origin=origin,
                origin_city=origin_city,
                scheduled_at=sched,
                aircraft_type=aircraft,
            ))

        if flights:
            return _dedup_flight_list(flights)

    except (_json.JSONDecodeError, ValueError, TypeError):
        pass

    # -- 2. Etsi JSON-blokkeja HTML:sta -------------------------
    for block in re.findall(
        r'<script[^>]*>(.*?)</script>', raw, re.DOTALL
    ):
        block = block.strip()
        if '"flight"' not in block and '"Ident"' not in block:
            continue
        for m in re.finditer(r'\{[^{}]{30,500}\}', block):
            try:
                obj = _json.loads(m.group(0))
                fn = obj.get("flight") or obj.get("Ident") or ""
                if fn and re.match(r'^[A-Z]{1,3}\d{1,4}$', fn.upper()):
                    ts = obj.get("time") or obj.get("eta") or 0
                    if isinstance(ts, (int, float)) and ts > 1_000_000_000:
                        sched2 = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                    else:
                        sched2 = now + timedelta(hours=1)
                    flights.append(FlightArrival(
                        flight_no=fn.upper(),
                        airline="",
                        origin="",
                        origin_city="",
                        scheduled_at=sched2,
                    ))
            except Exception:
                continue
        if flights:
            return _dedup_flight_list(flights)

    # -- 3. Regex-fallback HTML:sta -----------------------------
    for m in re.finditer(
        r'\b([A-Z]{2}\d{3,4})\b.{0,50}?(\d{2}:\d{2})',
        raw[:200_000],
        re.IGNORECASE | re.DOTALL,
    ):
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

    return _dedup_flight_list(flights)


def _dedup_flight_list(flights: list[FlightArrival]) -> list[FlightArrival]:
    """Poista duplikaatit lentotunnuksen + ajan perusteella."""
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
    """Joustava aikaleiman jasennin - tukee useita muotoja."""
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
            try:
                from zoneinfo import ZoneInfo
                hki_tz = ZoneInfo("Europe/Helsinki")
                local_dt = dt.replace(tzinfo=hki_tz)
                return local_dt.astimezone(timezone.utc)
            except Exception:
                return (dt - timedelta(hours=3)).replace(tzinfo=timezone.utc)
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
    """Poista signaaliduplikaatit per alue."""
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
