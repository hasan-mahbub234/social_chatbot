"""Crawl job and related PostgreSQL models."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Boolean, Text, Float, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class CrawlJob(Base):
    """Tracks a full crawl job per organization."""
    __tablename__ = "crawl_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(String(255), nullable=False, index=True)
    start_url = Column(Text, nullable=False)
    status = Column(String(50), default="pending", index=True)
    # pending | queued | crawling | extracting | embedding | completed | failed | cancelled
    max_pages = Column(Integer, default=100)
    max_depth = Column(Integer, default=5)
    max_js_renders = Column(Integer, default=20)
    respect_robots = Column(Boolean, default=True)
    pages_discovered = Column(Integer, default=0)
    pages_crawled = Column(Integer, default=0)
    pages_ingested = Column(Integer, default=0)
    pages_skipped = Column(Integer, default=0)
    pages_failed = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    next_crawl_at = Column(DateTime, nullable=True)
    recrawl_interval_hours = Column(Integer, default=24)
    crawl_budget_seconds = Column(Integer, default=3600)
    result_summary = Column(JSON, nullable=True)


class CrawledPage(Base):
    """Stores metadata for each crawled page."""
    __tablename__ = "crawled_pages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("crawl_jobs.id"), nullable=False, index=True)
    organization_id = Column(String(255), nullable=False, index=True)
    url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=True)
    status_code = Column(Integer, nullable=True)
    content_type = Column(String(100), nullable=True)
    platform = Column(String(50), nullable=True)
    page_type = Column(String(50), nullable=True)
    title = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    etag = Column(String(255), nullable=True)
    last_modified = Column(String(255), nullable=True)
    extraction_quality = Column(Float, nullable=True)
    used_browser = Column(Boolean, default=False)
    s3_raw_key = Column(Text, nullable=True)
    crawl_depth = Column(Integer, default=0)
    crawled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    chunks_created = Column(Integer, default=0)
    # V2: completeness tracking
    completeness_score = Column(Float, nullable=True)          # 0.0-1.0 entity completeness
    extraction_sources = Column(JSON, nullable=True)           # ["shopify_json", "hydration", ...]


class CrawlError(Base):
    """Logs per-URL crawl errors."""
    __tablename__ = "crawl_errors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("crawl_jobs.id"), nullable=False, index=True)
    organization_id = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    error_type = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    status_code = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CrawlMetric(Base):
    """Aggregated crawl metrics per job."""
    __tablename__ = "crawl_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("crawl_jobs.id"), nullable=False, index=True)
    organization_id = Column(String(255), nullable=False)
    pages_per_minute = Column(Float, default=0.0)
    avg_fetch_time_ms = Column(Float, default=0.0)
    avg_extraction_quality = Column(Float, default=0.0)
    browser_render_count = Column(Integer, default=0)
    duplicate_ratio = Column(Float, default=0.0)
    success_rate = Column(Float, default=0.0)
    total_bytes_fetched = Column(Integer, default=0)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
