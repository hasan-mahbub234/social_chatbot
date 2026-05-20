"""Response service — format and enrich AI responses."""
from typing import Dict, Any, Optional
from datetime import datetime


class ResponseService:
    """Build standardized API response objects."""

    def build_chat_response(
        self,
        conversation_id: str,
        message_id: str,
        content: str,
        model: str,
        tokens_used: int,
        cost: float,
        sources: Dict = None,
        hallucination_score: Optional[float] = None,
        risk_level: str = "low",
        from_cache: bool = False,
        trace_id: str = "",
    ) -> Dict[str, Any]:
        return {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "role": "assistant",
            "content": content,
            "model": model,
            "tokens_used": tokens_used,
            "cost": cost,
            "sources": sources or {},
            "hallucination_score": hallucination_score,
            "risk_level": risk_level,
            "from_cache": from_cache,
            "trace_id": trace_id,
            "created_at": datetime.utcnow().isoformat(),
        }

    def build_error_response(self, error: str, code: str = "INTERNAL_ERROR") -> Dict[str, Any]:
        return {
            "error": {"code": code, "message": error},
            "created_at": datetime.utcnow().isoformat(),
        }


response_service = ResponseService()
