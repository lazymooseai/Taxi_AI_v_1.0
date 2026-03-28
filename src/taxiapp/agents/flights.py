"""
flights.py -- FlightAgent v3.0
Helsinki Taxi AI

Hakee saapuvat lennot EFHK:lle.

Lahdejarjestys:
  1. Finavia API (jos avaimet konfiguroitu)
  2. Flightradar24 EFHK-sivu (scrape)
  3. Finavia HTML-sivu (scrape)
  4. Fallback: staattinen signaali + linkki

OpenSky POISTETTU (alhaalla pysyvasti).
"""

from __future__ import annotations

import logging, re, json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal
from src.taxiapp.config import config

logger = logging.getLogger("taxiapp.FlightAgent")

AREA = "Lentokentta"
TIKKURILA = "Tikkurila"
MAX_FLIGHTS = 7
LOOKAHEAD_H = 2

FINAVIA_ARR = "https://www.finavia.fi/fi/lentoasemat/helsinki-vantaa/lennot?tab=arr"
FINAVIA_API = "https://api.finavia.fi/flights/public/v0"
FR24_URL = "https://www.flightradar24.com/data/airports/hel/arrivals"

CAPACITY = {
    "A380": 525, "B748": 410, "B773": 350, "B77W": 370,
    "B788": 250, "B789": 290, "A359": 314, "A333": 300,
    "B738": 189, "A320": 180, "A321": 220, "A319": 140,
    "A20N": 180, "A21N": 220, "E190": 100, "E195": 120,
    "AT72": 68, "DH8D": 78, "CRJ9": 90,
}


@dataclass
class Flight:
    flight_no: str
    origin_city: str
    scheduled_at: datetime
    estimated_at: Optional[datetime] = None
    aircraft: str = ""
    cancelled: bool = False

    @property
    def effective(self):
        return self.estimated_at or self.scheduled_at

    @property
    def delay(self):
        if self.estimated_at:
            return max(0, int((self.estimated_at - self.scheduled_at).total_seconds() / 60))
        return 0

    @property
    def eta_min(self):
        return (self.effective - datetime.now(timezone.utc)).total_seconds() / 60

    @property
    def pax(self):
        return CAPACITY.get(self.aircraft.upper(), 150) if self.aircraft else 150


