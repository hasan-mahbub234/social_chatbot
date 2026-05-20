"""Knowledge ingestion API — website crawl + file upload into RAG."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.tenancy.context import tenant_resolver
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}


class CrawlRequest(BaseModel):
    url: HttpUrl
    agent_id: str = ""


class BulkCrawlRequest(BaseModel):
    urls: list[HttpUrl]
    agent_id: str = ""


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_text(content: bytes, content_type: str, filename: str) -> str:
    """Extract plain text from uploaded file bytes."""
    if "pdf" in content_type:
        try:
            import io
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            raise HTTPException(status_code=422, detail="pypdf not installed — cannot parse PDF")

    if "wordprocessingml" in content_type or filename.endswith(".docx"):
        try:
            import io
            import docx
            doc = docx.Document(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            raise HTTPException(status_code=422, detail="python-docx not installed — cannot parse DOCX")

    return content.decode("utf-8", errors="ignore")


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/crawl")
async def crawl_website(
    body: CrawlRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a website URL for crawling via Celery. Available on all plans."""
    org_id = str(current_user.organization_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="User must belong to an organization")

    tenant = tenant_resolver.resolve(org_id, db)
    max_pages = tenant.plan.limits.max_crawl_pages

    # Try Celery first, fall back to sync if worker not running
    try:
        from app.workers.crawler_tasks import crawl_website as crawl_task
        from app.workers.celery_config import celery_app
        # Check if any worker is active before queuing
        inspector = celery_app.control.inspect(timeout=1.0)
        active_workers = inspector.active()
        if active_workers:
            task = crawl_task.delay(str(body.url), org_id, max_pages)
            logger.info("crawl_queued", org=org_id, url=str(body.url), task_id=task.id)
            return {
                "status": "queued",
                "task_id": task.id,
                "url": str(body.url),
                "max_pages": max_pages,
                "plan": tenant.plan_name,
                "message": f"Crawling up to {max_pages} pages in background. Use task_id to check status.",
            }
        raise RuntimeError("No Celery workers available")
    except Exception:
        # Celery worker not running — run synchronously
        logger.info("crawl_sync_fallback", org=org_id, url=str(body.url))
        from app.crawler.engine import crawler_engine
        result = await crawler_engine.crawl(
            start_url=str(body.url),
            organization_id=org_id,
            db=db,
            max_pages=max_pages,
        )
        logger.info("crawl_sync_done", org=org_id, **result)
        return {
            "status": "completed",
            "task_id": None,
            "url": str(body.url),
            "max_pages": max_pages,
            "plan": tenant.plan_name,
            "pages_ingested": result.get("pages_ingested", 0),
            "pages_visited": result.get("pages_visited", 0),
            "message": "Crawled synchronously (Celery worker not running).",
        }


@router.get("/crawl/{task_id}")
async def crawl_status(task_id: str, current_user=Depends(get_current_user)):
    """Check the status of a crawl task."""
    from app.workers.celery_config import celery_app
    task = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task.status,
        "result": task.result if task.ready() else None,
    }


