"""Vector store — pgvector-backed document storage and search."""
import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.rag.embeddings import rag_embeddings
from app.core.logging import get_logger

logger = get_logger(__name__)


class VectorStore:
    """Store and search document embeddings using pgvector."""

    def _raw(self, db: Session):
        """Return the underlying psycopg2 connection."""
        return db.connection().connection

    async def upsert(
        self,
        db: Session,
        content: str,
        embedding: List[float],
        organization_id: str,
        metadata: Dict[str, Any],
    ) -> str:
        """
        Insert a document chunk.

        Does NOT pass an explicit id — lets the DB default (uuid_generate_v4()
        or serial) generate it, avoiding type-mismatch errors when the live
        schema differs from init.sql.

        Uses raw psycopg2 %s placeholders to avoid SQLAlchemy text() colon
        scanning issues with content that contains 'Sources: shopify_json'.
        """
        try:
            embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
            source = str(metadata.get("source", ""))
            chunk_index = int(metadata.get("chunk_index", 0))
            metadata_json = json.dumps(metadata, ensure_ascii=False)

            conn = self._raw(db)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO document_chunks
                        (organization_id, content, embedding,
                         source, chunk_index, metadata)
                    VALUES
                        (%s, %s, %s::vector, %s, %s, %s::jsonb)
                    RETURNING id
                    """,
                    (
                        organization_id,
                        content,
                        embedding_str,
                        source,
                        chunk_index,
                        metadata_json,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return str(row[0]) if row else ""
        except Exception as e:
            logger.error("vector_store_upsert_failed", error=str(e))
            try:
                self._raw(db).rollback()
            except Exception:
                db.rollback()
            raise

    async def search(
        self,
        db: Session,
        query_embedding: List[float],
        organization_id: str,
        top_k: int = 5,
        threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks using cosine similarity."""
        try:
            embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
            conn = self._raw(db)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, content, source, chunk_index, metadata,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM document_chunks
                    WHERE organization_id = %s
                      AND 1 - (embedding <=> %s::vector) >= %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (
                        embedding_str,
                        organization_id,
                        embedding_str,
                        threshold,
                        embedding_str,
                        top_k,
                    ),
                )
                rows = cur.fetchall()
            return [
                {
                    "id":          str(row[0]),
                    "content":     row[1],
                    "source":      row[2],
                    "chunk_index": row[3],
                    "metadata":    row[4],
                    "similarity":  float(row[5]),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error("vector_store_search_failed", error=str(e))
            return []


vector_store = VectorStore()
