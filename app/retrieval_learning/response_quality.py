"""Response quality tracker — scores response quality based on retrieval signals."""
import json
import time
from typing import Any, Dict, List
from app.core.logging import get_logger

logger = get_logger(__name__)

QUALITY_KEY = "retrieval_learning:response_quality"
QUALITY_TTL = 86400 * 14
MAX_ENTRIES = 500


class ResponseQualityTracker:
    """
    Track response quality signals to identify systematic issues.

    Quality signals:
      - had_rag_context: did retrieval return anything?
      - hallucination_detected: did hallucination validator flag it?
      - response_length: very short = likely "I don't know"
      - user_re_asked: user asked same/similar question again
    """

    async def record(
        self,
        conversation_id: str,
        query: str,
        organization_id: str,
        had_rag_context: bool,
        hallucination_detected: bool,
        response_length: int,
        retrieval_count: int,
        top_similarity: float,
    ) -> None:
        """Record a response quality event."""
        try:
            from app.core.redis_client import redis_client
            # Infer quality score
            quality_score = self._score(
                had_rag_context, hallucination_detected, response_length, retrieval_count
            )
            entry = {
                "conversation_id":      conversation_id,
                "query":                query[:150],
                "org_id":               organization_id,
                "had_rag_context":      had_rag_context,
                "hallucination":        hallucination_detected,
                "response_length":      response_length,
                "retrieval_count":      retrieval_count,
                "top_similarity":       round(top_similarity, 3),
                "quality_score":        quality_score,
                "timestamp":            time.time(),
            }
            raw = await redis_client.get(QUALITY_KEY)
            entries: List[Dict] = json.loads(raw) if raw else []
            entries.append(entry)
            if len(entries) > MAX_ENTRIES:
                entries = entries[-MAX_ENTRIES:]
            await redis_client.set(QUALITY_KEY, json.dumps(entries), ex=QUALITY_TTL)
        except Exception as e:
            logger.warning("quality_record_error", error=str(e))

    def _score(
        self,
        had_context: bool,
        hallucination: bool,
        response_length: int,
        retrieval_count: int,
    ) -> float:
        score = 1.0
        if not had_context:
            score -= 0.4
        if hallucination:
            score -= 0.5
        if response_length < 50:
            score -= 0.2   # very short = likely "I don't know"
        if retrieval_count == 0:
            score -= 0.3
        return max(0.0, round(score, 2))

    async def get_summary(self) -> Dict[str, Any]:
        """Get response quality summary."""
        try:
            from app.core.redis_client import redis_client
            raw = await redis_client.get(QUALITY_KEY)
            if not raw:
                return {}
            entries = json.loads(raw)
            total = len(entries)
            avg_quality = sum(e.get("quality_score", 0) for e in entries) / max(total, 1)
            no_context = sum(1 for e in entries if not e.get("had_rag_context"))
            hallucinations = sum(1 for e in entries if e.get("hallucination"))
            return {
                "total_responses":      total,
                "avg_quality_score":    round(avg_quality, 3),
                "no_context_rate":      round(no_context / max(total, 1), 3),
                "hallucination_rate":   round(hallucinations / max(total, 1), 3),
            }
        except Exception:
            return {}


response_quality_tracker = ResponseQualityTracker()
