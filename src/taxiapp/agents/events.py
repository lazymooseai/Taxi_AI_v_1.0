“””
events.py — EventsAgent
Helsinki Taxi AI

Hakee tapahtumat useista lähteistä:

1. Messukeskus (tapahtumakalenteri)
1. Olympiastadion
1. Hartwall-areena / Nordis
1. Finlandia-talo
1. Helsingin kaupunginteatteri (RSS)
1. Kansallisooppera
1. Stadissa.fi RSS

Kaikki lähteet merkitty täyttöaste-arvioilla kun data on saatavilla.
Jokainen signaali sisältää source_url → suora linkki tapahtuman sivulle.

HUOM: myhelsinki.fi (301/302) ja digitransit.fi (401) poistettu —
käytetään vain toimivia lähteitä.
“””

from **future** import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from xml.etree import ElementTree as ET

import httpx
import feedparser  # type: ignore

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger(“taxiapp.EventsAgent”)

# ── RSS-lähteet ja niiden asetukset ───────────────────────────────────────

RSS_SOURCES: list[dict] = [
{
“name”: “Messukeskus”,
“url”: “https://www.messukeskus.com/kavijalle/tapahtumat/tapahtumakalenteri/”,
“type”: “scrape”,
“area”: “pasila”,
“base_url”: “https://www.messukeskus.com”,
“capacity”: 15000,
},
{
“name”: “Stadissa.fi”,
“url”: “https://stadissa.fi/tapahtumat”,
“type”: “scrape_fallback”,
“area”: “helsinki_central”,
“base_url”: “https://stadissa.fi”,
“capacity”: None,
},
{
“name”: “Olympiastadion”,
“url”: “https://www.olympiastadion.fi/tapahtumat/”,
“type”: “scrape_fallback”,
“area”: “helsinki_central”,
“base_url”: “https://olympiastadion.fi”,
“capacity”: 36000,
“calendar_url”: “https://www.olympiastadion.fi/tapahtumat/”,
},
{
“name”: “Finlandia-talo”,
“url”: “https://www.finlandiatalo.fi/tapahtumakalenteri/”,
“type”: “scrape_fallback”,
“area”: “helsinki_central”,
“base_url”: “https://finlandiatalo.fi”,
“capacity”: 1700,
“calendar_url”: “https://www.finlandiatalo.fi/tapahtumakalenteri/”,
},
{
“name”: “Kansallisooppera”,
“url”: “https://oopperabaletti.fi/ohjelmisto-ja-liput/”,
“type”: “scrape_fallback”,
“area”: “helsinki_central”,
“base_url”: “https://oopperabaletti.fi”,
“capacity”: 1340,
“calendar_url”: “https://oopperabaletti.fi/ohjelmisto-ja-liput/”,
},
{
“name”: “Kaupunginteatteri”,
“url”: “https://hkt.fi/kalenteri/”,
“type”: “scrape_fallback”,
“area”: “helsinki_central”,
“base_url”: “https://hkt.fi”,
“capacity”: 900,
“calendar_url”: “https://hkt.fi/kalenteri/”,
},
{
“name”: “Kansallisteatteri”,
“url”: “https://kansallisteatteri.fi/esityskalenteri/”,
“type”: “scrape_fallback”,
“area”: “helsinki_central”,
“base_url”: “https://kansallisteatteri.fi”,
“capacity”: 700,
“calendar_url”: “https://kansallisteatteri.fi/esityskalenteri/”,
},
{
“name”: “Musiikkitalo”,
“url”: “https://www.musiikkitalo.fi/tapahtumat/”,
“type”: “scrape_fallback”,
“area”: “helsinki_central”,
“base_url”: “https://musiikkitalo.fi”,
“capacity”: 1700,
“calendar_url”: “https://www.musiikkitalo.fi/tapahtumat/”,
},
{
“name”: “Tavastia”,
“url”: “https://tavastiaklubi.fi/fi_FI/ohjelma”,
“type”: “scrape_fallback”,
“area”: “helsinki_central”,
“base_url”: “https://tavastiaklubi.fi”,
“capacity”: 900,
“calendar_url”: “https://tavastiaklubi.fi/fi_FI/ohjelma”,
},
]

