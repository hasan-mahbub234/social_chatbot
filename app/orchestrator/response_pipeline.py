"""Response pipeline — builds structured final response."""
from typing import Dict, Any, Optional
from app.services.llm import llm_service
from app.core.logging import get_logger

logger = get_logger(__name__)


class ResponsePipeline:
    """Build and enrich the final response object."""

    async def build(
        self,
        query: str,
        response: str,
        model: str,
        sources: Dict[str, Any],
        hallucination_result: Optional[Dict] = None,
        risk_result: Optional[Dict] = None,
        trace_id: str = "",
    ) -> Dict[str, Any]:
        """Build structured response with metadata."""
        input_tokens = llm_service.count_tokens(query)
        output_tokens = llm_service.count_tokens(response)
        cost = llm_service.estimate_cost(input_tokens, output_tokens, model)

        return {
            "content": response,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens_used": input_tokens + output_tokens,
            "cost": cost,
            "sources": sources,
            "hallucination_score": hallucination_result.get("hallucination_score") if hallucination_result else None,
            "risk_level": risk_result.get("risk_category", "low") if risk_result else "low",
            "trace_id": trace_id,
        }


response_pipeline = ResponsePipeline()
