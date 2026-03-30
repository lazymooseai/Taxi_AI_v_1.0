"""
trains.py - TrainAgent
Helsinki Taxi AI

Hakee saapuvat kaukojunat kolmelle asemalle:
  HKI  (Helsinki paerautatieasema)
  PSL  (Pasila -- Messukeskus / Hartwall-areena)
  TKL  (Tikkurila -- lentoaseman syottoliikenne)

Ei nayta lahtoja Helsingista. Vain Helsinkiin saapuvat IC/S/P/AE/PYO-junat.

Laehde: rata.digitraffic.fi (avoin data, ei API-avainta)
Linkit: vr.fi/radalla -- suodatettu saapuviin kaukojuniin

KORJAUKSET (bugfix_8):
  - Signal-kentat korjattu: score_delta, reason (ei score/title/description)
  - Aluenimet korjattu: "Rautatieasema", "Pasila", "Tikkurila"
    (aiemmat "helsinki_central", "pasila", "tikkurila" eivat loydy AREAS-sanakirjasta)
  - AgentResult korjattu: status="ok", fetch_duration_ms
    (aiemmin ok=True, elapsed_ms -> TypeError joka syklissa)
  - _now_ms() nyt BaseAgentissa -> ei tarvita paikallista maarittelya
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger("taxiapp.TrainAgent")


# ── Vakiot ─────────────────────────────────────────────────────────────────

# HUOM: area-arvot PITAA loytya areas.py AREAS-sanakirjasta!
STATIONS: dict[str, dict] = {
    "HKI": {
        "name": "Rautatieasema",
        "area": "Rautatieasema",          # KORJATTU: oli "helsinki_central"
        "lat": 60.1719,
        "lon": 24.9414,
        "live_url": (
            "https://www.vr.fi/radalla"
            "?station=HKI"
            "&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D"
        ),
    },
    "PSL": {
        "name": "Pasila",
        "area": "Pasila",                  # KORJATTU: oli "pasila" (pieni kirjain)
        "lat": 60.1989,
        "lon": 24.9340,
        "live_url": (
            "https://www.vr.fi/radalla"
            "?station=PSL"
            "&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D"
        ),
    },
    "TKL": {
        "name": "Tikkurila",
        "area": "Tikkurila",               # KORJATTU: oli "tikkurila" (pieni kirjain)
        "lat": 60.2925,
        "lon": 25.0440,
        "live_url": (
            "https://www.vr.fi/radalla"
            "?station=TKL"
            "&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D"
        ),
    },
}

# Junatyypit joita pideytaan kaukojunina (Digitraffic trainCategory-arvo)
LONG_DISTANCE_CATEGORIES: frozenset[str] = frozenset({"Long-distance"})

# Myoehastyminen minuutteina -- eri pisteytystasot
DELAY_THRESHOLD_NORMAL: int = 5
DELAY_THRESHOLD_HIGH: int = 15
DELAY_THRESHOLD_CRITICAL: int = 30

# Aikaikkuna: haetaan junat jotka saapuvat seuraavan X minuutin sisaella
LOOKAHEAD_MINUTES: int = 120

# Digitraffic API -- live-junat per asema, VAIN saapuvat
BASE_URL = "https://rata.digitraffic.fi/api/v1/live-trains/station/{station}"

# Tunnetut asemat lyhennyskoodeilla -> suomenkielinen nimi
KNOWN_STATIONS: dict[str, str] = {
    "OL":  "Oulu",
    "RV":  "Rovaniemi",
    "TPE": "Tampere",
    "TRE": "Tampere",
    "JY":  "Jyvaskyla",
    "KUO": "Kuopio",
    "JNS": "Joensuu",
    "LH":  "Lahti",
    "KV":  "Kouvola",
    "TUR": "Turku",
    "SM":  "Seinajoki",
    "VS":  "Vaasa",
    "IM":  "Imatra",
    "KTA": "Kotka",
    "TL":  "Toijala",
    "HPL": "Haapamaki",
    "YV":  "Ylivieska",
    "KKN": "Kokemaki",
    "PE":  "Pieksamaki",
    "SL":  "Savonlinna",
}


# ==============================================================
# TRAINAGENT
# ==============================================================

class TrainAgent(BaseAgent):
    """
    Hakee reaaliaikaiset kaukojuna-aikataulut kolmelta asemalta.

    Palauttaa signaalit vain SAAPUVISTA kaukojunista.
    Signaalin pisteet (score_delta):
      - Perus saapuminen:         2.5 pistetta
      - Myoehastyminen 5-14 min:  3.5 pistetta
      - Myoehastyminen 15-29 min: 4.5 pistetta
      - Myoehastyminen 30+ min:   6.0 pistetta
      - Peruutus:                 7.0 pistetta
      - Saapuu alle 10 min:      +1.5 pistetta
    """

    name = "TrainAgent"
    ttl = 120

    def __init__(self) -> None:
        super().__init__(name="TrainAgent")

    async def fetch(self) -> AgentResult:
        """Hae saapuvat kaukojunat kaikilta asemilta rinnakkain."""
        start_ms = self._now_ms()  # BaseAgentissa maaeritelty

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0),
            headers={"User-Agent": "HelsinkiTaxiAI/1.0 (rata.digitraffic.fi)"},
        ) as client:
            tasks = [
                self._fetch_station(client, station_id, station_info)
                for station_id, station_info in STATIONS.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        signals: list[Signal] = []
        total_trains = 0

        for station_id, result in zip(STATIONS.keys(), results):
            if isinstance(result, Exception):
                logger.warning(
                    "TrainAgent: asema %s virhe: %s", station_id, result
                )
                continue
            station_signals, count = result
            signals.extend(station_signals)
            total_trains += count

        # Jarjesta kiireellisimmast ensin
        signals.sort(key=lambda s: s.urgency, reverse=True)

        elapsed = self._now_ms() - start_ms
        logger.info(
            "TrainAgent: %d junaa (HKI/PSL/TKL) -> %d signaalia | %dms",
            total_trains,
            len(signals),
            elapsed,
        )

        # KORJATTU: status="ok" + fetch_duration_ms (ei ok=True/elapsed_ms)
        return AgentResult(
            agent_name=self.name,
            status="ok",
            signals=signals,
            raw_data={
                "total_trains": total_trains,
                "stations": list(STATIONS.keys()),
            },
            fetch_duration_ms=float(elapsed),
        )

    async def _fetch_station(
        self,
        client: httpx.AsyncClient,
        station_id: str,
        station_info: dict,
    ) -> tuple[list[Signal], int]:
        """
        Hae yhden aseman saapuvat kaukojunat Digitraffic-APIsta.

        Digitraffic-parametrit:
          arrived_trains=0        -- ei nayteta jo saapuneita
          arriving_trains=10      -- max 10 saapuvaa
          departed_trains=0       -- ei lahtoja
          departing_trains=0      -- ei lahtoja
          include_nonstopping=false

        TAERKEAA: Suodatetaan lisaeksi Python-puolella
        trainCategory=="Long-distance" jotta taajamajunat (H, E jne.)
        eivat paase laapi.
        """
        url = BASE_URL.format(station=station_id)
        params = {
            "arrived_trains":     0,
            "arriving_trains":    10,
            "departed_trains":    0,
            "departing_trains":   0,
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
            # 1. Suodata: vain kaukojunat
            if train.get("trainCategory") not in LONG_DISTANCE_CATEGORIES:
                continue
            long_distance_count += 1

            train_number = train.get("trainNumber", "?")
            train_type   = train.get("trainType", "?")

            # 2. Etsi aseman pysahtymistiedot
            arrival_row = self._find_arrival_row(train, station_id)
            if arrival_row is None:
                continue

            # 3. Laske saapumisaika ja myoehastyminen
            scheduled_str = arrival_row.get("scheduledTime", "")
            actual_str    = arrival_row.get("liveEstimateTime") or scheduled_str
            cancelled     = arrival_row.get("cancelled", False)

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

            # Ohita jo saapuneet ja liian kaukana olevat
            if actual_dt < now_utc:
                continue
            if actual_dt > lookahead_cutoff:
                continue

            # 4. Laske myoehastyminen minuutteina
            delay_min = max(
                0,
                int((actual_dt - scheduled_dt).total_seconds() / 60),
            )

            # 5. Laske pisteet ja kiireellisyys
            score_delta, urgency = self._calculate_score(
                delay_min=delay_min,
                cancelled=cancelled,
                minutes_until_arrival=int(
                    (actual_dt - now_utc).total_seconds() / 60
                ),
            )

            # 6. Muodosta lahtoa-asema-teksti
            origin_station    = self._get_origin_station(train)
            minutes_away      = int((actual_dt - now_utc).total_seconds() / 60)
            arrival_time_str  = actual_dt.strftime("%H:%M")
            expires_at        = actual_dt + timedelta(minutes=20)

            # 7. Rakenna reason-teksti (ei literal-emojeja -> Unicode-escapet)
            if cancelled:
                reason = (
                    "\U0001f6ab "
                    f"{train_type}{train_number} "
                    f"{origin_station} -> {station_info['name']} "
                    f"PERUUTETTU (aik. {arrival_time_str})"
                )
            elif delay_min >= DELAY_THRESHOLD_CRITICAL:
                reason = (
                    "\U0001f534 "
                    f"{train_type}{train_number} "
                    f"{origin_station} -> {station_info['name']} "
                    f"{arrival_time_str} (+{delay_min} min myohassa!)"
                )
            elif delay_min >= DELAY_THRESHOLD_HIGH:
                reason = (
                    "\U0001f7e0 "
                    f"{train_type}{train_number} "
                    f"{origin_station} -> {station_info['name']} "
                    f"{arrival_time_str} (+{delay_min} min)"
                )
            elif delay_min >= DELAY_THRESHOLD_NORMAL:
                reason = (
                    "\U0001f7e1 "
                    f"{train_type}{train_number} "
                    f"{origin_station} -> {station_info['name']} "
                    f"{arrival_time_str} (+{delay_min} min)"
                )
            else:
                reason = (
                    "\U0001f7e2 "
                    f"{train_type}{train_number} "
                    f"{origin_station} -> {station_info['name']} "
                    f"{arrival_time_str} ({minutes_away} min)"
                )

            # 8. KORJATTU: Signal kentat: score_delta, reason
            #    (ei score/title/description kuten vanhassa versiossa)
            sig = Signal(
                area=station_info["area"],   # "Rautatieasema" / "Pasila" / "Tikkurila"
                score_delta=score_delta,
                reason=reason,
                urgency=urgency,
                expires_at=expires_at,
                source_url=station_info["live_url"],
                extra={
                    "train_number":       train_number,
                    "train_type":         train_type,
                    "station":            station_id,
                    "station_name":       station_info["name"],
                    "scheduled_arrival":  scheduled_str,
                    "actual_arrival":     actual_str,
                    "delay_minutes":      delay_min,
                    "minutes_away":       minutes_away,
                    "cancelled":          cancelled,
                    "origin":             origin_station,
                },
            )
            signals.append(sig)

        return signals, long_distance_count

    def _find_arrival_row(
        self, train: dict, station_id: str
    ) -> Optional[dict]:
        """Etsi aseman pysahtymisrivi junasta (saapumistiedot)."""
        for row in train.get("timeTableRows", []):
            if (
                row.get("stationShortCode") == station_id
                and row.get("type") == "ARRIVAL"
                and row.get("trainStopping") is not False
            ):
                return row
        return None

    def _get_origin_station(self, train: dict) -> str:
        """Palauta junan lahtoa-aseman nimi."""
        rows = train.get("timeTableRows", [])
        if not rows:
            return "?"
        first_row = rows[0]
        code = first_row.get("stationShortCode", "?")
        return KNOWN_STATIONS.get(code, code)

    def _calculate_score(
        self,
        delay_min: int,
        cancelled: bool,
        minutes_until_arrival: int,
    ) -> tuple[float, int]:
        """
        Laske pistemaeaerae (score_delta) ja kiireellisyystaso (urgency).
        Palauttaa (score_delta: float, urgency: int).
        """
        if cancelled:
            # Peruutus = paljon takseja tarvitaan nopeasti
            return 7.0, 7

        # Myoehastyminen lisaa kysyntaa
        if delay_min >= DELAY_THRESHOLD_CRITICAL:
            base_score = 6.0
            urgency    = 6
        elif delay_min >= DELAY_THRESHOLD_HIGH:
            base_score = 4.5
            urgency    = 4
        elif delay_min >= DELAY_THRESHOLD_NORMAL:
            base_score = 3.5
            urgency    = 3
        else:
            base_score = 2.5
            urgency    = 2

        # Laehestyvae juna saa lisaepisteitae
        if minutes_until_arrival <= 10:
            base_score += 1.5
            urgency = min(urgency + 1, 9)
        elif minutes_until_arrival <= 20:
            base_score += 0.8

        return round(base_score, 1), urgency