# Urheilutapahtumat — staattiset linkit kalentereihin

SPORTS_CALENDARS: list[dict] = [
{
“name”: “HIFK kotiottelut (Liiga/Nordis)”,
“url”: (
“https://liiga.fi/fi/ohjelma”
“?kausi=2025-2026&sarja=runkosarja”
“&joukkue=hifk&kotiVieras=koti”
),
“area”: “helsinki_central”,
“venue”: “Nordis (Nokia Arena)”,
“capacity”: 13500,
“sport”: “jääkiekko”,
},
{
“name”: “Jokerit (Mestis)”,
“url”: “https://jokerit.fi/ottelut”,
“area”: “helsinki_central”,
“venue”: “Nordis”,
“capacity”: 13500,
“sport”: “jääkiekko”,
},
{
“name”: “Kiekko-Espoo (Metro Areena)”,
“url”: (
“https://liiga.fi/fi/ohjelma”
“?kausi=2025-2026&sarja=runkosarja”
“&joukkue=k-espoo&kotiVieras=koti”
),
“area”: “espoo_center”,
“venue”: “Metro Areena”,
“capacity”: 8000,
“sport”: “jääkiekko”,
},
{
“name”: “Veikkausliiga”,
“url”: “https://veikkausliiga.com/tilastot/2025/veikkausliiga/ottelut/”,
“area”: “helsinki_central”,
“venue”: “Bolt Arena”,
“capacity”: 10770,
“sport”: “jalkapallo”,
},
]

# Aikaikkuna: tapahtumat 0-6h sisällä erityistarkkailussa

LOOKAHEAD_HOURS: int = 6

# Tapahtumat 6-24h: perustasoinen signaali

LOOKAHEAD_DAILY_HOURS: int = 24

class EventsAgent(BaseAgent):
“””
Hakee tapahtumat useista helsinkiläislähteistä.

