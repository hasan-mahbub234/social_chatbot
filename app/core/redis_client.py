"""Redis client — uses redis.asyncio (compatible with Python 3.13+)."""
import redis.asyncio as aioredis
import redis as sync_redis
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client wrapper."""

    def __init__(self):
        self.client: aioredis.Redis | None = None

    async def connect(self):
        """Connect to Redis."""
        try:
            self.client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await self.client.ping()
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.aclose()
            logger.info("Disconnected from Redis")

    async def _ensure_connected(self):
        """Reconnect if client is None (Redis was unavailable at startup)."""
        if self.client is None:
            try:
                self.client = aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self.client.ping()
                logger.info("Redis reconnected successfully")
            except Exception as e:
                logger.warning(f"Redis reconnect failed: {e}")
                self.client = None

    async def get(self, key: str):
        await self._ensure_connected()
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: int = None, nx: bool = False):
        await self._ensure_connected()
        return await self.client.set(key, value, ex=ex or settings.REDIS_CACHE_EXPIRY, nx=nx if nx else None)

    async def delete(self, key: str):
        await self._ensure_connected()
        await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        await self._ensure_connected()
        return bool(await self.client.exists(key))

    async def incr(self, key: str) -> int:
        await self._ensure_connected()
        return await self.client.incr(key)

    async def expire(self, key: str, seconds: int):
        await self._ensure_connected()
        await self.client.expire(key, seconds)


# Global instances
redis_client = RedisClient()

# Synchronous client for Celery broker
sync_redis_client = sync_redis.from_url(settings.REDIS_URL)
