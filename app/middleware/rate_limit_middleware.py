"""Rate limiting middleware."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.redis_client import redis_client
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis."""

    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting."""
        try:
            # Skip rate limiting for health checks
            if request.url.path in ["/health", "/docs", "/redoc"]:
                return await call_next(request)

            # Get client identifier
            client_id = request.client.host if request.client else "unknown"
            
            # Create rate limit key
            key = f"rate_limit:{client_id}:{request.url.path}"
            
            # Check rate limit (100 requests per minute)
            try:
                count = await redis_client.incr(key)
                if count == 1:
                    await redis_client.expire(key, 60)
                if count > 100:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Rate limit exceeded"},
                    )
            except Exception as e:
                logger.warning(f"Rate limit check failed: {e}")
                count = None

            response = await call_next(request)
            if count is not None:
                response.headers["X-RateLimit-Limit"] = "100"
                response.headers["X-RateLimit-Remaining"] = str(max(0, 100 - count))
            return response

        except Exception as e:
            logger.error(f"Rate limit error: {e}")
            return await call_next(request)
