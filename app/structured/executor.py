"""
Structured Executor — bypasses RAG for simple structured queries.

For price_query, availability_query, and simple product lookups:
  - Searches document_chunks directly using entity keywords
  - Extracts structured fields (price, availability, SKU) from chunk metadata
  - Builds a minimal LLM prompt (50-150 tokens of context vs 500-700 from RAG)
  - Returns result in ~100-250 total input tokens instead of 1000-1500

This is the correct path for:
  "মেনস ব্রিফ কম্বো প্রাইস কত?"  → structured lookup → 150 tokens
  "boxer price"                    → structured lookup → 120 tokens
  "is the hoodie available?"       → structured lookup → 130 tokens

RAG is still used for:
  - FAQ / policy queries (need full text context)
  - Comparison / reasoning (need multiple chunks)
  - "tell me about" / detail queries (need full product description)
  - Queries where structured lookup returns no results (fallback to RAG)
"""
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.logging import get_logger

logger = get_logger(__name__)

# Intents that use structured execution instead of full RAG
STRUCTURED_INTENTS = {"price_query", "availability_query"}

# Max chunks to fetch in structured mode — much lower than RAG top_k
STRUCTURED_TOP_K = 3

# Minimal system prompt for structured responses — ~80 tokens vs ~350 for default
_STRUCTURED_SYSTEM_PROMPT = (
    "You are a helpful store assistant. "
    "Answer the user's question using ONLY the product data below. "
    "Be brief. Reply in the same language the user used. "
    "No formatting, no markdown."
)