```
Strategia:
  1. Yritetään hakea live-data httpx:llä
  2. Jos sivusto ei vastaa (301/403/timeout), käytetään staattisia
     kalenterilinkkejä joilla kuljettaja pääsee itse tarkistamaan
  3. Urheilutapahtumat lisätään aina staattisina signaaleina
     (kalenterilinkit ovat aina toimivia)

Jokainen signaali sisältää:
  - source_url: suora linkki tapahtuman sivulle tai kalenteriin
  - extra.capacity: kapasiteetti jos tunnettu
  - extra.fill_rate: arvioitu täyttöaste (0.0-1.0) jos saatavilla
"""

def __init__(self) -> None:
    super().__init__(name="EventsAgent")

async def fetch(self) -> AgentResult:
    """Hae tapahtumat kaikista lähteistä rinnakkain."""
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
            logger.debug("EventsAgent: %s virhe: %s", source["name"], result)
            # Lisää staattinen signaali kalenterilinkkiin
            fallback_sig = self._make_static_calendar_signal(source)
            if fallback_sig:
                signals.append(fallback_sig)
            continue
        if result:
            signals.extend(result)

    # Lisää urheilutapahtumalinkit aina
    sports_signals = self._build_sports_signals()
    signals.extend(sports_signals)

    elapsed = self._now_ms() - start_ms
    logger.info(
        "EventsAgent: %d tapahtumaa -> %d signaalia",
        len(signals),
        len(signals),
    )
    logger.info("EventsAgent: ok | %d signaalia | %dms", len(signals), elapsed)

    return AgentResult(
        agent_name=self.name,
        signals=signals,
        ok=True,
        elapsed_ms=elapsed,
    )

async def _fetch_source(
    self, client: httpx.AsyncClient, source: dict
) -> list[Signal]:
    """Hae yksi lähde. Palauttaa signaalilistan (voi olla tyhjä)."""
    try:
        resp = await client.get(source["url"])
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (301, 302, 403, 404):
            return []
        raise
    except (httpx.ConnectError, httpx.TimeoutException):
        return []

    # Parsitaan HTML yksinkertaisesti (ei BS4-riippuvuutta)
    return self._parse_html_events(resp.text, source)

def _parse_html_events(self, html: str, source: dict) -> list[Signal]:
    """
    Parsii tapahtumat HTML:stä kevyesti.

    Etsii title-tagit, og:title, JSON-LD schema.org Event -merkinnät.
    Palauttaa enintään 5 signaalia per lähde.
    """
    signals: list[Signal] = []
    base_url = source.get("base_url", "")
    calendar_url = source.get("calendar_url", source["url"])

    # Etsitään JSON-LD Event-merkinnät
    json_ld_pattern = re.compile(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in json_ld_pattern.finditer(html):
        try:
            import json
            data = json.loads(match.group(1))
            events = []
            if isinstance(data, dict):
                if data.get("@type") == "Event":
                    events = [data]
                elif data.get("@type") == "ItemList":
                    events = [
                        item.get("item", item)
                        for item in data.get("itemListElement", [])
                    ]
            elif isinstance(data, list):
                events = [d for d in data if isinstance(d, dict) and d.get("@type") == "Event"]

            for event_data in events[:5]:
                sig = self._event_to_signal(event_data, source, base_url)
                if sig:
                    signals.append(sig)
        except Exception:
            pass

    if signals:
        return signals[:5]

    # Fallback: hae og:title + og:url
    og_title = re.search(
        r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
        html, re.IGNORECASE
    )
    og_url = re.search(
        r'<meta[^>]*property="og:url"[^>]*content="([^"]+)"',
        html, re.IGNORECASE
    )

    if og_title:
        title = og_title.group(1).strip()
        event_url = og_url.group(1) if og_url else calendar_url

        # Puhdista osoite
        if event_url and not event_url.startswith("http"):
            event_url = base_url + event_url

        sig = Signal(
            agent=self.name,
            area=source.get("area", "helsinki_central"),
            score=2.0,
            urgency=2,
            title=f"📅 {source['name']}: {title[:50]}",
            description=f"{source['name']} — katso aikataulu ja liput",
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

    # Päivämäärä
    start_date_str = event_data.get("startDate", "")
    end_date_str = event_data.get("endDate", "")

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

    # Täyttöaste
    offers = event_data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    availability = offers.get("availability", "")
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

    capacity = source.get("capacity")
    fill_text = ""
    if fill_rate == 1.0:
        fill_text = " 🔴 LOPPUUNMYYTY"
    elif fill_rate and fill_rate >= 0.85:
        fill_text = " 🟠 Viim. liput"
    elif capacity:
        fill_text = f" ({capacity:,} katsojaa)"

    description = f"{source['name']}"
    if date_display:
        description += f" — {date_display}"
    description += fill_text

    return Signal(
        agent=self.name,
        area=source.get("area", "helsinki_central"),
        score=score,
        urgency=urgency,
        title=f"📅 {name[:60]}",
        description=description,
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

def _make_static_calendar_signal(self, source: dict) -> Optional[Signal]:
    """
    Luo staattinen signaali kalenterilinkillä kun live-haku epäonnistuu.
    Kuljettaja voi painaa → avautuu tapahtumapaikkan kalenteri.
    """
    calendar_url = source.get("calendar_url", source["url"])
    if not calendar_url:
        return None

    return Signal(
        agent=self.name,
        area=source.get("area", "helsinki_central"),
        score=1.5,
        urgency=1,
        title=f"📅 {source['name']} — kalenteri",
        description=f"Tarkista {source['name']}n tapahtumat ja aikataulut",
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

    Nämä ovat aina mukana — linkit urheilu-kalentereihin jotka
    kuljettaja voi itse tarkistaa. Otteluaikataulut eivät ole
    API:ssa saatavilla ilman lisenssiä, mutta linkki menee suoraan
    kalenteriin.
    """
    signals: list[Signal] = []
    for sport in SPORTS_CALENDARS:
        sig = Signal(
            agent=self.name,
            area=sport["area"],
            score=3.0,
            urgency=2,
            title=f"🏒 {sport['name']}",
            description=(
                f"{sport['venue']} — "
                f"kapasiteetti {sport['capacity']:,} | "
                f"avaa otteluohjelma"
            ),
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
```
