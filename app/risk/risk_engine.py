"""Risk engine — central risk scoring coordinator."""
from typing import Dict, Any
from app.risk.scoring import score_to_level, should_escalate, combine_scores
from app.risk.fraud_detection import fraud_detector
from app.risk.abuse_detector import abuse_detector
from app.risk.escalation_rules import escalation_rules
from app.governance.pii_detector import pii_detector
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SENSITIVE_KEYWORDS = ["password", "api_key", "secret", "token", "credential", "private_key"]


class RiskEngine:
    """Comprehensive risk scoring engine."""

    async def score(
        self,
        text: str,
        user_id: str,
        organization_id: str,
    ) -> Dict[str, Any]:
        """
        Score request risk.
        Returns: {risk_score, escalate, risk_category, reason}
        """
        component_scores: Dict[str, float] = {}

        # Fraud detection
        fraud = fraud_detector.detect(text)
        component_scores["fraud"] = fraud["score"]

        # Abuse detection
        abuse = await abuse_detector.check(user_id)
        component_scores["abuse"] = abuse["score"]

        # PII risk
        pii = pii_detector.detect(text)
        pii_score = min(100.0, len(pii) * 25.0)
        component_scores["pii"] = pii_score

        # Data leakage
        lower = text.lower()
        leakage_hits = sum(1 for kw in SENSITIVE_KEYWORDS if kw in lower)
        component_scores["leakage"] = min(100.0, leakage_hits * 30.0)

        # Combine
        overall_score = combine_scores(component_scores)
        risk_level = score_to_level(overall_score)
        escalate = should_escalate(overall_score)

        # Check escalation rules
        esc_result = escalation_rules.should_escalate({
            "risk_score": overall_score,
            "fraud_score": fraud["score"],
            "jailbreak_detected": False,
        })
        if esc_result["escalate"]:
            escalate = True

        reason = self._build_reason(component_scores, fraud, abuse, pii)

        logger.info(
            "risk_scored",
            score=overall_score,
            level=risk_level,
            escalate=escalate,
        )

        return {
            "risk_score": round(overall_score, 2),
            "escalate": escalate,
            "risk_category": risk_level,
            "reason": reason,
            "component_scores": component_scores,
        }

    def _build_reason(self, scores, fraud, abuse, pii) -> str:
        parts = []
        if scores.get("fraud", 0) > 0:
            parts.append(f"fraud indicators ({fraud['triggered_patterns'][:2]})")
        if scores.get("abuse", 0) > 50:
            parts.append("abuse pattern detected")
        if pii:
            parts.append(f"PII detected: {list(pii.keys())}")
        if scores.get("leakage", 0) > 0:
            parts.append("sensitive data keywords")
        return "; ".join(parts) if parts else "no significant risk"


risk_engine = RiskEngine()
