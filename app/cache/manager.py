"""Cache management."""
import json
from typing import Any, Optional, Dict
from datetime import timedelta
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger(__name__)


class CacheManager:
    """Manages caching operations with Redis."""
    
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.default_ttl = settings.CACHE_TTL
    
    async def initialize(self):
        """Initialize Redis connection."""
        try:
            self.redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf8",
                decode_responses=True,
            )
            await self.redis.ping()
            logger.info("Cache manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize cache manager: {e}")
            raise
    
    async def close(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("Cache manager closed")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        try:
            if not self.redis:
                return None
            
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set value in cache."""
        try:
            if not self.redis:
                return False
            
            serialized = json.dumps(value)
            await self.redis.set(
                key,
                serialized,
                ex=ttl or self.default_ttl,
            )
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        try:
            if not self.redis:
                return False
            
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            if not self.redis:
                return False
            
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            return False
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a counter."""
        try:
            if not self.redis:
                return None
            
            return await self.redis.incrby(key, amount)
        except Exception as e:
            logger.error(f"Cache increment error: {e}")
            return None
    
    async def get_many(self, keys: list[str]) -> Dict[str, Any]:
        """Get multiple values from cache."""
        try:
            if not self.redis or not keys:
                return {}
            
            values = await self.redis.mget(keys)
            result = {}
            
            for key, value in zip(keys, values):
                if value:
                    result[key] = json.loads(value)
            
            return result
        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            return {}
    
    async def set_many(
        self,
        data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Set multiple values in cache."""
        try:
            if not self.redis or not data:
                return False
            
            pipe = self.redis.pipeline()
            
            for key, value in data.items():
                serialized = json.dumps(value)
                pipe.set(key, serialized, ex=ttl or self.default_ttl)
            
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Cache set_many error: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """Clear cache by pattern."""
        try:
            if not self.redis:
                return 0
            
            keys = await self.redis.keys(pattern)
            if keys:
                return await self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache clear_pattern error: {e}")
            return 0


# Global cache manager instance
cache_manager = CacheManager()
