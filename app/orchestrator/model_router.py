"""Model router — selects optimal LLM based on intent and cost."""
from app.core.constants import (
    GPT4O, GPT4O_MINI,
    INTENT_GREETING, INTENT_FAQ, INTENT_REASONING,
    INTENT_SUMMARIZATION, INTENT_GOVERNANCE, INTENT_RISK,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Intent → model mapping (cost-optimized)
INTENT_MODEL_MAP = {
    INTENT_GREETING: None,           # No LLM needed
    INTENT_FAQ: GPT4O_MINI,          # RAG + mini
    INTENT_SUMMARIZATION: GPT4O_MINI,
    INTENT_GOVERNANCE: GPT4O_MINI,
    INTENT_RISK: GPT4O_MINI,
    INTENT_REASONING: GPT4O,         # Only reasoning uses GPT-4o
    "general": GPT4O_MINI,
}


class ModelRouter:
    """Select the most cost-effective model for the task."""

    async def select(self, intent: str, query: str, risk_level: str = "low") -> str:
        """Select model based on intent and risk level."""
        # Force GPT-4o for high-risk or complex reasoning
        if risk_level in ("high", "critical"):
            logger.info("model_selected", model=GPT4O, reason="high_risk")
            return GPT4O

        model = INTENT_MODEL_MAP.get(intent, GPT4O_MINI)

        # Fallback if no model (greeting)
        if model is None:
            model = GPT4O_MINI

        logger.info("model_selected", model=model, intent=intent)
        return model

    def get_governance_model(self) -> str:
        return GPT4O_MINI

    def get_hallucination_model(self) -> str:
        return GPT4O_MINI

    def get_reasoning_model(self) -> str:
        return GPT4O


model_router = ModelRouter()
