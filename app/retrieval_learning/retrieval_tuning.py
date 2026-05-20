"""
Retrieval Tuner — analyzes failure patterns and suggests parameter adjustments.

Reads from failed_query_tracker and feedback_loop to recommend:
  - threshold adjustments (too strict = no results)
  - top_k adjustments (too few = missing context)
  - BM25 weight adjustments
  - query expansion improvements
"""
from typing import Any, Dict
from app.core.logging import get_logger

logger = get_logger(__name__)

# Thresholds for auto-tuning recommendations
NO_RESULT_RATE_THRESHOLD = 0.10     # > 10% no-result queries = threshold too strict
LOW_SIMILARITY_THRESHOLD = 0.50     # avg top similarity < 0.5 = poor embedding match
HIGH_ESCALATION_THRESHOLD = 0.15    # > 15% escalation = retrieval quality issue


class RetrievalTuner:
    """Analyze retrieval metrics and suggest parameter improvements."""

    async def get_recommendations(self) -> Dict[str, Any]:
        """
        Analyze current retrieval metrics and return tuning recommendations.
        Called periodically (e.g. daily) or on-demand via admin API.
        """
        from app.retrieval_learning.failed_queries import failed_query_tracker
        from app.retrieval_learning.feedback_loop import feedback_loop
        from app.observability.retrieval_observability import retrieval_observability

        patterns = await failed_query_tracker.get_patterns()
        satisfaction = await feedback_loop.get_satisfaction_rate()
        obs_summary = retrieval_observability.get_summary()

        recommendations = []
        severity = "ok"

        no_result_rate = obs_summary.get("no_result_rate", 0.0)
        avg_similarity = obs_summary.get("avg_top_similarity", 1.0)
        escalation_rate = satisfaction.get("escalation_rate", 0.0)

        # Threshold too strict
        if no_result_rate > NO_RESULT_RATE_THRESHOLD:
            recommendations.append({
                "parameter":    "similarity_threshold",
                "current":      0.25,
                "suggested":    0.20,
                "reason":       f"No-result rate {no_result_rate:.1%} exceeds {NO_RESULT_RATE_THRESHOLD:.0%}",
                "action":       "lower_threshold",
            })
            severity = "warning"

        # Poor embedding match
        if avg_similarity < LOW_SIMILARITY_THRESHOLD and obs_summary.get("total_queries", 0) > 10:
            recommendations.append({
                "parameter":    "embedding_model",
                "current":      "current",
                "suggested":    "re-ingest with contextual embeddings",
                "reason":       f"Avg top similarity {avg_similarity:.2f} is low",
                "action":       "reingest_content",
            })
            severity = "warning"

        # High escalation
        if escalation_rate > HIGH_ESCALATION_THRESHOLD:
            recommendations.append({
                "parameter":    "top_k",
                "current":      6,
                "suggested":    8,
                "reason":       f"Escalation rate {escalation_rate:.1%} suggests insufficient context",
                "action":       "increase_top_k",
            })
            severity = "warning"

        # BM25 not contributing
        bm25_rate = obs_summary.get("bm25_hit_rate", 0.0)
        if bm25_rate < 0.05 and obs_summary.get("total_queries", 0) > 20:
            recommendations.append({
                "parameter":    "bm25_index",
                "current":      "possibly not migrated",
                "suggested":    "run alembic upgrade head",
                "reason":       f"BM25 hit rate {bm25_rate:.1%} — FTS index may not be applied",
                "action":       "apply_migration_004",
            })
            severity = "critical"

        return {
            "severity":        severity,
            "recommendations": recommendations,
            "metrics_snapshot": {
                "no_result_rate":   no_result_rate,
                "avg_similarity":   avg_similarity,
                "escalation_rate":  escalation_rate,
                "bm25_hit_rate":    bm25_rate,
                "total_failures":   patterns.get("total_failures", 0),
            },
        }


retrieval_tuner = RetrievalTuner()
