"""Hallucination detection and validation service."""
from app.services.embedding import embedding_service
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class HallucinationValidator:
    """Service for detecting hallucinations in AI responses."""

    async def validate_response(
        self,
        query: str,
        response: str,
        sources: list = None,
    ) -> Dict[str, any]:
        """Validate AI response for hallucinations."""
        try:
            hallucination_score = 0.0
            findings = []

            # 1. Check for self-contradiction
            contradiction_score = await self._check_self_contradiction(response)
            if contradiction_score > 0.5:
                findings.append("Response contains self-contradictory statements")
                hallucination_score += contradiction_score * 0.3

            # 2. Check semantic coherence with query
            coherence_score = await self._check_query_relevance(query, response)
            if coherence_score < 0.5:
                findings.append("Response has low semantic relevance to query")
                hallucination_score += (1 - coherence_score) * 0.3

            # 3. Check if sources are cited
            citation_score = await self._check_source_citation(response, sources)
            if citation_score < 0.5:
                findings.append("Response lacks proper source citations")
                hallucination_score += (1 - citation_score) * 0.2

            # 4. Check for factual consistency patterns
            factual_score = await self._check_factual_patterns(response)
            if factual_score < 0.5:
                findings.append("Response contains suspicious factual patterns")
                hallucination_score += (1 - factual_score) * 0.2

            # Normalize score to 0-100
            hallucination_score = min(100, hallucination_score * 100)

            # Determine risk level
            if hallucination_score > 75:
                risk_level = "high"
            elif hallucination_score > 50:
                risk_level = "medium"
            elif hallucination_score > 25:
                risk_level = "low"
            else:
                risk_level = "minimal"

            return {
                "hallucination_score": hallucination_score,
                "risk_level": risk_level,
                "findings": findings,
                "is_hallucination_likely": hallucination_score > 60,
                "recommended_actions": self._get_recommendations(risk_level),
            }
        except Exception as e:
            logger.error(f"Error validating response: {e}")
            return {
                "hallucination_score": 50.0,
                "risk_level": "medium",
                "findings": [str(e)],
                "is_hallucination_likely": True,
                "recommended_actions": ["Manual review recommended"],
            }

    async def _check_self_contradiction(self, text: str) -> float:
        """Check for self-contradictory statements."""
        try:
            # Simple heuristic: check for "is" and "is not" patterns
            is_count = text.lower().count(" is ")
            is_not_count = text.lower().count(" is not ")

            # Check for "however", "but" indicating contradiction
            contradiction_indicators = [
                " however, ",
                " but ",
                " although ",
                " whereas ",
            ]
            contradiction_count = sum(
                text.lower().count(indicator) for indicator in contradiction_indicators
            )

            # Calculate score based on contradictory language patterns
            if contradiction_count > 3:
                return 0.7
            elif contradiction_count > 1:
                return 0.4
            else:
                return 0.1
        except Exception as e:
            logger.error(f"Error checking self-contradiction: {e}")
            return 0.0

    async def _check_query_relevance(self, query: str, response: str) -> float:
        """Check semantic relevance between query and response."""
        try:
            # Get embeddings
            query_embedding = await embedding_service.embed_text(query)
            response_embedding = await embedding_service.embed_text(response)

            # Calculate similarity
            similarity = embedding_service._cosine_similarity(
                query_embedding, response_embedding
            )
            return similarity
        except Exception as e:
            logger.error(f"Error checking query relevance: {e}")
            return 0.5

    async def _check_source_citation(
        self, response: str, sources: list = None
    ) -> float:
        """Check if response properly cites sources."""
        try:
            if not sources:
                return 0.3  # No sources provided

            # Check for citation markers
            citation_markers = ["according to", "based on", "from", "source:", "["]
            citation_count = sum(
                response.lower().count(marker) for marker in citation_markers
            )

            if len(sources) == 0:
                return 1.0  # No sources needed

            # Expected citation count should be at least half the sources
            expected_citations = len(sources) * 0.5
            actual_score = min(1.0, citation_count / max(1, expected_citations))

            return actual_score
        except Exception as e:
            logger.error(f"Error checking source citation: {e}")
            return 0.5

    async def _check_factual_patterns(self, text: str) -> float:
        """Check for suspicious factual patterns."""
        try:
            # Check for over-confident language
            overconfident_phrases = [
                "always",
                "never",
                "definitely",
                "certainly",
                "absolutely",
            ]
            overconfident_count = sum(
                text.lower().count(phrase) for phrase in overconfident_phrases
            )

            # Check for vague language (potential hallucination indicator)
            vague_phrases = [
                "may be",
                "could be",
                "might be",
                "perhaps",
                "apparently",
            ]
            vague_count = sum(text.lower().count(phrase) for phrase in vague_phrases)

            # Balanced language is better (some vague + some confident)
            # Too much confidence or too much vagueness is suspicious
            total_confidence_words = overconfident_count + vague_count
            if total_confidence_words == 0:
                return 0.7  # Mostly neutral

            vague_ratio = vague_count / total_confidence_words
            # Ideal ratio is around 0.3-0.7 (some vagueness, some confidence)
            if 0.3 <= vague_ratio <= 0.7:
                return 0.9  # Good balance
            elif 0 < vague_ratio < 0.3:
                return 0.4  # Too confident
            else:
                return 0.5  # Too vague

        except Exception as e:
            logger.error(f"Error checking factual patterns: {e}")
            return 0.5

    @staticmethod
    def _get_recommendations(risk_level: str) -> list:
        """Get recommendations based on risk level."""
        recommendations = {
            "high": [
                "Flag for manual review",
                "Consider requesting with citations",
                "Use fact-checking tools",
            ],
            "medium": [
                "Verify key claims",
                "Request sources",
                "Cross-reference with reliable sources",
            ],
            "low": ["Minor verification recommended"],
            "minimal": ["Response appears reliable"],
        }
        return recommendations.get(risk_level, [])


# Global hallucination validator instance
hallucination_validator = HallucinationValidator()
