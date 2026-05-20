"""Health check routes."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from app.core.redis_client import redis_client
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check(db: Session = Depends(get_db)):
    """Check application health."""
    try:
        # Check database
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    try:
        # Check Redis
        await redis_client.client.ping()
        redis_status = "healthy"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        redis_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "redis": redis_status,
        "version": "1.0.0",
    }


@router.get("/readiness")
async def readiness_check(db: Session = Depends(get_db)):
    """Check if application is ready to serve traffic."""
    try:
        db.execute(text("SELECT 1"))
        return {
            "ready": True,
            "status": "ready",
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "ready": False,
            "status": "not ready",
        }


@router.get("/liveness")
async def liveness_check():
    """Check if application is alive."""
    return {
        "alive": True,
        "status": "alive",
    }
