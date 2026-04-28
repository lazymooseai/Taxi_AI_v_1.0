"""
trains.py - TrainAgent
Helsinki Taxi AI

Hakee VAIN saapuvat kaukojunat kolmelle asemalle:
  HKI  (Helsinki paarautatieasema)
  PSL  (Pasila - Messukeskus / Hartwall-areena)
  TKL  (Tikkurila - lentoaseman syottöliikenne)

Composition-haku: haetaan top-3 saapuvan junan todellinen
istumapaikkamäärä Digitraffic /compositions-rajapinnasta.
Muille junille kaytetaan junatyyppikohtaista oletusarviota.

Lahde: rata.digitraffic.fi (avoin data, ei API-avainta)
Linkit: vr.fi/radalla - suodatettu saapuviin kaukojuniin
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger("taxiapp.TrainAgent")

# ---------------------------------------------------------------------------
# VAKIOT
# ---------------------------------------------------------------------------

STATIONS: dict[str, dict] = {
    "HKI": {
        "name": "Rautatieasema",
        "area": "Rautatieasema",
        "lat": 60.1719,
        "lon": 24.9414,
        "live_url": "https://www.vr.fi/radalla",
    },
    "PSL": {
        "name": "Pasila",
        "area": "Pasila",
        "lat": 60.1989,
        "lon": 24.9340,
        "live_url": "https://www.vr.fi/radalla",
    },
    "TKL": {
        "name": "Tikkurila",
        "area": "Tikkurila",
        "lat": 60.2925,
        "lon": 25.0440,
        "live_url": "https://www.vr.fi/radalla",
    },
}

LONG_DISTANCE_CATEGORIES: frozenset[str] = frozenset({"Long-distance"})

DELAY_THRESHOLD_NORMAL: int = 5
DELAY_THRESHOLD_HIGH: int = 15
DELAY_THRESHOLD_CRITICAL: int = 30

LOOKAHEAD_MINUTES: int = 120

# Haetaan kokoonpanotiedot enintaan nalle monelle junalle per ajo
COMPOSITION_FETCH_LIMIT: int = 3

BASE_URL = "https://rata.digitraffic.fi/api/v1/live-trains/station/{station}"
COMPOSITION_URL = "https://rata.digitraffic.fi/api/v1/compositions/{date}/{train_number}"

# Digitraffic-User header - suositeltava kaytanto
DT_HEADERS = {"Digitraffic-User": "HelsinkiTaxiAI/1.0"}

# ---------------------------------------------------------------------------
# JUNATYYPPIKOHTAISET OLETUSKAPASITEETIT
# Kaytetaan kun /compositions ei ole saatavilla tai junalle ei haeta tietoja.
# Laskettu VR:n julkisista kalustotiedoista (istumapaikat, ei seisomapaikkoja).
# ---------------------------------------------------------------------------

TYPE_CAPACITY: dict[str, int] = {
    # Pendolino Sm6 (7 vaunua)
    "S": 297,
    # InterCity 2 (vaihtelee 5-9 vaunua) - keskiarvo
    "IC": 480,
    # InterCity 1 (vanhempi kalusto)
    "IC1": 420,
    # Pikajuna
    "P": 360,
    # AE = Allegro (ei liikennoi, historiallinen)
    "AE": 352,
    # PYO = Pyorakiekko-juna
    "PYO": 280,
    # Oletusarvo tuntemattomalle junatyypille
    "DEFAULT": 350,
}


def _type_capacity(train_type: str) -> int:
    """Palauta junatyyppikohtainen oletuskapasiteetti."""
    t = (train_type or "").upper()
    for prefix, cap in TYPE_CAPACITY.items():
        if t.startswith(prefix):
            return cap
    return TYPE_CAPACITY["DEFAULT"]


# ---------------------------------------------------------------------------
# COMPOSITION-PARSERI
# ---------------------------------------------------------------------------

def _parse_seat_count(composition_data: dict) -> Optional[int]:
    """
    Laske kokonaisistumapaikkamaara Digitraffic /compositions-vastauksesta.

    Rakenne (tiivistetty):
      {
        "trainNumber": 45,
        "journeySections": [
          {
            "wagons": [
              {
                "wagonType": "Ed",
                "seatingDisabled": 4,
                "seating": 64,
                ...
              },
              ...
            ]
          }
        ]
      }

    Summaa kaikkien vaunujen istuinpaikat kaikista journeySections-osioista.
    Veturit (ei seating-kenttaa) ohitetaan automaattisesti.
    """
    if not composition_data:
        return None

    total_seats: int = 0
    sections = composition_data.get("journeySections") or []

    for section in sections:
        wagons = section.get("wagons") or []
        for wagon in wagons:
            # Normaalit istumapaikat
            seats = wagon.get("seating", 0) or 0
            # Invaistumapaikat lasketaan mukaan
            disabled_seats = wagon.get("seatingDisabled", 0) or 0
            total_seats += seats + disabled_seats

    return total_seats if total_seats > 0 else None


# ---------------------------------------------------------------------------
# TRAINAGENT
# ---------------------------------------------------------------------------

class TrainAgent(BaseAgent):
    """
    Hakee reaaliaikaiset kaukojuna-aikataulut kolmelta asemalta.

    Uudistukset v2:
      - /compositions-haku top-3 junalle (todellinen istumapaikkamäärä)
      - Tyyppikohtainen fallback jos compositions ei saatavilla
      - Istumapaikkamäärä nakyy signaalin reason-tekstissä
      - score_delta skaalautuu matkustajamäärän mukaan
      - Digitraffic-User header kaikissa pyynnöissä
    """

    name = "TrainAgent"
    ttl = 120  # 2 min valimuisti

    def __init__(self) -> None:
        super().__init__()

    # ------------------------------------------------------------------
    # PAAHAKULOGIIKKA
    # ------------------------------------------------------------------

    async def fetch(self) -> AgentResult:
        """Hae saapuvat kaukojunat + kokoonpanotiedot rinnakkain."""
        start_ms = self._now_ms()

        async with httpx.AsyncClient(
            timeout=12.0,
            headers=DT_HEADERS,
        ) as client:
            # 1. Hae kaikki asemat rinnakkain
            station_tasks = [
                self._fetch_station(client, sid, sinfo)
                for sid, sinfo in STATIONS.items()
            ]
            station_results = await asyncio.gather(
                *station_tasks, return_exceptions=True
            )

        # 2. Keraa raakadata asemilta
        raw_trains: list[dict] = []
        total_trains: int = 0

        for sid, result in zip(STATIONS.keys(), station_results):
            if isinstance(result, Exception):
                logger.warning("TrainAgent: asema %s virhe: %s", sid, result)
                continue
            trains_data, count = result
            raw_trains.extend(trains_data)
            total_trains += count

        # 3. Deduploi: sama junanumero voi loytya usealta asemalta
        #    Sailytetaan kaikki - kukin asemapaytys on eri signaali
        #    mutta compositions haetaan vain kerran per junanumero

        # 4. Hae compositions top-3 junalle (lyhimman ETA:n mukaan)
        raw_trains_sorted = sorted(
            raw_trains, key=lambda x: x.get("_eta_minutes", 999)
        )
        top_trains = raw_trains_sorted[:COMPOSITION_FETCH_LIMIT]
        other_trains = raw_trains_sorted[COMPOSITION_FETCH_LIMIT:]

        # Hae compositions asynkronisesti top-junille
        async with httpx.AsyncClient(
            timeout=8.0,
            headers=DT_HEADERS,
        ) as client:
            comp_tasks = [
                self._fetch_composition(
                    client,
                    t["_train_number"],
                    t["_departure_date"],
                )
                for t in top_trains
            ]
            comp_results = await asyncio.gather(
                *comp_tasks, return_exceptions=True
            )

        # Rakenna junanumero -> istumapaikat -hakemisto
        seat_map: dict[str, int] = {}
        for train_data, comp_result in zip(top_trains, comp_results):
            if isinstance(comp_result, Exception):
                logger.debug(
                    "Compositions virhe junalle %s: %s",
                    train_data["_train_number"],
                    comp_result,
                )
                continue
            seats = _parse_seat_count(comp_result)
            if seats:
                seat_map[str(train_data["_train_number"])] = seats
                logger.debug(
                    "Compositions: juna %s = %d paikkaa",
                    train_data["_train_number"],
                    seats,
                )

        # 5. Rakenna signaalit kaikista junista
        signals: list[Signal] = []
        for train_data in raw_trains:
            sig = self._build_signal(train_data, seat_map)
            if sig:
                signals.append(sig)

        elapsed = self._now_ms() - start_ms
        logger.info(
            "TrainAgent: %d junaa -> %d signaalia | compositions: %d/%d | %dms",
            total_trains,
            len(signals),
            len(seat_map),
            len(top_trains),
            elapsed,
        )

        return AgentResult(
            agent_name=self.name,
            status="ok",
            signals=signals,
            raw_data={
                "total_trains": total_trains,
                "signals": len(signals),
                "compositions_fetched": len(seat_map),
            },
            elapsed_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # ASEMAHAKU
    # ------------------------------------------------------------------

    async def _fetch_station(
        self,
        client: httpx.AsyncClient,
        station_id: str,
        station_info: dict,
    ) -> tuple[list[dict], int]:
        """
        Hae yhden aseman saapuvat kaukojunat.
        Palauttaa listan raakadatadikteista joihin on liitetty
        laskettuja apukenttiä (_-prefiksilla).
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

        enriched: list[dict] = []
        long_distance_count = 0

        for train in trains:
            if train.get("trainCategory") not in LONG_DISTANCE_CATEGORIES:
                continue
            long_distance_count += 1

            train_number = train.get("trainNumber", "?")
            train_type = train.get("trainType", "?")

            # Etsi pysahtymisrivi
            arrival_row = self._find_arrival_row(train, station_id)
            if arrival_row is None:
                continue

            scheduled_str = arrival_row.get("scheduledTime", "")
            actual_str = (
                arrival_row.get("liveEstimateTime") or scheduled_str
            )
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
            minutes_away = int(
                (actual_dt - now_utc).total_seconds() / 60
            )

            # Lahtopaivamaara compositions-hakua varten
            dep_date = train.get("departureDate") or datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%d")

            # Liita lasketut aputiedot suoraan diktiin
            train["_station_id"] = station_id
            train["_station_info"] = station_info
            train["_train_number"] = train_number
            train["_train_type"] = train_type
            train["_scheduled_dt"] = scheduled_dt
            train["_actual_dt"] = actual_dt
            train["_delay_min"] = delay_min
            train["_minutes_away"] = minutes_away
            train["_cancelled"] = cancelled
            train["_arrival_time_str"] = actual_dt.strftime("%H:%M")
            train["_origin"] = self._get_origin_station(train)
            train["_departure_date"] = dep_date
            train["_eta_minutes"] = minutes_away  # jarjestelyavain

            enriched.append(train)

        return enriched, long_distance_count

    # ------------------------------------------------------------------
    # COMPOSITION-HAKU
    # ------------------------------------------------------------------

    async def _fetch_composition(
        self,
        client: httpx.AsyncClient,
        train_number: int | str,
        departure_date: str,
    ) -> dict:
        """
        Hae junan kokoonpanotiedot Digitraffic /compositions-rajapinnasta.

        URL: /api/v1/compositions/{departure_date}/{train_number}
        Esim: /api/v1/compositions/2026-04-28/45

        Palauttaa raakavasteen tai heittaa poikkeuksen.
        Ei kaada koko agenttia - virheet lokataan debug-tasolla.
        """
        url = COMPOSITION_URL.format(
            date=departure_date,
            train_number=train_number,
        )
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # SIGNAALIN RAKENTAMINEN
    # ------------------------------------------------------------------

    def _build_signal(
        self,
        train: dict,
        seat_map: dict[str, int],
    ) -> Optional[Signal]:
        """
        Rakenna Signal-objekti rikastetusta junadatasta.

        Prioriteetti matkustajamääralle:
          1. seat_map[train_number]  <- Digitraffic /compositions (tarkin)
          2. _type_capacity(type)    <- Junatyypin oletusarvo (fallback)
        """
        station_id: str = train["_station_id"]
        station_info: dict = train["_station_info"]
        train_number = train["_train_number"]
        train_type: str = train["_train_type"]
        delay_min: int = train["_delay_min"]
        minutes_away: int = train["_minutes_away"]
        cancelled: bool = train["_cancelled"]
        arrival_time_str: str = train["_arrival_time_str"]
        origin: str = train["_origin"]

        # -- Matkustajamäärä: oikea tai arvio --
        seats_real: Optional[int] = seat_map.get(str(train_number))
        seats_est: int = seats_real or _type_capacity(train_type)
        seats_source: str = "oikea" if seats_real else "arvio"

        # -- Pisteet ja urgency --
        score, urgency = self._calculate_score(
            delay_min=delay_min,
            cancelled=cancelled,
            minutes_until_arrival=minutes_away,
            seats=seats_est,
        )

        # -- Kuljettajateksti --
        seats_tag = f"{seats_est} paikkaa ({seats_source})"

        if cancelled:
            reason = (
                f"{train_type}{train_number} {origin} saapuu "
                f"{station_info['name']} {arrival_time_str} - "
                f"PERUUTETTU | {seats_tag}"
            )
        elif delay_min >= DELAY_THRESHOLD_CRITICAL:
            reason = (
                f"{train_type}{train_number} {origin} saapuu "
                f"{station_info['name']} {arrival_time_str} "
                f"(+{delay_min} min myohassa!) | {seats_tag}"
            )
        elif delay_min >= DELAY_THRESHOLD_HIGH:
            reason = (
                f"{train_type}{train_number} {origin} saapuu "
                f"{station_info['name']} {arrival_time_str} "
                f"(+{delay_min} min) | {seats_tag}"
            )
        elif delay_min >= DELAY_THRESHOLD_NORMAL:
            reason = (
                f"{train_type}{train_number} {origin} saapuu "
                f"{station_info['name']} {arrival_time_str} "
                f"(+{delay_min} min) | {seats_tag}"
            )
        else:
            reason = (
                f"{train_type}{train_number} {origin} saapuu "
                f"{station_info['name']} {arrival_time_str} "
                f"({minutes_away} min) | {seats_tag}"
            )

        # Signaali vanhenee kun juna on saapunut (+ 5 min buffer)
        expires_at = train["_actual_dt"] + timedelta(minutes=5)

        return Signal(
            area=station_info["area"],
            score_delta=score,
            reason=reason,
            urgency=urgency,
            expires_at=expires_at,
            source_url=station_info["live_url"],
        )

    # ------------------------------------------------------------------
    # APUMETODIT
    # ------------------------------------------------------------------

    def _find_arrival_row(
        self, train: dict, station_id: str
    ) -> Optional[dict]:
        """Etsi aseman pysahtymisrivi junasta (saapumistiedot)."""
        for row in train.get("timeTableRows", []):
            if (
                row.get("stationShortCode") == station_id
                and row.get("type") == "ARRIVAL"
                and row.get("trainStopping", True) is not False
            ):
                return row
        return None

    def _get_origin_station(self, train: dict) -> str:
        """Palauta junan lahtöaseman nimi lyhytkoodista."""
        rows = train.get("timeTableRows", [])
        if not rows:
            return "?"
        code = rows[0].get("stationShortCode", "?")
        known: dict[str, str] = {
            "OL": "Oulu",
            "RO": "Rovaniemi",
            "RV": "Rovaniemi",
            "TPE": "Tampere",
            "TRE": "Tampere",
            "TL": "Tampere",
            "JY": "Jyvaskyla",
            "KUO": "Kuopio",
            "JNS": "Joensuu",
            "LH": "Lahti",
            "KV": "Kouvola",
            "TUR": "Turku",
            "TKU": "Turku",
            "SM": "Seinajoki",
            "SK": "Seinajoki",
            "VS": "Vaasa",
            "IM": "Imatra",
            "KTA": "Kotka",
            "MKL": "Mikkeli",
            "SLO": "Salo",
            "PMK": "Paimio",
        }
        return known.get(code, code)

    def _calculate_score(
        self,
        delay_min: int,
        cancelled: bool,
        minutes_until_arrival: int,
        seats: int = 350,
    ) -> tuple[float, int]:
        """
        Laske pistemäärä ja kiireellisyystaso.

        Matkustajamäärä vaikuttaa base_scoreen:
          alle 300 paikkaa: 1.0x
          300-499 paikkaa: 1.2x
          500+ paikkaa:    1.5x

        Palauttaa (score_delta: float, urgency: int).
        """
        if cancelled:
            return 7.0, 7

        # Peruspistemäärä myohastymisen mukaan
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

        # Matkustajamäärakerroin
        if seats >= 500:
            seat_multiplier = 1.5
        elif seats >= 300:
            seat_multiplier = 1.2
        else:
            seat_multiplier = 1.0

        base_score *= seat_multiplier

        # Lahestymisbonus
        if minutes_until_arrival <= 10:
            base_score += 2.0
            urgency = min(urgency + 1, 9)
        elif minutes_until_arrival <= 20:
            base_score += 1.0

        return round(base_score, 1), urgency

    @staticmethod
    def _now_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
