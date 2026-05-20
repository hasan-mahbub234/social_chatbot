"""RAG sync manager — handles document re-indexing and sync state tracking."""
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.logging import get_logger

logger = get_logger(__name__)


class RAGSyncManager:
    """Manage document sync state for RAG pipeline."""

    async def sync_document(
        self,
        content: str,
        source: str,
        organization_id: str,
        db: Session,
        metadata: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Sync a document — ingest if new or changed."""
        from app.rag.ingestion import document_ingestion
        from app.crawler.page_hashing import page_hasher

        if not force and page_hasher.is_unchanged(source, content):
            logger.info("rag_sync_skipped_unchanged", source=source)
            return {"status": "skipped", "source": source, "reason": "unchanged"}

        result = await document_ingestion.ingest(
            content=content,
            organization_id=organization_id,
            db=db,
            source=source,
            metadata=metadata or {},
        )
        page_hasher.store(source, content)
        logger.info("rag_sync_completed", source=source, chunks=result["chunks_created"])
        return {"status": "synced", "source": source, **result}

    async def sync_batch(
        self,
        documents: List[Dict[str, Any]],
        organization_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Sync multiple documents."""
        synced = 0
        skipped = 0
        errors = 0

        for doc in documents:
            try:
                result = await self.sync_document(
                    content=doc["content"],
                    source=doc.get("source", ""),
                    organization_id=organization_id,
                    db=db,
                    metadata=doc.get("metadata"),
                )
                if result["status"] == "synced":
                    synced += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("rag_sync_doc_failed", source=doc.get("source"), error=str(e))
                errors += 1

        return {"synced": synced, "skipped": skipped, "errors": errors}

    async def delete_source(self, source: str, organization_id: str, db: Session) -> int:
        """Delete all chunks from a specific source."""
        from sqlalchemy import text
        try:
            result = db.execute(
                text("DELETE FROM document_chunks WHERE organization_id = :org AND source = :source"),
                {"org": organization_id, "source": source},
            )
            db.commit()
            deleted = result.rowcount
            logger.info("rag_source_deleted", source=source, chunks=deleted)
            return deleted
        except Exception as e:
            logger.error("rag_delete_source_failed", error=str(e))
            db.rollback()
            return 0


rag_sync_manager = RAGSyncManager()