@router.post("/upload")
async def upload_business_data(
    file: UploadFile = File(...),
    agent_id: str = "",
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload PDF, DOCX, or TXT — saves file record then queues embedding via Celery."""
    org_id = str(current_user.organization_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="User must belong to an organization")

    content_type = file.content_type or ""
    filename = file.filename or ""

    if content_type not in SUPPORTED_MIME_TYPES and not filename.endswith((".pdf", ".docx", ".txt", ".md")):
        raise HTTPException(status_code=415, detail="Unsupported file type. Supported: PDF, DOCX, TXT, Markdown")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    tenant = tenant_resolver.resolve(org_id, db)
    max_bytes = tenant.plan.limits.max_storage_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds plan storage limit of {tenant.plan.limits.max_storage_mb}MB",
        )

    text = _extract_text(content, content_type, filename)
    if not text or len(text.strip()) < 50:
        raise HTTPException(status_code=422, detail="Could not extract meaningful text from file")

    # Save uploaded file record to DB
    from app.models.uploaded_file import UploadedFile
    from uuid import uuid4
    file_record = UploadedFile(
        organization_id=org_id,
        agent_id=agent_id or None,
        filename=filename,
        file_type=content_type or "text/plain",
        file_size=len(content),
        storage_path=f"uploads/{org_id}/{uuid4()}",
    )
    # Store text preview for Celery worker to use
    if hasattr(file_record, "content_preview"):
        file_record.content_preview = text[:10000]
    db.add(file_record)
    db.commit()
    db.refresh(file_record)

    # Queue embedding via Celery
    from app.workers.embedding_tasks import embed_document
    task = embed_document.delay(str(file_record.id), org_id)

    # Also ingest synchronously as fallback (Celery may not be running in dev)
    try:
        from app.rag.ingestion import document_ingestion
        result = await document_ingestion.ingest(
            content=text,
            organization_id=org_id,
            db=db,
            source=filename,
            metadata={"filename": filename, "type": "upload", "agent_id": agent_id},
        )
        chunks = result["chunks_created"]
    except Exception:
        chunks = 0

    logger.info("file_upload_queued", org=org_id, filename=filename, task_id=task.id)
    return {
        "status": "ingested",
        "file_id": str(file_record.id),
        "task_id": task.id,
        "filename": filename,
        "chunks_created": chunks,
        "plan": tenant.plan_name,
    }


@router.delete("/cache")
async def clear_semantic_cache(
    current_user=Depends(get_current_user),
):
    """Clear all semantic cache entries (use after system prompt or crawler changes)."""
    from app.cache.semantic_cache import semantic_cache
    await semantic_cache.clear_all()
    return {"status": "cleared"}


@router.delete("/all")
async def delete_all_knowledge(
    delete_s3: bool = True,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete ALL vector chunks for the organization. Also deletes raw HTML from S3 by default."""
    org_id = str(current_user.organization_id)
    try:
        from sqlalchemy import text

        # Collect S3 keys before deleting DB rows
        s3_keys = []
        if delete_s3:
            rows = db.execute(
                text("SELECT s3_raw_key FROM crawled_pages WHERE organization_id = :org AND s3_raw_key IS NOT NULL"),
                {"org": org_id},
            ).fetchall()
            s3_keys = [r[0] for r in rows if r[0]]

        # Delete vector chunks
        result = db.execute(
            text("DELETE FROM document_chunks WHERE organization_id = :org"),
            {"org": org_id},
        )
        # Delete crawled_pages records
        db.execute(
            text("DELETE FROM crawled_pages WHERE organization_id = :org"),
            {"org": org_id},
        )
        db.commit()

        # Delete S3 raw HTML objects
        s3_deleted = 0
        s3_errors = 0
        if delete_s3 and s3_keys:
            from app.integrations.s3 import s3_service
            for key in s3_keys:
                try:
                    await s3_service.delete(key)
                    s3_deleted += 1
                except Exception as e:
                    logger.warning("s3_delete_failed_on_knowledge_clear", key=key, error=str(e))
                    s3_errors += 1

        # Clear page hashes and semantic cache
        from app.crawler.page_hashing import page_hasher
        page_hasher.clear_org(org_id)
        from app.cache.semantic_cache import semantic_cache
        await semantic_cache.clear_all()

        deleted = result.rowcount
        logger.info("knowledge_all_deleted", org=org_id, deleted=deleted, s3_deleted=s3_deleted)
        return {
            "status": "deleted",
            "chunks_deleted": deleted,
            "s3_objects_deleted": s3_deleted,
            "s3_errors": s3_errors,
        }
    except Exception as e:
        db.rollback()
        logger.error("knowledge_delete_all_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to delete all knowledge")


@router.post("/crawl/bulk")
async def bulk_crawl(
    body: BulkCrawlRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crawl multiple URLs sequentially and ingest into RAG."""
    org_id = str(current_user.organization_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="User must belong to an organization")

    tenant = tenant_resolver.resolve(org_id, db)
    max_pages = tenant.plan.limits.max_crawl_pages
    from app.crawler.engine import crawler_engine

    results = []
    for url in body.urls:
        url_str = str(url)
        try:
            result = await crawler_engine.crawl(
                start_url=url_str,
                organization_id=org_id,
                db=db,
                max_pages=max_pages,
            )
            results.append({"url": url_str, "status": "ok", **result})
            logger.info("bulk_crawl_url_done", url=url_str, org=org_id)
        except Exception as e:
            logger.error("bulk_crawl_url_failed", url=url_str, error=str(e))
            results.append({"url": url_str, "status": "error", "error": str(e)})

    total_ingested = sum(r.get("pages_ingested", 0) for r in results)
    return {"status": "completed", "total_ingested": total_ingested, "results": results}


@router.delete("/source")
async def delete_knowledge_source(
    source: str,
    delete_s3: bool = True,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete all RAG chunks for a given source (URL or filename). Also deletes S3 raw HTML by default."""
    org_id = str(current_user.organization_id)
    try:
        from sqlalchemy import text

        # Collect S3 key for this source before deleting
        s3_key = None
        if delete_s3:
            row = db.execute(
                text("SELECT s3_raw_key FROM crawled_pages WHERE organization_id = :org AND url = :src LIMIT 1"),
                {"org": org_id, "src": source},
            ).fetchone()
            if row and row[0]:
                s3_key = row[0]

        db.execute(
            text("DELETE FROM document_chunks WHERE organization_id = :org AND source = :src"),
            {"org": org_id, "src": source},
        )
        db.execute(
            text("DELETE FROM crawled_pages WHERE organization_id = :org AND url = :src"),
            {"org": org_id, "src": source},
        )
        db.commit()

        s3_deleted = False
        if s3_key:
            try:
                from app.integrations.s3 import s3_service
                await s3_service.delete(s3_key)
                s3_deleted = True
            except Exception as e:
                logger.warning("s3_delete_failed_on_source_delete", key=s3_key, error=str(e))

        logger.info("knowledge_source_deleted", org=org_id, source=source, s3_deleted=s3_deleted)
        return {"status": "deleted", "source": source, "s3_deleted": s3_deleted}
    except Exception as e:
        db.rollback()
        logger.error("knowledge_delete_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to delete knowledge source")


@router.get("/sources")
async def list_knowledge_sources(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all ingested knowledge sources for the organization."""
    org_id = str(current_user.organization_id)
    try:
        from sqlalchemy import text
        rows = db.execute(
            text("""
                SELECT source, COUNT(*) as chunks, MAX(created_at) as last_updated
                FROM document_chunks
                WHERE organization_id = :org
                GROUP BY source
                ORDER BY last_updated DESC
            """),
            {"org": org_id},
        ).fetchall()
        return {
            "sources": [
                {"source": r[0], "chunks": r[1], "last_updated": str(r[2])}
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("knowledge_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list knowledge sources")
