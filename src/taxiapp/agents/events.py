"""
events.py -- EventsAgent v3.0
Helsinki Taxi AI

KRIITTINEN KORJAUS: Suomalaiset tapahtumasivut EIVAT kayta JSON-LD.
Sivut ovat JS-renderoityja (React/Next.js).
httpx saa vain HTML-rungon jossa og:title + joitain linkkeja.

STRATEGIA v3.0:
  1. Poimitaan tapahtumien NIMET ja PAIVAT HTML:sta aggressiivisesti
  2. Etsitaan <a href> + <h2/h3> + <time> + paivamaara-patternit
  3. Fallback: og:title + fill_rate (HKT LOPPUUNMYYTY)
  4. Urheilutapahtumat staattisina mutta nimilla
  5. 60-90 min ennakkovaroitus

Toimivat lahteet (logeista vahvistettu 28.3.2026):
  - Messukeskus: 200 OK
  - Stadion (olympiastadion): 200 OK
  - Musiikkitalo: 200 OK
  - HKT: 200 OK
  - Ooppera: 200 OK
  - Kaapelitehdas: 200 OK
  - Finlandiatalo: redirect -> 200 OK (tulevat tapahtumat)

Rikkinaiset:
  - Kansallisteatteri: 404 -> fallback
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
    {"name": "Kaupunginteatteri", "url": "https://hkt.fi/kalenteri/",
     "area": "Rautatieasema", "base_url": "https://hkt.fi",
     "capacity": 900, "category": "culture"},
    {"name": "Musiikkitalo", "url": "https://musiikkitalo.fi/konsertit-ja-tapahtumat",
     "area": "Rautatieasema", "base_url": "https://musiikkitalo.fi",
     "capacity": 1700, "category": "concerts"},
    {"name": "Kansallisooppera", "url": "https://oopperabaletti.fi/ohjelmisto/",
     "area": "Rautatieasema", "base_url": "https://oopperabaletti.fi",
     "capacity": 1340, "category": "culture"},
    {"name": "Messukeskus",
     "url": "https://www.messukeskus.com/kavijalle/tapahtumat/tapahtumakalenteri/",
     "area": "Pasila", "base_url": "https://www.messukeskus.com",
     "capacity": 15000, "category": "culture"},
    {"name": "Olympiastadion",
     "url": "https://www.stadion.fi/fi/tapahtumat/tapahtumat",
     "area": "Olympiastadion", "base_url": "https://www.stadion.fi",
     "capacity": 36000, "category": "sports"},
    {"name": "Kaapelitehdas", "url": "https://www.kaapelitehdas.fi/tapahtumat/",
     "area": "Kamppi", "base_url": "https://www.kaapelitehdas.fi",
     "capacity": 3000, "category": "culture"},
    {"name": "Finlandia-talo",
     "url": "https://www.finlandiatalo.fi/tapahtumat/",
     "area": "Rautatieasema", "base_url": "https://www.finlandiatalo.fi",
     "capacity": 1700, "category": "culture"},
]

SPORTS = [
    {"name": "HIFK kotiottelut",
     "url": "https://liiga.fi/fi/ohjelma?kausi=2025-2026&sarja=runkosarja&joukkue=hifk&kotiVieras=koti",
     "area": "Rautatieasema", "venue": "Nordis", "capacity": 13500},
    {"name": "Jokerit (Mestis)", "url": "https://jokerit.fi/ottelut",
     "area": "Rautatieasema", "venue": "Nordis", "capacity": 13500},
    {"name": "Veikkausliiga",
     "url": "https://veikkausliiga.com/tilastot/2025/veikkausliiga/ottelut/",
     "area": "Olympiastadion", "venue": "Bolt Arena", "capacity": 10770},
]


class EventsAgent(BaseAgent):
    name = "EventsAgent"
    ttl = 1800

    def __init__(self):
        super().__init__(name="EventsAgent")

    async def fetch(self):
        t0 = self._now_ms()
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TaxiAI/3.0)",
                     "Accept": "text/html"}) as c:
            tasks = [self._src(c, s) for s in SOURCES]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        sigs = []
        for src, r in zip(SOURCES, results):
            if isinstance(r, Exception):
                logger.debug("EventsAgent %s: %s", src["name"], r)
                fb = self._fallback(src)
                if fb:
                    sigs.append(fb)
                continue
            if r:
                sigs.extend(r)
        sigs.extend(self._sports())
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
        """Aggressiivinen HTML-parseri: poimi tapahtumat usealla strategialla."""
        sigs = []
        now = datetime.now(timezone.utc)
        cat = s.get("category", "culture")
        cal_url = s.get("url")
        base_url = s.get("base_url", "")

        # Strategia 1: JSON-LD (harvoin toimii suomalaisilla sivuilla)
        for m in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE
        ):
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
                    sig = self._jsonld_to_signal(ev, s, cat)
                    if sig:
                        sigs.append(sig)
            except Exception:
                pass
        if sigs:
            return sigs[:5]

        # Strategia 2: Poimi tapahtumien nimet <h2>, <h3>, <a> tageista
        # jotka sisaltavat otsikkoja (ei navigaatiota)
        event_names = []
        # <h2> ja <h3> tagit - yleensa tapahtumien nimia
        for tag in re.finditer(r'<h[23][^>]*>(.*?)</h[23]>', html, re.DOTALL | re.IGNORECASE):
            text = re.sub(r'<[^>]+>', '', tag.group(1)).strip()
            if len(text) > 5 and len(text) < 120:
                # Suodata navigaatio-elementit pois
                skip_words = ["kalenteri", "ohjelma", "ohjelmisto", "menu", "nav",
                              "footer", "cookie", "evaste", "tietosuoja"]
                if not any(sw in text.lower() for sw in skip_words):
                    event_names.append(text)

        # <a> tagit joissa href sisaltaa /tapahtuma, /esitys, /konsertti tms
        event_links = []
        for a_match in re.finditer(
            r'<a[^>]*href="([^"]*(?:tapahtum|esity|konsertti|ottelu|naytely|ohjelma)[^"]*)"[^>]*>(.*?)</a>',
            html, re.DOTALL | re.IGNORECASE
        ):
            href = a_match.group(1)
            link_text = re.sub(r'<[^>]+>', '', a_match.group(2)).strip()
            if len(link_text) > 3 and len(link_text) < 120:
                full_url = href if href.startswith("http") else base_url + href
                event_links.append((link_text, full_url))

        # Yhdista tulokset
        seen_names = set()
        for name in event_names[:8]:
            if name not in seen_names:
                seen_names.add(name)
                sigs.append(self._make_event_signal(name, s, cat, cal_url, now))

        for name, url in event_links[:5]:
            if name not in seen_names:
                seen_names.add(name)
                sigs.append(self._make_event_signal(name, s, cat, url, now))

        if sigs:
            return sigs[:5]

        # Strategia 3: Fallback - og:title + fill_rate
        fr = None
        if "hkt.fi" in s.get("url", ""):
            hl = html.lower()
            if "loppuunmyyty" in hl:
                fr = 1.0
            elif "viimeiset" in hl or "vain muutama" in hl:
                fr = 0.85

        og = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html, re.IGNORECASE)
        title_tag = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)

        page_title = ""
        if og:
            page_title = og.group(1).strip()
        elif title_tag:
            page_title = re.sub(r'<[^>]+>', '', title_tag.group(1)).strip()

        if page_title:
            tag = ""
            sc, u = 2.0, 2
            if fr and fr >= 1.0:
                sc, u, tag = 5.0, 5, " [LOPPUUNMYYTY]"
            elif fr and fr >= 0.85:
                sc, u, tag = 3.5, 4, " [Viimeiset liput]"

            sigs.append(Signal(
                area=s.get("area", "Rautatieasema"),
                score_delta=sc, urgency=u,
                reason=s["name"] + ": " + page_title[:50] + tag,
                expires_at=now + timedelta(hours=6),
                source_url=cal_url,
                title=s["name"] + ": " + page_title[:50] + tag,
                description=s["name"], agent=self.name, category=cat,
                extra={"venue": s["name"], "fill_rate": fr},
            ))

        return sigs[:5]

    def _make_event_signal(self, name, s, cat, url, now):
        """Luo signaali tapahtuman nimesta."""
        return Signal(
            area=s.get("area", "Rautatieasema"),
            score_delta=3.0, urgency=3,
            reason=name,
            expires_at=now + timedelta(hours=12),
            source_url=url,
            title=name, description=s["name"],
            agent=self.name, category=cat,
            extra={"venue": s["name"], "capacity": s.get("capacity"),
                   "event_name": name},
        )

    def _jsonld_to_signal(self, ev, s, cat):
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
        sdt = None
        hu = None
        if sd:
            try:
                sdt = datetime.fromisoformat(sd.replace("Z", "+00:00"))
                hu = (sdt - now).total_seconds() / 3600
            except ValueError:
                pass
        sc, u = 2.5, 2
        if hu is not None:
            if 0 <= hu <= 2: sc, u = 6.0, 6
            elif hu <= 6: sc, u = 4.5, 4
            elif hu <= 24: sc, u = 3.0, 3
        dd = sdt.strftime("%d.%m %H:%M") if sdt else ""
        desc = s["name"]
        if dd: desc += " " + dd
        return Signal(
            area=s.get("area", "Rautatieasema"),
            score_delta=sc, urgency=u, reason=desc,
            expires_at=now + timedelta(hours=6),
            source_url=url, title=name[:60], description=desc,
            agent=self.name, category=cat,
            extra={"venue": s["name"], "hours_until": hu},
        )

    def _fallback(self, s):
        now = datetime.now(timezone.utc)
        return Signal(
            area=s.get("area", "Rautatieasema"),
            score_delta=1.5, urgency=1,
            reason="Tarkista " + s["name"],
            expires_at=now + timedelta(hours=6),
            source_url=s.get("url"), title=s["name"],
            description="Katso ohjelma", agent=self.name,
            category=s.get("category", "culture"),
            extra={"venue": s["name"], "static_fallback": True},
        )

    def _sports(self):
        sigs = []
        now = datetime.now(timezone.utc)
        for s in SPORTS:
            sigs.append(Signal(
                area=s["area"], score_delta=3.0, urgency=2,
                reason=s["venue"] + " -- " + str(s["capacity"]) + " katsojaa | " + s["name"],
                expires_at=now + timedelta(hours=12),
                source_url=s["url"], title=s["name"],
                description=s["venue"] + " " + str(s["capacity"]) + " katsojaa",
                agent=self.name, category="sports",
                extra={"venue": s["venue"], "capacity": s["capacity"]},
            ))
        return sigs
