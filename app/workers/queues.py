"""Celery queue definitions."""
from kombu import Queue
from app.core.constants import (
    QUEUE_AI_PROCESSING, QUEUE_EMBEDDINGS, QUEUE_GOVERNANCE,
    QUEUE_RISK, QUEUE_HALLUCINATION, QUEUE_VOICE,
    QUEUE_ANALYTICS, QUEUE_CLEANUP, QUEUE_ESCALATION,
    QUEUE_CRAWLER, QUEUE_CRAWLER_FETCH, QUEUE_CRAWLER_EXTRACT, QUEUE_CRAWLER_EMBED,
)

CELERY_QUEUES = (
    Queue(QUEUE_AI_PROCESSING, routing_key="ai.processing"),
    Queue(QUEUE_EMBEDDINGS, routing_key="embeddings.#"),
    Queue(QUEUE_GOVERNANCE, routing_key="governance.#"),
    Queue(QUEUE_RISK, routing_key="risk.#"),
    Queue(QUEUE_HALLUCINATION, routing_key="hallucination.#"),
    Queue(QUEUE_VOICE, routing_key="voice.#"),
    Queue(QUEUE_ANALYTICS, routing_key="analytics.#"),
    Queue(QUEUE_CLEANUP, routing_key="cleanup.#"),
    Queue(QUEUE_ESCALATION, routing_key="escalation.#"),
    # Crawler queues — each independently scalable
    Queue(QUEUE_CRAWLER, routing_key="crawler.#"),
    Queue(QUEUE_CRAWLER_FETCH, routing_key="crawler.fetch.#"),
    Queue(QUEUE_CRAWLER_EXTRACT, routing_key="crawler.extract.#"),
    Queue(QUEUE_CRAWLER_EMBED, routing_key="crawler.embed.#"),
)

CELERY_TASK_ROUTES = {
    "app.workers.embedding_tasks.*": {"queue": QUEUE_EMBEDDINGS},
    "app.workers.governance_tasks.*": {"queue": QUEUE_GOVERNANCE},
    "app.workers.risk_tasks.*": {"queue": QUEUE_RISK},
    "app.workers.hallucination_tasks.*": {"queue": QUEUE_HALLUCINATION},
    "app.workers.voice_tasks.*": {"queue": QUEUE_VOICE},
    "app.workers.analytics_tasks.*": {"queue": QUEUE_ANALYTICS},
    "app.workers.cleanup_tasks.*": {"queue": QUEUE_CLEANUP},
    "app.workers.crawler_tasks.crawl_website": {"queue": QUEUE_CRAWLER},
    "app.workers.crawler_tasks.crawl_sitemap": {"queue": QUEUE_CRAWLER},
    "app.workers.crawler_tasks.recrawl_scheduled": {"queue": QUEUE_CRAWLER},
}
