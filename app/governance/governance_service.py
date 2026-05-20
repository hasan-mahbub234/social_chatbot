"""Governance service — orchestrates all governance checks."""
from typing import Dict, Any
from app.governance.pii_detector import pii_detector
from app.governance.jailbreak_detector import jailbreak_detector
from app.governance.moderation import moderation_service
from app.governance.compliance_rules import compliance_rules
from app.core.logging import get_logger

logger = get_logger(__name__)


class GovernanceService:
    """Run all governance checks and return unified result."""

    async def evaluate(self, text: str, organization_id: str = "", advanced: bool = False) -> Dict[str, Any]:
        """
        Run full governance pipeline.
        Returns: {allowed, risk_level, policy_flags, reason, action}
        """
        policy_flags = []
        risk_level = "low"
        action = "allow"
        reason = ""

        # 1. Jailbreak detection
        jailbreak = jailbreak_detector.detect(text)
        if jailbreak["is_jailbreak"]:
            policy_flags.append("jailbreak_detected")
            risk_level = "critical"
            action = "block"
            reason = "Jailbreak attempt detected"
            return self._result(False, risk_level, policy_flags, reason, action)

        # 2. Content moderation
        moderation = moderation_service.moderate(text)
        if not moderation["is_safe"]:
            policy_flags.append("unsafe_content")
            if moderation["severity"] == "critical":
                action = "block"
                risk_level = "critical"
                reason = "Unsafe content detected"
                return self._result(False, risk_level, policy_flags, reason, action)
            else:
                action = "warn"
                risk_level = "high"
                reason = "Potentially unsafe content"

        # 3. PII detection
        pii = pii_detector.detect(text)
        if pii:
            policy_flags.append("pii_detected")
            if risk_level not in ("critical", "high"):
                risk_level = "medium"
            reason = reason or f"PII detected: {list(pii.keys())}"

        # 4. Compliance rules
        compliance = compliance_rules.evaluate(text)
        if not compliance["compliant"]:
            policy_flags.extend([v["rule_id"] for v in compliance["violations"]])
            if compliance["should_block"]:
                action = "block"
                risk_level = "critical"
                reason = reason or "Compliance violation"
                return self._result(False, risk_level, policy_flags, reason, action)
            elif compliance["severity"] in ("high", "critical"):
                action = "warn"
                if risk_level == "low":
                    risk_level = "medium"

        allowed = action != "block"
        logger.info(
            "governance_evaluated",
            allowed=allowed,
            risk_level=risk_level,
            flags=policy_flags,
        )
        return self._result(allowed, risk_level, policy_flags, reason, action)

    def _result(self, allowed: bool, risk_level: str, flags: list, reason: str, action: str) -> Dict:
        return {
            "allowed": allowed,
            "risk_level": risk_level,
            "policy_flags": flags,
            "reason": reason,
            "action": action,
        }


governance_service = GovernanceService()
