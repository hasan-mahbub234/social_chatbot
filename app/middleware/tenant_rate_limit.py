"""Tenant-aware rate limit middleware — enforces per-plan rate limits."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.redis_client import redis_client
from app.core.logging import get_logger

logger = get_logger(__name__)

SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/api/v1/billing/webhook"}


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit per organization using plan-specific limits."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        # Extract org from request state (set by AuthMiddleware)
        org_id = getattr(request.state, "organization_id", None)
        if not org_id:
            return await call_next(request)

        # Get plan rate limit from request state (set after tenant resolution)
        rate_limit = getattr(request.state, "rate_limit_per_minute", 20)

        key = f"tenant_rate:{org_id}:{request.url.path}"
        try:
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, 60)

            if count > rate_limit:
                logger.warning("tenant_rate_limit_exceeded", org=org_id, path=request.url.path, count=count)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": f"Rate limit of {rate_limit} requests/minute exceeded for your plan.",
                        }
                    },
                    headers={
                        "X-RateLimit-Limit": str(rate_limit),
                        "X-RateLimit-Remaining": "0",
                        "Retry-After": "60",
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, rate_limit - count))
            return response

        except Exception as e:
            logger.warning("tenant_rate_limit_check_failed", error=str(e))
            return await call_next(request)
