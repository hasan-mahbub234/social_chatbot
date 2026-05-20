"""Groq AI service — fast inference for development environment."""
from typing import List, Dict, Optional
from app.core.config import settings
from app.core.constants import MODEL_PRICING
from app.core.logging import get_logger

logger = get_logger(__name__)

GROQ_MODELS = {
    "fast": "llama-3.1-8b-instant",
    "smart": "llama-3.3-70b-versatile",
    "default": "llama-3.1-8b-instant",
}


class GroqService:
    """Groq AI inference service for development/low-cost usage."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from groq import AsyncGroq
                self._client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            except ImportError:
                raise RuntimeError("groq package not installed. Run: pip install groq")
        return self._client

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = None,
    ) -> Dict:
        """Call Groq chat completions API."""
        client = self._get_client()
        model = model or GROQ_MODELS["default"]
        max_tokens = max_tokens or settings.MAX_OUTPUT_TOKENS

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        usage = response.usage
        # Groq is essentially free in dev — minimal cost tracking
        cost = 0.0

        logger.info(
            "groq_call",
            model=model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )

        return {
            "content": response.choices[0].message.content,
            "model": model,
            "input_tokens": usage.prompt_tokens,
            "output_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "cost": cost,
        }

    async def is_available(self) -> bool:
        """Check if Groq is configured and available."""
        return bool(settings.GROQ_API_KEY)


groq_service = GroqService()
