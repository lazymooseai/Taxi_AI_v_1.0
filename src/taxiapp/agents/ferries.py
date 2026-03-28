"""
ferries.py - Lauttaagentti (Averio.fi + HSL Suomenlinna)
Helsinki Taxi AI | Päivittyy 8 min välein (ttl=480)
"""
from __future__ import annotations
import logging, re, json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger(__name__)

TERMINALS = {
    "P1": {"name": "Olympiaterminaali", "area": "Eteläsatama", "capacity": 1500},
    "P2": {"name": "Katajanokka", "area": "Katajanokka", "capacity": 2000},
    "P3": {"name": "Länsiterminaali", "area": "Länsisatama", "capacity": 1800},
    "SUOMENLINNA": {"name": "Suomenlinna-lautta", "area": "Kauppatori", "capacity": 200},
}

AVERIO_SCHEDULE = "https://www.averio.fi/laivat"
HSL_API_URL = "https://api.digitransit.fi/routing/v1/routers/hsl/index/graphql"

@dataclass
class FerryArrival:
    vessel_name: str
    terminal_code: str
    operator: str
    route: str
    scheduled_at: datetime
    estimated_at: Optional[datetime] = None
    passengers_est: Optional[int] = None
    cancelled: bool = False
    source: str = ""

    @property
    def terminal(self):
        return TERMINALS.get(self.terminal_code, TERMINALS["P1"])

    @property
    def area(self):
        return self.terminal["area"]

    @property
    def effective_at(self):
        return self.estimated_at or self.scheduled_at

    @property
    def minutes_until_arrival(self):
        return (self.effective_at - datetime.now(timezone.utc)).total_seconds() / 60

    @property
    def estimated_pax(self):
        return self.passengers_est or self.terminal["capacity"]

