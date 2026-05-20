"""Compliance rules engine."""
from typing import Dict, List, Any
from app.core.logging import get_logger

logger = get_logger(__name__)

# Compliance rule definitions
COMPLIANCE_RULES = [
    {
        "id": "no_financial_advice",
        "name": "No Financial Advice",
        "description": "Agent must not provide specific financial investment advice",
        "keywords": ["invest in", "buy stock", "sell stock", "guaranteed return", "financial advice"],
        "action": "warn",
        "severity": "medium",
    },
    {
        "id": "no_medical_diagnosis",
        "name": "No Medical Diagnosis",
        "description": "Agent must not diagnose medical conditions",
        "keywords": ["you have", "you are diagnosed", "your diagnosis", "take this medication"],
        "action": "warn",
        "severity": "high",
    },
    {
        "id": "no_legal_advice",
        "name": "No Legal Advice",
        "description": "Agent must not provide specific legal advice",
        "keywords": ["you should sue", "file a lawsuit", "legal action against", "your legal rights are"],
        "action": "warn",
        "severity": "medium",
    },
    {
        "id": "gdpr_pii",
        "name": "GDPR PII Protection",
        "description": "Do not process or store PII without consent",
        "keywords": [],  # Handled by PII detector
        "action": "block",
        "severity": "critical",
    },
]


class ComplianceRules:
    """Evaluate requests against compliance rules."""

    def evaluate(self, text: str) -> Dict[str, Any]:
        """Check text against all compliance rules."""
        violations: List[Dict] = []
        lower = text.lower()

        for rule in COMPLIANCE_RULES:
            for kw in rule["keywords"]:
                if kw in lower:
                    violations.append({
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "action": rule["action"],
                        "severity": rule["severity"],
                        "triggered_by": kw,
                    })
                    break

        has_violations = bool(violations)
        should_block = any(v["action"] == "block" for v in violations)

        return {
            "compliant": not has_violations,
            "violations": violations,
            "should_block": should_block,
            "severity": max((v["severity"] for v in violations), default="low",
                            key=lambda s: ["low", "medium", "high", "critical"].index(s)),
        }


compliance_rules = ComplianceRules()
