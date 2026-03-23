“””
trains.py — TrainAgent
Helsinki Taxi AI

Hakee VAIN saapuvat kaukojunat kolmelle asemalle:

- HKI  (Helsinki päärautatieasema)
- PSL  (Pasila — Messukeskus / Hartwall-areena)
- TKL  (Tikkurila — lentoaseman syöttöliikenne)

Ei näytä lähtöjä Helsingistä. Vain Helsinkiin saapuvat IC/S/P/AE/PYO-junat.

Lähde: rata.digitraffic.fi (avoin data, ei API-avainta)
Linkit: vr.fi/radalla — suodatettu saapuviin kaukojuniin
“””

from **future** import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger(“taxiapp.TrainAgent”)

# ── Vakiot ─────────────────────────────────────────────────────────────────

STATIONS: dict[str, dict] = {
“HKI”: {
“name”: “Rautatieasema”,
“area”: “helsinki_central”,
“lat”: 60.1719,
“lon”: 24.9414,
# Suora linkki VR:n live-tauluun — VAIN saapuvat kaukojunat
“live_url”: (
“https://www.vr.fi/radalla”
“?station=HKI”
“&direction=ARRIVAL”
“&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D”
),
},
“PSL”: {
“name”: “Pasila”,
“area”: “pasila”,
“lat”: 60.1989,
“lon”: 24.9340,
“live_url”: (
“https://www.vr.fi/radalla”
“?station=PSL”
“&direction=ARRIVAL”
“&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D”
),
},
“TKL”: {
“name”: “Tikkurila”,
“area”: “tikkurila”,
“lat”: 60.2925,
“lon”: 25.0440,
“live_url”: (
“https://www.vr.fi/radalla”
“?station=TKL”
“&direction=ARRIVAL”
“&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D”
),
},
}

# Junatyypit joita pidetään kaukojunina (Digitraffic trainCategory-arvo)

LONG_DISTANCE_CATEGORIES: frozenset[str] = frozenset({“Long-distance”})

# Myöhästyminen minuutteina — eri pisteytystasot

DELAY_THRESHOLD_NORMAL: int = 5    # pieni myöhästyminen
DELAY_THRESHOLD_HIGH: int = 15     # korotettu pisteytys
DELAY_THRESHOLD_CRITICAL: int = 30  # kriittinen (taso 4 CEO:ssa)

# Aikaikkuna: haetaan junat jotka saapuvat seuraavan X minuutin sisällä

LOOKAHEAD_MINUTES: int = 120

# Digitraffic API — live-junat per asema, VAIN saapuvat

BASE_URL = “https://rata.digitraffic.fi/api/v1/live-trains/station/{station}”

class TrainAgent(BaseAgent):
“””
Hakee reaaliaikaiset kaukojuna-aikataulut kolmelta asemalta.

