"""FastAPI application factory."""
import sys
import asyncio

# Set ProactorEventLoop on Windows BEFORE uvicorn creates its event loop.
# This is required for Playwright (subprocess spawning) to work.
# Must be at module level, before any other imports that touch asyncio.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.database import init_db, get_db, SessionLocal
from app.core.redis_client import redis_client
from app.core.logging import logger
from app.api import auth, agents, conversations, health, voice, uploads, webhooks, knowledge
from app.api import plans, subscriptions, billing, usage, quotas
from app.api import analytics, governance, hallucination, risk, organizations, admin
from app.api import products
from app.exceptions.handlers import add_exception_handlers
from app.plans.seeder import seed_plans
from sqlalchemy.orm import Session
import logging


def get_current_superuser_optional():
    """Optional superuser dep for internal metrics."""
    return None


# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))


def _silent_exception_handler(loop, context):
    """Suppress Playwright NotImplementedError noise on Windows SelectorEventLoop."""
    exc = context.get("exception")
    if isinstance(exc, NotImplementedError) and "subprocess" in str(context).lower():
        return
    loop.default_exception_handler(context)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    # Startup
    try:
        init_db()
        # Suppress Playwright subprocess errors on Windows
        try:
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(_silent_exception_handler)
        except Exception:
            pass
        try:
            await redis_client.connect()
        except Exception as e:
            logger.warning(f"Redis unavailable at startup: {e}")
        _db = SessionLocal()
        try:
            seed_plans(_db)
        finally:
            _db.close()
    except Exception as e:
        logger.error(f"Startup error: {e}")

    yield

    await redis_client.disconnect()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Enterprise AI Agent Platform with Governance, Risk Management, and Advanced Orchestration",
        lifespan=lifespan,
    )

    from app.core.middleware_config import configure_middleware
    configure_middleware(app)

    # Include routers
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(agents.router, prefix="/api/v1")
    app.include_router(conversations.router, prefix="/api/v1")
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(voice.router, prefix="/api/v1")
    app.include_router(uploads.router, prefix="/api/v1")
    app.include_router(webhooks.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(plans.router, prefix="/api/v1")
    app.include_router(subscriptions.router, prefix="/api/v1")
    app.include_router(billing.router, prefix="/api/v1")
    app.include_router(usage.router, prefix="/api/v1")
    app.include_router(quotas.router, prefix="/api/v1")
    app.include_router(analytics.router, prefix="/api/v1")
    app.include_router(governance.router, prefix="/api/v1")
    app.include_router(hallucination.router, prefix="/api/v1")
    app.include_router(risk.router, prefix="/api/v1")
    app.include_router(organizations.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(products.router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health_check():
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "service": settings.APP_NAME,
        }

    @app.get("/metrics", tags=["observability"])
    async def get_metrics():
        from app.observability.dashboards import dashboard_service
        return dashboard_service.get_overview()

    @app.get("/metrics/saas", tags=["observability"])
    async def get_saas_metrics(
        current_user=Depends(get_current_superuser_optional),
        db: Session = Depends(get_db),
    ):
        from app.billing.analytics import saas_analytics
        return saas_analytics.get_overview(db)

    @app.get("/metrics/prometheus", tags=["observability"])
    async def get_prometheus_metrics():
        from fastapi.responses import PlainTextResponse
        from app.observability.dashboards import dashboard_service
        return PlainTextResponse(dashboard_service.get_prometheus_metrics())

    @app.get("/", tags=["info"])
    async def root():
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "redoc": "/redoc",
            "status": "running",
            "endpoints": {
                "health": "/health",
                "metrics": "/metrics",
                "docs": "/docs",
            }
        }

    add_exception_handlers(app)
    return app


# Create app instance
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )
