"""
events.py -- EventsAgent v2.2
Helsinki Taxi AI

Korjattu URL:t logien perusteella:
  - Olympiastadion: stadion.fi/fi/tapahtumat/tapahtumat (200 OK)
  - Musiikkitalo: musiikkitalo.fi/konsertit-ja-tapahtumat (200 OK)
  - Ooppera: oopperabaletti.fi/ohjelmisto/ (200 OK)
  - Kansallisteatteri: 404 -> fallback
  - Finlandiatalo: 404 -> fallback
  - Kaapelitehdas: kaapelitehdas.fi/tapahtumat/ (200 OK redirect)
  - Tavastia: uusi URL
  - HKT: hkt.fi/kalenteri/ (200 OK) + fill rate

60-90 min ennakkovaroitus tapahtumien paattymisesta.
"""

from __future__ import annotations

import asyncio, json, logging, re
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger("taxiapp.EventsAgent")

PREDICT_MIN = 90
DEFAULT_DUR_H = 2.5

SOURCES = [
    {"name": "Messukeskus",
     "url": "https://www.messukeskus.com/kavijalle/tapahtumat/tapahtumakalenteri/",
     "area": "Pasila", "base_url": "https://www.messukeskus.com",
     "capacity": 15000, "category": "culture"},
    {"name": "Olympiastadion",
     "url": "https://www.stadion.fi/fi/tapahtumat/tapahtumat",
     "area": "Olympiastadion", "base_url": "https://www.stadion.fi",
     "capacity": 36000, "category": "sports"},
    {"name": "Finlandia-talo",
     "url": "https://www.finlandiatalo.fi/tapahtumat/",
     "area": "Rautatieasema", "base_url": "https://www.finlandiatalo.fi",
     "capacity": 1700, "category": "culture"},
    {"name": "Kansallisooppera",
     "url": "https://oopperabaletti.fi/ohjelmisto/",
     "area": "Rautatieasema", "base_url": "https://oopperabaletti.fi",
     "capacity": 1340, "category": "culture"},
    {"name": "Kaupunginteatteri",
     "url": "https://hkt.fi/kalenteri/",
     "area": "Rautatieasema", "base_url": "https://hkt.fi",
     "capacity": 900, "category": "culture"},
    {"name": "Musiikkitalo",
     "url": "https://musiikkitalo.fi/konsertit-ja-tapahtumat",
     "area": "Rautatieasema", "base_url": "https://musiikkitalo.fi",
     "capacity": 1700, "category": "concerts"},
    {"name": "Kaapelitehdas",
     "url": "https://www.kaapelitehdas.fi/tapahtumat/",
     "area": "Kamppi", "base_url": "https://www.kaapelitehdas.fi",
     "capacity": 3000, "category": "culture"},
]

SPORTS = [
    {"name": "HIFK (Nordis)", "url": "https://liiga.fi/fi/ohjelma?kausi=2025-2026&sarja=runkosarja&joukkue=hifk&kotiVieras=koti",
     "area": "Rautatieasema", "venue": "Nordis", "capacity": 13500, "sport": "j\u00e4\u00e4kiekko"},
    {"name": "Jokerit (Mestis)", "url": "https://jokerit.fi/ottelut",
     "area": "Rautatieasema", "venue": "Nordis", "capacity": 13500, "sport": "j\u00e4\u00e4kiekko"},
    {"name": "Veikkausliiga", "url": "https://veikkausliiga.com/tilastot/2025/veikkausliiga/ottelut/",
     "area": "Olympiastadion", "venue": "Bolt Arena", "capacity": 10770, "sport": "jalkapallo"},
]


