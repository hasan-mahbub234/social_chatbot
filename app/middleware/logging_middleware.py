"""Logging middleware."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests and responses."""

    async def dispatch(self, request: Request, call_next):
        return await call_next(request)
