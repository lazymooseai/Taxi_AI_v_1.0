"""
events.py -- EventsAgent
Helsinki Taxi AI v2.0

Hakee tapahtumat useista lahteista + staattinen tietopankki.

UUTTA v2.0:
  - 60-90 min ennakkovaroitus tapahtumien paattymisesta
  - Staattinen tapahtumatietopankki (Tapahtumat_2026_2.pdf)
  - Korjattu Signal-luokan kenttien kaytto
  - Kategoriakohtaiset signaalit (culture/sports/concerts)

Aikaikkuna: 6h (live), 24h (daily)
Ennakkovaroitus: 90min ennen tapahtuman paattymista
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


# ---------------------------------------------------------------------------
# ENNAKKOVAROITUS-ASETUKSET
# ---------------------------------------------------------------------------

PREDICTIVE_WINDOW_MIN: int = 90    # Ennakkovaroitusikkuna minuuteissa
EVENT_DURATION_DEFAULT_H: float = 2.5  # Oletustapahtuman kesto tunneissa


# ---------------------------------------------------------------------------
# RSS-LAHTEET JA NIIDEN ASETUKSET
# ---------------------------------------------------------------------------

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
        "url": "https://www.olympiastadion.fi/tapahtumat/",
        "area": "Olympiastadion",
        "base_url": "https://www.olympiastadion.fi",
        "capacity": 36000,
        "calendar_url": "https://www.olympiastadion.fi/tapahtumat/",
        "category": "sports",
    },
    {
        "name": "Finlandia-talo",
        "url": "https://www.finlandiatalo.fi/tapahtumakalenteri/",
        "area": "Rautatieasema",
        "base_url": "https://www.finlandiatalo.fi",
        "capacity": 1700,
        "calendar_url": "https://www.finlandiatalo.fi/tapahtumakalenteri/",
        "category": "culture",
    },
    {
        "name": "Kansallisooppera",
        "url": "https://oopperabaletti.fi/ohjelmisto-ja-liput/",
        "area": "Rautatieasema",
        "base_url": "https://oopperabaletti.fi",
        "capacity": 1340,
        "calendar_url": "https://oopperabaletti.fi/ohjelmisto-ja-liput/",
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
        "url": "https://kansallisteatteri.fi/esityskalenteri/",
        "area": "Rautatieasema",
        "base_url": "https://kansallisteatteri.fi",
        "capacity": 700,
        "calendar_url": "https://kansallisteatteri.fi/esityskalenteri/",
        "category": "culture",
    },
    {
        "name": "Musiikkitalo",
        "url": "https://www.musiikkitalo.fi/tapahtumat/",
        "area": "Rautatieasema",
        "base_url": "https://www.musiikkitalo.fi",
        "capacity": 1700,
        "calendar_url": "https://www.musiikkitalo.fi/tapahtumat/",
        "category": "concerts",
    },
    {
        "name": "Tavastia",
        "url": "https://tavastiaklubi.fi/fi_FI/ohjelma",
        "area": "Kamppi",
        "base_url": "https://tavastiaklubi.fi",
        "capacity": 900,
        "calendar_url": "https://tavastiaklubi.fi/fi_FI/ohjelma",
        "category": "concerts",
    },
    {
        "name": "Stadissa.fi",
        "url": "https://stadissa.fi/tapahtumat",
        "area": "Kamppi",
        "base_url": "https://stadissa.fi",
        "capacity": None,
        "calendar_url": "https://stadissa.fi/tapahtumat",
        "category": "culture",
    },
]

# Urheilutapahtumat
SPORTS_CALENDARS: list[dict] = [
    {
        "name": "HIFK kotiottelut (Liiga/Nordis)",
        "url": (
            "https://liiga.fi/fi/ohjelma"
            "?kausi=2025-2026&sarja=runkosarja"
            "&joukkue=hifk&kotiVieras=koti"
        ),
        "area": "Rautatieasema",
        "venue": "Nordis (Nokia Arena)",
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


# ---------------------------------------------------------------------------
# EVENTSAGENT
# ---------------------------------------------------------------------------

class EventsAgent(BaseAgent):
    """
    Hakee tapahtumat useista helsinkilaisista lahteista.

    v2.0 uutta:
      - Ennakkovaroitus: sininen kortti nayttaa tapahtuman
        paattymisen 60-90 min ennen purkautumista
      - Staattinen tietopankki fallback-tietona
      - Kategoriakohtaiset signaalit
    """

    name = "EventsAgent"
    ttl = 1800  # 30 min

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
                    "Mozilla/5.0 (compatible; TaxiAI/2.0; "
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

        # Staattinen tietopankki fallback
        if len(signals) < 3:
            signals.extend(self._build_static_fallback_signals())

        elapsed = self._now_ms() - start_ms
        logger.info(
            "EventsAgent: %d signaalia | %dms", len(signals), elapsed
        )

        return AgentResult(
            agent_name=self.name,
            status="ok",
            signals=signals,
            raw_data={"signal_count": len(signals)},
            elapsed_ms=elapsed,
        )

    async def _fetch_source(
        self, client: httpx.AsyncClient, source: dict
    ) -> list[Signal]:
        """Hae yksi lahde."""
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
        """Parsii tapahtumat HTML:sta (JSON-LD schema.org Event)."""
        signals: list[Signal] = []
        base_url = source.get("base_url", "")
        calendar_url = source.get("calendar_url", source["url"])
        category = source.get("category", "culture")

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
                    sig = self._event_to_signal(
                        event_data, source, base_url, category
                    )
                    if sig:
                        signals.append(sig)

            except Exception:
                pass

        if signals:
            return signals[:5]

        # Fallback: og:title
        og_title_m = re.search(
            r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
            html, re.IGNORECASE,
        )
        if og_title_m:
            title = og_title_m.group(1).strip()
            now = datetime.now(timezone.utc)
            sig = Signal(
                area=source.get("area", "Rautatieasema"),
                score_delta=2.0,
                reason=source["name"] + " -- katso aikataulu ja liput",
                urgency=2,
                expires_at=now + timedelta(hours=6),
                source_url=calendar_url,
                title=source["name"] + ": " + title[:50],
                description=source["name"] + " -- katso aikataulu",
                agent=self.name,
                category=category,
                extra={
                    "venue": source["name"],
                    "capacity": source.get("capacity"),
                    "calendar_url": calendar_url,
                },
            )
            signals.append(sig)

        return signals[:5]

    def _event_to_signal(
        self,
        event_data: dict,
        source: dict,
        base_url: str,
        category: str,
    ) -> Optional[Signal]:
        """Muunna JSON-LD Event -objekti signaaliksi."""
        name = event_data.get("name", "").strip()
        if not name:
            return None

        event_url = event_data.get("url", "")
        if event_url and not event_url.startswith("http"):
            event_url = base_url + event_url
        if not event_url:
            event_url = source.get("calendar_url", source["url"])

        start_date_str = event_data.get("startDate", "")
        end_date_str = event_data.get("endDate", "")
        now_utc = datetime.now(timezone.utc)
        hours_until: Optional[float] = None
        date_display = ""

        start_dt: Optional[datetime] = None
        end_dt: Optional[datetime] = None

        if start_date_str:
            try:
                start_dt = datetime.fromisoformat(
                    start_date_str.replace("Z", "+00:00")
                )
                hours_until = (start_dt - now_utc).total_seconds() / 3600
                date_display = start_dt.strftime("%d.%m %H:%M")
            except ValueError:
                date_display = start_date_str[:16]

        if end_date_str:
            try:
                end_dt = datetime.fromisoformat(
                    end_date_str.replace("Z", "+00:00")
                )
            except ValueError:
                end_dt = None

        # Laske paattymisaika jos ei suoraan saatavilla
        if end_dt is None and start_dt is not None:
            end_dt = start_dt + timedelta(hours=EVENT_DURATION_DEFAULT_H)

        # Tayttoaste
        offers = event_data.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        availability = (
            offers.get("availability", "") if isinstance(offers, dict) else ""
        )
        fill_rate: Optional[float] = None

        if "SoldOut" in availability:
            fill_rate = 1.0
        elif "LimitedAvailability" in availability:
            fill_rate = 0.85
        elif "InStock" in availability:
            fill_rate = 0.5

        # Pisteet - perus
        score = 2.5
        urgency = 2
        is_predictive = False

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

        # UUTTA v2.0: Ennakkovaroitus paattymisesta
        # Jos tapahtuma paattyy seuraavan 90 min sisalla -> sininen kortti
        if end_dt is not None:
            minutes_to_end = (end_dt - now_utc).total_seconds() / 60
            if 0 < minutes_to_end <= PREDICTIVE_WINDOW_MIN:
                is_predictive = True
                capacity = source.get("capacity") or 5000
                end_time_str = end_dt.strftime("%H:%M")

                # Korotettu pisteytys ennakkovaroitukselle
                if minutes_to_end <= 30:
                    score = max(score, 8.0)
                    urgency = max(urgency, 7)
                elif minutes_to_end <= 60:
                    score = max(score, 6.0)
                    urgency = max(urgency, 5)
                else:
                    score = max(score, 4.0)
                    urgency = max(urgency, 4)

                reason = (
                    f"{source['name']} {name[:30]} paattyy {end_time_str}"
                    f" -- {capacity} katsojaa odottaa kyytiia"
                )

                return Signal(
                    area=source.get("area", "Rautatieasema"),
                    score_delta=score,
                    reason=reason,
                    urgency=urgency,
                    expires_at=end_dt + timedelta(minutes=30),
                    source_url=event_url,
                    title=f"Paattyy pian: {name[:40]}",
                    description=reason,
                    agent=self.name,
                    category=category,
                    extra={
                        "venue": source["name"],
                        "capacity": capacity,
                        "fill_rate": fill_rate,
                        "end_time": end_date_str,
                        "minutes_to_end": round(minutes_to_end),
                        "predictive": True,
                    },
                )

        # Normaali signaali
        capacity = source.get("capacity")
        fill_text = ""
        if fill_rate == 1.0:
            fill_text = " [LOPPUUNMYYTY]"
        elif fill_rate and fill_rate >= 0.85:
            fill_text = " [Viimeiset liput]"
        elif capacity:
            fill_text = f" ({capacity} katsojaa)"

        description = source["name"]
        if date_display:
            description += " -- " + date_display
        description += fill_text

        expires = now_utc + timedelta(hours=6)
        if end_dt:
            expires = end_dt + timedelta(minutes=30)

        return Signal(
            area=source.get("area", "Rautatieasema"),
            score_delta=score,
            reason=description,
            urgency=urgency,
            expires_at=expires,
            source_url=event_url,
            title=name[:60],
            description=description,
            agent=self.name,
            category=category,
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
        """Staattinen signaali kun live-haku epaonnistuu."""
        calendar_url = source.get("calendar_url", source["url"])
        if not calendar_url:
            return None

        now = datetime.now(timezone.utc)
        return Signal(
            area=source.get("area", "Rautatieasema"),
            score_delta=1.5,
            reason="Tarkista " + source["name"] + ":n tapahtumat",
            urgency=1,
            expires_at=now + timedelta(hours=6),
            source_url=calendar_url,
            title=source["name"] + " -- kalenteri",
            description="Tarkista " + source["name"] + ":n tapahtumat",
            agent=self.name,
            category=source.get("category", "culture"),
            extra={
                "venue": source["name"],
                "static_fallback": True,
                "calendar_url": calendar_url,
            },
        )

    def _build_sports_signals(self) -> list[Signal]:
        """Staattiset urheilutapahtumisignaalit."""
        signals: list[Signal] = []
        now = datetime.now(timezone.utc)

        for sport in SPORTS_CALENDARS:
            sig = Signal(
                area=sport["area"],
                score_delta=3.0,
                reason=(
                    sport["venue"] + " -- kapasiteetti "
                    + str(sport["capacity"]) + " | avaa otteluohjelma"
                ),
                urgency=2,
                expires_at=now + timedelta(hours=12),
                source_url=sport["url"],
                title=sport["name"],
                description=(
                    sport["venue"] + " -- kapasiteetti "
                    + str(sport["capacity"])
                ),
                agent=self.name,
                category="sports",
                extra={
                    "venue": sport["venue"],
                    "capacity": sport["capacity"],
                    "sport": sport["sport"],
                },
            )
            signals.append(sig)
        return signals

    def _build_static_fallback_signals(self) -> list[Signal]:
        """Staattinen tietopankki (Tapahtumat_2026_2.pdf) fallback."""
        signals: list[Signal] = []
        now = datetime.now(timezone.utc)

        try:
            from src.taxiapp.data.static_events import CULTURE_VENUES
            for venue in CULTURE_VENUES[:5]:
                sig = Signal(
                    area=venue.area,
                    score_delta=1.0,
                    reason=f"Tarkista {venue.name}:n ohjelma",
                    urgency=1,
                    expires_at=now + timedelta(hours=12),
                    source_url=venue.url,
                    title=venue.name,
                    description=f"{venue.name} -- katso ohjelma",
                    agent=self.name,
                    category=venue.category,
                    extra={
                        "venue": venue.name,
                        "capacity": venue.capacity,
                        "static": True,
                    },
                )
                signals.append(sig)
        except ImportError:
            pass

        return signals
