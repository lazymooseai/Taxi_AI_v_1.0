"""
base_agent.py - Kaikkien agenttien yhteinen pohja
Helsinki Taxi AI

Jokainen agentti:
  1. Perii BaseAgentin
  2. Toteuttaa async def fetch() -> AgentResult
  3. Palauttaa standardoidun AgentResult-objektin
  4. Toimii taeysin itsenaeisesti

KORJAUKSET (bugfix_8):
  - Lisaetty _now_ms() staattinen metodi BaseAgentiin
    -> TrainAgent ja OCRDispatchAgent kayttavat tata
    -> Aiemmin puuttui -> AttributeError joka syklissa
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ==============================================================
# SIGNAL - Yksittainen paikkasignaali CEO:lle
# ==============================================================

@dataclass
class Signal:
    """
    Yksi pistesignaali jollekin Helsinki-alueelle.
    CEO keraae kaikki signaalit ja laskee alueiden kokonaispisteet.
    """
    area: str               # Vastaa AREAS-sanakirjan avainta (esim. "Rautatieasema")
    score_delta: float      # Lisaettaevae pisteet (positiivinen = enemmaen kyytejae)
    reason: str             # Suomenkielinen selitys kuljettajalle
    urgency: int            # Prioriteetti 1-10 (10 = OVERRIDE, 1 = historiatieto)
    expires_at: datetime    # Milloin signaali vanhenee (UTC)
    source_url: str         # Alkuperainen laehde / URL
    extra: dict[str, Any] = field(default_factory=dict)  # Lisadata

    def is_valid(self) -> bool:
        """Onko signaali vielae voimassa?"""
        return datetime.now(timezone.utc) < self.expires_at

    def __post_init__(self):
        # Validointi
        if not self.area:
            raise ValueError("Signal.area ei voi olla tyhjae")
        if not 1 <= self.urgency <= 10:
            raise ValueError(f"Signal.urgency pitaa olla 1-10, sai: {self.urgency}")
        if not self.reason:
            raise ValueError("Signal.reason ei voi olla tyhjae")


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
    status: str                         # "ok" | "error" | "disabled" | "cached"
    signals: list[Signal] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_msg: Optional[str] = None
    cached: bool = False                # True jos palautettu vaelimistosta
    fetch_duration_ms: Optional[float] = None  # Suoritusaika debug-kayttoon

    @property
    def ok(self) -> bool:
        return self.status == "ok"

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
        """Lyhyt tiivistelma - kaeytetaan dashboardin -ilmoituksissa."""
        if self.status == "disabled":
            return f" {self.agent_name} poistettu kaeytoesta"
        if self.status == "error":
            return f" {self.agent_name} ei saatavilla: {self.error_msg or 'tuntematon virhe'}"
        if self.status == "cached":
            return f" {self.agent_name} vaelimistosta ({len(self.signals)} signaalia)"
        return f" {self.agent_name} ({len(self.signals)} signaalia)"


# ==============================================================
# BASEAGENT - Kaikkien agenttien yliluokka
# ==============================================================

class BaseAgent(ABC):
    """
    Kaikkien data-agenttien yliluokka.

    Periytyessae toteuta:
        async def fetch(self) -> AgentResult

    Kayta apumetodeja:
        self._ok(signals, raw_data)   -> onnistunut AgentResult
        self._error(msg)              -> virheellinen AgentResult
        self._disabled()              -> agentti pois paalta
        self._now_ms()                -> nykyinen aika millisekunteina
    """

    # Aliluokka asettaa namat
    name: str = "BaseAgent"
    ttl: int = 300          # Vaelimiston elinaika sekunteina
    enabled: bool = True    # Voidaan kytkeae pois agent_sources-taulusta

    def __init__(self, name: str | None = None):
        if name is not None:
            self.name = name
        self._cache: Optional[AgentResult] = None
        self._cache_until: float = 0.0
        self._last_request_time: float = 0.0
        self.logger = logging.getLogger(f"taxiapp.{self.name}")

    # == Pakollinen toteutettava metodi ==========================
    @abstractmethod
    async def fetch(self) -> AgentResult:
        """
        Hae data ulkoisesta laehteesta ja palauta AgentResult.
        Aelae kutsu suoraan - kayta fetch_with_cache().
        """
        ...

    # == Ajanmittaus ============================================
    @staticmethod
    def _now_ms() -> int:
        """
        Palauta nykyinen aikaleima millisekunteina (UTC).
        Kaeytetaan suoritusajan mittaamiseen fetch()-metodeissa.

        KORJAUS bugfix_8: siirretty BaseAgentiin jotta TrainAgent
        ja OCRDispatchAgent voivat kutsua self._now_ms() ilman
        AttributeError-virhetta.
        """
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    # == Vaelimisto + rate limiting =============================
    async def fetch_with_cache(self) -> AgentResult:
        """
        Paaasiallinen kutsurajapinta CEOlle.
        Hoitaa: vaelimisto -> rate limiting -> fetch() -> virheenkaesittely.
        """
        if not self.enabled:
            return self._disabled()

        # Vaelimistiosuma
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
            self.logger.debug(f"Vaelimistosta: {self.name}")
            return cached

        # Rate limiting (max 1 pyynto / 5s oletuksena)
        from src.taxiapp.config import config
        min_interval = config.rate_limit_seconds
        elapsed = now - self._last_request_time
        if elapsed < min_interval:
            wait = min_interval - elapsed
            self.logger.debug(f"Rate limit: odotetaan {wait:.1f}s ({self.name})")
            await asyncio.sleep(wait)

        # Oikea haku + ajastus
        t0 = time.monotonic()
        try:
            self._last_request_time = time.monotonic()
            result = await self.fetch()
            result.fetch_duration_ms = (time.monotonic() - t0) * 1000

            # Vaelimistoon vain ok-tulokset
            if result.status == "ok":
                self._cache = result
                self._cache_until = time.monotonic() + self.ttl

            self.logger.info(
                f"{self.name}: {result.status} | "
                f"{len(result.signals)} signaalia | "
                f"{result.fetch_duration_ms:.0f}ms"
            )
            return result

        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            self.logger.error(f"{self.name} kaatui: {exc}", exc_info=True)
            err = self._error(str(exc))
            err.fetch_duration_ms = duration_ms
            return err

    def invalidate_cache(self):
        """Pakota seuraava haku ohittamaan vaelimisto."""
        self._cache = None
        self._cache_until = 0.0
        self.logger.debug(f"Vaelimisto tyhjennetty: {self.name}")

    # == Apumetodit tuloksen rakentamiseen ======================
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
        """Rakenna virheellinen AgentResult - ei kaada muita agentteja."""
        return AgentResult(
            agent_name=self.name,
            status="error",
            signals=[],
            raw_data=raw_data or {},
            fetched_at=datetime.now(timezone.utc),
            error_msg=msg,
        )

    def _disabled(self) -> AgentResult:
        """Agentti on kytketty pois paalta agent_sources-taulusta."""
        return AgentResult(
            agent_name=self.name,
            status="disabled",
            signals=[],
            fetched_at=datetime.now(timezone.utc),
        )

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"name={self.name!r} ttl={self.ttl}s enabled={self.enabled}>"
        )