class FlightAgent(BaseAgent):
    name = "FlightAgent"
    ttl = 300

    async def fetch(self):
        flights = []
        err = None
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TaxiAI/3.0)"}) as c:
            # 1. Finavia API
            if config.finavia_app_id and config.finavia_app_key:
                flights, err = await self._api(c)
            # 2. Finavia HTML
            if not flights:
                flights, e2 = await self._finavia_html(c)
                if e2:
                    err = f"{err or ''} | {e2}" if err else e2
            # 3. Flightradar24 scrape
            if not flights:
                flights, e3 = await self._fr24(c)
                if e3:
                    err = f"{err or ''} | {e3}" if err else e3

        if not flights:
            now = datetime.now(timezone.utc)
            sig = Signal(
                area=AREA, score_delta=5.0, urgency=3,
                reason="Tarkista saapuvat lennot Finavian sivulta",
                expires_at=now + timedelta(hours=2),
                source_url=FINAVIA_ARR,
                title="Helsinki-Vantaa saapuvat lennot",
                description="Finavian lentoaikataulu",
                agent=self.name, category="airport",
                extra={"static_fallback": True},
            )
            return AgentResult(
                agent_name=self.name, status="ok", signals=[sig],
                raw_data={"source": "fallback", "error": err},
            )

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=LOOKAHEAD_H)
        arr = sorted(
            [f for f in flights if not f.cancelled
             and f.effective >= now - timedelta(minutes=5)
             and f.effective <= cutoff],
            key=lambda f: f.effective,
        )[:MAX_FLIGHTS]

        sigs = [self._to_signal(f) for f in arr]
        sigs.sort(key=lambda s: s.urgency, reverse=True)
        return self._ok(sigs, {"source": "live", "flights": len(arr)})

    async def _api(self, c):
        try:
            r = await c.get(
                f"{FINAVIA_API}/airport/EFHK/arr",
                headers={"app_id": config.finavia_app_id or "",
                         "app_key": config.finavia_app_key or "",
                         "Accept": "application/json"})
            r.raise_for_status()
            return self._parse_api_json(r.json()), None
        except Exception as e:
            return [], f"Finavia API: {str(e)[:60]}"

    async def _finavia_html(self, c):
        try:
            r = await c.get(FINAVIA_ARR, headers={"Accept": "text/html"})
            r.raise_for_status()
            flights = self._parse_html(r.text)
            if flights:
                return flights, None
            return [], "Finavia HTML: ei lentoja loydetty"
        except Exception as e:
            return [], f"Finavia HTML: {str(e)[:60]}"

    async def _fr24(self, c):
        try:
            r = await c.get(FR24_URL, headers={"Accept": "text/html"})
            r.raise_for_status()
            flights = self._parse_html(r.text)
            if flights:
                return flights, None
            return [], "FR24: ei lentoja"
        except Exception as e:
            return [], f"FR24: {str(e)[:60]}"

    def _parse_api_json(self, data):
        flights = []
        if isinstance(data, dict):
            body = data.get("body", data)
            inner = body.get("flights", body) if isinstance(body, dict) else body
            raw = inner.get("flight", []) if isinstance(inner, dict) else (inner if isinstance(inner, list) else [])
        else:
            raw = data if isinstance(data, list) else []
        if isinstance(raw, dict):
            raw = [raw]
        for item in raw:
            if not isinstance(item, dict):
                continue
            fn = (item.get("fltnr") or item.get("flightno") or "").strip()
            if not fn:
                continue
            city = (item.get("orig_name") or item.get("origin_name") or item.get("orig") or "").strip()
            ac = (item.get("actype") or "").strip()
            sched = self._dt(item.get("sched") or item.get("scheduled") or item.get("sta") or "")
            est = self._dt(item.get("estimate") or item.get("estimated") or item.get("eta") or "")
            if sched:
                flights.append(Flight(fn, city, sched, est, ac,
                    "cancel" in (item.get("status") or "").lower()))
        return flights

    def _parse_html(self, html):
        flights = []
        now = datetime.now(timezone.utc)
        # JSON blocks
        for block in re.findall(r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                data = json.loads(block.strip())
                parsed = self._parse_api_json(data)
                if parsed:
                    return parsed
            except Exception:
                pass
        # Regex: flight number + time
        for m in re.finditer(r'([A-Z]{2}\d{1,4})\D+?(\d{2}:\d{2})', html):
            fn = m.group(1).upper()
            ts = m.group(2)
            try:
                h, mi = map(int, ts.split(":"))
                dt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
                if dt < now - timedelta(hours=1):
                    dt += timedelta(days=1)
                flights.append(Flight(fn, "", dt))
            except Exception:
                pass
        seen = set()
        unique = []
        for f in flights:
            k = f"{f.flight_no}_{f.scheduled_at.strftime('%H%M')}"
            if k not in seen:
                seen.add(k)
                unique.append(f)
        return unique[:MAX_FLIGHTS * 2]

    def _to_signal(self, f):
        eta = f.eta_min
        delay = f.delay
        pax = f.pax
        base = max(5.0, pax / 10.0)
        if delay >= 60: urg, bonus = 8, 30.0
        elif delay >= 30: urg, bonus = 7, 18.0
        elif delay >= 15: urg, bonus = 5, 8.0
        else: urg, bonus = 2, 0.0
        if 0 <= eta <= 10: eu, es = 6, base * 1.5
        elif eta <= 30: eu, es = 4, base * 1.2
        elif eta <= 60: eu, es = 3, base
        else: eu, es = 2, base * 0.6
        fu = max(urg, eu)
        fs = round(es + bonus, 1)
        mins = max(0, int(eta))
        hhmm = f.effective.strftime("%H:%M")
        city = f.origin_city or "?"
        if delay >= 15:
            title = f"{f.flight_no} {city} {hhmm} (+{delay}min)"
        else:
            title = f"{f.flight_no} {city} \u2192 HEL {hhmm}"
        return Signal(
            area=AREA, score_delta=fs, urgency=fu,
            reason=title,
            expires_at=f.effective + timedelta(minutes=20),
            source_url=FINAVIA_ARR,
            title=title, description=f"Saapuu {mins}min",
            agent=self.name, category="airport",
            extra={"flight_no": f.flight_no, "origin": city,
                   "minutes_away": mins, "delay_minutes": delay,
                   "arrival_time": hhmm, "pax_est": pax},
        )

    def _dt(self, s):
        if not s: return None
        s = s.strip()
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            pass
        m = re.match(r'^(\d{2}):(\d{2})$', s)
        if m:
            now = datetime.now(timezone.utc)
            dt = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
            if dt < now - timedelta(hours=1):
                dt += timedelta(days=1)
            return dt
        return None
