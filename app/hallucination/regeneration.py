"""Response regeneration on hallucination detection."""
from typing import List, Optional
from app.services.llm import llm_service
from app.core.logging import get_logger

logger = get_logger(__name__)


class RegenerationService:
    """Regenerate responses when hallucination is detected."""

    async def regenerate(
        self,
        query: str,
        context: List[str],
        model: str,
        original_response: Optional[str] = None,
        max_attempts: int = 2,
    ) -> str:
        """Regenerate response with stricter context grounding."""
        context_text = "\n\n".join(context[:5]) if context else ""

        for attempt in range(max_attempts):
            try:
                prompt = (
                    "Answer the following question using ONLY the provided context. "
                    "If the context does not contain enough information, say 'I don't have enough information to answer this accurately.'\n\n"
                    f"Context:\n{context_text}\n\n"
                    f"Question: {query}"
                )
                response = await llm_service.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    temperature=0.3,  # Lower temperature for factual accuracy
                )
                logger.info("response_regenerated", attempt=attempt + 1)
                return response
            except Exception as e:
                logger.error("regeneration_attempt_failed", attempt=attempt + 1, error=str(e))

        return "I don't have enough verified information to answer this question accurately."


regeneration_service = RegenerationService()
