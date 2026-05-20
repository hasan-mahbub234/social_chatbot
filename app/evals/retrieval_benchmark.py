"""
Retrieval Benchmark — runs a full retrieval benchmark suite and
produces a pass/fail report for CI/CD regression testing.

Loads gold queries from evaluation/benchmarks/gold_queries.json
and runs them against the live retrieval stack.
"""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.core.logging import get_logger

logger = get_logger(__name__)

GOLD_QUERIES_PATH = Path(__file__).parent.parent / "evaluation" / "benchmarks" / "gold_queries.json"

# Minimum acceptable metrics for CI pass
PASS_THRESHOLDS = {
    "recall_at_k": 0.70,        # 70% of queries must retrieve correct chunk
    "no_result_rate": 0.10,     # < 10% zero-result queries
    "avg_top_similarity": 0.40, # average top similarity must be > 0.40
}


@dataclass
class BenchmarkReport:
    passed: bool
    total_queries: int
    recall_at_k: float
    no_result_rate: float
    avg_top_similarity: float
    avg_latency_ms: float
    failures: List[Dict[str, Any]] = field(default_factory=list)
    threshold_violations: List[str] = field(default_factory=list)
    run_timestamp: float = field(default_factory=time.time)


class RetrievalBenchmark:
    """
    Run retrieval benchmark against gold queries.

    Gold queries format (gold_queries.json):
    [
      {
        "query": "return policy",
        "expected_keywords": ["return", "exchange", "refund"],
        "intent": "policy_lookup"
      },
      ...
    ]
    """

    def load_gold_queries(self) -> List[Dict[str, Any]]:
        """Load gold queries from benchmark file."""
        try:
            if GOLD_QUERIES_PATH.exists():
                return json.loads(GOLD_QUERIES_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("gold_queries_load_failed", error=str(e))
        return []

    async def run(
        self,
        organization_id: str,
        db: Session,
        top_k: int = 5,
        custom_queries: Optional[List[Dict]] = None,
    ) -> BenchmarkReport:
        """Run the full benchmark suite."""
        from app.evals.rag_eval import rag_evaluator

        test_cases = custom_queries or self.load_gold_queries()
        if not test_cases:
            logger.warning("retrieval_benchmark_no_test_cases")
            return BenchmarkReport(
                passed=False, total_queries=0,
                recall_at_k=0.0, no_result_rate=1.0,
                avg_top_similarity=0.0, avg_latency_ms=0.0,
                threshold_violations=["no_test_cases"],
            )

        summary = await rag_evaluator.evaluate(test_cases, organization_id, db, top_k=top_k)

        # Check thresholds
        violations = []
        if summary.recall_at_k < PASS_THRESHOLDS["recall_at_k"]:
            violations.append(
                f"recall_at_k={summary.recall_at_k:.2f} < {PASS_THRESHOLDS['recall_at_k']}"
            )
        if summary.no_result_rate > PASS_THRESHOLDS["no_result_rate"]:
            violations.append(
                f"no_result_rate={summary.no_result_rate:.2f} > {PASS_THRESHOLDS['no_result_rate']}"
            )
        if summary.avg_top_similarity < PASS_THRESHOLDS["avg_top_similarity"]:
            violations.append(
                f"avg_top_similarity={summary.avg_top_similarity:.2f} < {PASS_THRESHOLDS['avg_top_similarity']}"
            )

        failures = [
            {"query": q, "reason": "no_recall"} for q in summary.failed_queries
        ]

        report = BenchmarkReport(
            passed=len(violations) == 0,
            total_queries=summary.total_queries,
            recall_at_k=summary.recall_at_k,
            no_result_rate=summary.no_result_rate,
            avg_top_similarity=summary.avg_top_similarity,
            avg_latency_ms=summary.avg_latency_ms,
            failures=failures,
            threshold_violations=violations,
        )

        logger.info(
            "retrieval_benchmark_complete",
            passed=report.passed,
            total=report.total_queries,
            recall=report.recall_at_k,
            violations=violations,
        )
        return report


retrieval_benchmark = RetrievalBenchmark()
