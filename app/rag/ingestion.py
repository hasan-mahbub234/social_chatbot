"""Document ingestion pipeline for RAG."""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.rag.chunker import text_chunker
from app.rag.embeddings import rag_embeddings
from app.rag.vector_store import vector_store
from app.core.logging import get_logger

logger = get_logger(__name__)


class DocumentIngestion:
    """Ingest documents into the RAG vector store."""

    def _build_context_header(self, chunk_meta: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """
        Build a short context header prepended to each chunk before embedding.
        The header is NOT stored — only used to produce a richer embedding vector.

        Anthropic-style contextual retrieval: embedding the chunk in isolation
        loses surrounding context (e.g. '100% POLYESTER WOVEN' has no product name).
        Prepending title/type/platform dramatically improves recall for attribute chunks.
        """
        parts = []
        title = metadata.get("title", "")
        content_type = metadata.get("type", "") or metadata.get("content_type", "")
        platform = metadata.get("platform", "")
        source = metadata.get("source", "") or metadata.get("url", "")
        chunk_type = chunk_meta.get("chunk_type", "")

        if title:
            parts.append(f"Title: {title}")
        if content_type:
            parts.append(f"Type: {content_type}")
        if platform:
            parts.append(f"Platform: {platform}")
        if source:
            # Only include the path portion to keep header short
            from urllib.parse import urlparse
            try:
                path = urlparse(source).path.rstrip("/")
                if path:
                    parts.append(f"Source: {path}")
            except Exception:
                pass
        if chunk_type:
            parts.append(f"Section: {chunk_type}")

        return "\n".join(parts) + "\n\n" if parts else ""

    async def ingest(
        self,
        content: str,
        organization_id: str,
        db: Session,
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ) -> Dict[str, Any]:
        """Chunk, embed (with contextual header), and store a document."""
        from app.rag.chunker import TextChunker
        from app.core.constants import MAX_CHUNK_SIZE, CHUNK_OVERLAP
        chunker = TextChunker(
            chunk_size=chunk_size or MAX_CHUNK_SIZE,
            overlap=chunk_overlap or CHUNK_OVERLAP,
        )
        meta = metadata or {}
        content_type = meta.get("type", "page")
        chunks_with_meta = chunker.chunk_with_metadata(content, source=source, content_type=content_type)

        # Build contextual versions for embedding — original content is stored unchanged
        contextual_texts = [
            self._build_context_header(c, meta) + c["content"]
            for c in chunks_with_meta
        ]
        embeddings = await rag_embeddings.embed_chunks(contextual_texts)

        stored_ids = []
        for chunk_meta, embedding in zip(chunks_with_meta, embeddings):
            chunk_metadata = {**meta, **chunk_meta}
            chunk_id = await vector_store.upsert(
                db=db,
                content=chunk_meta["content"],   # store original, not contextual
                embedding=embedding,              # embed contextual version
                organization_id=organization_id,
                metadata=chunk_metadata,
            )
            stored_ids.append(chunk_id)

        logger.info("document_ingested", chunks=len(stored_ids), source=source)
        return {
            "chunks_created": len(stored_ids),
            "chunk_ids": stored_ids,
            "source": source,
        }


document_ingestion = DocumentIngestion()
