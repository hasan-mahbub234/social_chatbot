"""
Product Retriever — pgvector retrieval with ProductEntity reconstruction.

Retrieves document chunks from pgvector, reconstructs ProductEntity objects
by merging all chunks for the same canonical URL, applies source priority
ordering, and returns ranked product candidates.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.rag.embeddings import rag_embeddings
from app.rag.reranker import reranker
from app.crawler.entity_model import ProductEntity, FieldValue, ProductVariant, SOURCE_PRIORITY
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Retrieval config
PRODUCT_TOP_K = 20          # fetch more chunks, collapse to entities
ENTITY_TOP_K = 3            # max product entities to return
SIMILARITY_THRESHOLD = 0.45 # lower than default — product queries need recall
PRODUCT_CHUNK_TYPES = {"product_spec", "product"}

# Field confidence by source (mirrors SOURCE_PRIORITY but as 0-1 float)
SOURCE_CONFIDENCE: Dict[str, float] = {
    "shopify_json": 1.00,
    "graphql":      0.95,
    "xhr_api":      0.90,
    "jsonld":       0.80,
    "hydration":    0.70,
    "dom":          0.50,
    "og_meta":      0.30,
    "llm":          0.15,
}


class ProductRetriever:
    """
    Retrieve product entities from pgvector.

    Pipeline:
      1. Embed query
      2. Vector search (top-k chunks)
      3. Keyword boost for product-specific terms
      4. Rerank by query relevance
      5. Group chunks by canonical URL
      6. Reconstruct ProductEntity per URL via source-priority merging
      7. Return top-N entities sorted by completeness × similarity
    """

    async def retrieve(
        self,
        query: str,
        organization_id: str,
        db: Session,
        top_k: int = ENTITY_TOP_K,
    ) -> List[Tuple[ProductEntity, float]]:
        """
        Returns list of (ProductEntity, relevance_score) tuples,
        sorted by relevance descending, capped at top_k.
        """
        # 1. Embed query
        query_embedding = await rag_embeddings.embed_query(query)

        # 2. Vector search
        chunks = await self._vector_search(query_embedding, organization_id, db)

        # 3. Keyword boost
        keyword_chunks = self._keyword_search(query, organization_id, db)
        chunks = self._merge_chunk_lists(chunks, keyword_chunks)

        if not chunks:
            return []

        # 4. Rerank
        chunks = await reranker.rerank(query, chunks, top_k=PRODUCT_TOP_K)

        # 5. Group by canonical URL
        groups = self._group_by_url(chunks)

        # 6. Reconstruct entities
        entities: List[Tuple[ProductEntity, float]] = []
        for canonical_url, url_chunks in groups.items():
            entity = self._reconstruct_entity(canonical_url, url_chunks, organization_id)
            relevance = max(c.get("rerank_score", c.get("similarity", 0)) for c in url_chunks)

            # Knowledge fusion: enrich entity by merging all chunk sources
            # with confidence-aware field resolution and conflict detection
            try:
                from app.services.knowledge_fusion import knowledge_fusion, FusionSource
                fusion_sources = []
                for chunk in url_chunks:
                    meta = chunk.get("metadata") or {}
                    ctype = meta.get("type") or meta.get("content_type", "")
                    source_type = "product_page" if ctype == "product" else "collection_page"
                    field_data = self._extract_meta_fields(meta)
                    if field_data:
                        fusion_sources.append(FusionSource(
                            source_type=source_type,
                            url=chunk.get("source", canonical_url),
                            data=field_data,
                            confidence=1.0 if source_type == "product_page" else 0.6,
                        ))
                if fusion_sources:
                    fusion_result = knowledge_fusion.fuse(
                        canonical_url=canonical_url,
                        organization_id=organization_id,
                        sources=fusion_sources,
                    )
                    entity = fusion_result.entity
            except Exception as fusion_err:
                logger.debug("knowledge_fusion_skipped", url=canonical_url, error=str(fusion_err))

            entities.append((entity, relevance))

        # 7. Sort by relevance × completeness × graph affinity
        from app.crawler.completeness_engine import CompletenessScore
        from app.crawler.entity_graph import entity_graph

        def rank_score(item: Tuple[ProductEntity, float]) -> float:
            entity, relevance = item
            completeness = CompletenessScore(entity).total

            # Graph affinity boost: entities with more graph connections
            # (related products, collection memberships) are ranked higher
            graph_boost = 0.0
            try:
                node_id = entity_graph._url_to_node_id(entity.url)
                neighbors = entity_graph.get_neighbors(
                    organization_id, node_id, max_depth=1
                )
                # Each neighbor adds a small boost, capped at +0.10
                graph_boost = min(0.10, len(neighbors) * 0.02)
            except Exception:
                pass

            # Weighted: relevance 55%, completeness 35%, graph affinity 10%
            return relevance * 0.55 + completeness * 0.35 + graph_boost * 0.10

        entities.sort(key=rank_score, reverse=True)
        return entities[:top_k]

    async def retrieve_by_url(
        self,
        url: str,
        organization_id: str,
        db: Session,
    ) -> Optional[ProductEntity]:
        """Retrieve and reconstruct a ProductEntity for a specific URL."""
        chunks = self._fetch_chunks_by_url(url, organization_id, db)
        if not chunks:
            return None
        return self._reconstruct_entity(url, chunks, organization_id)

    # ── Vector search ─────────────────────────────────────────────────────────

    async def _vector_search(
        self,
        embedding: List[float],
        organization_id: str,
        db: Session,
    ) -> List[Dict[str, Any]]:
        try:
            embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
            sql = text(f"""
                SELECT id, content, source, chunk_index, metadata,
                       1 - (embedding <=> '{embedding_str}'::vector) AS similarity
                FROM document_chunks
                WHERE organization_id = :org
                  AND 1 - (embedding <=> '{embedding_str}'::vector) >= :threshold
                ORDER BY embedding <=> '{embedding_str}'::vector
                LIMIT :top_k
            """)
            rows = db.execute(sql, {
                "org": organization_id,
                "threshold": SIMILARITY_THRESHOLD,
                "top_k": PRODUCT_TOP_K,
            }).fetchall()
            return [self._row_to_chunk(r) for r in rows]
        except Exception as e:
            logger.error("product_vector_search_failed", error=str(e))
            return []

    # ── Keyword search ────────────────────────────────────────────────────────

    def _keyword_search(
        self,
        query: str,
        organization_id: str,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """
        PostgreSQL full-text search using ts_rank — real BM25 equivalent.
        Falls back to ILIKE if the fts column is not yet available (pre-migration).
        """
        # Primary: PostgreSQL FTS with ts_rank
        try:
            sql = text("""
                SELECT id, content, source, chunk_index, metadata,
                       ts_rank(fts, plainto_tsquery('english', :query)) AS similarity
                FROM document_chunks
                WHERE organization_id = :org
                  AND fts @@ plainto_tsquery('english', :query)
                ORDER BY similarity DESC
                LIMIT 30
            """)
            rows = db.execute(sql, {"org": organization_id, "query": query}).fetchall()
            if rows is not None:
                return [self._row_to_chunk(r) for r in rows]
        except Exception as fts_err:
            logger.warning("product_bm25_fts_unavailable", error=str(fts_err))
            try:
                db.rollback()
            except Exception:
                pass

        # Fallback: ILIKE (pre-migration 004)
        try:
            stop = {"what", "show", "tell", "give", "find", "the", "for", "and",
                    "with", "from", "that", "this", "have", "does", "about"}
            words = [w for w in re.findall(r'[a-zA-Z\u0980-\u09FF]{3,}', query.lower())
                     if w not in stop]
            if not words:
                return []
            conditions = " OR ".join(f"content ILIKE :kw{i}" for i in range(len(words)))
            params: Dict[str, Any] = {f"kw{i}": f"%{w}%" for i, w in enumerate(words)}
            params["org"] = organization_id
            sql = text(f"""
                SELECT id, content, source, chunk_index, metadata, 0.50 AS similarity
                FROM document_chunks
                WHERE organization_id = :org AND ({conditions})
                ORDER BY chunk_index ASC
                LIMIT 30
            """)
            rows = db.execute(sql, params).fetchall()
            return [self._row_to_chunk(r) for r in rows]
        except Exception as e:
            logger.warning("product_keyword_search_failed", error=str(e))
            return []

    # ── Chunk fetching by URL ─────────────────────────────────────────────────

    def _fetch_chunks_by_url(
        self,
        url: str,
        organization_id: str,
        db: Session,
    ) -> List[Dict[str, Any]]:
        try:
            sql = text("""
                SELECT id, content, source, chunk_index, metadata, 1.0 AS similarity
                FROM document_chunks
                WHERE organization_id = :org AND source = :url
                ORDER BY chunk_index ASC
                LIMIT 50
            """)
            rows = db.execute(sql, {"org": organization_id, "url": url}).fetchall()
            return [self._row_to_chunk(r) for r in rows]
        except Exception as e:
            logger.warning("fetch_chunks_by_url_failed", url=url, error=str(e))
            return []

    # ── Entity reconstruction ─────────────────────────────────────────────────

    def _reconstruct_entity(
        self,
        canonical_url: str,
        chunks: List[Dict[str, Any]],
        organization_id: str,
    ) -> ProductEntity:
        """
        Build a ProductEntity from a list of chunks for the same URL.
        Chunks are processed in source-priority order so higher-priority
        sources always win field-level conflicts.
        """
        entity = ProductEntity(url=canonical_url, organization_id=organization_id)

        # Sort chunks by source priority (highest first)
        def chunk_priority(chunk: Dict) -> int:
            meta = chunk.get("metadata") or {}
            sources = meta.get("sources_used", [])
            if sources:
                return max(SOURCE_PRIORITY.get(s, 0) for s in sources)
            # Infer from chunk_type
            ct = meta.get("chunk_type", "")
            if ct == "product_spec":
                return SOURCE_PRIORITY.get("shopify_json", 0)
            return 0

        sorted_chunks = sorted(chunks, key=chunk_priority, reverse=True)

        for chunk in sorted_chunks:
            meta = chunk.get("metadata") or {}
            content = chunk.get("content", "")
            source_name = self._infer_source(meta, chunk)

            # Parse structured fields from chunk content
            parsed = self._parse_chunk_content(content, meta)
            if parsed:
                entity.merge(source_name, parsed)

            # Merge metadata fields directly
            meta_data = self._extract_meta_fields(meta)
            if meta_data:
                entity.merge(source_name, meta_data)

        # Resolve canonical URL from chunks if entity URL is empty
        if not entity.url:
            entity.url = canonical_url

        return entity

    def _parse_chunk_content(self, content: str, meta: Dict) -> Dict[str, Any]:
        """Parse structured product fields from chunk text content."""
        result: Dict[str, Any] = {}
        if not content:
            return result

        # Title
        m = re.search(r'^Product:\s*(.+)$', content, re.M)
        if m:
            result["title"] = m.group(1).strip()

        # Price
        m = re.search(r'^Price:\s*(.+)$', content, re.M)
        if m:
            price_str = m.group(1).strip()
            price_match = re.search(r'[\d,]+\.?\d*', price_str.replace(",", ""))
            if price_match:
                try:
                    result["price"] = float(price_match.group())
                except ValueError:
                    pass
            # Extract currency
            currency_match = re.search(r'(BDT|USD|GBP|EUR|INR|৳|\$|£|€)', price_str)
            if currency_match:
                result["currency"] = currency_match.group(1)

        # Availability
        m = re.search(r'^Availability:\s*(.+)$', content, re.M)
        if m:
            result["availability"] = m.group(1).strip()

        # Brand
        m = re.search(r'^Brand:\s*(.+)$', content, re.M)
        if m:
            result["brand"] = m.group(1).strip()

        # SKU
        m = re.search(r'^SKU:\s*(.+)$', content, re.M)
        if m:
            result["sku"] = m.group(1).strip()

        # Type
        m = re.search(r'^Type:\s*(.+)$', content, re.M)
        if m:
            result["product_type"] = m.group(1).strip()

        # Material
        m = re.search(r'^Material:\s*(.+)$', content, re.M | re.I)
        if m:
            result["material"] = m.group(1).strip()

        # Color
        m = re.search(r'^Color:\s*(.+)$', content, re.M | re.I)
        if m:
            result["color"] = m.group(1).strip()

        # Sizes
        m = re.search(r'^(?:Size|Sizes|Size Options):\s*(.+)$', content, re.M | re.I)
        if m:
            result["size_options"] = m.group(1).strip()

        # Tags
        m = re.search(r'^Tags:\s*(.+)$', content, re.M)
        if m:
            result["tags"] = m.group(1).strip()

        # Description block
        desc_match = re.search(r'Description:\s*\n(.*?)(?=\nVariants:|\nShipping:|\nReturn|\nCare|\Z)',
                               content, re.S)
        if desc_match:
            result["description"] = desc_match.group(1).strip()

        # Shipping
        ship_match = re.search(r'Shipping:\s*\n(.*?)(?=\nReturn|\nCare|\nVariants:|\Z)',
                               content, re.S)
        if ship_match:
            result["shipping_info"] = ship_match.group(1).strip()

        # Return policy
        ret_match = re.search(r'Return Policy:\s*\n(.*?)(?=\nCare|\nVariants:|\Z)',
                              content, re.S)
        if ret_match:
            result["return_policy"] = ret_match.group(1).strip()

        # Care instructions
        care_match = re.search(r'Care Instructions:\s*\n(.*?)(?=\nVariants:|\Z)',
                               content, re.S)
        if care_match:
            result["care_instructions"] = care_match.group(1).strip()

        # Variants block
        variants_match = re.search(r'Variants:\s*\n(.*?)(?=\nShipping:|\nReturn|\nCare|\Z)',
                                   content, re.S)
        if variants_match:
            variants = self._parse_variants_block(variants_match.group(1))
            if variants:
                result["variants"] = variants

        return result

    def _parse_variants_block(self, block: str) -> List[Dict]:
        """Parse variant lines: '  - Black / M: 1390.00 BDT, In Stock, SKU: TRGM032486-M'"""
        variants = []
        for line in block.strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if not line:
                continue
            variant: Dict[str, Any] = {"title": "", "price": 0.0, "available": True, "sku": "", "options": {}}

            # SKU
            sku_m = re.search(r'SKU:\s*(\S+)', line)
            if sku_m:
                variant["sku"] = sku_m.group(1).rstrip(",")
                line = line[:sku_m.start()].strip().rstrip(",")

            # Availability
            if "Out of Stock" in line:
                variant["available"] = False
                line = line.replace("Out of Stock", "").strip().rstrip(",")
            elif "In Stock" in line:
                variant["available"] = True
                line = line.replace("In Stock", "").strip().rstrip(",")

            # Price
            price_m = re.search(r'([\d,]+\.?\d*)\s*(BDT|USD|GBP|EUR|৳|\$|£|€)?', line)
            if price_m:
                try:
                    variant["price"] = float(price_m.group(1).replace(",", ""))
                    if price_m.group(2):
                        variant["currency"] = price_m.group(2)
                except ValueError:
                    pass
                line = line[:price_m.start()].strip().rstrip(",")

            # Title / options (what remains)
            title = line.strip().rstrip(":,")
            if title:
                variant["title"] = title
                # Parse "Black / M" → {Color: Black, Size: M}
                parts = [p.strip() for p in title.split("/")]
                if len(parts) == 2:
                    variant["options"] = {"Color": parts[0], "Size": parts[1]}
                elif len(parts) == 1:
                    variant["options"] = {"Option": parts[0]}

            variants.append(variant)
        return variants

    def _extract_meta_fields(self, meta: Dict) -> Dict[str, Any]:
        """Extract entity fields directly from chunk metadata."""
        result: Dict[str, Any] = {}
        field_map = {
            "title": "title", "sku": "sku", "brand": "brand",
            "price": "price", "currency": "currency",
            "availability": "availability", "product_type": "product_type",
        }
        for meta_key, entity_key in field_map.items():
            val = meta.get(meta_key)
            if val not in (None, "", [], {}):
                result[entity_key] = val
        return result

    def _infer_source(self, meta: Dict, chunk: Dict) -> str:
        """Infer the best source name for a chunk."""
        sources = meta.get("sources_used", [])
        if sources:
            # Return highest-priority source from the list
            return max(sources, key=lambda s: SOURCE_PRIORITY.get(s, 0))
        platform = meta.get("platform", "")
        if platform == "shopify":
            return "shopify_json"
        chunk_type = meta.get("chunk_type", "")
        if chunk_type == "product_spec":
            return "shopify_json"
        return "dom"

    # ── Grouping + merging ────────────────────────────────────────────────────

    def _group_by_url(self, chunks: List[Dict]) -> Dict[str, List[Dict]]:
        """Group chunks by canonical URL."""
        groups: Dict[str, List[Dict]] = {}
        for chunk in chunks:
            url = self._canonical_url(chunk)
            groups.setdefault(url, []).append(chunk)
        return groups

    def _canonical_url(self, chunk: Dict) -> str:
        """Resolve canonical URL from chunk source + metadata."""
        meta = chunk.get("metadata") or {}
        # Prefer explicit url field in metadata
        url = meta.get("url") or chunk.get("source", "")
        # Strip query params and fragments for canonical form
        url = re.sub(r'[?#].*$', '', str(url)).rstrip("/")
        return url

    def _merge_chunk_lists(
        self,
        primary: List[Dict],
        secondary: List[Dict],
    ) -> List[Dict]:
        """Merge two chunk lists, deduplicating by chunk id."""
        seen = {c["id"] for c in primary}
        for c in secondary:
            if c["id"] not in seen:
                primary.append(c)
                seen.add(c["id"])
        return primary

    def _row_to_chunk(self, row) -> Dict[str, Any]:
        return {
            "id": str(row[0]),
            "content": row[1],
            "source": row[2],
            "chunk_index": row[3],
            "metadata": row[4] or {},
            "similarity": float(row[5]),
        }


product_retriever = ProductRetriever()
