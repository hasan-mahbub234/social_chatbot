"""RAG retriever — main retrieval interface."""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.rag.vector_store import vector_store
from app.rag.embeddings import rag_embeddings
from app.rag.metadata_filters import metadata_filters
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RAGRetriever:
    """Retrieve relevant document chunks for a query."""

    async def retrieve(
        self,
        query: str,
        organization_id: str,
        db: Session,
        top_k: int = 5,
        threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Embed query and retrieve top-k similar chunks, with keyword boost."""
        try:
            threshold = threshold or settings.SIMILARITY_THRESHOLD
            query_embedding = await rag_embeddings.embed_query(query)

            results = await vector_store.search(
                db=db,
                query_embedding=query_embedding,
                organization_id=organization_id,
                top_k=top_k,
                threshold=threshold,
            )

            import re as _re

            # Product source pinning: if the top result is a product page,
            # fetch ALL chunks from that exact source URL and pin them first.
            # This ensures material/shipping/variant chunks from the same product
            # are always included even if vector similarity ranks them lower.
            if results:
                top_source = results[0].get("source", "")
                top_meta = results[0].get("metadata") or {}
                is_product = (
                    top_meta.get("type") == "product"
                    or top_meta.get("content_type") == "product"
                    or "/products/" in top_source
                )
                if is_product and top_source:
                    pinned = self._fetch_by_source(top_source, organization_id, db, exact=True)
                    if pinned:
                        pinned_ids = {c["id"] for c in pinned}
                        # Remove duplicates from vector results, prepend pinned
                        results = pinned + [
                            r for r in results if r["id"] not in pinned_ids
                        ]

            # For location queries: fetch ALL chunks from store-locations source directly
            location_keywords = {
                "store", "location", "shop", "branch", "sylhet", "chittagong", "ctg",
                "narayanganj", "mirpur", "gulshan", "dhanmondi", "bashundhara", "wari",
            }
            query_words = set(_re.findall(r'[a-z]+', query.lower()))
            if query_words & location_keywords:
                source_chunks = self._fetch_by_source("store-location", organization_id, db)
                if source_chunks:
                    merged_content = "\n\n".join(c["content"] for c in source_chunks)
                    merged = {
                        "id": source_chunks[0]["id"],
                        "content": merged_content,
                        "source": source_chunks[0]["source"],
                        "chunk_index": 0,
                        "metadata": source_chunks[0]["metadata"],
                        "similarity": 0.95,
                    }
                    results = [r for r in results
                               if "store-location" not in r.get("source", "")]
                    results.insert(0, merged)

            # Keyword boost
            keyword_results = self._keyword_search(query, organization_id, db, top_k)
            if keyword_results:
                existing_ids = {r["id"] for r in results}
                for kr in keyword_results:
                    if kr["id"] not in existing_ids:
                        results.append(kr)
                        existing_ids.add(kr["id"])
                results = sorted(results, key=lambda x: x["similarity"], reverse=True)[:top_k + len(keyword_results)]

            if filters:
                results = metadata_filters.apply(results, filters)

            # Variant deduplication: for simple field queries (price, availability),
            # collapse duplicate product titles — keep highest-similarity chunk per title.
            # For "tell me about" queries, keep all variants so user sees full range.
            _simple_q = bool(_re.search(
                r'\b(how much|price|cost|available|in stock|availability)\b',
                query, _re.I
            ))
            if _simple_q:
                results = self._deduplicate_by_title(results)

            logger.info("rag_retrieved", count=len(results), query_len=len(query))

            # Retrieval observability — track quality metrics per query
            try:
                from app.observability.retrieval_observability import retrieval_observability
                retrieval_observability.record_retrieval(
                    org_id=organization_id,
                    query=query,
                    result_count=len(results),
                    top_similarity=results[0]["similarity"] if results else 0.0,
                    used_bm25=bool(keyword_results),
                    used_reranker=False,
                    from_cache=False,
                )
            except Exception:
                pass  # observability must never break retrieval

            return results
        except Exception as e:
            logger.error("rag_retrieval_failed", error=str(e))
            return []

    def _fetch_by_source(
        self, source_pattern: str, organization_id: str, db: Session,
        exact: bool = False
    ) -> List[Dict[str, Any]]:
        """Fetch all chunks for a source URL. Use exact=True for product pinning."""
        try:
            if exact:
                sql = text("""
                    SELECT id, content, source, chunk_index, metadata, 0.95 AS similarity
                    FROM document_chunks
                    WHERE organization_id = :org AND source = :pattern
                    ORDER BY chunk_index ASC
                    LIMIT 20
                """)
                rows = db.execute(sql, {"org": organization_id, "pattern": source_pattern}).fetchall()
            else:
                sql = text("""
                    SELECT id, content, source, chunk_index, metadata, 0.9 AS similarity
                    FROM document_chunks
                    WHERE organization_id = :org AND source ILIKE :pattern
                    ORDER BY chunk_index ASC
                    LIMIT 20
                """)
                rows = db.execute(sql, {"org": organization_id, "pattern": f"%{source_pattern}%"}).fetchall()
            return [
                {"id": str(r[0]), "content": r[1], "source": r[2],
                 "chunk_index": r[3], "metadata": r[4], "similarity": float(r[5])}
                for r in rows
            ]
        except Exception as e:
            logger.warning("source_fetch_failed", pattern=source_pattern, error=str(e))
            try:
                db.rollback()
            except Exception:
                pass
            return []

    def _keyword_search(
        self, query: str, organization_id: str, db: Session, top_k: int
    ) -> List[Dict[str, Any]]:
        """
        PostgreSQL full-text search using ts_rank — real BM25 equivalent.
        Uses the generated tsvector column + GIN index from migration 004.
        Falls back to ILIKE if the fts column is not yet available.

        IMPORTANT: after a failed BM25 query, PostgreSQL marks the transaction
        as aborted. We must call db.rollback() before the ILIKE fallback,
        otherwise every subsequent query in the same request fails with
        InFailedSqlTransaction.
        """
        # Primary: PostgreSQL FTS with ts_rank (TF-IDF weighted, GIN-indexed)
        try:
            sql = text("""
                SELECT id, content, source, chunk_index, metadata,
                       ts_rank(fts, plainto_tsquery('english', :query)) AS similarity
                FROM document_chunks
                WHERE organization_id = :org
                  AND fts @@ plainto_tsquery('english', :query)
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, {
                "org": organization_id,
                "query": query,
                "limit": top_k * 2,
            }).fetchall()
            if rows is not None:  # empty list is valid — fts column exists
                return [
                    {"id": str(r[0]), "content": r[1], "source": r[2],
                     "chunk_index": r[3], "metadata": r[4], "similarity": float(r[5])}
                    for r in rows
                ]
        except Exception as fts_err:
            # fts column not yet migrated — clear the aborted transaction
            # so subsequent queries in this request are not poisoned.
            logger.warning("bm25_fts_unavailable_falling_back", error=str(fts_err))
            try:
                db.rollback()
            except Exception:
                pass

        # Fallback: ILIKE (used only before migration 004 is applied)
        try:
            import re
            stop = {"what", "when", "where", "which", "have", "does", "your", "their",
                    "this", "that", "with", "from", "about", "available",
                    "price", "there", "now", "much", "many", "tell", "its"}
            words = [w for w in re.findall(r'[a-zA-Z\u0980-\u09FF]{3,}', query.lower())
                     if w not in stop]
            if not words:
                return []
            conditions = " OR ".join([f"content ILIKE :kw{i}" for i in range(len(words))])
            params = {f"kw{i}": f"%{w}%" for i, w in enumerate(words)}
            params["org"] = organization_id
            params["limit"] = top_k * 2
            sql = text(f"""
                SELECT id, content, source, chunk_index, metadata, 0.45 AS similarity
                FROM document_chunks
                WHERE organization_id = :org AND ({conditions})
                ORDER BY chunk_index ASC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            return [
                {"id": str(r[0]), "content": r[1], "source": r[2],
                 "chunk_index": r[3], "metadata": r[4], "similarity": float(r[5])}
                for r in rows
            ]
        except Exception as e:
            logger.warning("keyword_search_failed", error=str(e))
            return []

    def _deduplicate_by_title(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        For price/availability queries, collapse multiple chunks with the same
        product title into one (highest similarity wins).
        Preserves order of first occurrence.
        """
        import re
        seen_titles: dict = {}
        deduped = []
        for r in results:
            meta = r.get("metadata") or {}
            title = str(meta.get("title", "")).strip().lower()
            # Normalise: strip color suffixes like "(Black)", "- Navy"
            title = re.sub(r'\s*[-—(].*$', '', title).strip()
            if not title:
                deduped.append(r)
                continue
            if title not in seen_titles:
                seen_titles[title] = r
                deduped.append(r)
            else:
                # Keep higher similarity
                if r["similarity"] > seen_titles[title]["similarity"]:
                    idx = deduped.index(seen_titles[title])
                    deduped[idx] = r
                    seen_titles[title] = r
        return deduped


rag_retriever = RAGRetriever()