```
Palauttaa signaalit vain SAAPUVISTA kaukojunista.
Signaalin pisteet:
  - Perus saapuminen: 2 pistettä
  - Iso juna (yli 300 matkustajaa, arvio): 3 pistettä
  - Myöhästyminen 15-29 min: 4 pistettä (lisää kysyntää)
  - Myöhästyminen 30+ min: 6 pistettä (kriittinen tarve)
"""

def __init__(self) -> None:
    super().__init__(name="TrainAgent")

async def fetch(self) -> AgentResult:
    """Hae saapuvat kaukojunat kaikilta asemilta rinnakkain."""
    start_ms = self._now_ms()

    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [
            self._fetch_station(client, station_id, station_info)
            for station_id, station_info in STATIONS.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    signals: list[Signal] = []
    total_trains = 0

    for station_id, result in zip(STATIONS.keys(), results):
        if isinstance(result, Exception):
            logger.warning("TrainAgent: asema %s virhe: %s", station_id, result)
            continue
        station_signals, count = result
        signals.extend(station_signals)
        total_trains += count

    elapsed = self._now_ms() - start_ms
    logger.info(
        "TrainAgent: %d junaa (HKI/PSL/TKL) -> %d signaalia",
        total_trains,
        len(signals),
    )
    logger.info("TrainAgent: ok | %d signaalia | %dms", len(signals), elapsed)

    return AgentResult(
        agent_name=self.name,
        signals=signals,
        ok=True,
        elapsed_ms=elapsed,
    )

async def _fetch_station(
    self,
    client: httpx.AsyncClient,
    station_id: str,
    station_info: dict,
) -> tuple[list[Signal], int]:
    """
    Hae yhden aseman saapuvat kaukojunat.

    Digitraffic-parametrit:
      arrived_trains=0        — ei näytetä jo saapuneita
      arriving_trains=10      — max 10 saapuvaa
      departed_trains=0       — ei lähtöjä
      departing_trains=0      — ei lähtöjä
      include_nonstopping=false

    TÄRKEÄÄ: Suodatetaan lisäksi Python-puolella trainCategory=="Long-distance"
    jotta taajamajunat (H, E, jne.) eivät pääse läpi.
    """
    url = BASE_URL.format(station=station_id)
    params = {
        "arrived_trains": 0,
        "arriving_trains": 10,
        "departed_trains": 0,
        "departing_trains": 0,
        "include_nonstopping": "false",
    }

    resp = await client.get(url, params=params)
    resp.raise_for_status()
    trains: list[dict] = resp.json()

    now_utc = datetime.now(timezone.utc)
    lookahead_cutoff = now_utc + timedelta(minutes=LOOKAHEAD_MINUTES)

    signals: list[Signal] = []
    long_distance_count = 0

    for train in trains:
        # ── 1. Suodata: vain kaukojunat ─────────────────────────────
        if train.get("trainCategory") not in LONG_DISTANCE_CATEGORIES:
            continue
        long_distance_count += 1

        train_number = train.get("trainNumber", "?")
        train_type = train.get("trainType", "?")

        # ── 2. Etsi aseman pysähtymistiedot ─────────────────────────
        arrival_row = self._find_arrival_row(train, station_id)
        if arrival_row is None:
            continue  # ei pysähdy tällä asemalla

        # ── 3. Laske saapumisaika ja myöhästyminen ──────────────────
        scheduled_str = arrival_row.get("scheduledTime", "")
        actual_str = arrival_row.get("liveEstimateTime") or scheduled_str
        cancelled = arrival_row.get("cancelled", False)

        if not scheduled_str:
            continue

        try:
            scheduled_dt = datetime.fromisoformat(
                scheduled_str.replace("Z", "+00:00")
            )
            actual_dt = datetime.fromisoformat(
                actual_str.replace("Z", "+00:00")
            )
        except ValueError:
            continue

        # Ohita junat jotka ovat jo saapuneet tai liian kaukana
        if actual_dt < now_utc:
            continue
        if actual_dt > lookahead_cutoff:
            continue

        # ── 4. Laske myöhästyminen minuutteina ──────────────────────
        delay_min = max(
            0,
            int((actual_dt - scheduled_dt).total_seconds() / 60),
        )

        # ── 5. Laske pisteet ─────────────────────────────────────────
        score, urgency = self._calculate_score(
            delay_min=delay_min,
            cancelled=cancelled,
            minutes_until_arrival=int(
                (actual_dt - now_utc).total_seconds() / 60
            ),
        )

        # ── 6. Muodosta lähtöasema-teksti ───────────────────────────
        origin_station = self._get_origin_station(train)

        # ── 7. Luo signaali ─────────────────────────────────────────
        minutes_away = int((actual_dt - now_utc).total_seconds() / 60)
        arrival_time_str = actual_dt.strftime("%H:%M")

        if cancelled:
            status_emoji = "🚫"
            description = (
                f"{train_type}{train_number} {origin_station} → "
                f"{station_info['name']} — PERUUTETTU (aik. {arrival_time_str})"
            )
        elif delay_min >= DELAY_THRESHOLD_CRITICAL:
            status_emoji = "🔴"
            description = (
                f"{train_type}{train_number} {origin_station} → "
                f"{station_info['name']} {arrival_time_str} "
                f"(+{delay_min} min myöhässä!)"
            )
        elif delay_min >= DELAY_THRESHOLD_HIGH:
            status_emoji = "🟠"
            description = (
                f"{train_type}{train_number} {origin_station} → "
                f"{station_info['name']} {arrival_time_str} "
                f"(+{delay_min} min)"
            )
        elif delay_min >= DELAY_THRESHOLD_NORMAL:
            status_emoji = "🟡"
            description = (
                f"{train_type}{train_number} {origin_station} → "
                f"{station_info['name']} {arrival_time_str} "
                f"(+{delay_min} min)"
            )
        else:
            status_emoji = "🟢"
            description = (
                f"{train_type}{train_number} {origin_station} → "
                f"{station_info['name']} {arrival_time_str} "
                f"({minutes_away} min)"
            )

        sig = Signal(
            agent=self.name,
            area=station_info["area"],
            score=score,
            urgency=urgency,
            title=f"{status_emoji} Juna saapuu: {station_info['name']}",
            description=description,
            source_url=station_info["live_url"],  # ← VR live-taulu, VAIN saapuvat
            extra={
                "train_number": train_number,
                "train_type": train_type,
                "station": station_id,
                "station_name": station_info["name"],
                "scheduled_arrival": scheduled_str,
                "actual_arrival": actual_str,
                "delay_minutes": delay_min,
                "minutes_away": minutes_away,
                "cancelled": cancelled,
                "origin": origin_station,
            },
        )
        signals.append(sig)

    return signals, long_distance_count

def _find_arrival_row(
    self, train: dict, station_id: str
) -> Optional[dict]:
    """Etsi aseman pysähtymisrivi junasta (saapumistiedot)."""
    for row in train.get("timeTableRows", []):
        if (
            row.get("stationShortCode") == station_id
            and row.get("type") == "ARRIVAL"
            and not row.get("trainStopping") is False
        ):
            return row
    return None

def _get_origin_station(self, train: dict) -> str:
    """Palauta junan lähtöaseman nimi."""
    rows = train.get("timeTableRows", [])
    if not rows:
        return "?"
    first_row = rows[0]
    code = first_row.get("stationShortCode", "?")
    # Tunnetut asemat
    known: dict[str, str] = {
        "OL": "Oulu", "RV": "Rovaniemi", "TL": "Tampere",
        "TPE": "Tampere", "JY": "Jyväskylä", "KUO": "Kuopio",
        "JNS": "Joensuu", "LH": "Lahti", "KV": "Kouvola",
        "TRE": "Tampere", "TUR": "Turku", "SM": "Seinäjoki",
        "VS": "Vaasa", "IM": "Imatra", "KTA": "Kotka",
    }
    return known.get(code, code)

def _calculate_score(
    self,
    delay_min: int,
    cancelled: bool,
    minutes_until_arrival: int,
) -> tuple[float, int]:
    """
    Laske pistemäärä ja kiireellisyystaso.

    Palauttaa (score: float, urgency: int)
    """
    if cancelled:
        # Peruutus = paljon takseja tarvitaan nopeasti
        return 7.0, 7

    # Myöhästyminen lisää kysyntää (ihmiset odottaneet kauan, taksi tuntuu hyvältä)
    if delay_min >= DELAY_THRESHOLD_CRITICAL:
        base_score = 6.0
        urgency = 6
    elif delay_min >= DELAY_THRESHOLD_HIGH:
        base_score = 4.5
        urgency = 4
    elif delay_min >= DELAY_THRESHOLD_NORMAL:
        base_score = 3.5
        urgency = 3
    else:
        base_score = 2.5
        urgency = 2

    # Lähestyvä juna saa lisäpisteitä
    if minutes_until_arrival <= 10:
        base_score += 1.5
        urgency = min(urgency + 1, 9)
    elif minutes_until_arrival <= 20:
        base_score += 0.8

    return base_score, urgency

@staticmethod
def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
```
