"""Risk assessment and governance service."""
from app.core.redis_client import redis_client
from app.core.config import settings
import re
import logging
from typing import Dict, List, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


class RiskAssessmentService:
    """Service for risk assessment and governance."""

    def __init__(self):
        self.pii_patterns = {
            "email": r"[\w\.-]+@[\w\.-]+\.\w+",
            "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
            "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        }

    async def assess_cost_risk(
        self,
        organization_id: str,
        tokens_used: int,
        cost: float,
        model: str,
    ) -> Dict[str, any]:
        """Assess cost risk for request."""
        try:
            risk_level = "low"
            findings = []
            recommended_actions = []

            # Check if cost exceeds maximum per request
            if cost > settings.MAX_COST_PER_REQUEST:
                risk_level = "high"
                findings.append(
                    f"Cost ${cost:.2f} exceeds max per request ${settings.MAX_COST_PER_REQUEST}"
                )
                recommended_actions.append("Reduce max_tokens or use cheaper model")

            # Check monthly budget
            org_key = f"org_cost:{organization_id}:month"
            monthly_cost = await redis_client.get(org_key)
            if monthly_cost:
                monthly_total = float(monthly_cost) + cost
                if monthly_total > settings.MAX_COST_PER_REQUEST * 1000:  # Arbitrary threshold
                    if risk_level != "high":
                        risk_level = "medium"
                    findings.append(f"Monthly cost approaching budget limit")
                    recommended_actions.append("Review usage patterns")

            # Calculate risk score (0-100)
            risk_score = min(100, (cost / settings.MAX_COST_PER_REQUEST) * 100)

            return {
                "risk_level": risk_level,
                "score": risk_score,
                "findings": findings,
                "recommended_actions": recommended_actions,
                "is_escalated": risk_level in ["high", "critical"],
            }
        except Exception as e:
            logger.error(f"Error assessing cost risk: {e}")
            return {
                "risk_level": "medium",
                "score": 50,
                "findings": [str(e)],
                "recommended_actions": ["Review manually"],
                "is_escalated": True,
            }

    async def detect_pii(self, text: str) -> Dict[str, List[str]]:
        """Detect PII in text."""
        findings = {}
        try:
            for pii_type, pattern in self.pii_patterns.items():
                matches = re.findall(pattern, text)
                if matches:
                    findings[pii_type] = matches

            return findings
        except Exception as e:
            logger.error(f"Error detecting PII: {e}")
            return {}

    async def assess_pii_risk(self, text: str) -> Dict[str, any]:
        """Assess PII exposure risk."""
        try:
            pii_findings = await self.detect_pii(text)

            if not pii_findings:
                return {
                    "risk_level": "low",
                    "score": 0,
                    "findings": [],
                    "recommended_actions": [],
                    "is_escalated": False,
                }

            risk_level = "medium" if len(pii_findings) <= 2 else "high"
            risk_score = min(100, len(pii_findings) * 25)

            findings = [
                f"Found {len(matches)} instances of {pii_type}"
                for pii_type, matches in pii_findings.items()
            ]

            return {
                "risk_level": risk_level,
                "score": risk_score,
                "findings": findings,
                "pii_detected": pii_findings,
                "recommended_actions": [
                    "Review data before sending",
                    "Enable output filtering",
                ],
                "is_escalated": risk_level == "high",
            }
        except Exception as e:
            logger.error(f"Error assessing PII risk: {e}")
            return {
                "risk_level": "medium",
                "score": 50,
                "findings": [str(e)],
                "recommended_actions": ["Review manually"],
                "is_escalated": True,
            }

    async def assess_data_leakage_risk(self, text: str) -> Dict[str, any]:
        """Assess risk of data leakage."""
        try:
            # Check for sensitive keywords
            sensitive_keywords = [
                "password",
                "api_key",
                "secret",
                "token",
                "credential",
            ]
            found_keywords = [
                kw for kw in sensitive_keywords if kw.lower() in text.lower()
            ]

            if not found_keywords:
                return {
                    "risk_level": "low",
                    "score": 0,
                    "findings": [],
                    "recommended_actions": [],
                    "is_escalated": False,
                }

            risk_level = "high" if len(found_keywords) > 0 else "low"
            risk_score = min(100, len(found_keywords) * 20)

            return {
                "risk_level": risk_level,
                "score": risk_score,
                "findings": [
                    f"Potential sensitive keyword: {kw}" for kw in found_keywords
                ],
                "recommended_actions": [
                    "Remove sensitive information",
                    "Use data masking",
                ],
                "is_escalated": risk_level == "high",
            }
        except Exception as e:
            logger.error(f"Error assessing data leakage risk: {e}")
            return {
                "risk_level": "medium",
                "score": 50,
                "findings": [str(e)],
                "recommended_actions": ["Review manually"],
                "is_escalated": True,
            }

    async def comprehensive_risk_assessment(
        self,
        organization_id: str,
        user_input: str,
        ai_response: str,
        tokens_used: int,
        cost: float,
        model: str,
    ) -> Dict[str, any]:
        """Perform comprehensive risk assessment."""
        assessments = []

        # Cost risk
        cost_risk = await self.assess_cost_risk(
            organization_id, tokens_used, cost, model
        )
        assessments.append(("cost", cost_risk))

        # Input PII risk
        input_pii_risk = await self.assess_pii_risk(user_input)
        assessments.append(("input_pii", input_pii_risk))

        # Output PII risk
        output_pii_risk = await self.assess_pii_risk(ai_response)
        assessments.append(("output_pii", output_pii_risk))

        # Data leakage risk
        leakage_risk = await self.assess_data_leakage_risk(ai_response)
        assessments.append(("data_leakage", leakage_risk))

        # Determine overall risk level
        risk_levels = ["low", "medium", "high", "critical"]
        max_risk_idx = max(
            risk_levels.index(assessment[1]["risk_level"]) for assessment in assessments
        )
        overall_risk = risk_levels[max_risk_idx]

        # Check if escalation needed
        is_escalated = any(assessment[1]["is_escalated"] for assessment in assessments)

        return {
            "overall_risk_level": overall_risk,
            "is_escalated": is_escalated,
            "assessments": {name: data for name, data in assessments},
        }


# Global risk assessment service instance
risk_assessment_service = RiskAssessmentService()
