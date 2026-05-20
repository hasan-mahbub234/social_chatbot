"""
Parent Retriever — fetches parent chunks when child chunks are retrieved.

The chunker stores parent_chunk_index on every chunk. When a small child
chunk is retrieved (e.g. "100% POLYESTER WOVEN"), this retriever fetches
the parent chunk (the full product spec block) for richer LLM context.

This is how Anthropic, Cursor, and Perplexity work internally:
  - Retrieve small chunks for precision (high recall)
  - Return parent chunks for context (high quality answers)
"""
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.logging import get_logger

logger = get_logger(__name__)

# Max parent chunks to fetch per retrieval call
MAX_PARENT_CHUNKS = 10


class ParentRetriever:
    """
    Fetch parent chunks for retrieved child chunks.

    When chunk_with_metadata() splits a large section into child chunks,
    it stores parent_chunk_index. This retriever uses that index to fetch
    the full parent section for LLM context injection.
    """

    def fetch_parents(
        self,
        child_chunks: List[Dict[str, Any]],
        organization_id: str,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """
        For each child chunk that has a parent_chunk_index, fetch the parent.
        Returns a merged list: parent chunks replace their children.
        Chunks without parent_chunk_index are returned unchanged.
        """
        if not child_chunks:
            return child_chunks

        # Separate chunks with and without parent references
        has_parent = []
        no_parent = []
        for chunk in child_chunks:
            meta = chunk.get("metadata") or {}
            if meta.get("parent_chunk_index") is not None and chunk.get("source"):
                has_parent.append(chunk)
            else:
                no_parent.append(chunk)

        if not has_parent:
            return child_chunks

        # Fetch parent chunks grouped by (source, parent_chunk_index)
        parent_keys = set()
        for chunk in has_parent:
            meta = chunk.get("metadata") or {}
            key = (chunk["source"], int(meta["parent_chunk_index"]))
            parent_keys.add(key)

        fetched_parents: List[Dict[str, Any]] = []
        seen_parent_keys = set()

        for source, parent_idx in list(parent_keys)[:MAX_PARENT_CHUNKS]:
            if (source, parent_idx) in seen_parent_keys:
                continue
            seen_parent_keys.add((source, parent_idx))

            parent = self._fetch_parent_chunk(source, parent_idx, organization_id, db)
            if parent:
                fetched_parents.append(parent)

        # Build result: parents first (for context), then chunks without parents
        result = fetched_parents + no_parent

        # Deduplicate by chunk id
        seen_ids = set()
        deduped = []
        for chunk in result:
            cid = chunk.get("id", "")
            if cid not in seen_ids:
                seen_ids.add(cid)
                deduped.append(chunk)

        logger.debug(
            "parent_chunks_fetched",
            child_count=len(has_parent),
            parent_count=len(fetched_parents),
        )
        return deduped

    def _fetch_parent_chunk(
        self,
        source: str,
        parent_chunk_index: int,
        organization_id: str,
        db: Session,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a specific parent chunk by source + parent_chunk_index."""
        try:
            sql = text("""
                SELECT id, content, source, chunk_index, metadata, 0.95 AS similarity
                FROM document_chunks
                WHERE organization_id = :org
                  AND source = :source
                  AND chunk_index = :parent_idx
                LIMIT 1
            """)
            row = db.execute(sql, {
                "org": organization_id,
                "source": source,
                "parent_idx": parent_chunk_index,
            }).fetchone()

            if row:
                return {
                    "id":          str(row[0]),
                    "content":     row[1],
                    "source":      row[2],
                    "chunk_index": row[3],
                    "metadata":    row[4] or {},
                    "similarity":  float(row[5]),
                    "is_parent":   True,
                }
        except Exception as e:
            logger.warning("parent_chunk_fetch_failed", source=source, error=str(e))
        return None

    def expand_with_siblings(
        self,
        chunk: Dict[str, Any],
        organization_id: str,
        db: Session,
        window: int = 1,
    ) -> str:
        """
        Fetch adjacent chunks (siblings) around a chunk for sliding window context.
        Returns merged content string.
        """
        source = chunk.get("source", "")
        chunk_index = chunk.get("chunk_index", 0)
        if not source:
            return chunk.get("content", "")

        try:
            sql = text("""
                SELECT content, chunk_index
                FROM document_chunks
                WHERE organization_id = :org
                  AND source = :source
                  AND chunk_index BETWEEN :start AND :end
                ORDER BY chunk_index ASC
            """)
            rows = db.execute(sql, {
                "org": organization_id,
                "source": source,
                "start": max(0, chunk_index - window),
                "end": chunk_index + window,
            }).fetchall()

            if rows:
                return "\n\n".join(r[0] for r in rows)
        except Exception as e:
            logger.warning("sibling_fetch_failed", source=source, error=str(e))

        return chunk.get("content", "")


parent_retriever = ParentRetriever()