class EventsAgent(BaseAgent):
    name = "EventsAgent"
    ttl = 1800

    def __init__(self):
        super().__init__(name="EventsAgent")

    async def fetch(self):
        t0 = self._now_ms()
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TaxiAI/2.2)"}) as c:
            tasks = [self._src(c, s) for s in SOURCES]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        sigs = []
        for src, r in zip(SOURCES, results):
            if isinstance(r, Exception):
                fb = self._fallback(src)
                if fb:
                    sigs.append(fb)
                continue
            if r:
                sigs.extend(r)
        sigs.extend(self._sports())
        if len(sigs) < 3:
            sigs.extend(self._static())
        el = self._now_ms() - t0
        logger.info("EventsAgent: %d signaalia | %dms", len(sigs), el)
        return AgentResult(agent_name=self.name, status="ok", signals=sigs, elapsed_ms=el)

    async def _src(self, c, s):
        try:
            r = await c.get(s["url"])
            r.raise_for_status()
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException):
            return []
        return self._parse(r.text, s)

    def _parse(self, html, s):
        sigs = []
        now = datetime.now(timezone.utc)
        cat = s.get("category", "culture")
        cal = s.get("url")

        # JSON-LD
        for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
            try:
                data = json.loads(m.group(1))
                evs = []
                if isinstance(data, dict):
                    if data.get("@type") == "Event":
                        evs = [data]
                    elif data.get("@type") == "ItemList":
                        evs = [i.get("item", i) for i in data.get("itemListElement", []) if isinstance(i, dict)]
                elif isinstance(data, list):
                    evs = [d for d in data if isinstance(d, dict) and d.get("@type") == "Event"]
                for ev in evs[:5]:
                    sig = self._ev(ev, s, cat)
                    if sig:
                        sigs.append(sig)
            except Exception:
                pass
        if sigs:
            return sigs[:5]

        # HKT fill rate
        fr = None
        if "hkt.fi" in s.get("url", ""):
            hl = html.lower()
            if "loppuunmyyty" in hl:
                fr = 1.0
            elif "viimeiset" in hl or "vain muutama" in hl:
                fr = 0.85

        og = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html, re.IGNORECASE)
        if og:
            title = og.group(1).strip()[:50]
            sc = 2.0
            u = 2
            tag = ""
            if fr and fr >= 1.0:
                sc, u, tag = 4.0, 5, " [LOPPUUNMYYTY]"
            elif fr and fr >= 0.85:
                sc, u, tag = 3.5, 4, " [Viimeiset liput]"
            sigs.append(Signal(
                area=s.get("area", "Rautatieasema"),
                score_delta=sc, urgency=u,
                reason=s["name"] + ": " + title + tag,
                expires_at=now + timedelta(hours=6),
                source_url=cal,
                title=s["name"] + ": " + title + tag,
                description=s["name"], agent=self.name, category=cat,
                extra={"venue": s["name"], "fill_rate": fr, "calendar_url": cal},
            ))
        return sigs[:5]

    def _ev(self, ev, s, cat):
        name = ev.get("name", "").strip()
        if not name:
            return None
        url = ev.get("url", "")
        bu = s.get("base_url", "")
        if url and not url.startswith("http"):
            url = bu + url
        if not url:
            url = s.get("url")
        now = datetime.now(timezone.utc)
        sd = ev.get("startDate", "")
        ed = ev.get("endDate", "")
        sdt = edt = None
        hu = None
        if sd:
            try:
                sdt = datetime.fromisoformat(sd.replace("Z", "+00:00"))
                hu = (sdt - now).total_seconds() / 3600
            except ValueError:
                pass
        if ed:
            try:
                edt = datetime.fromisoformat(ed.replace("Z", "+00:00"))
            except ValueError:
                pass
        if not edt and sdt:
            edt = sdt + timedelta(hours=DEFAULT_DUR_H)

        offers = ev.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        avail = offers.get("availability", "") if isinstance(offers, dict) else ""
        fr = None
        if "SoldOut" in avail: fr = 1.0
        elif "LimitedAvailability" in avail: fr = 0.85
        elif "InStock" in avail: fr = 0.5

        sc, u = 2.5, 2
        if hu is not None:
            if 0 <= hu <= 2: sc, u = 6.0, 6
            elif hu <= 6: sc, u = 4.5, 4
            elif hu <= 24: sc, u = 3.0, 3
        if fr and fr >= 0.85:
            sc += 1.0
            u = min(u + 1, 9)

        # Ennakkovaroitus
        if edt:
            me = (edt - now).total_seconds() / 60
            if 0 < me <= PREDICT_MIN:
                cap = s.get("capacity") or 5000
                et = edt.strftime("%H:%M")
                if me <= 30: sc, u = max(sc, 8.0), max(u, 7)
                elif me <= 60: sc, u = max(sc, 6.0), max(u, 5)
                else: sc, u = max(sc, 4.0), max(u, 4)
                reason = f"{s['name']} {name[:30]} p\u00e4\u00e4ttyy {et} -- {cap} katsojaa"
                return Signal(
                    area=s.get("area", "Rautatieasema"),
                    score_delta=sc, urgency=u, reason=reason,
                    expires_at=edt + timedelta(minutes=30),
                    source_url=url, title=f"P\u00e4\u00e4ttyy: {name[:40]}",
                    description=reason, agent=self.name, category=cat,
                    extra={"venue": s["name"], "capacity": cap,
                           "minutes_to_end": round(me), "predictive": True},
                )

        tag = ""
        if fr and fr >= 1.0: tag = " [LOPPUUNMYYTY]"
        elif fr and fr >= 0.85: tag = " [Viimeiset liput]"
        dd = sdt.strftime("%d.%m %H:%M") if sdt else ""
        desc = s["name"]
        if dd: desc += " " + dd
        desc += tag
        exp = edt + timedelta(minutes=30) if edt else now + timedelta(hours=6)

        return Signal(
            area=s.get("area", "Rautatieasema"),
            score_delta=sc, urgency=u, reason=desc,
            expires_at=exp, source_url=url,
            title=name[:60] + tag, description=desc,
            agent=self.name, category=cat,
            extra={"venue": s["name"], "capacity": s.get("capacity"),
                   "fill_rate": fr, "hours_until": hu, "calendar_url": s.get("url")},
        )

    def _fallback(self, s):
        now = datetime.now(timezone.utc)
        return Signal(
            area=s.get("area", "Rautatieasema"),
            score_delta=1.5, urgency=1,
            reason="Tarkista " + s["name"],
            expires_at=now + timedelta(hours=6),
            source_url=s.get("url"), title=s["name"],
            description="Tarkista " + s["name"],
            agent=self.name, category=s.get("category", "culture"),
            extra={"venue": s["name"], "static_fallback": True},
        )

    def _sports(self):
        sigs = []
        now = datetime.now(timezone.utc)
        for s in SPORTS:
            sigs.append(Signal(
                area=s["area"], score_delta=3.0, urgency=2,
                reason=f"{s['venue']} -- {s['capacity']} katsojaa | {s['name']}",
                expires_at=now + timedelta(hours=12),
                source_url=s["url"], title=s["name"],
                description=f"{s['venue']} {s['capacity']} katsojaa",
                agent=self.name, category="sports",
                extra={"venue": s["venue"], "capacity": s["capacity"], "sport": s["sport"]},
            ))
        return sigs

    def _static(self):
        sigs = []
        now = datetime.now(timezone.utc)
        try:
            from src.taxiapp.data.static_events import CULTURE_VENUES
            for v in CULTURE_VENUES[:3]:
                sigs.append(Signal(
                    area=v.area, score_delta=1.0, urgency=1,
                    reason=f"Tarkista {v.name}", expires_at=now + timedelta(hours=12),
                    source_url=v.url, title=v.name,
                    description=f"{v.name} -- katso ohjelma",
                    agent=self.name, category=v.category,
                    extra={"venue": v.name, "static": True},
                ))
        except ImportError:
            pass
        return sigs
