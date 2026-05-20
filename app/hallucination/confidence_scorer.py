"""Confidence scorer for hallucination detection."""
from typing import List
from app.services.embedding import embedding_service
from app.core.logging import get_logger

logger = get_logger(__name__)

OVERCONFIDENT_PHRASES = ["always", "never", "definitely", "certainly", "absolutely", "guaranteed", "100%"]
HEDGING_PHRASES = ["may be", "could be", "might be", "perhaps", "apparently", "possibly", "I think", "I believe"]


class ConfidenceScorer:
    """Score response confidence and detect overconfidence."""

    async def score(self, query: str, response: str) -> float:
        """Return confidence score 0.0-1.0 (higher = more reliable)."""
        try:
            # Semantic relevance
            q_emb = await embedding_service.embed_text(query)
            r_emb = await embedding_service.embed_text(response)
            relevance = embedding_service._cosine_similarity(q_emb, r_emb)

            # Language quality
            language_score = self._score_language(response)

            # Combined
            return (relevance * 0.6) + (language_score * 0.4)
        except Exception as e:
            logger.warning("confidence_score_failed", error=str(e))
            return 0.5

    def _score_language(self, text: str) -> float:
        """Score based on language patterns."""
        lower = text.lower()
        overconfident = sum(lower.count(p) for p in OVERCONFIDENT_PHRASES)
        hedging = sum(lower.count(p) for p in HEDGING_PHRASES)
        total = overconfident + hedging

        if total == 0:
            return 0.7  # Neutral

        hedge_ratio = hedging / total
        # Ideal: some hedging (0.3-0.7)
        if 0.3 <= hedge_ratio <= 0.7:
            return 0.9
        elif hedge_ratio < 0.3:
            return 0.4  # Too confident
        return 0.5  # Too vague


confidence_scorer = ConfidenceScorer()
