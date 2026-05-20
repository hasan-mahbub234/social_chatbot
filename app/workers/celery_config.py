"""Celery configuration — all queues, routes, and beat schedule."""
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "ai_agent_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
)

celery_app.conf.task_routes = {
    "app.workers.tasks.*": {"queue": "ai_processing"},
    "app.workers.embedding_tasks.*": {"queue": "embeddings"},
    "app.workers.crawler_tasks.*": {"queue": "crawler"},
    "app.workers.governance_tasks.*": {"queue": "governance"},
    "app.workers.hallucination_tasks.*": {"queue": "hallucination"},
    "app.workers.risk_tasks.*": {"queue": "risk_assessment"},
    "app.workers.analytics_tasks.*": {"queue": "analytics"},
    "app.workers.cleanup_tasks.*": {"queue": "cleanup"},
    "app.workers.voice_tasks.*": {"queue": "ai_processing"},
}

# Periodic tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    "cleanup-expired-cache": {
        "task": "app.workers.cleanup_tasks.cleanup_expired_cache",
        "schedule": 3600.0,
    },
    "aggregate-analytics": {
        "task": "app.workers.analytics_tasks.aggregate_daily_metrics",
        "schedule": 86400.0,
    },
    "cleanup-old-conversations": {
        "task": "app.workers.cleanup_tasks.cleanup_old_conversations",
        "schedule": 86400.0,
    },
    "cleanup-old-usage-logs": {
        "task": "app.workers.cleanup_tasks.cleanup_old_usage_logs",
        "schedule": 86400.0,
    },
    # Crawler beat tasks
    "crawler-recrawl-check": {
        "task": "app.workers.crawler_tasks.recrawl_scheduled",
        "schedule": 3600.0,
        "kwargs": {},
    },
    # Phase 2: re-crawl incomplete products every 6 hours
    "crawler-incomplete-recrawl": {
        "task": "app.workers.crawler_tasks.recrawl_incomplete_products",
        "schedule": 21600.0,
    },
}
