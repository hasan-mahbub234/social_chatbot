"""Rate limiter utility using Redis."""
from app.core.redis_client import redis_client
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def check_rate_limit(identifier: str, limit: int = None, window: int = None) -> tuple[bool, int]:
    """
    Check rate limit for identifier.
    Returns (allowed: bool, remaining: int).
    """
    limit = limit or settings.RATE_LIMIT_REQUESTS
    window = window or settings.RATE_LIMIT_WINDOW
    key = f"rate_limit:{identifier}"

    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window)
        remaining = max(0, limit - count)
        return count <= limit, remaining
    except Exception as e:
        logger.warning(f"Rate limit check failed for {identifier}: {e}")
        return True, limit  # Fail open


async def reset_rate_limit(identifier: str):
    """Reset rate limit for identifier."""
    key = f"rate_limit:{identifier}"
    try:
        await redis_client.delete(key)
    except Exception as e:
        logger.warning(f"Failed to reset rate limit for {identifier}: {e}")
