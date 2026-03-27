"""
base_agent.py - Kaikkien agenttien yhteinen pohja
Helsinki Taxi AI v2.0

Jokainen agentti:
  1. Perii BaseAgentin
  2. Toteuttaa async def fetch() -> AgentResult
  3. Palauttaa standardoidun AgentResult-objektin
  4. Toimii taysin itsenaisesti

Signal-kentat:
  Pakolliset (CEO-pisteytys):
    area, score_delta, reason, urgency, expires_at, source_url
  Valinnaiset (naytto / meta):
    title, description, agent, extra, category
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TTL_MIN: int = 30


def _default_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=_DEFAULT_TTL_MIN)


# ==============================================================
# SIGNAL - Yksittainen paikkasignaali CEO:lle
# ==============================================================

@dataclass
class Signal:
    """
    Yksi pistesignaali jollekin Helsinki-alueelle.
    CEO keraa kaikki signaalit ja laskee alueiden kokonaispisteet.

    Pakolliset kentat:
      area         - AREAS-sanakirjan avain (esim. "Rautatieasema")
      score_delta  - Lisattavat pisteet (positiivinen = enemman kyyteja)
      reason       - Suomenkielinen selitys kuljettajalle
      urgency      - Prioriteetti 1-10 (10 = OVERRIDE)
      expires_at   - Milloin signaali vanhenee (UTC)

    Valinnaiset:
      source_url   - Alkuperainen lahde / URL
      title        - Lyhyt otsikko (korttinaytta)
      description  - Pidempi kuvaus (korttinaytta)
      agent        - Luonut agentti
      extra        - Vapaamuotoinen lisadata (dict)
      category     - Kategoria (trains/ferries/culture/airport/sports/...)
    """
    area: str
    score_delta: float = 0.0
    reason: str = ""
    urgency: int = 2
    expires_at: datetime = field(default_factory=_default_expiry)
    source_url: str = ""
    # Laajennetut kentat
    title: str = ""
    description: str = ""
    agent: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    category: str = ""

    def is_valid(self) -> bool:
        """Onko signaali viela voimassa?"""
        return datetime.now(timezone.utc) < self.expires_at

    def __post_init__(self) -> None:
        # Tayta reason automaattisesti jos tyhja
        if not self.reason:
            self.reason = self.description or self.title or f"Signaali: {self.area}"
        # Validointi
        if not self.area:
            raise ValueError("Signal.area ei voi olla tyhja")
        self.urgency = max(1, min(10, self.urgency))
        if not self.reason:
            self.reason = f"Signaali: {self.area}"


# ==============================================================
# AGENTRESULT - Agentin palautusarvo
# ==============================================================

@dataclass
class AgentResult:
    """
    Standardoitu palautusarvo jokaiselta agentilta.
    CEO kayttaa tata - ei suoria agenttikutsuja.
    """
    agent_name: str
    status: str = "ok"
    signals: list[Signal] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_msg: Optional[str] = None
    cached: bool = False
    fetch_duration_ms: Optional[float] = None
    elapsed_ms: Optional[float] = None

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "cached")

    @property
    def has_signals(self) -> bool:
        return bool(self.signals)

    @property
    def valid_signals(self) -> list[Signal]:
        """Palauttaa vain voimassaolevat signaalit."""
        return [s for s in self.signals if s.is_valid()]

    @property
    def top_urgency(self) -> int:
        """Korkein urgency-arvo taman agentin signaaleista."""
        if not self.signals:
            return 0
        return max(s.urgency for s in self.signals)

    def summary(self) -> str:
        """Lyhyt tiivistelma dashboardin ilmoituksissa."""
        if self.status == "disabled":
            return f"{self.agent_name} poistettu kaytosta"
        if self.status == "error":
            return f"{self.agent_name} ei saatavilla: {self.error_msg or 'tuntematon virhe'}"
        if self.status == "cached":
            return f"{self.agent_name} valimuistista ({len(self.signals)} signaalia)"
        return f"{self.agent_name} ({len(self.signals)} signaalia)"


# ==============================================================
# BASEAGENT - Kaikkien agenttien yliluokka
# ==============================================================

class BaseAgent(ABC):
    """
    Kaikkien data-agenttien yliluokka.

    Periytyessa toteuta:
        async def fetch(self) -> AgentResult

    Kayta apumetodeja:
        self._ok(signals, raw_data)   -> onnistunut AgentResult
        self._error(msg)              -> virheellinen AgentResult
        self._disabled()              -> agentti pois paalta
    """

    name: str = "BaseAgent"
    ttl: int = 300
    enabled: bool = True

    def __init__(self, name: str = "") -> None:
        if name:
            self.name = name
        self._cache: Optional[AgentResult] = None
        self._cache_until: float = 0.0
        self._last_request_time: float = 0.0
        self.logger = logging.getLogger(f"taxiapp.{self.name}")

    @abstractmethod
    async def fetch(self) -> AgentResult:
        """Hae data ulkoisesta lahteesta ja palauta AgentResult."""
        ...

    async def fetch_with_cache(self) -> AgentResult:
        """
        Paaasiallinen kutsurajapinta CEOlle.
        Hoitaa: valimuisti -> rate limiting -> fetch() -> virheenkasittely.
        """
        if not self.enabled:
            return self._disabled()

        now = time.monotonic()
        if self._cache and now < self._cache_until:
            cached = AgentResult(
                agent_name=self._cache.agent_name,
                status="cached",
                signals=self._cache.signals,
                raw_data=self._cache.raw_data,
                fetched_at=self._cache.fetched_at,
                cached=True,
            )
            return cached

        from src.taxiapp.config import config
        min_interval = config.rate_limit_seconds
        elapsed = now - self._last_request_time
        if elapsed < min_interval:
            wait = min_interval - elapsed
            await asyncio.sleep(wait)

        t0 = time.monotonic()
        try:
            self._last_request_time = time.monotonic()
            result = await self.fetch()
            result.fetch_duration_ms = (time.monotonic() - t0) * 1000

            if result.status == "ok":
                self._cache = result
                self._cache_until = time.monotonic() + self.ttl

            self.logger.info(
                "%s: %s | %d signaalia | %.0fms",
                self.name, result.status,
                len(result.signals),
                result.fetch_duration_ms or 0,
            )
            return result

        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            self.logger.error("%s kaatui: %s", self.name, exc, exc_info=True)
            err = self._error(str(exc))
            err.fetch_duration_ms = duration_ms
            return err

    def invalidate_cache(self) -> None:
        """Pakota seuraava haku ohittamaan valimuisti."""
        self._cache = None
        self._cache_until = 0.0

    def _ok(
        self,
        signals: list[Signal],
        raw_data: Optional[dict] = None,
    ) -> AgentResult:
        """Rakenna onnistunut AgentResult."""
        return AgentResult(
            agent_name=self.name,
            status="ok",
            signals=signals,
            raw_data=raw_data or {},
            fetched_at=datetime.now(timezone.utc),
        )

    def _error(self, msg: str, raw_data: Optional[dict] = None) -> AgentResult:
        """Rakenna virheellinen AgentResult."""
        return AgentResult(
            agent_name=self.name,
            status="error",
            signals=[],
            raw_data=raw_data or {},
            fetched_at=datetime.now(timezone.utc),
            error_msg=msg,
        )

    def _disabled(self) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            status="disabled",
            signals=[],
            fetched_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _now_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} name={self.name!r}"
            f" ttl={self.ttl}s enabled={self.enabled}>"
        )
