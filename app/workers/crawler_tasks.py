"""Crawler Celery tasks — distributed workers for URL discovery, fetch, extraction, embedding."""
import asyncio
import uuid
from datetime import datetime, timedelta
from app.workers.celery_config import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger

logger = get_logger(__name__)


def _get_or_create_loop():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


# ── Primary crawl task ────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=2, queue="crawler",
                 name="app.workers.crawler_tasks.crawl_website")
def crawl_website(
    self,
    url: str,
    organization_id: str,
    max_pages: int = 100,
    max_depth: int = 5,
    max_js_renders: int = 20,
    respect_robots: bool = True,
):
    """Full website crawl — discovery → fetch → extract → ingest into RAG."""
    from app.crawler.engine import crawler_engine
    from app.models.crawl_job import CrawlJob

    job_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        # Create DB job record
        job = CrawlJob(
            id=job_id,
            organization_id=organization_id,
            start_url=url,
            status="crawling",
            max_pages=max_pages,
            max_depth=max_depth,
            max_js_renders=max_js_renders,
            respect_robots=respect_robots,
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()

        loop = _get_or_create_loop()
        result = loop.run_until_complete(
            crawler_engine.crawl(
                start_url=url,
                organization_id=organization_id,
                db=db,
                job_id=job_id,
                max_pages=max_pages,
                max_depth=max_depth,
                max_js_renders=max_js_renders,
                respect_robots=respect_robots,
            )
        )

        # Update job to completed
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.pages_ingested = result.get("pages_ingested", 0)
        job.pages_skipped = result.get("pages_skipped", 0)
        job.pages_failed = result.get("errors", 0)
        job.next_crawl_at = datetime.utcnow() + timedelta(hours=24)
        job.result_summary = result
        db.commit()

        logger.info("crawl_task_completed", job_id=job_id, result=result)
        return {"job_id": job_id, "status": "completed", **result}

    except Exception as exc:
        try:
            job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(exc)[:500]
                job.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
        logger.error("crawl_task_failed", job_id=job_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()


# ── Sitemap-only crawl task ───────────────────────────────────────────────

@celery_app.task(queue="crawler", name="app.workers.crawler_tasks.crawl_sitemap")
def crawl_sitemap(url: str, organization_id: str, max_pages: int = 200):
    """Discover all URLs from sitemap and enqueue individual crawl tasks."""
    from app.crawler.sitemap_parser import sitemap_parser

    loop = _get_or_create_loop()
    urls = loop.run_until_complete(sitemap_parser.get_urls(url))
    logger.info("sitemap_urls_found", count=len(urls), base_url=url)

    # Enqueue individual page crawls
    for page_url in urls[:max_pages]:
        crawl_website.delay(page_url, organization_id, max_pages=1, max_depth=0)

    return {"sitemap_url": url, "urls_enqueued": min(len(urls), max_pages)}


# ── Scheduled re-crawl task ───────────────────────────────────────────────

@celery_app.task(queue="crawler", name="app.workers.crawler_tasks.recrawl_scheduled")
def recrawl_scheduled(organization_id: str):
    """Re-crawl all completed jobs that are past their recrawl interval."""
    from app.models.crawl_job import CrawlJob

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        due_jobs = (
            db.query(CrawlJob)
            .filter(
                CrawlJob.organization_id == organization_id,
                CrawlJob.status == "completed",
                CrawlJob.next_crawl_at <= now,
            )
            .all()
        )
        scheduled = 0
        for job in due_jobs:
            crawl_website.delay(
                job.start_url,
                organization_id,
                max_pages=job.max_pages,
                max_depth=job.max_depth,
                max_js_renders=job.max_js_renders,
            )
            scheduled += 1
            logger.info("recrawl_scheduled", url=job.start_url, org=organization_id)

        return {"scheduled": scheduled}
    finally:
        db.close()


# ── Crawl job status query (sync helper) ─────────────────────────────────

@celery_app.task(queue="crawler", name="app.workers.crawler_tasks.recrawl_incomplete_products")
def recrawl_incomplete_products(completeness_threshold: float = 0.75, limit: int = 50):
    """
    Find all product pages with completeness_score below threshold
    across all orgs and re-queue them for deep extraction.
    """
    from app.models.crawl_job import CrawledPage
    from sqlalchemy import text

    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT DISTINCT ON (organization_id, url)
                    organization_id, url
                FROM crawled_pages
                WHERE completeness_score < :threshold
                  AND completeness_score IS NOT NULL
                ORDER BY organization_id, url, crawled_at DESC
                LIMIT :limit
            """),
            {"threshold": completeness_threshold, "limit": limit},
        ).fetchall()

        queued = 0
        for row in rows:
            org_id, url = row[0], row[1]
            crawl_website.delay(url, org_id, max_pages=1, max_depth=0, max_js_renders=1)
            queued += 1
            logger.info("incomplete_product_requeued", url=url, org=org_id)

        return {"queued": queued, "threshold": completeness_threshold}
    finally:
        db.close()


def get_job_status(job_id: str) -> dict:
    """Fetch crawl job status from DB."""
    from app.models.crawl_job import CrawlJob
    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        if not job:
            return {"error": "job_not_found"}
        return {
            "job_id": str(job.id),
            "status": job.status,
            "start_url": job.start_url,
            "pages_ingested": job.pages_ingested,
            "pages_skipped": job.pages_skipped,
            "pages_failed": job.pages_failed,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "result_summary": job.result_summary,
        }
    finally:
        db.close()
