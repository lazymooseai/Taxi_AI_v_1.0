"""
ceo.py - TaxiCEOAgent - Orkestraattori v2.0
Helsinki Taxi AI

Keraa kaikkien agenttien signaalit asyncio.gather:lla,
laskee aluepisteet kuljettajan painoilla ja palauttaa
3 dynaamista korttia dashboardille.

Kortti #1 PUNAINEN  = OVERRIDE hairio TAI korkein pisteytys
Kortti #2 KULTA     = toiseksi korkein
Kortti #3 SININEN   = AINA ennakoiva (seuraava iso piikki)

v2.0: OCRDispatchAgent integroitu, Signal-kenttayhteensopivuus
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal
from src.taxiapp.areas import AREAS, Area
from src.taxiapp.location import (
    apply_location_bonus,
    get_location_bonuses,
    enrich_blue_card_reason,
    get_train_area_priority,
)

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS: dict[str, float] = {
    "weight_trains":    1.0,
    "weight_flights":   1.0,
    "weight_ferries":   1.0,
    "weight_events":    1.0,
    "weight_weather":   1.0,
    "weight_nightlife": 1.0,
    "weight_sports":    1.0,
    "weight_business":  1.0,
    "weight_dispatch":  1.5,
}

AGENT_WEIGHT_MAP: dict[str, str] = {
    "TrainAgent":        "weight_trains",
    "FlightAgent":       "weight_flights",
    "FerryAgent":        "weight_ferries",
    "EventsAgent":       "weight_events",
    "WeatherAgent":      "weight_weather",
    "SocialMediaAgent":  "weight_weather",
    "DisruptionAgent":   "weight_trains",
    "OCRDispatchAgent":  "weight_dispatch",
}

CATEGORY_WEIGHT_MAP: dict[str, str] = {
    "trains":    "weight_trains",
    "airport":   "weight_flights",
    "ferries":   "weight_ferries",
    "concerts":  "weight_events",
    "culture":   "weight_events",
    "sports":    "weight_sports",
    "nightlife": "weight_nightlife",
    "business":  "weight_business",
    "dispatch":  "weight_dispatch",
}

OVERRIDE_URGENCY = 9
BLUE_LOOKAHEAD_MINUTES = 60


@dataclass
class Hotspot:
    rank:       int
    area:       str
    score:      float
    urgency:    int
    reasons:    list[str]
    signals:    list[Signal]
    card_color: str
    predictive: bool
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def area_obj(self) -> Optional[Area]:
        return AREAS.get(self.area)

    @property
    def top_reason(self) -> str:
        return self.reasons[0] if self.reasons else f"Alue: {self.area}"

    @property
    def is_override(self) -> bool:
        return self.urgency >= OVERRIDE_URGENCY

    def to_dict(self) -> dict:
        return {
            "rank": self.rank, "area": self.area,
            "score": round(self.score, 1), "urgency": self.urgency,
            "reasons": self.reasons[:3], "card_color": self.card_color,
            "predictive": self.predictive,
            "lat": self.area_obj.lat if self.area_obj else None,
            "lon": self.area_obj.lon if self.area_obj else None,
            "created_at": self.created_at.isoformat(),
        }


class TaxiCEOAgent:
    def __init__(
        self,
        agents: list[BaseAgent],
        weights: Optional[dict[str, float]] = None,
        driver_id: Optional[str] = None,
        location: Optional[tuple[float, float]] = None,
    ):
        self.agents = agents
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self.driver_id = driver_id
        self.location = location
        self.logger = logging.getLogger("taxiapp.ceo")

    async def run(self) -> tuple[list[Hotspot], list[AgentResult]]:
        try:
            from src.taxiapp.location import get_driver_location
            live_loc = get_driver_location()
            if live_loc:
                self.location = live_loc
        except Exception:
            pass

        results = await asyncio.gather(
            *[agent.fetch_with_cache() for agent in self.agents],
            return_exceptions=True,
        )

        agent_results: list[AgentResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent_name = self.agents[i].name if i < len(self.agents) else "?"
                self.logger.error("CEO: agentti %s kaatui: %s", agent_name, result)
                agent_results.append(AgentResult(
                    agent_name=agent_name, status="error",
                    error_msg=str(result),
                ))
            elif isinstance(result, AgentResult):
                agent_results.append(result)

        area_scores, area_signals = self._aggregate_signals(agent_results)
        area_scores = apply_location_bonus(area_scores, self.location)
        hotspots = self._build_hotspots(area_scores, area_signals)

        if self.driver_id:
            self._save_snapshot(hotspots)

        self.logger.info(
            "CEO: %d agenttia | %d signaalia | 3 korttia -> %s",
            len(agent_results),
            sum(len(r.signals) for r in agent_results),
            [h.area for h in hotspots],
        )
        return hotspots, agent_results

    def _aggregate_signals(
        self, results: list[AgentResult],
    ) -> tuple[dict[str, float], dict[str, list[Signal]]]:
        area_scores: dict[str, float] = {}
        area_signals: dict[str, list[Signal]] = {}

        for area_name, area in AREAS.items():
            area_scores[area_name] = area.base_score
            area_signals[area_name] = []

        for result in results:
            if result.status in ("error", "disabled"):
                continue
            agent_weight = self._get_agent_weight(result.agent_name)
            for sig in result.valid_signals:
                if sig.area not in AREAS:
                    continue
                area_obj = AREAS[sig.area]
                category_weight = self._get_category_weight(area_obj)
                combined_weight = agent_weight * category_weight
                urgency_multiplier = self._urgency_multiplier(sig.urgency)
                weighted_score = sig.score_delta * combined_weight * urgency_multiplier
                area_scores[sig.area] = area_scores.get(sig.area, 0) + weighted_score
                area_signals[sig.area].append(sig)

        return area_scores, area_signals

    def _get_agent_weight(self, agent_name: str) -> float:
        weight_key = AGENT_WEIGHT_MAP.get(agent_name)
        if weight_key:
            return self.weights.get(weight_key, 1.0)
        return 1.0

    def _get_category_weight(self, area: Area) -> float:
        if not area.categories:
            return 1.0
        weights = []
        for cat in area.categories:
            key = CATEGORY_WEIGHT_MAP.get(cat)
            if key:
                weights.append(self.weights.get(key, 1.0))
        return max(weights) if weights else 1.0

    def _urgency_multiplier(self, urgency: int) -> float:
        if urgency >= 9:  return 3.0
        if urgency >= 7:  return 2.0
        if urgency >= 5:  return 1.5
        if urgency >= 3:  return 1.2
        return 1.0

    def _build_hotspots(
        self,
        area_scores: dict[str, float],
        area_signals: dict[str, list[Signal]],
    ) -> list[Hotspot]:
        ranked = sorted(
            [(a, s) for a, s in area_scores.items() if a in AREAS],
            key=lambda x: x[1], reverse=True,
        )
        override_area = self._find_override(area_signals)
        card1_area = override_area or (ranked[0][0] if ranked else "Rautatieasema")
        card1 = self._make_hotspot(1, card1_area, area_scores.get(card1_area, 0),
            area_signals.get(card1_area, []), "red", False)

        card2_area = None
        for area, _ in ranked:
            if area != card1_area:
                card2_area = area
                break
        if not card2_area:
            card2_area = ranked[1][0] if len(ranked) > 1 else "Kamppi"
        card2 = self._make_hotspot(2, card2_area, area_scores.get(card2_area, 0),
            area_signals.get(card2_area, []), "gold", False)

        blue_area = self._find_predictive(area_scores, area_signals, {card1_area, card2_area})
        card3 = self._make_hotspot(3, blue_area, area_scores.get(blue_area, 0),
            area_signals.get(blue_area, []), "blue", True)

        return [card1, card2, card3]

    def _find_override(self, area_signals: dict[str, list[Signal]]) -> Optional[str]:
        best_area: Optional[str] = None
        best_urgency: int = OVERRIDE_URGENCY - 1
        for area, signals in area_signals.items():
            for sig in signals:
                if sig.urgency >= OVERRIDE_URGENCY and sig.urgency > best_urgency:
                    best_urgency = sig.urgency
                    best_area = area
        return best_area

    def _find_predictive(
        self, area_scores: dict[str, float],
        area_signals: dict[str, list[Signal]], exclude: set[str],
    ) -> str:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(minutes=BLUE_LOOKAHEAD_MINUTES)
        horizon = now + timedelta(minutes=5)
        future_scores: dict[str, float] = {}
        for area, signals in area_signals.items():
            if area in exclude:
                continue
            future = sum(
                sig.score_delta for sig in signals
                if sig.expires_at > horizon and sig.expires_at <= cutoff
            )
            if future > 0:
                future_scores[area] = future
        if future_scores:
            return max(future_scores, key=future_scores.get)
        for area, _ in sorted(area_scores.items(), key=lambda x: x[1], reverse=True):
            if area not in exclude and area in AREAS:
                return area
        return "Lentokentta"

    def _make_hotspot(
        self, rank: int, area: str, score: float,
        signals: list[Signal], card_color: str, predictive: bool,
    ) -> Hotspot:
        sorted_sigs = sorted(signals, key=lambda s: s.urgency, reverse=True)
        top_urgency = sorted_sigs[0].urgency if sorted_sigs else 1
        reasons = [sig.reason for sig in sorted_sigs[:3]]
        if not reasons:
            area_obj = AREAS.get(area)
            if area_obj:
                cats = ", ".join(area_obj.categories[:2])
                reasons = [f"{area} - {cats}"]
            else:
                reasons = [f"{area}"]
        if card_color == "blue" and self.location:
            loc_reason = enrich_blue_card_reason(area, self.location)
            if loc_reason and loc_reason not in reasons:
                reasons = [loc_reason] + reasons[:2]
        return Hotspot(
            rank=rank, area=area, score=round(score, 1),
            urgency=top_urgency, reasons=reasons,
            signals=sorted_sigs, card_color=card_color,
            predictive=predictive,
        )

    def _save_snapshot(self, hotspots: list[Hotspot]) -> None:
        try:
            from src.taxiapp.repository.database import HotspotRepo
            rows = [{"rank": h.rank, "area": h.area, "score": h.score,
                     "reasons": h.reasons, "urgency": h.urgency}
                    for h in hotspots]
            HotspotRepo.save_snapshot(self.driver_id, rows)
        except Exception:
            pass

    def agent_summary(self, results: list[AgentResult]) -> list[dict]:
        return [
            {"name": r.agent_name, "status": r.status,
             "signals": len(r.signals), "summary": r.summary(),
             "duration": round(r.fetch_duration_ms or 0, 0)}
            for r in results
        ]


def build_agents() -> list[BaseAgent]:
    agents: list[BaseAgent] = []
    agent_classes = [
        ("src.taxiapp.agents.disruptions", "DisruptionAgent"),
        ("src.taxiapp.agents.weather",     "WeatherAgent"),
        ("src.taxiapp.agents.trains",      "TrainAgent"),
        ("src.taxiapp.agents.flights",     "FlightAgent"),
        ("src.taxiapp.agents.ferries",     "FerryAgent"),
        ("src.taxiapp.agents.events",      "EventsAgent"),
        ("src.taxiapp.agents.social_media","SocialMediaAgent"),
        ("src.taxiapp.agents.ocr_dispatch","OCRDispatchAgent"),
    ]
    for module_path, class_name in agent_classes:
        try:
            import importlib
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            agents.append(cls())
            logger.debug("Agentti ladattu: %s", class_name)
        except Exception as ex:
            logger.warning("Agentin lataus epaonnistui %s: %s", class_name, ex)
    logger.info("Agentit: %d/%d ladattu", len(agents), len(agent_classes))
    return agents


def build_ceo(
    driver_id: Optional[str] = None,
    weights: Optional[dict] = None,
    agents: Optional[list[BaseAgent]] = None,
    location: Optional[tuple[float, float]] = None,
) -> TaxiCEOAgent:
    if agents is None:
        agents = build_agents()
    return TaxiCEOAgent(agents=agents, weights=weights,
                        driver_id=driver_id, location=location)