def _parse_averio_html(html):
    arrivals = []
    now = datetime.now(timezone.utc)

    # Etsi JSON script-tageista
    json_pattern = r"""<script[^>]*type=["']application/json["'][^>]*>(.*?)</script>"""
    for block in re.findall(json_pattern, html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(block.strip())
            parsed = _parse_averio_json(data, now)
            if parsed:
                arrivals.extend(parsed)
        except:
            pass

    if arrivals:
        return arrivals

    # Fallback HTML-jäsennys
    vessel_keywords = ["Viking", "Silja", "Tallink", "Baltic", "Galaxy", "Cinderella", 
                      "Isabella", "Megastar", "Victoria", "Mariella", "Finlandia"]

    for vessel_name in vessel_keywords:
        pattern = rf'{vessel_name}\w*\s+[\w\s]*?(\d{{1,2}}[:.]\d{{2}})'
        for m in re.finditer(pattern, html[:50000], re.IGNORECASE | re.DOTALL):
            time_str = m.group(1).replace(".", ":")
            operator = _vessel_to_operator(vessel_name)
            term_code = _guess_terminal(operator)
            eta = _parse_time_today(time_str, now)
            if eta:
                arrivals.append(FerryArrival(
                    vessel_name=vessel_name, terminal_code=term_code, operator=operator,
                    route="", scheduled_at=eta, passengers_est=TERMINALS[term_code]["capacity"],
                    source="averio_html"))

    seen = set()
    unique = []
    for f in arrivals:
        key = f"{f.vessel_name}_{f.scheduled_at.strftime('%H:%M')}"
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique

def _parse_averio_json(data, now):
    arrivals = []
    items = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("arrivals", "saapuvat", "ships", "vessels", "data"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break

    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            vessel = (item.get("vessel") or item.get("alus") or item.get("name") or "").strip()
            if not vessel:
                continue

            operator = (item.get("operator") or item.get("varustamo") or "").lower()
            term_code = _guess_terminal(operator)
            route = (item.get("route") or item.get("reitti") or "").strip()

            sched_raw = item.get("scheduled") or item.get("arrival") or item.get("eta") or ""
            scheduled = _parse_dt_ferry(sched_raw, now) if sched_raw else None
            if not scheduled:
                continue

            pax = item.get("passengers") or item.get("matkustajat")
            arrivals.append(FerryArrival(
                vessel_name=vessel, terminal_code=term_code, operator=operator,
                route=route, scheduled_at=scheduled,
                passengers_est=int(pax) if pax else None, source="averio_json"))
        except:
            pass

    return arrivals

def _parse_hsl_suomenlinna(data, now):
    arrivals = []
    try:
        stop_data = data.get("data", {}).get("stop")
        if not stop_data:
            return arrivals

        for st in stop_data.get("stoptimesWithoutPatterns", []):
            service_day = st.get("serviceDay", 0)
            sched_sec = st.get("scheduledArrival", 0)
            real_sec = st.get("realtimeArrival")

            sched_ts = service_day + sched_sec
            sched_dt = datetime.fromtimestamp(sched_ts, tz=timezone.utc)

            real_dt = None
            if real_sec is not None:
                real_dt = datetime.fromtimestamp(service_day + real_sec, tz=timezone.utc)

            trip = st.get("trip", {}) or {}
            route = trip.get("route", {}) or {}
            route_name = route.get("shortName", "Suomenlinna")

            arrivals.append(FerryArrival(
                vessel_name=f"Suomenlinna-lautta ({route_name})",
                terminal_code="SUOMENLINNA", operator="HSL",
                route="Suomenlinna->Kauppatori", scheduled_at=sched_dt,
                estimated_at=real_dt, passengers_est=200, source="hsl_api"))
    except Exception as e:
        logger.debug(f"HSL jäsennys epäonnistui: {e}")

    return arrivals

def _static_schedule_fallback():
    now = datetime.now(timezone.utc)
    _STATIC = [
        ("P1", "Silja Serenade", "Stockholm->HKI", 9, 55, 2852),
        ("P2", "Viking Grace", "Turku->HKI", 7, 0, 2800),
        ("P2", "Viking Cinderella", "Stockholm->HKI", 8, 30, 2500),
        ("P3", "Tallink Megastar", "Tallinn->HKI", 10, 30, 2800),
        ("P3", "Tallink Megastar", "Tallinn->HKI", 15, 30, 2800),
        ("P3", "Tallink Star", "Tallinn->HKI", 19, 30, 1900),
        ("SUOMENLINNA", "Suomenlinna-lautta", "Kauppatori->Suomenlinna", 0, 10, 200),
    ]

    arrivals = []
    for term, vessel, route, h, m, pax in _STATIC:
        sched = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if sched < now - timedelta(minutes=10):
            sched += timedelta(days=1)

        arrivals.append(FerryArrival(
            vessel_name=vessel, terminal_code=term,
            operator=_vessel_to_operator(vessel),
            route=route, scheduled_at=sched, passengers_est=pax,
            source="static_fallback"))

    return arrivals

def _vessel_to_operator(vessel_name):
    name_low = str(vessel_name).lower()
    if "viking" in name_low:
        return "viking line"
    if "silja" in name_low or "serenade" in name_low or "symphony" in name_low:
        return "silja line"
    if "tallink" in name_low or "megastar" in name_low or "star" in name_low:
        return "tallink"
    if "eckerö" in name_low or "eckero" in name_low:
        return "eckerö line"
    if "suomenlinna" in name_low:
        return "hsl"
    return "unknown"

def _guess_terminal(operator):
    op_low = operator.lower()
    if "silja" in op_low or "serenade" in op_low or "symphony" in op_low:
        return "P1"
    if "viking" in op_low:
        return "P2"
    if "tallink" in op_low or "megastar" in op_low:
        return "P3"
    if "eckerö" in op_low or "eckero" in op_low or "finnlines" in op_low:
        return "P3"
    if "hsl" in op_low or "suomenlinna" in op_low:
        return "SUOMENLINNA"
    return "P1"

def _parse_dt_ferry(s, now):
    if not s:
        return None
    s = s.strip()

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except:
        pass

    for fmt in ["%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except:
            pass

    return _parse_time_today(s, now)

def _parse_time_today(time_str, now):
    m = re.match(r'^(\d{1,2})[:.:](\d{2})$', time_str.strip())
    if not m:
        return None
    try:
        h, mins = int(m.group(1)), int(m.group(2))
        if not (0 <= h <= 23 and 0 <= mins <= 59):
            return None
        dt = now.replace(hour=h, minute=mins, second=0, microsecond=0)
        if dt < now - timedelta(hours=1):
            dt += timedelta(days=1)
        return dt
    except:
        return None

def _dedup_ferry_signals(signals):
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

class FerryAgent(BaseAgent):
    name = "FerryAgent"
    ttl = 480

    async def fetch(self) -> AgentResult:
        all_arrivals = []
        errors = []

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "Mozilla/5.0 HelsinkiTaxiAI/1.0", "Accept": "text/html,application/json"},
            follow_redirects=True) as client:

            try:
                resp = await client.get(AVERIO_SCHEDULE)
                resp.raise_for_status()
                arrivals = _parse_averio_html(resp.text)
                if arrivals:
                    all_arrivals.extend(arrivals)
            except Exception as e:
                errors.append(f"Averio: {str(e)[:50]}")

            try:
                query = """{ stop(id: "HSL:1020452") { name stoptimesWithoutPatterns(numberOfDepartures: 6) { scheduledArrival realtimeArrival serviceDay trip { route { shortName } } } } }"""
                resp = await client.post(HSL_API_URL, 
                    json={"query": query},
                    headers={"Content-Type": "application/json"})
                resp.raise_for_status()
                data = resp.json()
                suom = _parse_hsl_suomenlinna(data, datetime.now(timezone.utc))
                if suom:
                    all_arrivals.extend(suom)
            except Exception as e:
                errors.append(f"HSL: {str(e)[:50]}")

        if not all_arrivals:
            all_arrivals = _static_schedule_fallback()
            errors.append("STATIC")

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=3)
        arriving = [f for f in all_arrivals
                   if not f.cancelled
                   and f.effective_at >= now - timedelta(minutes=5)
                   and f.effective_at <= cutoff]
        arriving.sort(key=lambda f: f.effective_at)

        signals = []
        for ferry in arriving:
            eta = ferry.minutes_until_arrival
            pax = ferry.estimated_pax

            if eta < -5 or eta > 180:
                continue

            score = max(5.0, pax / 80.0)

            if ferry.terminal_code == "SUOMENLINNA":
                reason = f" Suomenlinna-lautta ~{max(0,int(eta))}min"
                urgency = 3
                score *= 0.6
            elif 0 <= eta <= 15:
                reason = f" {ferry.vessel_name} saapuu ~{max(0,int(eta))}min ({pax} hlöä) -> {ferry.terminal['name']}"
                urgency = 6
                score *= 1.5
            elif 15 < eta <= 30:
                reason = f" {ferry.vessel_name} saapuu {int(eta)}min -> {ferry.terminal['name']}"
                urgency = 5
                score *= 1.2
            else:
                reason = f" {ferry.vessel_name} saapuu {int(eta)}min"
                urgency = 4
                score *= 1.0

            signals.append(Signal(
                area=ferry.area, score_delta=round(score, 1),
                reason=reason, urgency=urgency,
                expires_at=ferry.effective_at + timedelta(minutes=30),
                source_url=AVERIO_SCHEDULE,
                title=ferry.vessel_name + " -> " + ferry.terminal["name"],
                agent="FerryAgent", category="ferries"))

        signals = _dedup_ferry_signals(signals)
        signals.sort(key=lambda s: s.urgency, reverse=True)

        raw = {
            "total_vessels": len(arriving),
            "signals": len(signals),
            "errors": errors,
            "arrivals": [{"vessel": f.vessel_name, "terminal": f.terminal_code, "eta_min": round(f.minutes_until_arrival, 1)} for f in arriving[:8]]
        }

        logger.info(f"FerryAgent: {len(arriving)} laivaa -> {len(signals)} signaalia")
        return self._ok(signals, raw_data=raw)
