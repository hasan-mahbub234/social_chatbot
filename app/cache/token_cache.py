"""Token cache — cache JWT token validation results."""
import json
from typing import Optional, Dict, Any
from app.core.redis_client import redis_client
from app.cache.cache_keys import token_cache_key
from app.core.logging import get_logger

logger = get_logger(__name__)

TOKEN_CACHE_TTL = 300  # 5 minutes


class TokenCache:
    """Cache decoded JWT payloads to reduce decode overhead."""

    async def get(self, token: str) -> Optional[Dict[str, Any]]:
        raw = await redis_client.get(token_cache_key(token))
        return json.loads(raw) if raw else None

    async def set(self, token: str, payload: Dict[str, Any]):
        await redis_client.set(token_cache_key(token), json.dumps(payload), ex=TOKEN_CACHE_TTL)

    async def invalidate(self, token: str):
        """Blacklist a token."""
        await redis_client.set(token_cache_key(token), json.dumps({"blacklisted": True}), ex=TOKEN_CACHE_TTL)

    async def is_blacklisted(self, token: str) -> bool:
        payload = await self.get(token)
        return bool(payload and payload.get("blacklisted"))


token_cache = TokenCache()
