"""Hallucination validator — main validation coordinator."""
from typing import List, Dict, Any, Optional
from app.hallucination.contradiction_checker import contradiction_checker
from app.hallucination.confidence_scorer import confidence_scorer
from app.hallucination.unsupported_claim_detector import unsupported_claim_detector
from app.core.logging import get_logger

logger = get_logger(__name__)


class HallucinationValidator:
    """Validate AI responses for hallucinations."""

    async def validate(
        self,
        query: str,
        response: str,
        context: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run full hallucination validation pipeline.
        Returns score 0-100 (higher = more likely hallucination).
        """
        context = context or []
        findings = []
        score = 0.0

        # 1. Contradiction check
        contradiction_score = contradiction_checker.check(response)
        if context:
            ctx_contradiction = contradiction_checker.check_against_context(response, context)
            contradiction_score = max(contradiction_score, ctx_contradiction)
        if contradiction_score > 0.4:
            findings.append(f"Contradiction detected (score: {contradiction_score:.2f})")
            score += contradiction_score * 30

        # 2. Confidence scoring
        confidence = await confidence_scorer.score(query, response)
        if confidence < 0.5:
            findings.append(f"Low semantic relevance to query (confidence: {confidence:.2f})")
            score += (1 - confidence) * 30

        # 3. Unsupported claims
        if context:
            claim_result = await unsupported_claim_detector.detect(response, context)
            if not claim_result["supported"]:
                findings.append(claim_result["reason"])
                score += claim_result["unsupported_ratio"] * 40

        # Normalize to 0-100
        hallucination_score = min(100.0, score)

        if hallucination_score > 75:
            risk_level = "high"
        elif hallucination_score > 50:
            risk_level = "medium"
        elif hallucination_score > 25:
            risk_level = "low"
        else:
            risk_level = "minimal"

        result = {
            "hallucination_score": round(hallucination_score, 2),
            "risk_level": risk_level,
            "findings": findings,
            "is_hallucination_likely": hallucination_score > 60,
            "confidence": round(confidence, 2),
            "recommended_actions": self._recommendations(risk_level),
        }

        logger.info("hallucination_validated", score=hallucination_score, level=risk_level)
        return result

    def _recommendations(self, risk_level: str) -> List[str]:
        return {
            "high": ["Regenerate response", "Escalate for review", "Request with citations"],
            "medium": ["Verify key claims", "Request sources"],
            "low": ["Minor verification recommended"],
            "minimal": ["Response appears reliable"],
        }.get(risk_level, [])


hallucination_validator = HallucinationValidator()
