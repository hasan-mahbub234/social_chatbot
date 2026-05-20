"""Contradiction checker for hallucination detection."""
from typing import List
from app.core.logging import get_logger

logger = get_logger(__name__)

CONTRADICTION_INDICATORS = [" however, ", " but ", " although ", " whereas ", " on the contrary", " yet "]
NEGATION_PAIRS = [(" is ", " is not "), (" can ", " cannot "), (" will ", " will not "), (" does ", " does not ")]


class ContradictionChecker:
    """Detect self-contradictions in text."""

    def check(self, text: str) -> float:
        """Return contradiction score 0.0-1.0."""
        lower = text.lower()
        score = 0.0

        # Count contradiction indicators
        indicator_count = sum(lower.count(ind) for ind in CONTRADICTION_INDICATORS)
        if indicator_count > 3:
            score += 0.5
        elif indicator_count > 1:
            score += 0.25

        # Check negation pairs
        for pos, neg in NEGATION_PAIRS:
            if pos in lower and neg in lower:
                score += 0.15

        return min(1.0, score)

    def check_against_context(self, response: str, context: List[str]) -> float:
        """Check if response contradicts provided context."""
        if not context:
            return 0.0

        response_lower = response.lower()
        contradiction_score = 0.0

        for ctx in context:
            ctx_lower = ctx.lower()
            # Simple heuristic: check for direct negations of context statements
            ctx_words = set(ctx_lower.split())
            resp_words = set(response_lower.split())
            overlap = len(ctx_words & resp_words) / max(len(ctx_words), 1)
            if overlap < 0.1 and len(ctx) > 50:
                contradiction_score += 0.1

        return min(1.0, contradiction_score)


contradiction_checker = ContradictionChecker()
