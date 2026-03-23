"""
events.py — EventsAgent
Helsinki Taxi AI

Hakee tapahtumat useista lähteistä ja muuntaa ne signaaleiksi CEO:lle.
Kaikki Signal-kentät vastaavat base_agent.py:n määritelmää:
  Signal(area, score_delta, reason, urgency, expires_at, source_url)

Area-arvot vastaavat AREAS-sanakirjan avaimia (areas.py).
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


# ── Area-mapping: lähteen nimi → AREAS-avain ──────────────────────────────

SOURCE_AREA_MAP: dict[str, str] = {
    "Messukeskus":        "Messukeskus",
    "Olympiastadion":     "Olympiastadion",
    "Finlandia-talo":     "Rautatieasema",   # Töölö ~ Rautatieasema-alue
    "Kansallisooppera":   "Rautatieasema",   # Töölö
    "Kaupunginteatteri":  "Kamppi",
    "Kansallisteatteri":  "Rautatieasema",
    "Musiikkitalo":       "Rautatieasema",
    "Tavastia":           "Kamppi",
    "Stadissa.fi":        "Kamppi",
    # Urheilu
    "HIFK kotiottelut (Liiga/Nordis)": "Pasila",
    "Jokerit (Mestis)":                "Pasila",
    "Kiekko-Espoo (Metro Areena)":     "Messukeskus",
    "Veikkausliiga":                   "Olympiastadion",
}

DEFAULT_AREA = "Kamppi"

# ── RSS- ja tapahtumapaikkalähteet ────────────────────────────────────────

RSS_SOURCES: list[dict] = [
    {
        "name": "Messukeskus",
        "url": "https://www.messukeskus.com/kavijalle/tapahtumat/tapahtumakalenteri/",
        "base_url": "https://www.messukeskus.com",
        "capacity": 15000,
        "calendar_url": "https://www.messukeskus.com/kavijalle/tapahtumat/tapahtumakalenteri/",
    },
    {
        "name": "Olympiastadion",
        "url": "https://www.olympiastadion.fi/tapahtumat/",
        "base_url": "https://www.olympiastadion.fi",
        "capacity": 36000,
        "calendar_url": "https://www.olympiastadion.fi/tapahtumat/",
    },
    {
        "name": "Finlandia-talo",
        "url": "https://www.finlandiatalo.fi/tapahtumakalenteri/",
        "base_url": "https://www.finlandiatalo.fi",
        "capacity": 1700,
        "calendar_url": "https://www.finlandiatalo.fi/tapahtumakalenteri/",
    },
    {
        "name": "Kansallisooppera",
        "url": "https://oopperabaletti.fi/ohjelmisto-ja-liput/",
        "base_url": "https://oopperabaletti.fi",
        "capacity": 1340,
        "calendar_url": "https://oopperabaletti.fi/ohjelmisto-ja-liput/",
    },
    {
        "name": "Kaupunginteatteri",
        "url": "https://hkt.fi/kalenteri/",
        "base_url": "https://hkt.fi",
        "capacity": 900,
        "calendar_url": "https://hkt.fi/kalenteri/",
    },
    {
        "name": "Kansallisteatteri",
        "url": "https://kansallisteatteri.fi/esityskalenteri/",
        "base_url": "https://kansallisteatteri.fi",
        "capacity": 700,
        "calendar_url": "https://kansallisteatteri.fi/esityskalenteri/",
    },
    {
        "name": "Musiikkitalo",
        "url": "https://www.musiikkitalo.fi/tapahtumat/",
        "base_url": "https://www.musiikkitalo.fi",
        "capacity": 1700,
        "calendar_url": "https://www.musiikkitalo.fi/tapahtumat/",
    },
    {
        "name": "Tavastia",
        "url": "https://tavastiaklubi.fi/fi_FI/ohjelma",
        "base_url": "https://tavastiaklubi.fi",
        "capacity": 900,
        "calendar_url": "https://tavastiaklubi.fi/fi_FI/ohjelma",
    },
    {
        "name": "Stadissa.fi",
        "url": "https://stadissa.fi/tapahtumat",
        "base_url": "https://stadissa.fi",
        "capacity": None,
        "calendar_url": "https://stadissa.fi/tapahtumat",
    },
]

SPORTS_CALENDARS: list[dict] = [
    {
        "name":     "HIFK kotiottelut (Liiga/Nordis)",
        "url":      "https://liiga.fi/fi/ohjelma?kausi=2025-2026&sarja=runkosarja&joukkue=hifk&kotiVieras=koti",
        "venue":    "Nordis (Nokia Arena)",
        "capacity": 13500,
    },
    {
        "name":     "Jokerit (Mestis)",
        "url":      "https://jokerit.fi/ottelut",
        "venue":    "Nordis",
        "capacity": 13500,
    },
    {
        "name":     "Kiekko-Espoo (Metro Areena)",
        "url":      "https://liiga.fi/fi/ohjelma?kausi=2025-2026&sarja=runkosarja&joukkue=k-espoo&kotiVieras=koti",
        "venue":    "Metro Areena",
        "capacity": 8000,
    },
    {
        "name":     "Veikkausliiga",
        "url":      "https://veikkausliiga.com/tilastot/2025/veikkausliiga/ottelut/",
        "venue":    "Bolt Arena",
        "capacity": 10770,
    },
]

LOOKAHEAD_HOURS      = 6
LOOKAHEAD_DAILY_HOURS = 24


# ── Apufunktio: area-nimi lähteen nimestä ─────────────────────────────────

def _source_area(source_name: str) -> str:
    """Palauta oikea AREAS-avain lähteen nimestä."""
    return SOURCE_AREA_MAP.get(source_name, DEFAULT_AREA)


# ══════════════════════════════════════════════════════════════════════════════

class EventsAgent(BaseAgent):
    """
    Hakee tapahtumat useista helsinkiläislähteistä.

    Strategia:
      1. Yritetään hakea live-data httpx:lla (JSON-LD schema.org Event)
      2. Jos sivu ei vastaa, käytetään staattista kalenterilinkkiä
      3. Urheilutapahtumat lisätään aina staattisina signaaleina
    """

    name    = "EventsAgent"
    ttl     = 1800
    enabled = True

    async def fetch(self) -> AgentResult:
        """Hae tapahtumat kaikista lähteistä rinnakkain."""
        async with httpx.AsyncClient(
            timeout=8.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; HelsinkiTaxiAI/1.0)"
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
                fb = self._make_static_signal(source)
                if fb:
                    signals.append(fb)
                continue
            if result:
                signals.extend(result)

        # Urheilutapahtumat aina mukaan
        signals.extend(self._build_sports_signals())

        raw = {
            "total_signals": len(signals),
            "sources":       len(RSS_SOURCES),
        }
        logger.info("EventsAgent: %d signaalia", len(signals))
        return self._ok(signals, raw_data=raw)

    # ── HTTP-haku ──────────────────────────────────────────────────────────

    async def _fetch_source(
        self, client: httpx.AsyncClient, source: dict
    ) -> list[Signal]:
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

    # ── HTML-jäsennin ─────────────────────────────────────────────────────

    def _parse_html(self, html: str, source: dict) -> list[Signal]:
        """Jäsennä tapahtumat HTML:sta (JSON-LD → og:title fallback)."""
        signals: list[Signal] = []
        base_url     = source.get("base_url", "")
        calendar_url = source.get("calendar_url", source["url"])

        json_ld_re = re.compile(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            re.DOTALL | re.IGNORECASE,
        )

        for match in json_ld_re.finditer(html):
            try:
                data   = json.loads(match.group(1))
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
                    events = [d for d in data if isinstance(d, dict) and d.get("@type") == "Event"]

                for event_data in events[:5]:
                    sig = self._event_to_signal(event_data, source, base_url)
                    if sig:
                        signals.append(sig)
            except Exception:
                pass

        if signals:
            return signals[:5]

        # Fallback: og:title
        og_m = re.search(
            r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
            html, re.IGNORECASE,
        )
        if og_m:
            title   = og_m.group(1).strip()
            og_url  = re.search(r'<meta[^>]*property="og:url"[^>]*content="([^"]+)"', html, re.IGNORECASE)
            evt_url = og_url.group(1) if og_url else calendar_url
            if evt_url and not evt_url.startswith("http"):
                evt_url = base_url + evt_url

            signals.append(Signal(
                area        = _source_area(source["name"]),
                score_delta = 2.0,
                reason      = f"🎭 {source['name']}: {title[:60]}",
                urgency     = 2,
                expires_at  = datetime.now(timezone.utc) + timedelta(hours=6),
                source_url  = evt_url or calendar_url,
            ))

        return signals[:5]

    # ── JSON-LD Event → Signal ────────────────────────────────────────────

    def _event_to_signal(
        self, event_data: dict, source: dict, base_url: str
    ) -> Optional[Signal]:
        name = event_data.get("name", "").strip()
        if not name:
            return None

        # URL
        event_url = event_data.get("url", "")
        if event_url and not event_url.startswith("http"):
            event_url = base_url + event_url
        if not event_url:
            event_url = source.get("calendar_url", source["url"])

        # Päivämäärä
        start_str      = event_data.get("startDate", "")
        now_utc        = datetime.now(timezone.utc)
        hours_until:   Optional[float] = None
        date_display   = ""
        start_dt:      Optional[datetime] = None

        if start_str:
            try:
                start_dt     = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                hours_until  = (start_dt - now_utc).total_seconds() / 3600
                date_display = start_dt.strftime("%d.%m %H:%M")
            except ValueError:
                date_display = start_str[:16]

        # Täyttöaste JSON-LD:stä
        offers       = event_data.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        availability = offers.get("availability", "") if isinstance(offers, dict) else ""
        fill_rate:   Optional[float] = None
        if "SoldOut"           in availability:
            fill_rate = 1.0
        elif "LimitedAvailability" in availability:
            fill_rate = 0.85
        elif "InStock"         in availability:
            fill_rate = 0.5

        # Pisteet
        score, urgency = 2.5, 2
        if hours_until is not None:
            if 0 <= hours_until <= 2:
                score, urgency = 6.0, 6
            elif 2 < hours_until <= LOOKAHEAD_HOURS:
                score, urgency = 4.5, 4
            elif hours_until <= LOOKAHEAD_DAILY_HOURS:
                score, urgency = 3.0, 3

        if fill_rate and fill_rate >= 0.85:
            score  += 1.0
            urgency = min(urgency + 1, 9)

        # Reason-teksti
        fill_label = ""
        if fill_rate == 1.0:
            fill_label = " [LOPPUUNMYYTY]"
        elif fill_rate and fill_rate >= 0.85:
            fill_label = " [Viimeiset liput]"
        capacity = source.get("capacity")
        cap_str  = f" ({capacity:,} katsojaa)" if capacity else ""

        reason = f"🎭 {source['name']}"
        if date_display:
            reason += f" — {date_display}"
        reason += fill_label or cap_str
        reason += f": {name[:50]}"

        # Vanhentuminen: 30min tapahtuman alkamisen jälkeen
        if start_dt:
            expires = start_dt + timedelta(minutes=30)
        else:
            expires = now_utc + timedelta(hours=LOOKAHEAD_DAILY_HOURS)

        return Signal(
            area        = _source_area(source["name"]),
            score_delta = score,
            reason      = reason[:110],
            urgency     = urgency,
            expires_at  = expires,
            source_url  = event_url,
        )

    # ── Staattiset signaalit ──────────────────────────────────────────────

    def _make_static_signal(self, source: dict) -> Optional[Signal]:
        """Luo staattinen kalenteri-signaali kun live-haku epäonnistuu."""
        calendar_url = source.get("calendar_url", source["url"])
        if not calendar_url:
            return None
        return Signal(
            area        = _source_area(source["name"]),
            score_delta = 1.5,
            reason      = f"📅 {source['name']} — tarkista tapahtumakalenteri",
            urgency     = 1,
            expires_at  = datetime.now(timezone.utc) + timedelta(hours=12),
            source_url  = calendar_url,
        )

    def _build_sports_signals(self) -> list[Signal]:
        """Staattiset urheilutapahtumisignaalit kalenterilinkeillä."""
        signals: list[Signal] = []
        now = datetime.now(timezone.utc)
        for sport in SPORTS_CALENDARS:
            signals.append(Signal(
                area        = _source_area(sport["name"]),
                score_delta = 3.0,
                reason      = (
                    f"⚽ {sport['name']} — {sport['venue']} "
                    f"({sport['capacity']:,} paikkaa)"
                ),
                urgency     = 2,
                expires_at  = now + timedelta(hours=24),
                source_url  = sport["url"],
            ))
        return signals
