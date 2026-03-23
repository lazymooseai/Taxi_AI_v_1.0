# demand_model.py -- Helsinki Taxi AI
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DemandFeatures:
    hour: int = 0
    weekday: int = 0
    temperature: float = 10.0
    is_raining: bool = False
    active_events: int = 0
    train_arrivals: int = 0
    flight_arrivals: int = 0
    disruption_level: int = 0


@dataclass
class DemandPrediction:
    score: float = 0.0
    confidence: float = 0.0
    features_used: list[str] = field(default_factory=list)


class DemandModel:
    def predict(self, features: DemandFeatures) -> DemandPrediction:
        score = 5.0
        if 7 <= features.hour <= 9:
            score += 2.0
        elif 16 <= features.hour <= 18:
            score += 2.5
        elif features.hour >= 22 or features.hour <= 2:
            score += 1.5
        if features.weekday >= 5:
            score += 1.0
        if features.is_raining:
            score += 2.0
        if features.temperature < -5:
            score += 1.5
        elif features.temperature < 0:
            score += 1.0
        score += features.active_events * 1.5
        score += features.train_arrivals * 0.3
        score += features.flight_arrivals * 0.5
        score += features.disruption_level * 2.0
        return DemandPrediction(
            score=round(min(score, 10.0), 2),
            confidence=0.6,
            features_used=["hour", "weekday", "temperature", "is_raining", "active_events"],
        )


_model: Optional[DemandModel] = None


def get_demand_model() -> DemandModel:
    global _model
    if _model is None:
        _model = DemandModel()
    return _model
