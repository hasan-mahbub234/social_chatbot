"""Session cache — store user session data in Redis."""
import json
from typing import Optional, Dict, Any
from app.core.redis_client import redis_client
from app.cache.cache_keys import session_cache_key
from app.core.logging import get_logger

logger = get_logger(__name__)

SESSION_TTL = 3600  # 1 hour


class SessionCache:
    """Manage user session data in Redis."""

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        raw = await redis_client.get(session_cache_key(session_id))
        return json.loads(raw) if raw else None

    async def set(self, session_id: str, data: Dict[str, Any], ttl: int = SESSION_TTL):
        await redis_client.set(session_cache_key(session_id), json.dumps(data), ex=ttl)

    async def update(self, session_id: str, updates: Dict[str, Any]):
        existing = await self.get(session_id) or {}
        existing.update(updates)
        await self.set(session_id, existing)

    async def delete(self, session_id: str):
        await redis_client.delete(session_cache_key(session_id))

    async def exists(self, session_id: str) -> bool:
        return await redis_client.exists(session_cache_key(session_id))


session_cache = SessionCache()
