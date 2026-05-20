"""Conversation memory — Redis-backed short-term message store."""
import json
from typing import List, Dict, Any
from app.core.redis_client import redis_client
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MEMORY_TTL = 3600  # 1 hour
MAX_MESSAGES = 50


class ConversationMemory:
    """Store and retrieve recent conversation messages from Redis."""

    def _key(self, conversation_id: str) -> str:
        return f"conv_memory:{conversation_id}"

    async def add(self, conversation_id: str, role: str, content: str):
        """Append a message to conversation memory."""
        key = self._key(conversation_id)
        raw = await redis_client.get(key)
        messages: List[Dict] = json.loads(raw) if raw else []
        messages.append({"role": role, "content": content})

        # Keep last MAX_MESSAGES
        if len(messages) > MAX_MESSAGES:
            messages = messages[-MAX_MESSAGES:]

        await redis_client.set(key, json.dumps(messages), ex=MEMORY_TTL)

    async def get(self, conversation_id: str, limit: int = 20) -> List[Dict[str, str]]:
        """Get recent messages from memory."""
        key = self._key(conversation_id)
        raw = await redis_client.get(key)
        if not raw:
            return []
        messages = json.loads(raw)
        return messages[-limit:]

    async def clear(self, conversation_id: str):
        """Clear conversation memory."""
        await redis_client.delete(self._key(conversation_id))

    async def count(self, conversation_id: str) -> int:
        raw = await redis_client.get(self._key(conversation_id))
        return len(json.loads(raw)) if raw else 0


conversation_memory = ConversationMemory()
