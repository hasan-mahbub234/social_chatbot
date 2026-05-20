"""
Retrieval Observability — tracks RAG quality metrics per organization.

Metrics tracked:
  rag.queries_total              — total retrieval calls
  rag.no_result_queries          — queries that returned 0 chunks
  rag.low_confidence_retrievals  — top similarity < 0.5 (poor match)
  rag.bm25_hits                  — queries where BM25 added results
  rag.reranker_used              — queries that went through cross-encoder
  rag.cache_hits                 — queries served from semantic cache
  rag.hallucinations_total       — hallucinations detected
  rag.hallucinations_no_context  — hallucinations when RAG returned nothing
  rag.hallucinations_with_context— hallucinations despite having RAG context
  rag.result_count               — histogram of result counts
  rag.top_similarity             — histogram of top similarity scores
  rag.latency_ms                 — histogram of retrieval latency

Exposed via GET /api/v1/product/retrieval-health
"""
from typing import Any, Dict
from app.observability.metrics import metrics_collector
from app.core.logging import get_logger

logger = get_logger(__name__)

# Threshold below which a retrieval is considered low-confidence
LOW_CONFIDENCE_THRESHOLD = 0.50


class RetrievalObservability:
    """Track and expose RAG retrieval quality metrics."""

    def record_retrieval(
        self,
        org_id: str,
        query: str,
        result_count: int,
        top_similarity: float,
        used_bm25: bool,
        used_reranker: bool,
        from_cache: bool,
    ) -> None:
        """Record a single retrieval event."""
        metrics_collector.increment_counter("rag.queries_total")
        metrics_collector.record_histogram("rag.result_count", result_count)
        metrics_collector.record_histogram("rag.top_similarity", top_similarity)

        if result_count == 0:
            metrics_collector.increment_counter("rag.no_result_queries")
            logger.warning(
                "rag_no_results",
                org=org_id,
                query=query[:80],
            )

        if top_similarity < LOW_CONFIDENCE_THRESHOLD and result_count > 0:
            metrics_collector.increment_counter("rag.low_confidence_retrievals")

        if used_bm25:
            metrics_collector.increment_counter("rag.bm25_hits")

        if used_reranker:
            metrics_collector.increment_counter("rag.reranker_used")

        if from_cache:
            metrics_collector.increment_counter("rag.cache_hits")

    def record_latency(self, latency_ms: float) -> None:
        """Record retrieval latency separately (called after retrieval completes)."""
        metrics_collector.record_histogram("rag.latency_ms", latency_ms)

    def record_hallucination_vs_retrieval(
        self,
        org_id: str,
        had_rag_context: bool,
        hallucination_detected: bool,
    ) -> None:
        """
        Track whether hallucinations correlate with missing RAG context.

        This is the most important metric for understanding whether your
        retrieval quality is causing hallucinations or whether the LLM
        is hallucinating despite having good context.
        """
        if not hallucination_detected:
            return

        metrics_collector.increment_counter("rag.hallucinations_total")

        if not had_rag_context:
            # Hallucination with no context — retrieval failure
            metrics_collector.increment_counter("rag.hallucinations_no_context")
            logger.warning("hallucination_no_rag_context", org=org_id)
        else:
            # Hallucination despite context — LLM or prompt issue
            metrics_collector.increment_counter("rag.hallucinations_with_context")
            logger.warning("hallucination_despite_context", org=org_id)

    def record_chunk_reuse(self, chunk_id: str) -> None:
        """
        Track which chunks are retrieved most frequently.
        High-reuse chunks are your most valuable content — low-reuse chunks
        may indicate poor chunking or irrelevant content.
        """
        metrics_collector.increment_counter(f"rag.chunk_reuse.{chunk_id[:16]}")

    def get_summary(self) -> Dict[str, Any]:
        """
        Return a dashboard-ready summary of all retrieval quality metrics.
        Exposed via GET /api/v1/product/retrieval-health
        """
        c = metrics_collector.counters
        h = metrics_collector.histograms

        def avg(key: str) -> float:
            vals = h.get(key, [])
            return round(sum(vals) / len(vals), 3) if vals else 0.0

        def pct(key: str, total_key: str = "rag.queries_total") -> float:
            total = c.get(total_key, 0)
            return round(c.get(key, 0) / max(total, 1), 3)

        total = c.get("rag.queries_total", 0)
        hallucinations = c.get("rag.hallucinations_total", 0)

        return {
            "total_queries":                total,
            "no_result_rate":               pct("rag.no_result_queries"),
            "low_confidence_rate":          pct("rag.low_confidence_retrievals"),
            "bm25_hit_rate":                pct("rag.bm25_hits"),
            "reranker_usage_rate":          pct("rag.reranker_used"),
            "cache_hit_rate":               pct("rag.cache_hits"),
            "avg_result_count":             avg("rag.result_count"),
            "avg_top_similarity":           avg("rag.top_similarity"),
            "avg_latency_ms":               avg("rag.latency_ms"),
            "hallucination_rate":           round(hallucinations / max(total, 1), 3),
            "hallucination_no_context_rate": round(
                c.get("rag.hallucinations_no_context", 0) / max(hallucinations, 1), 3
            ),
            "hallucination_with_context_rate": round(
                c.get("rag.hallucinations_with_context", 0) / max(hallucinations, 1), 3
            ),
            "raw_counters": {
                k: v for k, v in c.items() if k.startswith("rag.")
            },
        }


retrieval_observability = RetrievalObservability()
