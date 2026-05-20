"""Authentication middleware."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.security import decode_token
import logging

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for FastAPI."""

    async def dispatch(self, request: Request, call_next):
        """Process request and validate token if needed."""
        # Skip auth for public endpoints
        public_paths = ["/", "/health", "/metrics", "/openapi.json", "/api/v1/auth/register", "/api/v1/auth/login"]
        public_prefixes = ("/docs", "/redoc", "/api/v1/health", "/api/v1/plans", "/api/v1/webhooks")

        if request.url.path in public_paths or request.url.path.startswith(public_prefixes):
            return await call_next(request)

        # Check for authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization header"},
            )

        try:
            scheme, token = auth_header.split()
            if scheme.lower() != "bearer":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authentication scheme"},
                )
            
            payload = decode_token(token)
            request.state.user_id = payload.get("sub")
        except Exception as e:
            logger.error(f"Auth error: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"},
            )

        return await call_next(request)
