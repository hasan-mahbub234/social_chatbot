"""
Latency Evaluator — measures end-to-end response latency across pipeline stages.

Tracks:
  - Query intelligence pipeline latency
  - RAG retrieval latency
  - LLM generation latency
  - Total end-to-end latency
  - P50 / P95 / P99 percentiles
  - SLA compliance (% of requests under target latency)
"""
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# SLA targets in milliseconds
SLA_TARGETS = {
    "fast_path_ms": 500,        # greetings/small talk
    "cached_response_ms": 200,  # semantic cache hit
    "rag_response_ms": 3000,    # full RAG pipeline
    "total_p95_ms": 5000,       # 95th percentile total
}


@dataclass
class LatencyMeasurement:
    trace_id: str
    query_intelligence_ms: float
    retrieval_ms: float
    llm_ms: float
    total_ms: float
    from_cache: bool
    is_fast_path: bool
    sla_met: bool


@dataclass
class LatencySummary:
    total_measurements: int
    avg_total_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    sla_compliance_rate: float
    avg_retrieval_ms: float
    avg_llm_ms: float
    avg_qi_ms: float            # query intelligence
    slow_queries: List[str] = field(default_factory=list)


class LatencyEvaluator:
    """Track and analyze pipeline latency."""

    def __init__(self):
        self._measurements: List[LatencyMeasurement] = []

    def record(self, measurement: LatencyMeasurement) -> None:
        """Record a latency measurement."""
        self._measurements.append(measurement)
        # Keep last 1000 measurements in memory
        if len(self._measurements) > 1000:
            self._measurements = self._measurements[-1000:]

    def get_summary(self) -> LatencySummary:
        """Compute latency summary statistics."""
        measurements = self._measurements
        if not measurements:
            return LatencySummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        totals = sorted(m.total_ms for m in measurements)
        n = len(totals)

        def percentile(data: List[float], pct: float) -> float:
            idx = int(len(data) * pct / 100)
            return round(data[min(idx, len(data) - 1)], 1)

        sla_target = SLA_TARGETS["rag_response_ms"]
        sla_met = sum(1 for m in measurements if m.sla_met) / n

        slow = [
            m.trace_id for m in measurements
            if m.total_ms > SLA_TARGETS["total_p95_ms"]
        ]

        return LatencySummary(
            total_measurements=n,
            avg_total_ms=round(sum(totals) / n, 1),
            p50_ms=percentile(totals, 50),
            p95_ms=percentile(totals, 95),
            p99_ms=percentile(totals, 99),
            sla_compliance_rate=round(sla_met, 3),
            avg_retrieval_ms=round(sum(m.retrieval_ms for m in measurements) / n, 1),
            avg_llm_ms=round(sum(m.llm_ms for m in measurements) / n, 1),
            avg_qi_ms=round(sum(m.query_intelligence_ms for m in measurements) / n, 1),
            slow_queries=slow[-10:],
        )

    def check_sla(self, total_ms: float, from_cache: bool, is_fast_path: bool) -> bool:
        """Check if a request met its SLA target."""
        if from_cache:
            return total_ms <= SLA_TARGETS["cached_response_ms"]
        if is_fast_path:
            return total_ms <= SLA_TARGETS["fast_path_ms"]
        return total_ms <= SLA_TARGETS["rag_response_ms"]


latency_evaluator = LatencyEvaluator()
