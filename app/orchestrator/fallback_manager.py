"""Fallback manager — safe responses for blocked/failed requests."""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.core.logging import get_logger
from app.services.llm import llm_service

logger = get_logger(__name__)

SAFE_FALLBACK_RESPONSE = (
    "I'm unable to process this request at the moment. "
    "Please try rephrasing or contact support if the issue persists."
)

GOVERNANCE_BLOCK_RESPONSE = (
    "This request cannot be processed as it violates our usage policies."
)


class FallbackManager:
    """Handle all failure and escalation fallback scenarios."""

    async def governance_block(self, gov_result: Dict[str, Any]) -> Dict[str, Any]:
        """Return safe response for governance-blocked requests."""
        logger.warning("governance_block_fallback", reason=gov_result.get("reason"))
        return {
            "content": GOVERNANCE_BLOCK_RESPONSE,
            "blocked": True,
            "reason": gov_result.get("reason", "Policy violation"),
            "policy_flags": gov_result.get("policy_flags", []),
            "tokens_used": 0,
            "cost": 0.0,
            "from_cache": False,
        }

    async def risk_escalation(
        self, risk_result: Dict[str, Any], conversation_id: str, db: Session
    ) -> Dict[str, Any]:
        """Create escalation record and return safe response."""
        try:
            from app.models.escalation import Escalation
            escalation = Escalation(
                reason=risk_result.get("reason", "High risk score"),
                severity=risk_result.get("risk_category", "high"),
                status="pending",
                context=risk_result,
            )
            db.add(escalation)
            db.commit()
            escalation_id = str(escalation.id)
        except Exception as e:
            logger.error("escalation_create_failed", error=str(e))
            escalation_id = None

        return {
            "content": "This request has been escalated for review. A team member will follow up.",
            "escalated": True,
            "escalation_id": escalation_id,
            "risk_score": risk_result.get("risk_score", 0),
            "tokens_used": 0,
            "cost": 0.0,
            "from_cache": False,
        }

    async def handle_hallucination(
        self,
        query: str,
        original_response: str,
        context: List[str],
        hallucination_result: Dict[str, Any],
        model: str,
        max_attempts: int = 2,
    ) -> str:
        """Attempt regeneration on hallucination detection."""
        for attempt in range(max_attempts):
            try:
                context_text = "\n\n".join(c[:400] for c in context[:5]) if context else ""
                regen_prompt = (
                    f"Answer strictly based on the following context only:\n\n"
                    f"{context_text}\n\nQuestion: {query}"
                )
                new_response = await llm_service.generate_response(
                    messages=[{"role": "user", "content": regen_prompt}],
                    model=model,
                )
                logger.info("hallucination_regenerated", attempt=attempt + 1)
                return new_response
            except Exception as e:
                logger.error("regeneration_failed", attempt=attempt + 1, error=str(e))

        # Final fallback
        return (
            "I want to ensure accuracy. Based on available information: "
            + original_response
        )

    async def safe_fallback(self, error: str = "") -> Dict[str, Any]:
        """Generic safe fallback for unexpected errors."""
        logger.error("safe_fallback_triggered", error=error)
        return {
            "content": SAFE_FALLBACK_RESPONSE,
            "error": True,
            "tokens_used": 0,
            "cost": 0.0,
            "from_cache": False,
        }


fallback_manager = FallbackManager()
