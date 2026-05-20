"""Summarizer — compress long conversation history using LLM."""
from typing import List, Dict
from app.services.llm import llm_service
from app.core.constants import GPT4O_MINI
from app.core.logging import get_logger

logger = get_logger(__name__)

SUMMARIZE_PROMPT = (
    "Summarize the following conversation history concisely, "
    "preserving key facts, decisions, and context:\n\n{history}"
)


class Summarizer:
    """Summarize conversation history to reduce token usage."""

    async def summarize(self, messages: List[Dict[str, str]]) -> str:
        """Summarize a list of messages into a compact string."""
        if not messages:
            return ""

        history = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        prompt = SUMMARIZE_PROMPT.format(history=history)

        try:
            summary = await llm_service.generate_response(
                messages=[{"role": "user", "content": prompt}],
                model=GPT4O_MINI,
                max_tokens=500,
                temperature=0.3,
            )
            logger.info("conversation_summarized", original_messages=len(messages))
            return summary
        except Exception as e:
            logger.error("summarization_failed", error=str(e))
            return history[-2000:]  # Fallback: truncate


summarizer = Summarizer()
