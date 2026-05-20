"""Performance monitor — track latency and throughput."""
import time
from typing import Dict, Any
from collections import defaultdict
from app.core.logging import get_logger

logger = get_logger(__name__)


class PerformanceMonitor:
    """Monitor and report system performance metrics."""

    def __init__(self):
        self._latencies: Dict[str, list] = defaultdict(list)
        self._counts: Dict[str, int] = defaultdict(int)

    def record_latency(self, operation: str, latency_ms: float):
        """Record operation latency."""
        self._latencies[operation].append(latency_ms)
        self._counts[operation] += 1
        # Keep last 1000 samples
        if len(self._latencies[operation]) > 1000:
            self._latencies[operation] = self._latencies[operation][-1000:]

    def get_stats(self, operation: str) -> Dict[str, Any]:
        """Get latency statistics for an operation."""
        samples = self._latencies.get(operation, [])
        if not samples:
            return {"operation": operation, "count": 0}
        return {
            "operation": operation,
            "count": self._counts[operation],
            "avg_ms": sum(samples) / len(samples),
            "min_ms": min(samples),
            "max_ms": max(samples),
            "p95_ms": sorted(samples)[int(len(samples) * 0.95)],
        }

    def get_all_stats(self) -> Dict[str, Any]:
        return {op: self.get_stats(op) for op in self._latencies}

    def timer(self, operation: str):
        """Context manager for timing operations."""
        return _Timer(self, operation)


class _Timer:
    def __init__(self, monitor: PerformanceMonitor, operation: str):
        self.monitor = monitor
        self.operation = operation
        self.start = None

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        latency_ms = (time.time() - self.start) * 1000
        self.monitor.record_latency(self.operation, latency_ms)


performance_monitor = PerformanceMonitor()
