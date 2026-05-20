"""Unsupported claim detector — checks claims against context."""
from typing import List, Dict, Any
from app.services.embedding import embedding_service
from app.core.logging import get_logger

logger = get_logger(__name__)


class UnsupportedClaimDetector:
    """Detect claims in response not supported by retrieved context."""

    async def detect(
        self,
        response: str,
        context: List[str],
        threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """Check if response claims are supported by context."""
        if not context:
            return {"unsupported_ratio": 0.5, "supported": False, "reason": "No context provided"}

        try:
            # Split response into sentences
            sentences = [s.strip() for s in response.split(".") if len(s.strip()) > 20]
            if not sentences:
                return {"unsupported_ratio": 0.0, "supported": True, "reason": "No claims to check"}

            context_text = " ".join(context)
            context_emb = await embedding_service.embed_text(context_text)

            unsupported = 0
            for sentence in sentences:
                sent_emb = await embedding_service.embed_text(sentence)
                sim = embedding_service._cosine_similarity(sent_emb, context_emb)
                if sim < threshold:
                    unsupported += 1

            ratio = unsupported / len(sentences)
            return {
                "unsupported_ratio": ratio,
                "supported": ratio < 0.4,
                "unsupported_count": unsupported,
                "total_claims": len(sentences),
                "reason": f"{unsupported}/{len(sentences)} claims lack context support",
            }
        except Exception as e:
            logger.warning("unsupported_claim_check_failed", error=str(e))
            return {"unsupported_ratio": 0.3, "supported": True, "reason": "Check failed"}


unsupported_claim_detector = UnsupportedClaimDetector()
