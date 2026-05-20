"""Crawler sync manager — tracks crawl jobs and schedules re-crawls."""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.logging import get_logger

logger = get_logger(__name__)

# In-memory crawl job registry (replace with DB in production)
_crawl_jobs: Dict[str, Dict[str, Any]] = {}


class CrawlerSyncManager:
    """Manage crawl job state and re-crawl scheduling."""

    def register_job(self, job_id: str, url: str, organization_id: str) -> Dict[str, Any]:
        """Register a new crawl job."""
        job = {
            "job_id": job_id,
            "url": url,
            "organization_id": organization_id,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "result": None,
        }
        _crawl_jobs[job_id] = job
        logger.info("crawl_job_registered", job_id=job_id, url=url)
        return job

    def update_job(self, job_id: str, status: str, result: Optional[Dict] = None):
        """Update crawl job status."""
        if job_id in _crawl_jobs:
            _crawl_jobs[job_id]["status"] = status
            if result:
                _crawl_jobs[job_id]["result"] = result
            if status in ("completed", "failed"):
                _crawl_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get crawl job by ID."""
        return _crawl_jobs.get(job_id)

    def list_jobs(self, organization_id: str) -> list:
        """List all crawl jobs for an organization."""
        return [j for j in _crawl_jobs.values() if j["organization_id"] == organization_id]

    def should_recrawl(self, url: str, interval_hours: int = 24) -> bool:
        """Check if a URL should be re-crawled based on interval."""
        for job in _crawl_jobs.values():
            if job["url"] == url and job["status"] == "completed" and job["completed_at"]:
                completed = datetime.fromisoformat(job["completed_at"])
                if datetime.utcnow() - completed < timedelta(hours=interval_hours):
                    return False
        return True


crawler_sync_manager = CrawlerSyncManager()