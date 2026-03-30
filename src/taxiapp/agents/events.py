# events.py -- EventsAgent
# Helsinki Taxi AI
#
# Hakee tapahtumat useista lahteista:
#   1. Messukeskus
#   2. Olympiastadion
#   3. Finlandia-talo
#   4. Helsingin kaupunginteatteri
#   5. Kansallisooppera
#   6. Kansallisteatteri
#   7. Musiikkitalo
#   8. Tavastia
#
# Jokaisella signaalilla on source_url -> suora linkki tapahtuman sivulle.
# Tayttöasteet luetaan JSON-LD offers.availability -kentästä.
#
# HUOM: myhelsinki.fi (301/302) ja digitransit.fi (401) poistettu.

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


# ---------------------------------------------------------------------------
# RSS-LAHTEET JA NIIDEN ASETUKSET
# ---------------------------------------------------------------------------

RSS_SOURCES: list[dict] = [
    {
        "name": "Messukeskus",
        "url": "https://www.messukeskus.com/kavijalle/tapahtumat/tapahtumakalenteri/",
        "area": "pasila",
        "base_url": "https://www.messukeskus.com",
        "capacity": 15000,
        "calendar_url": "https://www.messukeskus.com/kavijalle/tapahtumat/tapahtumakalenteri/",
    },
    {
        "name": "Olympiastadion",
        "url": "https://www.olympiastadion.fi/tapahtumat/",
        "area": "helsinki_central",
        "base_url": "https://www.olympiastadion.fi",
        "capacity": 36000,
        "calendar_url": "https://www.olympiastadion.fi/tapahtumat/",
    },
    {
        "name": "Finlandia-talo",
        "url": "https://www.finlandiatalo.fi/tapahtumakalenteri/",
        "area": "helsinki_central",
        "base_url": "https://www.finlandiatalo.fi",
        "capacity": 1700,
        "calendar_url": "https://www.finlandiatalo.fi/tapahtumakalenteri/",
    },
    {
        "name": "Kansallisooppera",
        "url": "https://oopperabaletti.fi/ohjelmisto-ja-liput/",
        "area": "helsinki_central",
        "base_url": "https://oopperabaletti.fi",
        "capacity": 1340,
        "calendar_url": "https://oopperabaletti.fi/ohjelmisto-ja-liput/",
    },
    {
        "name": "Kaupunginteatteri",
        "url": "https://hkt.fi/kalenteri/",
        "area": "helsinki_central",
        "base_url": "https://hkt.fi",
        "capacity": 900,
        "calendar_url": "https://hkt.fi/kalenteri/",
    },
    {
        "name": "Kansallisteatteri",
        "url": "https://kansallisteatteri.fi/esityskalenteri/",
        "area": "helsinki_central",
        "base_url": "https://kansallisteatteri.fi",
        "capacity": 700,
        "calendar_url": "https://kansallisteatteri.fi/esityskalenteri/",
    },
    {
        "name": "Musiikkitalo",
        "url": "https://www.musiikkitalo.fi/tapahtumat/",
        "area": "helsinki_central",
        "base_url": "https://www.musiikkitalo.fi",
        "capacity": 1700,
        "calendar_url": "https://www.musiikkitalo.fi/tapahtumat/",
    },
    {
        "name": "Tavastia",
        "url": "https://tavastiaklubi.fi/fi_FI/ohjelma",
        "area": "helsinki_central",
        "base_url": "https://tavastiaklubi.fi",
        "capacity": 900,
        "calendar_url": "https://tavastiaklubi.fi/fi_FI/ohjelma",
    },
    {
        "name": "Stadissa.fi",
        "url": "https://stadissa.fi/tapahtumat",
        "area": "helsinki_central",
        "base_url": "https://stadissa.fi",
        "capacity": None,
        "calendar_url": "https://stadissa.fi/tapahtumat",
    },
]

# Urheilutapahtumat -- staattiset kalenterilinkit
SPORTS_CALENDARS: list[dict] = [
    {
        "name": "HIFK kotiottelut (Liiga/Nordis)",
        "url": (
            "https://liiga.fi/fi/ohjelma"
            "?kausi=2025-2026&sarja=runkosarja"
            "&joukkue=hifk&kotiVieras=koti"
        ),
        "area": "helsinki_central",
        "venue": "Nordis (Nokia Arena)",
        "capacity": 13500,
        "sport": "jaakaiekko",
    },
    {
        "name": "Jokerit (Mestis)",
        "url": "https://jokerit.fi/ottelut",
        "area": "helsinki_central",
        "venue": "Nordis",
        "capacity": 13500,
        "sport": "jaakaiekko",
    },
    {
        "name": "Kiekko-Espoo (Metro Areena)",
        "url": (
            "https://liiga.fi/fi/ohjelma"
            "?kausi=2025-2026&sarja=runkosarja"
            "&joukkue=k-espoo&kotiVieras=koti"
        ),
        "area": "espoo_center",
        "venue": "Metro Areena",
        "capacity": 8000,
        "sport": "jaakaiekko",
    },
    {
        "name": "Veikkausliiga",
        "url": "https://veikkausliiga.com/tilastot/2025/veikkausliiga/ottelut/",
        "area": "helsinki_central",
        "venue": "Bolt Arena",
        "capacity": 10770,
        "sport": "jalkapallo",
    },
]

