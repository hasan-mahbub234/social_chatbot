"""Metrics collection and tracking."""
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import time


@dataclass
class RequestMetrics:
    """Request metrics."""
    timestamp: datetime
    endpoint: str
    method: str
    status_code: int
    duration_ms: float
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class AIMetrics:
    """AI processing metrics."""
    timestamp: datetime
    model: str
    tokens_used: int
    latency_ms: float
    cost: float
    success: bool
    error: Optional[str] = None


class MetricsCollector:
    """Collect and aggregate metrics."""
    
    def __init__(self):
        self.request_metrics: list[RequestMetrics] = []
        self.ai_metrics: list[AIMetrics] = []
        self.counters: Dict[str, int] = defaultdict(int)
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, list] = defaultdict(list)
    
    def record_request(self, **kwargs):
        """Record request metric."""
        metric = RequestMetrics(timestamp=datetime.utcnow(), **kwargs)
        self.request_metrics.append(metric)
        self._cleanup_old_metrics(self.request_metrics)
    
    def record_ai_call(self, **kwargs):
        """Record AI call metric."""
        metric = AIMetrics(timestamp=datetime.utcnow(), **kwargs)
        self.ai_metrics.append(metric)
        self._cleanup_old_metrics(self.ai_metrics)
    
    def increment_counter(self, name: str, amount: int = 1):
        """Increment counter."""
        self.counters[name] += amount
    
    def set_gauge(self, name: str, value: float):
        """Set gauge value."""
        self.gauges[name] = value
    
    def record_histogram(self, name: str, value: float):
        """Record histogram value."""
        self.histograms[name].append(value)
    
    def get_summary(self) -> Dict:
        """Get metrics summary."""
        return {
            "request_count": len(self.request_metrics),
            "ai_call_count": len(self.ai_metrics),
            "counters": dict(self.counters),
            "gauges": self.gauges,
            "histogram_stats": {
                name: {
                    "count": len(values),
                    "min": min(values) if values else 0,
                    "max": max(values) if values else 0,
                    "avg": sum(values) / len(values) if values else 0,
                }
                for name, values in self.histograms.items()
            }
        }
    
    def _cleanup_old_metrics(self, metrics_list: list, max_age_hours: int = 24):
        """Remove old metrics to prevent memory bloat."""
        cutoff_time = datetime.utcnow().timestamp() - (max_age_hours * 3600)
        
        metrics_list[:] = [
            m for m in metrics_list
            if m.timestamp.timestamp() > cutoff_time
        ]


# Global metrics collector
metrics_collector = MetricsCollector()
