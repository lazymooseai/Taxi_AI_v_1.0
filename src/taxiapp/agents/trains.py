"""
trains.py -- TrainAgent v2.2
Helsinki Taxi AI

Korjattu: VR-linkit yksinkertaistettu - ei URL-enkoodausongelmia.
Lahtooasema nakyy kortissa selkeasti.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal

logger = logging.getLogger("taxiapp.TrainAgent")

STATIONS: dict[str, dict] = {
    "HKI": {
        "name": "Helsinki",
        "area": "Rautatieasema",
        "live_url": "https://www.vr.fi/radalla",
    },
    "PSL": {
        "name": "Pasila",
        "area": "Pasila",
        "live_url": "https://www.vr.fi/radalla",
    },
    "TKL": {
        "name": "Tikkurila",
        "area": "Tikkurila",
        "live_url": "https://www.vr.fi/radalla",
    },
}

LONG_DISTANCE = frozenset({"Long-distance"})
DELAY_NORMAL = 5
DELAY_HIGH = 15
DELAY_CRITICAL = 30
LOOKAHEAD = 120

BASE_URL = "https://rata.digitraffic.fi/api/v1/live-trains/station/{station}"

ORIGINS: dict[str, str] = {
    "OL": "Oulu", "RV": "Rovaniemi", "TL": "Tampere",
    "TPE": "Tampere", "JY": "Jyv\u00e4skyl\u00e4", "KUO": "Kuopio",
    "JNS": "Joensuu", "LH": "Lahti", "KV": "Kouvola",
    "TRE": "Tampere", "TUR": "Turku", "SM": "Sein\u00e4joki",
    "VS": "Vaasa", "IM": "Imatra", "KTA": "Kotka",
    "PM": "Pieks\u00e4m\u00e4ki", "KOK": "Kokkola",
    "RI": "Riihim\u00e4ki", "HY": "Hyvink\u00e4\u00e4",
}


class TrainAgent(BaseAgent):
    name = "TrainAgent"
    ttl = 120

    def __init__(self):
        super().__init__(name="TrainAgent")

    async def fetch(self):
        t0 = self._now_ms()
        async with httpx.AsyncClient(timeout=10.0) as c:
            tasks = [self._station(c, sid, si) for sid, si in STATIONS.items()]
            res = await asyncio.gather(*tasks, return_exceptions=True)
        sigs = []
        total = 0
        for sid, r in zip(STATIONS, res):
            if isinstance(r, Exception):
                logger.warning("TrainAgent %s: %s", sid, r)
                continue
            ss, n = r
            sigs.extend(ss)
            total += n
        el = self._now_ms() - t0
        logger.info("TrainAgent: %d junaa -> %d signaalia | %dms", total, len(sigs), el)
        return AgentResult(agent_name=self.name, status="ok", signals=sigs, elapsed_ms=el)

    async def _station(self, client, sid, si):
        url = BASE_URL.format(station=sid)
        params = {"arrived_trains": 0, "arriving_trains": 10,
                  "departed_trains": 0, "departing_trains": 0,
                  "include_nonstopping": "false"}
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        trains = resp.json()
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(minutes=LOOKAHEAD)
        sigs = []
        count = 0
        for tr in trains:
            if tr.get("trainCategory") not in LONG_DISTANCE:
                continue
            count += 1
            tn = tr.get("trainNumber", "?")
            tt = tr.get("trainType", "?")
            ar = self._arrival_row(tr, sid)
            if not ar:
                continue
            sched_s = ar.get("scheduledTime", "")
            actual_s = ar.get("liveEstimateTime") or sched_s
            if not sched_s:
                continue
            try:
                sched = datetime.fromisoformat(sched_s.replace("Z", "+00:00"))
                actual = datetime.fromisoformat(actual_s.replace("Z", "+00:00"))
            except ValueError:
                continue
            if actual < now or actual > cutoff:
                continue
            delay = max(0, int((actual - sched).total_seconds() / 60))
            mins = int((actual - now).total_seconds() / 60)
            score, urg = self._score(delay, ar.get("cancelled", False), mins)
            origin = self._origin(tr)
            hhmm = actual.strftime("%H:%M")
            # Selkea title: "IC 173 Tampere -> Helsinki 23:45"
            title = f"{tt}{tn} {origin} \u2192 {si['name']} {hhmm}"
            if delay >= DELAY_CRITICAL:
                detail = f"+{delay}min my\u00f6h\u00e4ss\u00e4!"
            elif delay >= DELAY_NORMAL:
                detail = f"+{delay}min"
            elif ar.get("cancelled"):
                detail = "PERUUTETTU"
            else:
                detail = f"Saapuu {mins}min"
            sigs.append(Signal(
                area=si["area"], score_delta=score, urgency=urg,
                reason=f"{title} ({detail})",
                expires_at=actual + timedelta(minutes=15),
                source_url=si["live_url"],
                title=title, description=detail,
                agent=self.name, category="trains",
                extra={"train_number": tn, "train_type": tt,
                       "station": sid, "station_name": si["name"],
                       "delay_minutes": delay, "minutes_away": mins,
                       "cancelled": ar.get("cancelled", False),
                       "origin": origin, "arrival_time": hhmm},
            ))
        return sigs, count

    def _arrival_row(self, tr, sid):
        for r in tr.get("timeTableRows", []):
            if (r.get("stationShortCode") == sid
                    and r.get("type") == "ARRIVAL"
                    and r.get("trainStopping") is not False):
                return r
        return None

    def _origin(self, tr):
        rows = tr.get("timeTableRows", [])
        if not rows:
            return "?"
        return ORIGINS.get(rows[0].get("stationShortCode", "?"), rows[0].get("stationShortCode", "?"))

    def _score(self, delay, cancelled, mins):
        if cancelled:
            return 7.0, 7
        if delay >= DELAY_CRITICAL:
            s, u = 6.0, 6
        elif delay >= DELAY_HIGH:
            s, u = 4.5, 4
        elif delay >= DELAY_NORMAL:
            s, u = 3.5, 3
        else:
            s, u = 2.5, 2
        if mins <= 10:
            s += 1.5
            u = min(u + 1, 9)
        elif mins <= 20:
            s += 0.8
        return s, u
