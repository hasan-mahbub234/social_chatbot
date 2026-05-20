"""Middleware configuration — centralized middleware setup."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings


def configure_middleware(app: FastAPI) -> None:
    """Apply all middleware to the FastAPI app in correct order."""
    from app.middleware import (
        AuthMiddleware,
        RequestIDMiddleware,
        LoggingMiddleware,
        RateLimitMiddleware,
        SecurityHeadersMiddleware,
        ExceptionMiddleware,
    )
    from app.middleware.tenant_rate_limit import TenantRateLimitMiddleware

    # CORS first (outermost)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Starlette middleware executes in REVERSE order of add_middleware calls.
    # Last added = first executed.
    # Desired execution order: RequestID → Logging → Auth → RateLimit → TenantRateLimit → Security → Exception

    app.add_middleware(ExceptionMiddleware)        # 7th — outermost error handler
    app.add_middleware(SecurityHeadersMiddleware)  # 6th
    app.add_middleware(TenantRateLimitMiddleware)  # 5th
    app.add_middleware(RateLimitMiddleware)        # 4th
    app.add_middleware(AuthMiddleware)             # 3rd
    app.add_middleware(LoggingMiddleware)          # 2nd — logs after request_id is set
    app.add_middleware(RequestIDMiddleware)        # 1st — runs first, sets request_id