class StructuredExecutor:
    """
    Execute structured queries directly against the knowledge base
    without full RAG embedding + vector search overhead.

    Pipeline:
      1. Extract entity keywords from retrieval plan
      2. Direct DB lookup using BM25 FTS or ILIKE on metadata
      3. Extract price/availability fields from chunk metadata
      4. Build minimal LLM prompt with only the relevant fields
      5. Return (context_chunks, system_prompt, used_structured=True)
    """

    def can_execute(self, intent: str, retrieval_plan) -> bool:
        """Return True if this query should use structured execution."""
        if intent not in STRUCTURED_INTENTS:
            return False
        if retrieval_plan is None:
            return False
        # Need at least one entity to do a targeted lookup
        return len(retrieval_plan.entities) > 0 or bool(retrieval_plan.retrieval_query.strip())

    async def execute(
        self,
        query: str,
        retrieval_plan,
        organization_id: str,
        db: Session,
    ) -> Tuple[List[str], str, bool]:
        """
        Execute structured lookup.

        Returns:
          (rag_context, system_prompt, used_structured)
          used_structured=False means fallback to normal RAG
        """
        # Build search terms from entities + retrieval query
        search_terms = self._build_search_terms(retrieval_plan)
        if not search_terms:
            return [], "", False

        # Direct chunk lookup
        chunks = self._lookup_chunks(search_terms, organization_id, db)
        if not chunks:
            logger.info("structured_lookup_no_results", terms=search_terms[:3])
            return [], "", False

        # Extract structured fields from chunk metadata
        structured_data = self._extract_fields(chunks)

        # Build minimal context string
        context = self._build_context(structured_data, chunks)

        logger.info(
            "structured_execution",
            intent=retrieval_plan.intent,
            terms=search_terms[:3],
            chunks_found=len(chunks),
            fields_extracted=list(structured_data.keys()),
        )

        return [context], _STRUCTURED_SYSTEM_PROMPT, True

    def _build_search_terms(self, retrieval_plan) -> List[str]:
        """Extract the most useful search terms from the retrieval plan."""
        terms = []

        # Entity values (product names, categories, brands)
        for entity in retrieval_plan.entities[:4]:
            val = entity.value.strip()
            if len(val) > 2:
                terms.append(val)

        # Words from retrieval_query that aren't pure intent words
        intent_noise = {
            "price", "how", "much", "cost", "available", "availability",
            "in", "stock", "is", "the", "what", "rate", "how much",
        }
        for word in retrieval_plan.retrieval_query.split():
            w = word.lower().strip("?.,!")
            if len(w) > 2 and w not in intent_noise:
                terms.append(w)

        # Deduplicate preserving order
        seen = set()
        unique = []
        for t in terms:
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                unique.append(t)

        return unique[:6]

    def _lookup_chunks(
        self,
        search_terms: List[str],
        organization_id: str,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """
        Look up chunks using BM25 FTS first, ILIKE fallback.
        Returns chunks sorted by relevance.
        """
        # Try BM25 FTS first (fast, ranked)
        try:
            tsquery = " & ".join(search_terms[:4])
            sql = text("""
                SELECT id, content, source, chunk_index, metadata,
                       ts_rank(fts, to_tsquery('english', :tsq)) AS score
                FROM document_chunks
                WHERE organization_id = :org
                  AND fts @@ to_tsquery('english', :tsq)
                ORDER BY score DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, {
                "org": organization_id,
                "tsq": tsquery,
                "limit": STRUCTURED_TOP_K,
            }).fetchall()
            if rows:
                return [self._row_to_dict(r) for r in rows]
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        # ILIKE fallback
        try:
            conditions = " OR ".join(
                f"(content ILIKE :kw{i} OR metadata::text ILIKE :kw{i})"
                for i in range(len(search_terms[:4]))
            )
            params: Dict[str, Any] = {
                f"kw{i}": f"%{t}%" for i, t in enumerate(search_terms[:4])
            }
            params["org"] = organization_id
            params["limit"] = STRUCTURED_TOP_K

            sql = text(f"""
                SELECT id, content, source, chunk_index, metadata, 0.5 AS score
                FROM document_chunks
                WHERE organization_id = :org AND ({conditions})
                ORDER BY chunk_index ASC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.warning("structured_ilike_failed", error=str(e))
            try:
                db.rollback()
            except Exception:
                pass
            return []

    def _extract_fields(self, chunks: List[Dict]) -> Dict[str, Any]:
        """Extract structured product fields from chunk metadata and content."""
        import re
        fields: Dict[str, Any] = {}

        for chunk in chunks:
            meta = chunk.get("metadata") or {}

            # From metadata (highest confidence)
            for field in ("title", "price", "currency", "availability", "sku", "brand"):
                if field not in fields and meta.get(field) not in (None, "", []):
                    fields[field] = meta[field]

            # From content text (pattern matching)
            content = chunk.get("content", "")
            if "price" not in fields:
                m = re.search(r'Price:\s*([\d,]+\.?\d*)\s*(BDT|USD|৳|\$)?', content, re.I)
                if m:
                    fields["price"] = m.group(1).replace(",", "")
                    if m.group(2):
                        fields["currency"] = m.group(2)

            if "title" not in fields:
                m = re.search(r'Product:\s*(.+)$', content, re.M)
                if m:
                    fields["title"] = m.group(1).strip()

            if "availability" not in fields:
                m = re.search(r'Availability:\s*(.+)$', content, re.M)
                if m:
                    fields["availability"] = m.group(1).strip()

        return fields

    def _build_context(
        self,
        fields: Dict[str, Any],
        chunks: List[Dict],
    ) -> str:
        """
        Build a minimal context string for the LLM.
        Much smaller than injecting full chunk content.
        """
        parts = []

        if fields.get("title"):
            parts.append(f"Product: {fields['title']}")
        if fields.get("price"):
            currency = fields.get("currency", "BDT")
            parts.append(f"Price: {fields['price']} {currency}")
        if fields.get("availability"):
            parts.append(f"Availability: {fields['availability']}")
        if fields.get("sku"):
            parts.append(f"SKU: {fields['sku']}")
        if fields.get("brand"):
            parts.append(f"Brand: {fields['brand']}")

        # If metadata extraction was sparse, include first chunk content (truncated)
        if len(parts) <= 1 and chunks:
            content = chunks[0].get("content", "")[:400]
            parts.append(content)

        return "\n".join(parts)

    def _row_to_dict(self, row) -> Dict[str, Any]:
        return {
            "id": str(row[0]),
            "content": row[1],
            "source": row[2],
            "chunk_index": row[3],
            "metadata": row[4] or {},
            "similarity": float(row[5]),
        }


structured_executor = StructuredExecutor()
