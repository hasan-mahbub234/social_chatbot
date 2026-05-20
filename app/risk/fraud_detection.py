"""Fraud detection patterns."""
import re
from typing import Dict, List
from app.core.logging import get_logger

logger = get_logger(__name__)

FRAUD_PATTERNS = [
    r"wire transfer",
    r"send money",
    r"bitcoin|crypto payment",
    r"gift card",
    r"western union",
    r"money gram",
    r"urgent transfer",
    r"lottery winner",
    r"inheritance claim",
    r"advance fee",
    r"nigerian prince",
    r"verify your (account|bank|card)",
    r"click (here|this link) to (verify|confirm|update)",
]


class FraudDetector:
    """Detect fraud-related patterns in text."""

    def detect(self, text: str) -> Dict[str, any]:
        lower = text.lower()
        triggered: List[str] = []

        for pattern in FRAUD_PATTERNS:
            if re.search(pattern, lower):
                triggered.append(pattern)

        score = min(100.0, len(triggered) * 25.0)
        return {
            "is_fraud_risk": bool(triggered),
            "score": score,
            "triggered_patterns": triggered,
            "risk_level": "high" if score >= 50 else ("medium" if score > 0 else "low"),
        }


fraud_detector = FraudDetector()
