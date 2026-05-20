"""
Feedback Loop — records explicit user feedback (thumbs up/down, re-asks,
escalations) and correlates with retrieval quality.
"""
import json
import time
from typing import Any, Dict, List
from app.core.logging import get_logger

logger = get_logger(__name__)

FEEDBACK_KEY = "retrieval_learning:feedback"
FEEDBACK_TTL = 86400 * 30  # 30 days
MAX_FEEDBACK = 1000


class FeedbackLoop:
    """Record and analyze user feedback signals."""

    async def record_feedback(
        self,
        conversation_id: str,
        query: str,
        organization_id: str,
        signal: str,        # positive | negative | re_ask | escalated | no_click
        retrieval_count: int = 0,
        top_similarity: float = 0.0,
    ) -> None:
        """Record a feedback signal."""
        try:
            from app.core.redis_client import redis_client
            entry = {
                "conversation_id": conversation_id,
                "query":           query[:200],
                "org_id":          organization_id,
                "signal":          signal,
                "retrieval_count": retrieval_count,
                "top_similarity":  round(top_similarity, 3),
                "timestamp":       time.time(),
            }
            raw = await redis_client.get(FEEDBACK_KEY)
            entries: List[Dict] = json.loads(raw) if raw else []
            entries.append(entry)
            if len(entries) > MAX_FEEDBACK:
                entries = entries[-MAX_FEEDBACK:]
            await redis_client.set(FEEDBACK_KEY, json.dumps(entries), ex=FEEDBACK_TTL)
            logger.info("feedback_recorded", signal=signal, query=query[:40])
        except Exception as e:
            logger.warning("feedback_record_error", error=str(e))

    async def get_satisfaction_rate(self) -> Dict[str, Any]:
        """Calculate satisfaction rate from feedback signals."""
        try:
            from app.core.redis_client import redis_client
            raw = await redis_client.get(FEEDBACK_KEY)
            if not raw:
                return {"rate": 0.0, "total": 0}
            entries = json.loads(raw)
            total = len(entries)
            positive = sum(1 for e in entries if e.get("signal") == "positive")
            negative = sum(1 for e in entries if e.get("signal") in ("negative", "re_ask", "escalated"))
            return {
                "total":          total,
                "positive":       positive,
                "negative":       negative,
                "satisfaction_rate": round(positive / max(total, 1), 3),
                "escalation_rate":   round(
                    sum(1 for e in entries if e.get("signal") == "escalated") / max(total, 1), 3
                ),
            }
        except Exception:
            return {"rate": 0.0, "total": 0}


feedback_loop = FeedbackLoop()
