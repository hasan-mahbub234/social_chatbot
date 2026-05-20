"""Distributed tracing utilities."""
from datetime import datetime
from typing import Dict, Optional, List
from contextlib import contextmanager
import time


class Span:
    """Distributed trace span."""
    
    def __init__(self, name: str, trace_id: str, parent_span_id: Optional[str] = None):
        self.name = name
        self.trace_id = trace_id
        self.span_id = str(hash(f"{name}{time.time()}"))
        self.parent_span_id = parent_span_id
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None
        self.attributes: Dict = {}
        self.events: List[Dict] = []
        self.status = "unset"
    
    def set_attribute(self, key: str, value):
        """Set span attribute."""
        self.attributes[key] = value
    
    def add_event(self, name: str, attributes: Optional[Dict] = None):
        """Add event to span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.utcnow(),
            "attributes": attributes or {},
        })
    
    def end(self, status: str = "ok"):
        """End span."""
        self.end_time = datetime.utcnow()
        self.status = status
    
    @property
    def duration_ms(self) -> float:
        """Get duration in milliseconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return (datetime.utcnow() - self.start_time).total_seconds() * 1000
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
        }


class Tracer:
    """Distributed tracer."""
    
    def __init__(self):
        self.traces: Dict[str, List[Span]] = {}
        self.current_span: Optional[Span] = None
    
    def start_span(
        self,
        name: str,
        trace_id: str,
        parent_span_id: Optional[str] = None,
    ) -> Span:
        """Start new span."""
        span = Span(name, trace_id, parent_span_id)
        
        if trace_id not in self.traces:
            self.traces[trace_id] = []
        
        self.traces[trace_id].append(span)
        self.current_span = span
        
        return span
    
    @contextmanager
    def trace(self, name: str, trace_id: str):
        """Context manager for tracing."""
        span = self.start_span(name, trace_id)
        try:
            yield span
            span.end("ok")
        except Exception as e:
            span.end("error")
            span.set_attribute("error", str(e))
            raise
    
    def get_trace(self, trace_id: str) -> List[Span]:
        """Get trace spans."""
        return self.traces.get(trace_id, [])
    
    def get_trace_summary(self, trace_id: str) -> Dict:
        """Get trace summary."""
        spans = self.get_trace(trace_id)
        
        if not spans:
            return {}
        
        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "total_duration_ms": sum(span.duration_ms for span in spans),
            "spans": [span.to_dict() for span in spans],
        }


# Global tracer instance
tracer = Tracer()