# Aikaikkuna tunneissa
LOOKAHEAD_HOURS: int = 6
LOOKAHEAD_DAILY_HOURS: int = 24


# ---------------------------------------------------------------------------
# EVENTSAGENT
# ---------------------------------------------------------------------------

class EventsAgent(BaseAgent):
    """
    Hakee tapahtumat useista helsinkilaislahteista.

    Strategia:
      1. Yritetaan hakea live-data httpx:lla
      2. Jos sivu ei vastaa, kaytetaan staattista kalenterilinkkia
      3. Urheilutapahtumat lisataan aina staattisina signaaleina
    """

    def __init__(self) -> None:
        super().__init__(name="EventsAgent")

    async def fetch(self) -> AgentResult:
        """Hae tapahtumat kaikista lahteista rinnakkain."""
        start_ms = self._now_ms()

        async with httpx.AsyncClient(
            timeout=8.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; TaxiAI/1.0; "
                    "Helsinki taxi assistant)"
                )
            },
        ) as client:
            tasks = [
                self._fetch_source(client, source)
                for source in RSS_SOURCES
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        signals: list[Signal] = []

        for source, result in zip(RSS_SOURCES, results):
            if isinstance(result, Exception):
                logger.debug(
                    "EventsAgent: %s virhe: %s", source["name"], result
                )
                fallback = self._make_static_calendar_signal(source)
                if fallback:
                    signals.append(fallback)
                continue
            if result:
                signals.extend(result)

        # Urheilutapahtumat aina mukaan
        signals.extend(self._build_sports_signals())

        elapsed = self._now_ms() - start_ms
        logger.info(
            "EventsAgent: %d tapahtumaa -> %d signaalia",
            len(signals),
            len(signals),
        )
        logger.info(
            "EventsAgent: ok | %d signaalia | %dms", len(signals), elapsed
        )

        return AgentResult(
            agent_name=self.name,
            signals=signals,
            ok=True,
            elapsed_ms=elapsed,
        )

    async def _fetch_source(
        self, client: httpx.AsyncClient, source: dict
    ) -> list[Signal]:
        """Hae yksi lahde. Palauttaa signaalilistan."""
        try:
            resp = await client.get(source["url"])
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (301, 302, 403, 404):
                return []
            raise
        except (httpx.ConnectError, httpx.TimeoutException):
            return []

        return self._parse_html_events(resp.text, source)

    def _parse_html_events(self, html: str, source: dict) -> list[Signal]:
        """
        Parsii tapahtumat HTML:sta.
        Etsii JSON-LD schema.org Event -merkinnät.
        Palauttaa enintään 5 signaalia per lahde.
        """
        signals: list[Signal] = []
        base_url = source.get("base_url", "")
        calendar_url = source.get("calendar_url", source["url"])

        # JSON-LD Event -merkinnät
        json_ld_pattern = re.compile(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            re.DOTALL | re.IGNORECASE,
        )

        for match in json_ld_pattern.finditer(html):
            try:
                data = json.loads(match.group(1))
                events: list[dict] = []

                if isinstance(data, dict):
                    t = data.get("@type", "")
                    if t == "Event":
                        events = [data]
                    elif t == "ItemList":
                        for item in data.get("itemListElement", []):
                            if isinstance(item, dict):
                                events.append(item.get("item", item))
                elif isinstance(data, list):
                    events = [
                        d for d in data
                        if isinstance(d, dict) and d.get("@type") == "Event"
                    ]

                for event_data in events[:5]:
                    sig = self._event_to_signal(event_data, source, base_url)
                    if sig:
                        signals.append(sig)

            except Exception:
                pass

        if signals:
            return signals[:5]

        # Fallback: og:title + og:url
        og_title_m = re.search(
            r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
            html,
            re.IGNORECASE,
        )
        og_url_m = re.search(
            r'<meta[^>]*property="og:url"[^>]*content="([^"]+)"',
            html,
            re.IGNORECASE,
        )

        if og_title_m:
            title = og_title_m.group(1).strip()
            event_url = og_url_m.group(1) if og_url_m else calendar_url
            if event_url and not event_url.startswith("http"):
                event_url = base_url + event_url

            title_lower = title.lower()
            _NAV_BL = {"lippumyymala","verkkokauppa","nayttamot","ohjelmisto",
                "yritys","ryhmamyynti","yhteystiedot","tietoa","saavutettavuus",
                "tietosuoja","evasteet","medialle","lahjakortti","vuokraus","ravintola"}
            is_nav = any(bl in title_lower for bl in _NAV_BL)
            if not is_nav:
                sig = Signal(
                    area=source.get("area", "helsinki_central"),
                    score_delta=2.0,
                    reason=source["name"] + ": " + title[:50],
                    urgency=2,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
                    source_url=event_url or calendar_url,
                    extra={
                        "venue": source["name"],
                        "capacity": source.get("capacity"),
                        "fill_rate": None,
                        "calendar_url": calendar_url,
                    },
                )
                signals.append(sig)

        return signals[:5]

    def _event_to_signal(
        self, event_data: dict, source: dict, base_url: str
    ) -> Optional[Signal]:
        """Muunna JSON-LD Event -objekti signaaliksi."""
        name = event_data.get("name", "").strip()
        if not name:
            return None

        # Tapahtuman URL
        event_url = event_data.get("url", "")
        if event_url and not event_url.startswith("http"):
            event_url = base_url + event_url
        if not event_url:
            event_url = source.get("calendar_url", source["url"])

        # Paivamaara
        start_date_str = event_data.get("startDate", "")
        now_utc = datetime.now(timezone.utc)
        hours_until: Optional[float] = None
        date_display = ""

        if start_date_str:
            try:
                start_dt = datetime.fromisoformat(
                    start_date_str.replace("Z", "+00:00")
                )
                hours_until = (start_dt - now_utc).total_seconds() / 3600
                date_display = start_dt.strftime("%d.%m %H:%M")
            except ValueError:
                date_display = start_date_str[:16]

        # Tayttöaste JSON-LD offers.availability -kentasta
        offers = event_data.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        availability = offers.get("availability", "") if isinstance(offers, dict) else ""
        fill_rate: Optional[float] = None

        if "SoldOut" in availability:
            fill_rate = 1.0
        elif "LimitedAvailability" in availability:
            fill_rate = 0.85
        elif "InStock" in availability:
            fill_rate = 0.5

        # Pisteet
        score = 2.5
        urgency = 2

        if hours_until is not None:
            if 0 <= hours_until <= 2:
                score = 6.0
                urgency = 6
            elif 2 < hours_until <= LOOKAHEAD_HOURS:
                score = 4.5
                urgency = 4
            elif hours_until <= LOOKAHEAD_DAILY_HOURS:
                score = 3.0
                urgency = 3

        if fill_rate and fill_rate >= 0.85:
            score += 1.0
            urgency = min(urgency + 1, 9)

        # Kuvaus
        capacity = source.get("capacity")
        fill_text = ""
        if fill_rate == 1.0:
            fill_text = " [LOPPUUNMYYTY]"
        elif fill_rate and fill_rate >= 0.85:
            fill_text = " [Viimeiset liput]"
        elif capacity:
            fill_text = " (" + str(capacity) + " katsojaa)"

        description = source["name"]
        if date_display:
            description += " -- " + date_display
        description += fill_text

        return Signal(
            area=source.get("area", "helsinki_central"),
            score_delta=score,
            reason=name[:60] + " | " + description,
            urgency=urgency,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=3),
            source_url=event_url,
            extra={
                "venue": source["name"],
                "capacity": capacity,
                "fill_rate": fill_rate,
                "start_date": start_date_str,
                "hours_until": hours_until,
                "calendar_url": source.get("calendar_url", source["url"]),
            },
        )

    def _make_static_calendar_signal(
        self, source: dict
    ) -> Optional[Signal]:
        """
        Luo staattinen signaali kalenterilinkilla kun live-haku epaonnistuu.
        Kuljettaja voi painaa -> avautuu tapahtumapaikan kalenteri.
        """
        calendar_url = source.get("calendar_url", source["url"])
        if not calendar_url:
            return None

        return Signal(
            area=source.get("area", "helsinki_central"),
            score_delta=1.5,
            reason=source["name"] + " -- kalenteri",
            urgency=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
            source_url=calendar_url,
            extra={
                "venue": source["name"],
                "capacity": source.get("capacity"),
                "fill_rate": None,
                "static_fallback": True,
                "calendar_url": calendar_url,
            },
        )

    def _build_sports_signals(self) -> list[Signal]:
        """
        Luo staattiset urheilutapahtumisignaalit.
        Linkit urheilu-kalentereihin joista kuljettaja naakee otteluohjelmat.
        """
        signals: list[Signal] = []
        for sport in SPORTS_CALENDARS:
            sig = Signal(
                area=sport["area"],
                score_delta=3.0,
                reason=(
                    sport["name"] + " | " + sport["venue"]
                    + " -- kap. " + str(sport["capacity"])
                ),
                urgency=2,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
                source_url=sport["url"],
                extra={
                    "venue": sport["venue"],
                    "capacity": sport["capacity"],
                    "sport": sport["sport"],
                    "fill_rate": None,
                    "calendar_url": sport["url"],
                },
            )
            signals.append(sig)
        return signals

    @staticmethod
    def _now_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
