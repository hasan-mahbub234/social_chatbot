"""
Failed Query Tracker — records queries that returned no results or poor results.

Stored in Redis with TTL. Aggregated daily for analysis.
Used by retrieval_tuner to identify systematic retrieval gaps.
"""
import json
import time
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

FAILED_QUERY_TTL = 86400 * 7   # 7 days
FAILED_QUERY_KEY = "retrieval_learning:failed_queries"
MAX_STORED = 500


class FailedQueryTracker:
    """Track queries that failed to retrieve useful results."""

    async def record(
        self,
        query: str,
        organization_id: str,
        result_count: int,
        top_similarity: float,
        intent: str = "general",
        reason: str = "no_results",
    ) -> None:
        """Record a failed or poor-quality retrieval."""
        if result_count > 0 and top_similarity >= 0.5:
            return  # Not a failure

        try:
            from app.core.redis_client import redis_client
            entry = {
                "query":           query[:200],
                "org_id":          organization_id,
                "result_count":    result_count,
                "top_similarity":  round(top_similarity, 3),
                "intent":          intent,
                "reason":          reason,
                "timestamp":       time.time(),
            }
            raw = await redis_client.get(FAILED_QUERY_KEY)
            entries: List[Dict] = json.loads(raw) if raw else []
            entries.append(entry)
            if len(entries) > MAX_STORED:
                entries = entries[-MAX_STORED:]
            await redis_client.set(FAILED_QUERY_KEY, json.dumps(entries), ex=FAILED_QUERY_TTL)
            logger.info("failed_query_recorded", query=query[:60], reason=reason)
        except Exception as e:
            logger.warning("failed_query_record_error", error=str(e))

    async def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent failed queries."""
        try:
            from app.core.redis_client import redis_client
            raw = await redis_client.get(FAILED_QUERY_KEY)
            if not raw:
                return []
            entries = json.loads(raw)
            return entries[-limit:]
        except Exception:
            return []

    async def get_patterns(self) -> Dict[str, Any]:
        """Analyze failed query patterns."""
        entries = await self.get_recent(limit=500)
        if not entries:
            return {}

        intent_counts: Dict[str, int] = {}
        reason_counts: Dict[str, int] = {}
        zero_result_queries: List[str] = []

        for e in entries:
            intent_counts[e.get("intent", "unknown")] = intent_counts.get(e.get("intent", "unknown"), 0) + 1
            reason_counts[e.get("reason", "unknown")] = reason_counts.get(e.get("reason", "unknown"), 0) + 1
            if e.get("result_count", 0) == 0:
                zero_result_queries.append(e["query"])

        return {
            "total_failures":     len(entries),
            "by_intent":          intent_counts,
            "by_reason":          reason_counts,
            "zero_result_count":  len(zero_result_queries),
            "zero_result_sample": zero_result_queries[:10],
        }


failed_query_tracker = FailedQueryTracker()
