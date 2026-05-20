"""Response cache — exact-match response caching."""
import json
from typing import Optional, Dict, Any
from app.core.redis_client import redis_client
from app.cache.cache_keys import response_cache_key
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ResponseCache:
    """Cache exact query→response pairs."""

    async def get(self, query: str, agent_id: str) -> Optional[Dict[str, Any]]:
        key = response_cache_key(query, agent_id)
        raw = await redis_client.get(key)
        return json.loads(raw) if raw else None

    async def set(self, query: str, agent_id: str, response: Dict[str, Any], ttl: int = None):
        key = response_cache_key(query, agent_id)
        await redis_client.set(key, json.dumps(response), ex=ttl or settings.CACHE_TTL)

    async def invalidate(self, query: str, agent_id: str):
        await redis_client.delete(response_cache_key(query, agent_id))


response_cache = ResponseCache()
