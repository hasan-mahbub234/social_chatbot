"""Abuse detection — repeated failures, spam, misuse patterns."""
from typing import Dict
from app.core.redis_client import redis_client
from app.core.logging import get_logger

logger = get_logger(__name__)

ABUSE_WINDOW = 300  # 5 minutes
ABUSE_THRESHOLD = 20  # requests per window


class AbuseDetector:
    """Detect abusive usage patterns."""

    async def check(self, user_id: str, action: str = "request") -> Dict[str, any]:
        """Check if user is abusing the system."""
        key = f"abuse:{user_id}:{action}"
        try:
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, ABUSE_WINDOW)

            is_abuse = count > ABUSE_THRESHOLD
            score = min(100.0, (count / ABUSE_THRESHOLD) * 100)

            return {
                "is_abuse": is_abuse,
                "request_count": count,
                "score": score,
                "risk_level": "high" if is_abuse else "low",
            }
        except Exception as e:
            logger.warning("abuse_check_failed", error=str(e))
            return {"is_abuse": False, "request_count": 0, "score": 0.0, "risk_level": "low"}

    async def reset(self, user_id: str, action: str = "request"):
        """Reset abuse counter for user."""
        key = f"abuse:{user_id}:{action}"
        await redis_client.delete(key)


abuse_detector = AbuseDetector()
