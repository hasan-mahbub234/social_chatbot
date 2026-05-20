"""Escalation rules — configurable thresholds for auto-escalation."""
from typing import Dict, Any
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

ESCALATION_RULES = [
    {"id": "high_risk_score", "condition": "risk_score >= threshold", "threshold": settings.RISK_ESCALATION_THRESHOLD},
    {"id": "critical_fraud", "condition": "fraud_score >= 75"},
    {"id": "jailbreak_attempt", "condition": "jailbreak_detected == True"},
    {"id": "repeated_violations", "condition": "violation_count >= 3"},
    {"id": "high_hallucination", "condition": "hallucination_score >= 75"},
]


class EscalationRules:
    """Evaluate whether a situation requires escalation."""

    def should_escalate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Check all escalation rules against context."""
        triggered = []

        risk_score = context.get("risk_score", 0)
        if risk_score >= settings.RISK_ESCALATION_THRESHOLD:
            triggered.append("high_risk_score")

        if context.get("fraud_score", 0) >= 75:
            triggered.append("critical_fraud")

        if context.get("jailbreak_detected", False):
            triggered.append("jailbreak_attempt")

        if context.get("violation_count", 0) >= 3:
            triggered.append("repeated_violations")

        if context.get("hallucination_score", 0) >= 75:
            triggered.append("high_hallucination")

        escalate = bool(triggered)
        severity = "critical" if "jailbreak_attempt" in triggered else ("high" if escalate else "low")

        return {
            "escalate": escalate,
            "triggered_rules": triggered,
            "severity": severity,
            "reason": f"Triggered: {', '.join(triggered)}" if triggered else "",
        }


escalation_rules = EscalationRules()
