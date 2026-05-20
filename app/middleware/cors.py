"""CORS middleware configuration."""
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings


def setup_cors(app):
    """Setup CORS middleware."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_CREDENTIALS,
        allow_methods=settings.CORS_METHODS,
        allow_headers=settings.CORS_HEADERS,
        expose_headers=["X-Request-ID", "X-Process-Time", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
        max_age=3600,
    )
