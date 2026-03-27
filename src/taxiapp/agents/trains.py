"""
trains.py -- TrainAgent
Helsinki Taxi AI v2.0

Hakee VAIN saapuvat kaukojunat kolmelle asemalle:

- HKI  (Helsinki paarautatieasema)
- PSL  (Pasila -- Messukeskus / Hartwall-areena)
- TKL  (Tikkurila -- lentoaseman syottoliikenne)

Ei nayta lahtoja Helsingista. Vain Helsinkiin saapuvat IC/S/P/AE/PYO-junat.

Lahde: rata.digitraffic.fi (avoin data, ei API-avainta)
Linkit: vr.fi/radalla -- suodatettu saapuviin kaukojuniin

v2.0: Korjattu Signal-kentat, lisatty lahtooaseman nimi korttiin
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger("taxiapp.TrainAgent")

# -- Vakiot -------------------------------------------------------------------

STATIONS: dict[str, dict] = {
    "HKI": {
        "name": "Rautatieasema",
        "area": "Rautatieasema",
        "lat": 60.1719,
        "lon": 24.9414,
        "live_url": (
            "https://www.vr.fi/radalla"
            "?station=HKI"
            "&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22"
            "%3A%22Long-distance%22%7D"
        ),
    },
    "PSL": {
        "name": "Pasila",
        "area": "Pasila",
        "lat": 60.1989,
        "lon": 24.9340,
        "live_url": (
            "https://www.vr.fi/radalla"
            "?station=PSL"
            "&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22"
            "%3A%22Long-distance%22%7D"
        ),
    },
    "TKL": {
        "name": "Tikkurila",
        "area": "Tikkurila",
        "lat": 60.2925,
        "lon": 25.0440,
        "live_url": (
            "https://www.vr.fi/radalla"
            "?station=TKL"
            "&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22"
            "%3A%22Long-distance%22%7D"
        ),
    },
}

LONG_DISTANCE_CATEGORIES: frozenset[str] = frozenset({"Long-distance"})

DELAY_THRESHOLD_NORMAL: int = 5
DELAY_THRESHOLD_HIGH: int = 15
DELAY_THRESHOLD_CRITICAL: int = 30

LOOKAHEAD_MINUTES: int = 120

BASE_URL = "https://rata.digitraffic.fi/api/v1/live-trains/station/{station}"

# Tunnetut lahtoasemat
KNOWN_ORIGINS: dict[str, str] = {
    "OL": "Oulu", "RV": "Rovaniemi", "TL": "Tampere",
    "TPE": "Tampere", "JY": "Jyvaskyla", "KUO": "Kuopio",
    "JNS": "Joensuu", "LH": "Lahti", "KV": "Kouvola",
    "TRE": "Tampere", "TUR": "Turku", "SM": "Seinajoki",
    "VS": "Vaasa", "IM": "Imatra", "KTA": "Kotka",
    "OV": "Orivesi", "PM": "Pieksaemaki", "KOK": "Kokkola",
    "RI": "Riihimaeki", "HY": "Hyvinkaa",
}


class TrainAgent(BaseAgent):
    """
    Hakee reaaliaikaiset kaukojuna-aikataulut kolmelta asemalta.

    Palauttaa signaalit vain SAAPUVISTA kaukojunista.
    Signaalin pisteet:
      - Perus saapuminen: 2.5 pistetta
      - Myohastyminen 15-29 min: 4.5 pistetta
      - Myohastyminen 30+ min: 6.0 pistetta (kriittinen tarve)
      - Peruutettu: 7.0 pistetta
    """

    name = "TrainAgent"
    ttl = 120

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
                logger.warning(
                    "TrainAgent: asema %s virhe: %s", station_id, result
                )
                continue
            station_signals, count = result
            signals.extend(station_signals)
            total_trains += count

        elapsed = self._now_ms() - start_ms
        logger.info(
            "TrainAgent: %d junaa -> %d signaalia | %dms",
            total_trains, len(signals), elapsed,
        )

        return AgentResult(
            agent_name=self.name,
            status="ok",
            signals=signals,
            raw_data={"total_trains": total_trains},
            elapsed_ms=elapsed,
        )

    async def _fetch_station(
        self,
        client: httpx.AsyncClient,
        station_id: str,
        station_info: dict,
    ) -> tuple[list[Signal], int]:
        """Hae yhden aseman saapuvat kaukojunat."""
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
            if train.get("trainCategory") not in LONG_DISTANCE_CATEGORIES:
                continue
            long_distance_count += 1

            train_number = train.get("trainNumber", "?")
            train_type = train.get("trainType", "?")

            arrival_row = self._find_arrival_row(train, station_id)
            if arrival_row is None:
                continue

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

            if actual_dt < now_utc:
                continue
            if actual_dt > lookahead_cutoff:
                continue

            delay_min = max(
                0,
                int((actual_dt - scheduled_dt).total_seconds() / 60),
            )

            minutes_away = int((actual_dt - now_utc).total_seconds() / 60)
            score, urgency = self._calculate_score(
                delay_min=delay_min,
                cancelled=cancelled,
                minutes_until_arrival=minutes_away,
            )

            origin_station = self._get_origin_station(train)
            arrival_time_str = actual_dt.strftime("%H:%M")

            # Rakenna kuvaus
            if cancelled:
                reason = (
                    f"{train_type}{train_number} "
                    f"{origin_station} -> {station_info['name']}"
                    f" -- PERUUTETTU (aik. {arrival_time_str})"
                )
            elif delay_min >= DELAY_THRESHOLD_CRITICAL:
                reason = (
                    f"{train_type}{train_number} "
                    f"{origin_station} -> {station_info['name']}"
                    f" {arrival_time_str}"
                    f" (+{delay_min} min myohassa!)"
                )
            elif delay_min >= DELAY_THRESHOLD_NORMAL:
                reason = (
                    f"{train_type}{train_number} "
                    f"{origin_station} -> {station_info['name']}"
                    f" {arrival_time_str}"
                    f" (+{delay_min} min)"
                )
            else:
                reason = (
                    f"{train_type}{train_number} "
                    f"{origin_station} -> {station_info['name']}"
                    f" {arrival_time_str}"
                    f" ({minutes_away} min)"
                )

            sig = Signal(
                area=station_info["area"],
                score_delta=score,
                reason=reason,
                urgency=urgency,
                expires_at=actual_dt + timedelta(minutes=15),
                source_url=station_info["live_url"],
                title=f"Juna saapuu: {station_info['name']}",
                description=reason,
                agent=self.name,
                category="trains",
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
        """Etsi aseman pysahtymisrivi junasta."""
        for row in train.get("timeTableRows", []):
            if (
                row.get("stationShortCode") == station_id
                and row.get("type") == "ARRIVAL"
                and row.get("trainStopping") is not False
            ):
                return row
        return None

    def _get_origin_station(self, train: dict) -> str:
        """Palauta junan lahtoaseman nimi."""
        rows = train.get("timeTableRows", [])
        if not rows:
            return "?"
        first_row = rows[0]
        code = first_row.get("stationShortCode", "?")
        return KNOWN_ORIGINS.get(code, code)

    def _calculate_score(
        self,
        delay_min: int,
        cancelled: bool,
        minutes_until_arrival: int,
    ) -> tuple[float, int]:
        """Laske pisteamaara ja kiireellisyystaso."""
        if cancelled:
            return 7.0, 7

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

        if minutes_until_arrival <= 10:
            base_score += 1.5
            urgency = min(urgency + 1, 9)
        elif minutes_until_arrival <= 20:
            base_score += 0.8

        return base_score, urgency
