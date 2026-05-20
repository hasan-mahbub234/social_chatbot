"""Structured execution package — bypasses RAG for simple structured queries."""
from app.structured.executor import structured_executor, STRUCTURED_INTENTS

__all__ = ["structured_executor", "STRUCTURED_INTENTS"]
