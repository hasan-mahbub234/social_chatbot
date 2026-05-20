"""Risk scoring utilities."""
from typing import Dict
from app.core.constants import RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL
from app.core.config import settings


def score_to_level(score: float) -> str:
    """Convert numeric score (0-100) to risk level string."""
    if score >= 80:
        return RISK_CRITICAL
    elif score >= 60:
        return RISK_HIGH
    elif score >= 30:
        return RISK_MEDIUM
    return RISK_LOW


def should_escalate(score: float) -> bool:
    """Determine if score warrants escalation."""
    return score >= settings.RISK_ESCALATION_THRESHOLD


def combine_scores(scores: Dict[str, float]) -> float:
    """Combine multiple risk scores into a single weighted score."""
    if not scores:
        return 0.0
    weights = {
        "fraud": 0.3,
        "abuse": 0.25,
        "pii": 0.2,
        "leakage": 0.15,
        "cost": 0.1,
    }
    total = 0.0
    weight_sum = 0.0
    for key, score in scores.items():
        w = weights.get(key, 0.1)
        total += score * w
        weight_sum += w
    return min(100.0, total / weight_sum if weight_sum else 0.0)
