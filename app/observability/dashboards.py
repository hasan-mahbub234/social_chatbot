"""Dashboards — aggregate metrics for monitoring dashboards."""
from typing import Dict, Any
from app.observability.metrics import metrics_collector
from app.observability.performance_monitor import performance_monitor
from app.core.logging import get_logger

logger = get_logger(__name__)


class DashboardService:
    """Aggregate metrics for observability dashboards."""

    def get_overview(self) -> Dict[str, Any]:
        """Get platform overview metrics."""
        summary = metrics_collector.get_summary()
        perf = performance_monitor.get_all_stats()

        return {
            "requests": {
                "total": summary.get("request_count", 0),
                "ai_calls": summary.get("ai_call_count", 0),
            },
            "counters": summary.get("counters", {}),
            "cache": {
                "hits": summary.get("counters", {}).get("cache_hits", 0),
                "misses": summary.get("counters", {}).get("cache_misses", 0),
                "hit_ratio": self._cache_hit_ratio(summary),
            },
            "performance": perf,
            "gauges": summary.get("gauges", {}),
        }

    def _cache_hit_ratio(self, summary: Dict) -> float:
        counters = summary.get("counters", {})
        hits = counters.get("cache_hits", 0)
        misses = counters.get("cache_misses", 0)
        total = hits + misses
        return round(hits / total, 3) if total > 0 else 0.0

    def get_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus text format."""
        summary = metrics_collector.get_summary()
        lines = []
        for name, value in summary.get("counters", {}).items():
            lines.append(f"ai_platform_{name}_total {value}")
        for name, value in summary.get("gauges", {}).items():
            lines.append(f"ai_platform_{name} {value}")
        return "\n".join(lines)


dashboard_service = DashboardService()
