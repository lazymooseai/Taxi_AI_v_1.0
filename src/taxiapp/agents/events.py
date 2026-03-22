"""
events.py - Tapahtumat-agentti (kulttuuri/urheilu/politiikka)
Helsinki Taxi AI | Päivittyy 30 min välein (ttl=1800)
"""
from __future__ import annotations
import logging, re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal
from src.taxiapp.areas import AREAS

logger = logging.getLogger(__name__)

SOURCES = [
    
    {"name": "MyHelsinki", "url": "https://www.myhelsinki.fi/fi/rss/events", "cat": "kulttuuri"},
]

VENUE_MAP = {
    "olympiastadion": ("Olympiastadion", 40000),
    "hartwall arena": ("Pasila", 13500),
    "messukeskus": ("Messukeskus", 8000),
    "finlandia-talo": ("Kamppi", 1700),
    "musiikkitalo": ("Rautatieasema", 1700),
}

CATEGORY_KEYWORDS = {
    "konsertti": "kulttuuri", "festivaali": "kulttuuri", "teatteri": "kulttuuri",
    "ooppera": "kulttuuri", "näyttely": "kulttuuri", "museo": "kulttuuri",
    "jääkiekko": "urheilu", "jalkapallo": "urheilu", "maraton": "urheilu",
    "eduskunta": "politiikka", "valtuusto": "politiikka", "vaali": "politiikka",
}

@dataclass
class Event:
    title: str
    venue: str
    area: str
    category: str
    starts_at: datetime
    ends_at: Optional[datetime] = None
    capacity: int = 1000
    sold_out: bool = False
    source_url: str = ""
    source: str = ""

    @property
    def minutes_until_start(self):
        return (self.starts_at - datetime.now(timezone.utc)).total_seconds() / 60

    @property
    def minutes_until_end(self):
        if not self.ends_at:
            return float("inf")
        return (self.ends_at - datetime.now(timezone.utc)).total_seconds() / 60

    @property
    def is_large(self):
        return self.capacity >= 5000

def _rss_tag(text, tag):
    pattern = rf'<{re.escape(tag)}[^>]*>(.*?)</{re.escape(tag)}>'
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    content = m.group(1)
    content = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", content, flags=re.DOTALL)
    content = re.sub(r"<[^>]+>", " ", content)
    for ent, rep in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                     ("&nbsp;", " "), ("&auml;", "ä"), ("&ouml;", "ö"), ("&Auml;", "Ä")]:
        content = content.replace(ent, rep)
    return " ".join(content.split())

def _parse_event_dt(s):
    if not s:
        return None
    s = s.strip()

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except:
        pass

    for fmt in ["%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except:
            pass

    return None

def _detect_category(text, default):
    for keyword, category in CATEGORY_KEYWORDS.items():
        if keyword in text.lower():
            return category
    return default

def _detect_venue(text):
    for venue_key, (area, cap) in VENUE_MAP.items():
        if venue_key in text.lower():
            return area, cap

    for kw, (area, cap) in [("pasila", ("Pasila", 5000)), ("rautatieasema", ("Rautatieasema", 1000))]:
        if kw in text.lower():
            return area, cap

    return "Kamppi", 500

def _dedup_events(events):
    seen = set()
    unique = []
    for e in events:
        key = f"{e.title[:40]}_{e.starts_at.strftime('%Y%m%d%H%M')}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique

def _dedup_event_signals(signals):
    by_area = {}
    for sig in signals:
        if sig.area not in by_area:
            by_area[sig.area] = sig
        else:
            ex = by_area[sig.area]
            if sig.urgency >= ex.urgency:
                by_area[sig.area] = sig
    return list(by_area.values())

class EventsAgent(BaseAgent):
    name = "EventsAgent"
    ttl = 1800

    async def fetch(self) -> AgentResult:
        all_events = []
        errors = []

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "HelsinkiTaxiAI/1.0", "Accept": "application/rss+xml, text/xml"},
            follow_redirects=True) as client:

            for source in SOURCES:
                try:
                    resp = await client.get(source["url"])
                    resp.raise_for_status()
                    events = _parse_event_rss(resp.text, source["cat"], source["name"], source["url"])
                    all_events.extend(events)
                except Exception as e:
                    errors.append(f"{source['name']}: {str(e)[:30]}")

        if not all_events:
            errors.append("STATIC")

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)
        relevant = [e for e in all_events
                   if e.starts_at <= cutoff
                   and (not e.ends_at or e.ends_at >= now - timedelta(minutes=30))]

        relevant = _dedup_events(relevant)
        signals = []

        for event in relevant:
            until_end = event.minutes_until_end
            until_start = event.minutes_until_start

            if until_end < -30:
                continue

            if 0 <= until_end <= 20:
                urgency, score = 8, 15.0
                reason = f" LOPPUU {int(until_end)}min: {event.title[:50]} @ {event.venue}"
            elif 20 < until_end <= 60:
                urgency, score = 6, 10.0
                reason = f" Loppuu {int(until_end)}min: {event.title[:50]}"
            elif -30 <= until_start <= 30:
                urgency, score = 5, 8.0
                reason = f" Alkaa {max(0,int(until_start))}min: {event.title[:50]}"
            elif 30 < until_start <= 120:
                urgency, score = 4, 5.0
                reason = f" Tulossa {int(until_start)}min: {event.title[:50]}"
            else:
                continue

            if event.area in AREAS:
                signals.append(Signal(
                    area=event.area, score_delta=round(score, 1),
                    reason=reason, urgency=urgency,
                    expires_at=event.starts_at + timedelta(hours=2),
                    source_url=event.source_url))

        signals = _dedup_event_signals(signals)
        signals.sort(key=lambda s: s.urgency, reverse=True)

        raw = {"events": len(relevant), "signals": len(signals), "errors": errors}
        logger.info(f"EventsAgent: {len(relevant)} tapahtumaa -> {len(signals)} signaalia")
        return self._ok(signals, raw_data=raw)

def _parse_event_rss(xml, default_cat, source_name, source_url):
    events = []

    for block in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL):
        title = _rss_tag(block, "title")
        desc = _rss_tag(block, "description")
        link = _rss_tag(block, "link")
        pubdate = _rss_tag(block, "pubDate")
        location = _rss_tag(block, "location") or _rss_tag(block, "venue") or ""

        if not title:
            continue

        start_dt = _parse_event_dt(_rss_tag(block, "start") or pubdate)
        if not start_dt:
            continue

        end_dt = _parse_event_dt(_rss_tag(block, "end"))
        if not end_dt:
            end_dt = start_dt + timedelta(hours=3)

        text = f"{title} {desc}".lower()
        category = _detect_category(text, default_cat)
        area, capacity = _detect_venue(f"{location} {title} {desc}")

        sold_out = any(kw in text for kw in ["loppuunmyyty", "sold out", "täynnä"])

        events.append(Event(
            title=title[:120], venue=location or area, area=area,
            category=category, starts_at=start_dt, ends_at=end_dt,
            capacity=capacity, sold_out=sold_out,
            source_url=link or source_url, source=source_name))

    return events
