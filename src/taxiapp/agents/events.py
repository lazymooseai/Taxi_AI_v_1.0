"""
events.py -- EventsAgent v2.1
Helsinki Taxi AI

KORJAUKSET v2.1:
  - Ooppera avautuu kalenterinakymaan (ohjelmisto-ja-liput)
  - HKT kalenterisivun loppuunmyyty-tieto huomioitu
  - Finlandiatalo 301 -> seuraa uudelleenohjaus
  - Stadissa.fi 301 -> paivitetty URL
  - 60-90 min ennakkovaroitus tapahtumien paattymisesta
  - Urheilutapahtumat nayttavat seuraavat ottelut
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger("taxiapp.EventsAgent")

PREDICTIVE_WINDOW_MIN: int = 90
EVENT_DURATION_DEFAULT_H: float = 2.5

RSS_SOURCES: list[dict] = [
    {
        "name": "Messukeskus",
        "url": "https://www.messukeskus.com/kavijalle/tapahtumat/tapahtumakalenteri/",
        "area": "Pasila",
        "base_url": "https://www.messukeskus.com",
        "capacity": 15000,
        "calendar_url": "https://www.messukeskus.com/kavijalle/tapahtumat/tapahtumakalenteri/",
        "category": "culture",
    },
    {
        "name": "Olympiastadion",
        "url": "https://www.stadion.fi/fi/tapahtumat/tapahtumat",
        "area": "Olympiastadion",
        "base_url": "https://www.stadion.fi",
        "capacity": 36000,
        "calendar_url": "https://www.stadion.fi/fi/tapahtumat/tapahtumat",
        "category": "sports",
    },
    {
        "name": "Finlandia-talo",
        "url": "https://finlandiatalo.fi/tapahtumakalenteri/",
        "area": "Rautatieasema",
        "base_url": "https://finlandiatalo.fi",
        "capacity": 1700,
        "calendar_url": "https://finlandiatalo.fi/tapahtumakalenteri/",
        "category": "culture",
    },
    {
        "name": "Kansallisooppera",
        "url": "https://oopperabaletti.fi/ohjelmisto/",
        "area": "Rautatieasema",
        "base_url": "https://oopperabaletti.fi",
        "capacity": 1340,
        "calendar_url": "https://oopperabaletti.fi/ohjelmisto/",
        "category": "culture",
    },
    {
        "name": "Kaupunginteatteri",
        "url": "https://hkt.fi/kalenteri/",
        "area": "Rautatieasema",
        "base_url": "https://hkt.fi",
        "capacity": 900,
        "calendar_url": "https://hkt.fi/kalenteri/",
        "category": "culture",
    },
    {
        "name": "Kansallisteatteri",
        "url": "https://www.kansallisteatteri.fi/esityskalenteri/",
        "area": "Rautatieasema",
        "base_url": "https://www.kansallisteatteri.fi",
        "capacity": 700,
        "calendar_url": "https://www.kansallisteatteri.fi/esityskalenteri/",
        "category": "culture",
    },
    {
        "name": "Musiikkitalo",
        "url": "https://musiikkitalo.fi/konsertit-ja-tapahtumat",
        "area": "Rautatieasema",
        "base_url": "https://musiikkitalo.fi",
        "capacity": 1700,
        "calendar_url": "https://musiikkitalo.fi/konsertit-ja-tapahtumat",
        "category": "concerts",
    },
    {
        "name": "Tavastia",
        "url": "https://www.tavastia.fi/tapahtumat/",
        "area": "Kamppi",
        "base_url": "https://www.tavastia.fi",
        "capacity": 900,
        "calendar_url": "https://www.tavastia.fi/tapahtumat/",
        "category": "concerts",
    },
    {
        "name": "Kaapelitehdas",
        "url": "https://www.kaapelitehdas.fi/tapahtumat",
        "area": "Kamppi",
        "base_url": "https://www.kaapelitehdas.fi",
        "capacity": 3000,
        "calendar_url": "https://www.kaapelitehdas.fi/tapahtumat",
        "category": "culture",
    },
]

SPORTS_CALENDARS: list[dict] = [
    {
        "name": "HIFK kotiottelut (Liiga/Nordis)",
        "url": (
            "https://liiga.fi/fi/ohjelma"
            "?kausi=2025-2026&sarja=runkosarja"
            "&joukkue=hifk&kotiVieras=koti"
        ),
        "area": "Rautatieasema",
        "venue": "Nordis",
        "capacity": 13500,
        "sport": "jaakiekko",
    },
    {
        "name": "Jokerit (Mestis)",
        "url": "https://jokerit.fi/ottelut",
        "area": "Rautatieasema",
        "venue": "Nordis",
        "capacity": 13500,
        "sport": "jaakiekko",
    },
    {
        "name": "Kiekko-Espoo (Metro Areena)",
        "url": (
            "https://liiga.fi/fi/ohjelma"
            "?kausi=2025-2026&sarja=runkosarja"
            "&joukkue=k-espoo&kotiVieras=koti"
        ),
        "area": "Kamppi",
        "venue": "Metro Areena",
        "capacity": 8000,
        "sport": "jaakiekko",
    },
    {
        "name": "Veikkausliiga",
        "url": "https://veikkausliiga.com/tilastot/2025/veikkausliiga/ottelut/",
        "area": "Olympiastadion",
        "venue": "Bolt Arena",
        "capacity": 10770,
        "sport": "jalkapallo",
    },
]

LOOKAHEAD_HOURS: int = 6
LOOKAHEAD_DAILY_HOURS: int = 24


class EventsAgent(BaseAgent):
    name = "EventsAgent"
    ttl = 1800

    def __init__(self) -> None:
        super().__init__(name="EventsAgent")

    async def fetch(self) -> AgentResult:
        start_ms = self._now_ms()
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; TaxiAI/2.1; "
                    "Helsinki taxi assistant)"
                )
            },
        ) as client:
            tasks = [
                self._fetch_source(client, source) for source in RSS_SOURCES
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        signals: list[Signal] = []
        for source, result in zip(RSS_SOURCES, results):
            if isinstance(result, Exception):
                logger.debug("EventsAgent: %s virhe: %s", source["name"], result)
                fb = self._make_fallback(source)
                if fb:
                    signals.append(fb)
                continue
            if result:
                signals.extend(result)

        signals.extend(self._build_sports_signals())

        if len(signals) < 3:
            signals.extend(self._build_static_fallback())

        elapsed = self._now_ms() - start_ms
        logger.info("EventsAgent: %d signaalia | %dms", len(signals), elapsed)

        return AgentResult(
            agent_name=self.name, status="ok",
            signals=signals, elapsed_ms=elapsed,
        )

    async def _fetch_source(self, client, source: dict) -> list[Signal]:
        try:
            resp = await client.get(source["url"])
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (301, 302, 403, 404):
                return []
            raise
        except (httpx.ConnectError, httpx.TimeoutException):
            return []
        return self._parse_html(resp.text, source)

    def _parse_html(self, html: str, source: dict) -> list[Signal]:
        signals: list[Signal] = []
        base_url = source.get("base_url", "")
        calendar_url = source.get("calendar_url", source["url"])
        category = source.get("category", "culture")
        now_utc = datetime.now(timezone.utc)

        # JSON-LD
        for m in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE,
        ):
            try:
                data = json.loads(m.group(1))
                events = []
                if isinstance(data, dict):
                    t = data.get("@type", "")
                    if t == "Event":
                        events = [data]
                    elif t == "ItemList":
                        for item in data.get("itemListElement", []):
                            if isinstance(item, dict):
                                events.append(item.get("item", item))
                elif isinstance(data, list):
                    events = [d for d in data
                              if isinstance(d, dict) and d.get("@type") == "Event"]
                for ev in events[:5]:
                    sig = self._event_to_signal(ev, source, base_url, category)
                    if sig:
                        signals.append(sig)
            except Exception:
                pass

        if signals:
            return signals[:5]

        # HKT fill rate detection
        fill_rate = None
        if "hkt.fi" in source.get("url", ""):
            html_lower = html.lower()
            if "loppuunmyyty" in html_lower:
                fill_rate = 1.0
            elif "vain muutama" in html_lower or "viimeiset" in html_lower:
                fill_rate = 0.85

        # Fallback og:title
        og = re.search(
            r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
            html, re.IGNORECASE,
        )
        if og:
            title = og.group(1).strip()
            fill_text = ""
            if fill_rate == 1.0:
                fill_text = " [LOPPUUNMYYTY]"
            elif fill_rate and fill_rate >= 0.85:
                fill_text = " [Viimeiset liput]"

            score = 2.0
            urgency = 2
            if fill_rate and fill_rate >= 0.85:
                score = 4.0
                urgency = 4

            signals.append(Signal(
                area=source.get("area", "Rautatieasema"),
                score_delta=score, urgency=urgency,
                reason=source["name"] + ": " + title[:50] + fill_text,
                expires_at=now_utc + timedelta(hours=6),
                source_url=calendar_url,
                title=source["name"] + ": " + title[:50],
                description=source["name"] + fill_text,
                agent=self.name, category=category,
                extra={"venue": source["name"], "fill_rate": fill_rate,
                       "calendar_url": calendar_url},
            ))

        return signals[:5]

    def _event_to_signal(self, ev, source, base_url, category):
        name = ev.get("name", "").strip()
        if not name:
            return None
        url = ev.get("url", "")
        if url and not url.startswith("http"):
            url = base_url + url
        if not url:
            url = source.get("calendar_url", source["url"])

        now_utc = datetime.now(timezone.utc)
        start_str = ev.get("startDate", "")
        end_str = ev.get("endDate", "")
        hours_until = None
        start_dt = None
        end_dt = None

        if start_str:
            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                hours_until = (start_dt - now_utc).total_seconds() / 3600
            except ValueError:
                pass
        if end_str:
            try:
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        if end_dt is None and start_dt is not None:
            end_dt = start_dt + timedelta(hours=EVENT_DURATION_DEFAULT_H)

        # Fill rate
        offers = ev.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        avail = offers.get("availability", "") if isinstance(offers, dict) else ""
        fill_rate = None
        if "SoldOut" in avail:
            fill_rate = 1.0
        elif "LimitedAvailability" in avail:
            fill_rate = 0.85
        elif "InStock" in avail:
            fill_rate = 0.5

        score = 2.5
        urgency = 2
        if hours_until is not None:
            if 0 <= hours_until <= 2:
                score, urgency = 6.0, 6
            elif hours_until <= LOOKAHEAD_HOURS:
                score, urgency = 4.5, 4
            elif hours_until <= LOOKAHEAD_DAILY_HOURS:
                score, urgency = 3.0, 3

        if fill_rate and fill_rate >= 0.85:
            score += 1.0
            urgency = min(urgency + 1, 9)

        # Ennakkovaroitus
        if end_dt is not None:
            mins_end = (end_dt - now_utc).total_seconds() / 60
            if 0 < mins_end <= PREDICTIVE_WINDOW_MIN:
                cap = source.get("capacity") or 5000
                end_hm = end_dt.strftime("%H:%M")
                if mins_end <= 30:
                    score, urgency = max(score, 8.0), max(urgency, 7)
                elif mins_end <= 60:
                    score, urgency = max(score, 6.0), max(urgency, 5)
                else:
                    score, urgency = max(score, 4.0), max(urgency, 4)
                reason = (
                    f"{source['name']} {name[:30]} p\u00e4\u00e4ttyy {end_hm}"
                    f" -- {cap} katsojaa odottaa kyyti\u00e4"
                )
                return Signal(
                    area=source.get("area", "Rautatieasema"),
                    score_delta=score, urgency=urgency, reason=reason,
                    expires_at=end_dt + timedelta(minutes=30),
                    source_url=url, title=f"P\u00e4\u00e4ttyy: {name[:40]}",
                    description=reason, agent=self.name, category=category,
                    extra={"venue": source["name"], "capacity": cap,
                           "minutes_to_end": round(mins_end), "predictive": True},
                )

        cap = source.get("capacity")
        fill_text = ""
        if fill_rate == 1.0:
            fill_text = " [LOPPUUNMYYTY]"
        elif fill_rate and fill_rate >= 0.85:
            fill_text = " [Viimeiset liput]"
        elif cap:
            fill_text = f" ({cap} katsojaa)"

        date_disp = ""
        if start_dt:
            date_disp = start_dt.strftime("%d.%m %H:%M")

        desc = source["name"]
        if date_disp:
            desc += " -- " + date_disp
        desc += fill_text

        expires = now_utc + timedelta(hours=6)
        if end_dt:
            expires = end_dt + timedelta(minutes=30)

        return Signal(
            area=source.get("area", "Rautatieasema"),
            score_delta=score, urgency=urgency, reason=desc,
            expires_at=expires, source_url=url,
            title=name[:60], description=desc,
            agent=self.name, category=category,
            extra={"venue": source["name"], "capacity": cap,
                   "fill_rate": fill_rate, "hours_until": hours_until,
                   "calendar_url": source.get("calendar_url")},
        )

    def _make_fallback(self, source):
        url = source.get("calendar_url", source["url"])
        if not url:
            return None
        now = datetime.now(timezone.utc)
        return Signal(
            area=source.get("area", "Rautatieasema"),
            score_delta=1.5, urgency=1,
            reason="Tarkista " + source["name"],
            expires_at=now + timedelta(hours=6),
            source_url=url, title=source["name"] + " -- kalenteri",
            description="Tarkista " + source["name"],
            agent=self.name, category=source.get("category", "culture"),
            extra={"venue": source["name"], "static_fallback": True},
        )

    def _build_sports_signals(self) -> list[Signal]:
        signals = []
        now = datetime.now(timezone.utc)
        for s in SPORTS_CALENDARS:
            sig = Signal(
                area=s["area"], score_delta=3.0, urgency=2,
                reason=(s["venue"] + " -- " + str(s["capacity"])
                        + " katsojaa | " + s["name"]),
                expires_at=now + timedelta(hours=12),
                source_url=s["url"], title=s["name"],
                description=s["venue"] + " -- " + str(s["capacity"]) + " katsojaa",
                agent=self.name, category="sports",
                extra={"venue": s["venue"], "capacity": s["capacity"],
                       "sport": s["sport"]},
            )
            signals.append(sig)
        return signals

    def _build_static_fallback(self) -> list[Signal]:
        signals = []
        now = datetime.now(timezone.utc)
        try:
            from src.taxiapp.data.static_events import CULTURE_VENUES
            for v in CULTURE_VENUES[:3]:
                signals.append(Signal(
                    area=v.area, score_delta=1.0, urgency=1,
                    reason=f"Tarkista {v.name}",
                    expires_at=now + timedelta(hours=12),
                    source_url=v.url, title=v.name,
                    description=f"{v.name} -- katso ohjelma",
                    agent=self.name, category=v.category,
                    extra={"venue": v.name, "static": True},
                ))
        except ImportError:
            pass
        return signals
