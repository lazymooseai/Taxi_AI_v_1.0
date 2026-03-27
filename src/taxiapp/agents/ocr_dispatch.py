"""
ocr_dispatch.py - Valitysaseman OCR-agentti
Helsinki Taxi AI v2.0

TAKTINEN KRUUNUNJALOKIVI.

Kuljettaja ottaa kuvan valitysnaytosta ->
OCR lukee K+/T+/K-30/T-30/Autoja -sarakkeet ->
Jarjestelma ymmartaa missa on eniten kysyntaa vs. tarjontaa.

Tama on dataa mita kukaan muu ei keraa.

Sarakkeet:
  K+   = Historiadata: Kavelykyydit viikko sitten (30min ennuste)
         urgency = 4 (EI 6 - historiallinen vertailudata)
  T+   = Historiadata: Tilaukset viikko sitten (30min ennuste)
         urgency = 4
  K-30 = Reaalidata: Toteutuneet kavelykyydit nyt (alle 30min)
         urgency = 6
  T-30 = Reaalidata: Toteutuneet tilaukset nyt (alle 30min)
         urgency = 6
  Autoja = Reaaliaikainen kalustovahvuus

Pisteytys:
  demand_ratio = (K_30 + T_30) / max(autoja, 1)
  Korkea ratio (>2.0) = paljon kyyteja, vahan autoja -> KORKEA urgency
  Matala ratio (<0.5) = vahan kyyteja, paljon autoja -> ei signaalia

Graceful degradation:
  EasyOCR puuttuu -> manuaalinen syotto toimii
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal
from src.taxiapp.areas import AREAS, station_to_area

logger = logging.getLogger("taxiapp.OCRDispatchAgent")

# Valinnainen OCR-riippuvuus
try:
    import easyocr as _easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False
    logger.info("EasyOCR ei asennettu - OCR ei kaytettavissa")

try:
    import numpy as _np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ==============================================================
# DISPATCH DATA
# ==============================================================

@dataclass
class DispatchRow:
    """Yksi rivi valitysnayton datasta."""
    station_id: int = 0
    station_name: str = ""
    k_plus: int = 0      # K+ historiallinen vertailu
    t_plus: int = 0      # T+ historiallinen vertailu
    k_30: int = 0        # K-30 reaaliaikaiset kavelykyydit
    t_30: int = 0        # T-30 reaaliaikaiset tilaukset
    autoja: int = 0      # Vapaat autot
    area_name: str = ""  # Kartoitettu AREAS-alueeseen

    @property
    def real_demand(self) -> int:
        """Reaaliaikainen kokonaiskysynta (K-30 + T-30)."""
        return self.k_30 + self.t_30

    @property
    def historical_demand(self) -> int:
        """Historiallinen vertailukysynta (K+ + T+)."""
        return self.k_plus + self.t_plus

    @property
    def total_demand(self) -> int:
        """Kokonaiskysynta (reaali + historiallinen)."""
        return self.real_demand + self.historical_demand

    @property
    def demand_ratio(self) -> float:
        """Kysynta/tarjonta -suhde."""
        return self.real_demand / max(self.autoja, 1)

    @property
    def supply_gap(self) -> int:
        """Kuinka monta autoa puuttuu kysynnan tyydyttamiseen."""
        return max(0, self.real_demand - self.autoja)


@dataclass
class DispatchSnapshot:
    """Koko valitysnayton tilannekuva."""
    rows: list[DispatchRow] = field(default_factory=list)
    captured_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source: str = "ocr"  # "ocr" tai "manual"
    raw_text: str = ""

    @property
    def total_demand(self) -> int:
        return sum(r.real_demand for r in self.rows)

    @property
    def total_supply(self) -> int:
        return sum(r.autoja for r in self.rows)

    @property
    def hottest_rows(self) -> list[DispatchRow]:
        """Riveilla eniten kysyntaa vs. tarjontaa, jarjestetty."""
        return sorted(
            [r for r in self.rows if r.real_demand > 0],
            key=lambda r: r.demand_ratio,
            reverse=True,
        )


# ==============================================================
# OCR-PARSERI
# ==============================================================

# Regex: rivinumero + asemanimi + numerosarakkeet
_ROW_PATTERN = re.compile(
    r"(\d{1,3})\s+"           # aseman numero
    r"([A-Z][A-Za-z\s.-]+?)"  # aseman nimi
    r"\s+(\d+)"               # K+
    r"\s+(\d+)"               # T+
    r"\s+(\d+)"               # K-30
    r"\s+(\d+)"               # T-30
    r"\s+(\d+)",              # Autoja
)

# Vaihtoehtoinen parseri: puolipisteeroteltu
_CSV_PATTERN = re.compile(
    r"(\d{1,3})\s*;"          # aseman numero
    r"\s*([^;]+?)\s*;"        # aseman nimi
    r"\s*(\d+)\s*;"           # K+
    r"\s*(\d+)\s*;"           # T+
    r"\s*(\d+)\s*;"           # K-30
    r"\s*(\d+)\s*;"           # T-30
    r"\s*(\d+)",              # Autoja
)


def parse_dispatch_text(text: str) -> list[DispatchRow]:
    """
    Parsii valitysnayton teksti DispatchRow-listaksi.

    Tukee kahta formaattia:
      1. Valilyonteroteltu (OCR-tulos)
      2. Puolipisteeroteltu (CSV/manuaalinen)

    Kartoittaa aseman numeron AREAS-alueeseen.
    """
    rows: list[DispatchRow] = []

    for pattern in (_CSV_PATTERN, _ROW_PATTERN):
        matches = pattern.findall(text)
        if matches:
            for m in matches:
                station_id = int(m[0])
                station_name = m[1].strip()
                k_plus = int(m[2])
                t_plus = int(m[3])
                k_30 = int(m[4])
                t_30 = int(m[5])
                autoja = int(m[6])

                area_name = station_to_area(station_id) or ""

                rows.append(DispatchRow(
                    station_id=station_id,
                    station_name=station_name,
                    k_plus=k_plus,
                    t_plus=t_plus,
                    k_30=k_30,
                    t_30=t_30,
                    autoja=autoja,
                    area_name=area_name,
                ))
            break  # Kayta ensimmainen toimiva formaatti

    return rows


def ocr_image_to_text(image_bytes: bytes) -> str:
    """
    Suorita OCR kuvadatalle.
    Kayttaa EasyOCR-kirjastoa.
    Palauttaa tunnistetun tekstin.
    """
    if not HAS_EASYOCR:
        raise RuntimeError(
            "EasyOCR ei asennettu. Asenna: pip install easyocr"
        )
    if not HAS_NUMPY:
        raise RuntimeError(
            "NumPy ei asennettu. Asenna: pip install numpy"
        )

    reader = _easyocr.Reader(["fi", "en"], gpu=False, verbose=False)
    import io
    results = reader.readtext(image_bytes, detail=0, paragraph=True)
    return "\n".join(results)


# ==============================================================
# OCR DISPATCH AGENT
# ==============================================================

class OCRDispatchAgent(BaseAgent):
    """
    Valitysaseman OCR-agentti.

    Lukee kuljettajan ottaman kuvan valitysnaytosta,
    parsii K+/T+/K-30/T-30/Autoja -sarakkeet ja
    tuottaa signaalit korkean kysynnan alueille.

    Tama agentti ei hae dataa automaattisesti - se aktivoituu
    kun kuljettaja lataa kuvan tai syottaa datan manuaalisesti.

    Kaytto:
        agent = OCRDispatchAgent()
        # Kuvalataus:
        agent.set_image(image_bytes)
        result = await agent.fetch()
        # Tai manuaalinen syotto:
        agent.set_text(parsed_text)
        result = await agent.fetch()
    """

    name = "OCRDispatchAgent"
    ttl = 60  # 1 min valimuisti (data vanhenee nopeasti)
    enabled = True

    def __init__(self) -> None:
        super().__init__(name="OCRDispatchAgent")
        self._pending_image: Optional[bytes] = None
        self._pending_text: Optional[str] = None
        self._last_snapshot: Optional[DispatchSnapshot] = None

    def set_image(self, image_bytes: bytes) -> None:
        """Aseta kuva OCR-kasittelya varten."""
        self._pending_image = image_bytes
        self._pending_text = None
        self.invalidate_cache()

    def set_text(self, text: str) -> None:
        """Aseta manuaalisesti syotetty teksti."""
        self._pending_text = text
        self._pending_image = None
        self.invalidate_cache()

    @property
    def last_snapshot(self) -> Optional[DispatchSnapshot]:
        """Viimeisin kasitelty tilannekuva."""
        return self._last_snapshot

    async def fetch(self) -> AgentResult:
        """Kasittele kuva/teksti ja tuota signaalit."""
        start_ms = self._now_ms()

        # Ei dataa -> tyhja tulos
        if not self._pending_image and not self._pending_text:
            return self._ok(signals=[], raw_data={"status": "waiting"})

        try:
            # OCR tai suorateksti
            if self._pending_image:
                raw_text = ocr_image_to_text(self._pending_image)
                source = "ocr"
            else:
                raw_text = self._pending_text or ""
                source = "manual"

            # Parsii rivit
            rows = parse_dispatch_text(raw_text)

            if not rows:
                elapsed = self._now_ms() - start_ms
                return AgentResult(
                    agent_name=self.name,
                    status="ok",
                    signals=[],
                    raw_data={
                        "status": "no_data",
                        "raw_text": raw_text[:500],
                    },
                    elapsed_ms=elapsed,
                )

            # Luo tilannekuva
            snapshot = DispatchSnapshot(
                rows=rows,
                source=source,
                raw_text=raw_text,
            )
            self._last_snapshot = snapshot

            # Tuota signaalit
            signals = self._build_signals(snapshot)

            elapsed = self._now_ms() - start_ms
            logger.info(
                "OCRDispatch: %d rivia, %d signaalia, "
                "kokonaiskysynta=%d, tarjonta=%d",
                len(rows), len(signals),
                snapshot.total_demand, snapshot.total_supply,
            )

            return AgentResult(
                agent_name=self.name,
                status="ok",
                signals=signals,
                raw_data={
                    "rows": len(rows),
                    "total_demand": snapshot.total_demand,
                    "total_supply": snapshot.total_supply,
                    "source": source,
                    "hottest": [
                        {
                            "station": r.station_name,
                            "demand": r.real_demand,
                            "supply": r.autoja,
                            "ratio": round(r.demand_ratio, 2),
                        }
                        for r in snapshot.hottest_rows[:5]
                    ],
                },
                elapsed_ms=elapsed,
            )

        except Exception as e:
            logger.error("OCRDispatch virhe: %s", e)
            return self._error(str(e))

    def _build_signals(self, snapshot: DispatchSnapshot) -> list[Signal]:
        """
        Rakenna signaalit tilannekuvan perusteella.

        Pisteytyslogiikka:
          demand_ratio >= 3.0 -> urgency 8, score 12 (KRIITTINEN puute)
          demand_ratio >= 2.0 -> urgency 6, score 8  (KORKEA kysynta)
          demand_ratio >= 1.0 -> urgency 4, score 5  (NORMAALI)
          demand_ratio <  1.0 -> ei signaalia (tarjonta riittaa)

        K+/T+ historiallinen data saa urgency 4 (ei 6).
        """
        signals: list[Signal] = []
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=15)  # OCR-data vanhenee nopeasti

        # Aggregoi per alue
        area_data: dict[str, dict] = {}
        for row in snapshot.rows:
            if not row.area_name or row.area_name not in AREAS:
                continue

            if row.area_name not in area_data:
                area_data[row.area_name] = {
                    "real_demand": 0,
                    "historical_demand": 0,
                    "supply": 0,
                    "stations": [],
                }

            d = area_data[row.area_name]
            d["real_demand"] += row.real_demand
            d["historical_demand"] += row.historical_demand
            d["supply"] += row.autoja
            d["stations"].append(row)

        for area_name, data in area_data.items():
            real_demand = data["real_demand"]
            supply = data["supply"]
            historical = data["historical_demand"]

            # Reaaliaikainen kysynta -> korkea urgency
            if real_demand > 0:
                ratio = real_demand / max(supply, 1)

                if ratio >= 3.0:
                    score = 12.0
                    urgency = 8
                elif ratio >= 2.0:
                    score = 8.0
                    urgency = 6
                elif ratio >= 1.0:
                    score = 5.0
                    urgency = 4
                else:
                    continue  # Tarjonta riittaa

                station_names = ", ".join(
                    r.station_name for r in data["stations"][:3]
                )
                reason = (
                    f"Valitys: {area_name} - {real_demand} kyytia, "
                    f"{supply} autoa (suhde {ratio:.1f}x) "
                    f"[{station_names}]"
                )

                signals.append(Signal(
                    area=area_name,
                    score_delta=score,
                    reason=reason,
                    urgency=urgency,
                    expires_at=expires,
                    source_url="",
                    agent=self.name,
                    category="dispatch",
                    title=f"Valitys: {area_name}",
                    description=reason,
                    extra={
                        "demand": real_demand,
                        "supply": supply,
                        "ratio": round(ratio, 2),
                        "source": "realtime",
                    },
                ))

            # Historiallinen data -> matalampi urgency (4)
            if historical > 0 and real_demand == 0:
                h_ratio = historical / max(supply, 1)
                if h_ratio >= 1.5:
                    score = 3.0
                    urgency = 4  # K+/T+ = historiallinen, urgency 4

                    reason = (
                        f"Historia (vko sitten): {area_name} - "
                        f"{historical} kyytia odotettavissa "
                        f"({supply} autoa paikalla)"
                    )

                    signals.append(Signal(
                        area=area_name,
                        score_delta=score,
                        reason=reason,
                        urgency=urgency,
                        expires_at=expires,
                        source_url="",
                        agent=self.name,
                        category="dispatch",
                        title=f"Ennuste: {area_name}",
                        description=reason,
                        extra={
                            "demand": historical,
                            "supply": supply,
                            "ratio": round(h_ratio, 2),
                            "source": "historical",
                        },
                    ))

        return sorted(signals, key=lambda s: s.urgency, reverse=True)
