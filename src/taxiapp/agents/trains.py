"""
trains.py — TrainAgent
Helsinki Taxi AI

Hakee VAIN saapuvat kaukojunat kolmelle asemalle:
  HKI  — Helsinki päärautatieasema   → alue: "Rautatieasema"
  PSL  — Pasila                       → alue: "Pasila"
  TKL  — Tikkurila                    → alue: "Tikkurila"

Lähde:  rata.digitraffic.fi (avoin data, ei API-avainta)
Linkit: vr.fi/radalla — suodatettu saapuviin kaukojuniin
ttl:    120s (2 min)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger("taxiapp.TrainAgent")


# ── Asemat ─────────────────────────────────────────────────────────────────

STATIONS: dict[str, dict] = {
    "HKI": {
        "name": "Rautatieasema",
        "area": "Rautatieasema",          # täsmää AREAS-avaimen kanssa
        "lat":  60.1719,
        "lon":  24.9414,
        "live_url": (
            "https://www.vr.fi/radalla"
            "?station=HKI&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D"
        ),
    },
    "PSL": {
        "name": "Pasila",
        "area": "Pasila",
        "lat":  60.1989,
        "lon":  24.9340,
        "live_url": (
            "https://www.vr.fi/radalla"
            "?station=PSL&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D"
        ),
    },
    "TKL": {
        "name": "Tikkurila",
        "area": "Tikkurila",
        "lat":  60.2925,
        "lon":  25.0440,
        "live_url": (
            "https://www.vr.fi/radalla"
            "?station=TKL&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D"
        ),
    },
}

# Vain kaukojunat
LONG_DISTANCE_CATEGORIES: frozenset[str] = frozenset({"Long-distance"})

# Myöhästymiskynnykset (minuuttia)
DELAY_NORMAL:   int = 5
DELAY_HIGH:     int = 15
DELAY_CRITICAL: int = 30

# Aikaikkuna: haetaan junat jotka saapuvat seuraavan X min sisällä
LOOKAHEAD_MINUTES: int = 120

# Digitraffic API — VAIN saapuvat
BASE_URL = "https://rata.digitraffic.fi/api/v1/live-trains/station/{station}"

# Tunnetut lähtöasemat (Digitraffic-koodi → suomi)
KNOWN_ORIGINS: dict[str, str] = {
    "OL": "Oulu",    "RV": "Rovaniemi", "TPE": "Tampere",
    "TRE": "Tampere","JY": "Jyväskylä", "KUO": "Kuopio",
    "JNS": "Joensuu","LH": "Lahti",     "KV": "Kouvola",
    "TUR": "Turku",  "SM": "Seinäjoki", "VS": "Vaasa",
    "IM": "Imatra",  "KTA": "Kotka",    "HKI": "Helsinki",
    "TL": "Tampere", "PSL": "Pasila",
}


class TrainAgent(BaseAgent):
    """
    Hakee reaaliaikaiset kaukojuna-aikataulut kolmelta asemalta.

    Palauttaa signaalit vain SAAPUVISTA kaukojunista.
    Signal-pisteet:
      Perus saapuminen:         urgency=2, score=2.5
      Myöhässä 5–14 min:        urgency=3, score=3.5
      Myöhässä 15–29 min:       urgency=4, score=4.5
      Myöhässä 30+ min:         urgency=6, score=6.0
      Peruutettu:               urgency=7, score=7.0
      Saapuu alle 10 min:       urgency+1, score+1.5
    """

    name    = "TrainAgent"
    ttl     = 120
    enabled = True

    async def fetch(self) -> AgentResult:
        """Hae saapuvat kaukojunat kaikilta asemilta rinnakkain."""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            headers={"User-Agent": "HelsinkiTaxiAI/1.0"},
            follow_redirects=True,
        ) as client:
            tasks = [
                self._fetch_station(client, sid, sinfo)
                for sid, sinfo in STATIONS.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        signals:      list[Signal] = []
        total_trains: int          = 0

        for station_id, result in zip(STATIONS.keys(), results):
            if isinstance(result, Exception):
                logger.warning("TrainAgent: asema %s virhe: %s", station_id, result)
                continue
            station_signals, count = result
            signals.extend(station_signals)
            total_trains += count

        logger.info(
            "TrainAgent: %d kaukojunaa (HKI/PSL/TKL) → %d signaalia",
            total_trains, len(signals),
        )

        raw = {
            "total_trains": total_trains,
            "signals":      len(signals),
            "stations":     list(STATIONS.keys()),
        }
        return self._ok(signals, raw_data=raw)

    # ── Yhden aseman haku ─────────────────────────────────────────────────

    async def _fetch_station(
        self,
        client:       httpx.AsyncClient,
        station_id:   str,
        station_info: dict,
    ) -> tuple[list[Signal], int]:
        """Hae yhden aseman saapuvat kaukojunat."""
        url    = BASE_URL.format(station=station_id)
        params = {
            "arrived_trains":    0,
            "arriving_trains":   10,
            "departed_trains":   0,
            "departing_trains":  0,
            "include_nonstopping": "false",
        }

        resp = await client.get(url, params=params)
        resp.raise_for_status()
        trains: list[dict] = resp.json()

        now_utc  = datetime.now(timezone.utc)
        cutoff   = now_utc + timedelta(minutes=LOOKAHEAD_MINUTES)
        signals: list[Signal] = []
        ld_count = 0

        for train in trains:
            # 1. Vain kaukojunat
            if train.get("trainCategory") not in LONG_DISTANCE_CATEGORIES:
                continue
            ld_count += 1

            train_number = str(train.get("trainNumber", "?"))
            train_type   = str(train.get("trainType",   "?"))

            # 2. Etsi saapumisrivi
            arrival_row = self._find_arrival_row(train, station_id)
            if arrival_row is None:
                continue

            # 3. Laske ajat
            sched_str = arrival_row.get("scheduledTime",  "")
            actual_str = arrival_row.get("liveEstimateTime") or sched_str
            cancelled  = arrival_row.get("cancelled", False)

            if not sched_str:
                continue

            try:
                sched_dt  = datetime.fromisoformat(sched_str.replace("Z",  "+00:00"))
                actual_dt = datetime.fromisoformat(actual_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            # Ohita jo saapuneet ja liian kaukana olevat
            if actual_dt < now_utc:
                continue
            if actual_dt > cutoff:
                continue

            # 4. Myöhästyminen
            delay_min = max(0, int(
                (actual_dt - sched_dt).total_seconds() / 60
            ))
            minutes_away = int(
                (actual_dt - now_utc).total_seconds() / 60
            )

            # 5. Pisteet
            score, urgency = self._calculate_score(
                delay_min=delay_min,
                cancelled=cancelled,
                minutes_away=minutes_away,
            )

            # 6. Lähtöasema
            origin = self._get_origin(train)

            # 7. Teksti
            arrival_str = actual_dt.strftime("%H:%M")
            if cancelled:
                reason = (
                    f"🚫 {train_type}{train_number} {origin} → "
                    f"{station_info['name']} PERUUTETTU (aik. {arrival_str})"
                )
            elif delay_min >= DELAY_CRITICAL:
                reason = (
                    f"🔴 {train_type}{train_number} {origin} → "
                    f"{station_info['name']} {arrival_str} (+{delay_min} min)"
                )
            elif delay_min >= DELAY_HIGH:
                reason = (
                    f"🟠 {train_type}{train_number} {origin} → "
                    f"{station_info['name']} {arrival_str} (+{delay_min} min)"
                )
            elif delay_min >= DELAY_NORMAL:
                reason = (
                    f"🟡 {train_type}{train_number} {origin} → "
                    f"{station_info['name']} {arrival_str} (+{delay_min} min)"
                )
            else:
                reason = (
                    f"🟢 {train_type}{train_number} {origin} → "
                    f"{station_info['name']} {arrival_str} ({minutes_away} min)"
                )

            # 8. Luo Signal — käyttää OIKEITA kenttiä BaseAgentin mukaan
            signals.append(Signal(
                area        = station_info["area"],
                score_delta = score,
                reason      = reason,
                urgency     = urgency,
                expires_at  = actual_dt + timedelta(minutes=15),
                source_url  = station_info["live_url"],
            ))

        return signals, ld_count

    # ── Apumetodit ────────────────────────────────────────────────────────

    def _find_arrival_row(
        self, train: dict, station_id: str
    ) -> Optional[dict]:
        """Etsi saapumisrivi junasta."""
        for row in train.get("timeTableRows", []):
            if (
                row.get("stationShortCode") == station_id
                and row.get("type") == "ARRIVAL"
                and row.get("trainStopping") is not False
            ):
                return row
        return None

    def _get_origin(self, train: dict) -> str:
        """Palauta junan lähtöaseman nimi."""
        rows = train.get("timeTableRows", [])
        if not rows:
            return "?"
        code = rows[0].get("stationShortCode", "?")
        return KNOWN_ORIGINS.get(code, code)

    def _calculate_score(
        self,
        delay_min:   int,
        cancelled:   bool,
        minutes_away: int,
    ) -> tuple[float, int]:
        """Laske (score_delta, urgency)."""
        if cancelled:
            return 7.0, 7

        if delay_min >= DELAY_CRITICAL:
            score, urgency = 6.0, 6
        elif delay_min >= DELAY_HIGH:
            score, urgency = 4.5, 4
        elif delay_min >= DELAY_NORMAL:
            score, urgency = 3.5, 3
        else:
            score, urgency = 2.5, 2

        # Lähestyvä juna → pisteytysbonus
        if minutes_away <= 10:
            score   += 1.5
            urgency  = min(urgency + 1, 9)
        elif minutes_away <= 20:
            score += 0.8

        return score, urgency
