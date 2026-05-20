"""Cleanup background tasks."""
from app.workers.celery_config import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger
from datetime import datetime, timedelta

logger = get_logger(__name__)


@celery_app.task(queue="cleanup")
def cleanup_old_conversations(days: int = 90):
    """Archive conversations older than N days."""
    db = SessionLocal()
    try:
        from app.models.conversation import Conversation
        cutoff = datetime.utcnow() - timedelta(days=days)
        count = db.query(Conversation).filter(
            Conversation.created_at < cutoff,
            Conversation.is_archived == False,
        ).update({"is_archived": True})
        db.commit()
        logger.info("conversations_archived", count=count)
        return {"archived": count}
    except Exception as exc:
        logger.error("cleanup_conversations_failed", error=str(exc))
        return {"error": str(exc)}
    finally:
        db.close()


@celery_app.task(queue="cleanup")
def cleanup_expired_cache():
    """Remove expired cache entries from DB (alias used by beat schedule)."""
    return cleanup_expired_cache_entries()


@celery_app.task(queue="cleanup")
def cleanup_expired_cache_entries():
    """Remove expired cache entries from DB."""
    db = SessionLocal()
    try:
        from app.models.cache_entry import CacheEntry
        count = db.query(CacheEntry).filter(
            CacheEntry.expires_at < datetime.utcnow()
        ).delete()
        db.commit()
        logger.info("cache_entries_cleaned", count=count)
        return {"deleted": count}
    except Exception as exc:
        logger.error("cleanup_cache_failed", error=str(exc))
        return {"error": str(exc)}
    finally:
        db.close()


@celery_app.task(queue="cleanup")
def cleanup_old_usage_logs(days: int = 180):
    """Delete usage logs older than N days."""
    db = SessionLocal()
    try:
        from app.models.usage import UsageLog
        cutoff = datetime.utcnow() - timedelta(days=days)
        count = db.query(UsageLog).filter(UsageLog.created_at < cutoff).delete()
        db.commit()
        logger.info("usage_logs_cleaned", count=count)
        return {"deleted": count}
    except Exception as exc:
        logger.error("cleanup_usage_logs_failed", error=str(exc))
        return {"error": str(exc)}
    finally:
        db.close()
