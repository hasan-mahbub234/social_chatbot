"""Rolling summary — maintain compressed long-term memory."""
import json
from typing import Optional
from app.core.redis_client import redis_client
from app.memory.summarizer import summarizer
from app.core.logging import get_logger

logger = get_logger(__name__)

ROLLING_SUMMARY_TTL = 86400 * 7  # 7 days


class RollingSummary:
    """Maintain a rolling compressed summary of conversation history."""

    def _key(self, conversation_id: str) -> str:
        return f"rolling_summary:{conversation_id}"

    async def get(self, conversation_id: str) -> Optional[str]:
        """Get current rolling summary."""
        return await redis_client.get(self._key(conversation_id))

    async def update(self, conversation_id: str, new_messages: list):
        """Update rolling summary with new messages."""
        existing = await self.get(conversation_id) or ""
        if existing:
            new_messages = [{"role": "system", "content": f"Previous summary: {existing}"}] + new_messages

        new_summary = await summarizer.summarize(new_messages)
        await redis_client.set(self._key(conversation_id), new_summary, ex=ROLLING_SUMMARY_TTL)
        logger.info("rolling_summary_updated", conversation_id=conversation_id)
        return new_summary

    async def clear(self, conversation_id: str):
        await redis_client.delete(self._key(conversation_id))


rolling_summary = RollingSummary()
