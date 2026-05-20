"""Embedding background tasks."""
from app.workers.celery_config import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger
import asyncio

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, queue="embeddings")
def embed_document(self, file_id: str, organization_id: str):
    """Embed and index an uploaded document."""
    db = SessionLocal()
    try:
        from app.models.uploaded_file import UploadedFile
        from app.rag.ingestion import document_ingestion

        file = db.query(UploadedFile).filter(UploadedFile.id == file_id).first()
        if not file:
            logger.warning("embed_document_file_not_found", file_id=file_id)
            return {"status": "not_found"}

        # Read content from storage (simplified — in prod read from S3)
        content = file.content_preview or ""
        if not content:
            return {"status": "no_content"}

        result = asyncio.get_event_loop().run_until_complete(
            document_ingestion.ingest(
                content=content,
                organization_id=organization_id,
                db=db,
                source=file.filename,
            )
        )

        file.is_indexed = True
        file.processed_chunks = str(result["chunks_created"])
        db.commit()

        logger.info("document_embedded", file_id=file_id, chunks=result["chunks_created"])
        return {"status": "success", "chunks": result["chunks_created"]}
    except Exception as exc:
        logger.error("embed_document_failed", file_id=file_id, error=str(exc))
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    finally:
        db.close()


@celery_app.task(queue="embeddings")
def batch_embed_documents(file_ids: list, organization_id: str):
    """Embed multiple documents."""
    results = []
    for file_id in file_ids:
        result = embed_document.delay(file_id, organization_id)
        results.append(result.id)
    return {"status": "queued", "task_ids": results}
