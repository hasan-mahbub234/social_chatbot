"""
RAG Evaluator — measures retrieval quality against gold-standard queries.

Metrics:
  - Recall@K: did the correct chunk appear in top-K results?
  - MRR (Mean Reciprocal Rank): how high did the correct chunk rank?
  - Precision@K: what fraction of top-K results were relevant?
  - No-result rate: how often did retrieval return nothing?
"""
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RAGEvalResult:
    query: str
    expected_content_keywords: List[str]
    retrieved_count: int
    top_similarity: float
    recall_at_k: bool           # did any result contain expected keywords?
    reciprocal_rank: float      # 1/rank of first relevant result (0 if none)
    latency_ms: float
    passed: bool


@dataclass
class RAGEvalSummary:
    total_queries: int
    recall_at_k: float          # fraction of queries with recall
    mean_reciprocal_rank: float
    avg_top_similarity: float
    no_result_rate: float
    avg_latency_ms: float
    failed_queries: List[str] = field(default_factory=list)


class RAGEvaluator:
    """Evaluate RAG retrieval quality against benchmark queries."""

    async def evaluate(
        self,
        test_cases: List[Dict[str, Any]],
        organization_id: str,
        db: Session,
        top_k: int = 5,
    ) -> RAGEvalSummary:
        """
        Run evaluation over a list of test cases.

        Each test case: {"query": str, "expected_keywords": [str]}
        """
        from app.rag.retriever import rag_retriever

        results: List[RAGEvalResult] = []

        for case in test_cases:
            query = case["query"]
            expected = [kw.lower() for kw in case.get("expected_keywords", [])]

            t0 = time.monotonic()
            try:
                retrieved = await rag_retriever.retrieve(
                    query=query,
                    organization_id=organization_id,
                    db=db,
                    top_k=top_k,
                    threshold=0.20,
                )
            except Exception as e:
                logger.warning("rag_eval_retrieval_failed", query=query[:60], error=str(e))
                retrieved = []
            latency_ms = (time.monotonic() - t0) * 1000

            top_sim = retrieved[0]["similarity"] if retrieved else 0.0
            recall, rr = self._score(retrieved, expected)

            results.append(RAGEvalResult(
                query=query,
                expected_content_keywords=expected,
                retrieved_count=len(retrieved),
                top_similarity=top_sim,
                recall_at_k=recall,
                reciprocal_rank=rr,
                latency_ms=latency_ms,
                passed=recall,
            ))

        return self._summarize(results)

    def _score(
        self,
        retrieved: List[Dict],
        expected_keywords: List[str],
    ) -> tuple:
        """Return (recall_at_k: bool, reciprocal_rank: float)."""
        if not expected_keywords:
            return True, 1.0  # no ground truth = pass

        for rank, chunk in enumerate(retrieved, start=1):
            content_lower = chunk.get("content", "").lower()
            if any(kw in content_lower for kw in expected_keywords):
                return True, 1.0 / rank

        return False, 0.0

    def _summarize(self, results: List[RAGEvalResult]) -> RAGEvalSummary:
        total = len(results)
        if total == 0:
            return RAGEvalSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0)

        recall = sum(1 for r in results if r.recall_at_k) / total
        mrr = sum(r.reciprocal_rank for r in results) / total
        avg_sim = sum(r.top_similarity for r in results) / total
        no_result = sum(1 for r in results if r.retrieved_count == 0) / total
        avg_lat = sum(r.latency_ms for r in results) / total
        failed = [r.query for r in results if not r.passed]

        summary = RAGEvalSummary(
            total_queries=total,
            recall_at_k=round(recall, 3),
            mean_reciprocal_rank=round(mrr, 3),
            avg_top_similarity=round(avg_sim, 3),
            no_result_rate=round(no_result, 3),
            avg_latency_ms=round(avg_lat, 1),
            failed_queries=failed,
        )

        logger.info(
            "rag_eval_complete",
            total=total,
            recall=summary.recall_at_k,
            mrr=summary.mean_reciprocal_rank,
            no_result_rate=summary.no_result_rate,
        )
        return summary


rag_evaluator = RAGEvaluator()
