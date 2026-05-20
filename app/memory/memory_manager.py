"""Memory manager — coordinates short-term and long-term memory."""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.memory.conversation_memory import conversation_memory
from app.memory.rolling_summary import rolling_summary
from app.memory.summarizer import summarizer
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class MemoryManager:
    """Manage conversation memory with automatic compression."""

    async def add_message(self, conversation_id: str, role: str, content: str):
        """Add message to short-term memory."""
        await conversation_memory.add(conversation_id, role, content)

        # Auto-compress if over threshold
        count = await conversation_memory.count(conversation_id)
        if count >= settings.SUMMARY_THRESHOLD_MESSAGES:
            await self._compress(conversation_id)

    async def get_context(self, conversation_id: str, limit: int = 20) -> List[Dict[str, str]]:
        """Get conversation context, prepending rolling summary if available."""
        messages = await conversation_memory.get(conversation_id, limit=limit)
        summary = await rolling_summary.get(conversation_id)

        if summary:
            return [{"role": "system", "content": f"Conversation summary: {summary}"}] + messages
        return messages

    async def _compress(self, conversation_id: str):
        """Compress old messages into rolling summary."""
        messages = await conversation_memory.get(conversation_id)
        if messages:
            await rolling_summary.update(conversation_id, messages)
            await conversation_memory.clear(conversation_id)
            logger.info("memory_compressed", conversation_id=conversation_id)

    async def clear(self, conversation_id: str):
        """Clear all memory for a conversation."""
        await conversation_memory.clear(conversation_id)
        await rolling_summary.clear(conversation_id)


memory_manager = MemoryManager()
