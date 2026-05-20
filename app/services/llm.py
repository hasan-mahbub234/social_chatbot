"""LLM service — OpenAI in production, Groq in development.

Controlled by AI_PROVIDER env var:
  AI_PROVIDER=openai  → uses OpenAI GPT-4o / GPT-4o-mini  (production)
  AI_PROVIDER=groq    → uses Groq llama models             (development)

Groq is lazy-imported — never loaded when AI_PROVIDER=openai.
"""
from typing import List, Dict, Optional, AsyncGenerator
from app.core.config import settings
from app.core.constants import MODEL_PRICING, GPT4O, GPT4O_MINI
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMService:
    """Unified LLM service — routes to OpenAI or Groq based on AI_PROVIDER."""

    def __init__(self):
        self._openai = None
        self._groq = None

    @property
    def _is_groq(self) -> bool:
        return settings.AI_PROVIDER == "groq"

    def _get_openai(self):
        if self._openai is None:
            from app.services.openai_service import openai_service
            self._openai = openai_service
        return self._openai

    def _get_groq(self):
        if self._groq is None:
            from app.services.groq_service import groq_service  # only imported in dev
            self._groq = groq_service
        return self._groq

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = None,
        system_prompt: str = None,
    ) -> str:
        """Generate response — returns content string with markdown stripped."""
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}, *messages]
        result = await self.generate_with_usage(messages, model, temperature, max_tokens)
        return self._strip_markdown(result["content"])

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove markdown formatting that renders as literal symbols in chat channels."""
        import re
        # Remove markdown links: [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Remove bold/italic: **text** -> text, *text* -> text, __text__ -> text
        text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
        text = re.sub(r'_{1,2}([^_\n]+)_{1,2}', r'\1', text)
        # Remove headers: ## Header -> Header
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # Remove bullet list markers
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        # Remove inline code backticks
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # Collapse 3+ newlines to 2
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    async def generate_with_usage(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = None,
    ) -> Dict:
        """Generate response and return full usage dict with tokens + cost."""
        model = model or settings.OPENAI_MODEL

        if self._is_groq:
            from app.services.groq_service import GROQ_MODELS  # dev-only import
            groq_model = GROQ_MODELS["smart"] if model == GPT4O else GROQ_MODELS["fast"]
            return await self._get_groq().chat(messages, groq_model, temperature, max_tokens)

        return await self._get_openai().chat(messages, model, temperature, max_tokens)

    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = None,
        system_prompt: str = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response chunks — OpenAI only (Groq streaming not used in prod)."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        model = model or settings.OPENAI_MODEL
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}, *messages]

        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature or 0.7,
            max_tokens=max_tokens or settings.MAX_OUTPUT_TOKENS,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def count_tokens(self, text: str) -> int:
        """Estimate token count (1 token ≈ 4 chars)."""
        return len(text) // 4

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str = None) -> float:
        """Estimate cost — returns 0.0 for Groq (free in dev)."""
        if self._is_groq:
            return 0.0
        model = model or settings.OPENAI_MODEL
        pricing = MODEL_PRICING.get(model, MODEL_PRICING.get(GPT4O_MINI, {"input": 0.15, "output": 0.60}))
        return (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]


llm_service = LLMService()
