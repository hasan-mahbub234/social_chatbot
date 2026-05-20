"""
Product Intelligence Service

Orchestrates the full product query pipeline:
  1. Retrieve product entities from pgvector (via ProductRetriever)
  2. Score completeness (via CompletenessScore)
  3. Trigger deep extraction if score < threshold (via DeepExtractionLoop)
  4. Decide response mode: FULL / PARTIAL / FALLBACK
  5. Format response (via ProductEntityFormatter)
  6. Generate natural language answer grounded in entity data (via LLM)

No-hallucination enforcement:
  - LLM receives ONLY the structured entity text as context
  - LLM is instructed to never add information not present in context
  - If entity is in FALLBACK mode, LLM is not called at all
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.crawler.entity_model import ProductEntity
from app.crawler.completeness_engine import CompletenessScore, DeepExtractionLoop
from app.services.product_formatter import ProductEntityFormatter, FULL_THRESHOLD, PARTIAL_THRESHOLD
from app.rag.product_retriever import ProductRetriever
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# LLM system prompt for grounded product answers
PRODUCT_ANSWER_SYSTEM = """You are a Product Knowledge Assistant.
Answer the user's question using ONLY the structured product data provided below.

Rules:
- Never guess, estimate, or invent any product field
- Never add prices, SKUs, variants, or availability not present in the data
- If a field is marked "Not available" — state it is not available
- If the data is marked FALLBACK — do not attempt to answer, return the URL only
- Always include the Source URL at the end of your response
- Be concise and factual"""

PRODUCT_ANSWER_USER = """Product Data:
{entity_text}

User Question: {query}

Answer (grounded only in the product data above):"""


class ProductIntelligenceService:
    """
    End-to-end product query pipeline with completeness-gated response modes.
    """

    def __init__(self):
        self._retriever = ProductRetriever()
        self._formatter = ProductEntityFormatter()
        self._deep_loop = DeepExtractionLoop()

    async def query(
        self,
        query: str,
        organization_id: str,
        db: Session,
        top_k: int = 3,
        enable_deep_extraction: bool = False,  # requires live crawler access
    ) -> Dict[str, Any]:
        """
        Execute a product intelligence query.

        Returns:
          - mode: FULL / PARTIAL / FALLBACK
          - products: list of formatted product results
          - answer: LLM-grounded natural language answer (FULL/PARTIAL only)
          - query: original query
        """
        # 1. Retrieve product entities
        results: List[Tuple[ProductEntity, float]] = await self._retriever.retrieve(
            query=query,
            organization_id=organization_id,
            db=db,
            top_k=top_k,
        )

        if not results:
            return self._no_results_response(query)

        # 2. Score + optionally deep-extract each entity
        scored: List[Tuple[ProductEntity, CompletenessScore, float]] = []
        for entity, relevance in results:
            score = CompletenessScore(entity)

            # Deep extraction only when explicitly enabled (requires crawler context)
            if enable_deep_extraction and score.needs_deep_extraction and entity.url:
                try:
                    entity, score = await self._deep_loop.run(
                        entity=entity,
                        url=entity.url,
                        html="",  # no raw HTML in query path — triggers API-only strategies
                        organization_id=organization_id,
                    )
                except Exception as e:
                    logger.warning("deep_extraction_failed_in_query", url=entity.url, error=str(e))

            scored.append((entity, score, relevance))

        # 3. Determine overall response mode (worst-case of top result)
        top_entity, top_score, top_relevance = scored[0]
        overall_mode = self._decide_mode(top_score)

        # 4. Format all results
        formatted_products = []
        for entity, score, relevance in scored:
            formatted = self._formatter.format(entity, score)
            formatted["relevance_score"] = round(relevance, 3)
            formatted_products.append(formatted)

        # 5. Generate grounded LLM answer (skip for FALLBACK)
        answer = None
        if overall_mode != "FALLBACK":
            answer = await self._generate_answer(
                query=query,
                entity_text=formatted_products[0]["text"],
                mode=overall_mode,
            )

        # 6. Build response
        response: Dict[str, Any] = {
            "query": query,
            "mode": overall_mode,
            "result_count": len(formatted_products),
            "products": formatted_products,
            "answer": answer,
        }

        # Always include primary product URL
        if formatted_products:
            response["primary_product_url"] = formatted_products[0].get("product_url", "")

        logger.info(
            "product_query_complete",
            query=query[:60],
            mode=overall_mode,
            results=len(formatted_products),
            top_score=round(top_score.total, 3),
        )
        return response

    async def query_by_url(
        self,
        url: str,
        organization_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Retrieve and format a specific product by its canonical URL."""
        entity = await self._retriever.retrieve_by_url(url, organization_id, db)
        if not entity:
            return {
                "mode": "FALLBACK",
                "answer": "Data incomplete — requires API or network extraction.",
                "primary_product_url": url,
                "products": [],
            }

        score = CompletenessScore(entity)
        formatted = self._formatter.format(entity, score)
        mode = self._decide_mode(score)

        answer = None
        if mode != "FALLBACK":
            answer = await self._generate_answer(
                query=f"Describe this product: {url}",
                entity_text=formatted["text"],
                mode=mode,
            )

        return {
            "mode": mode,
            "answer": answer,
            "primary_product_url": url,
            "products": [formatted],
        }

    # ── Response mode decision ────────────────────────────────────────────────

    def _decide_mode(self, score: CompletenessScore) -> str:
        if score.total >= FULL_THRESHOLD:
            return "FULL"
        elif score.total >= PARTIAL_THRESHOLD:
            return "PARTIAL"
        return "FALLBACK"

    # ── Grounded LLM answer generation ───────────────────────────────────────

    async def _generate_answer(
        self,
        query: str,
        entity_text: str,
        mode: str,
    ) -> Optional[str]:
        """
        Generate a natural language answer grounded strictly in entity_text.
        LLM receives no external knowledge — only the structured product data.
        """
        try:
            prompt = PRODUCT_ANSWER_USER.format(
                entity_text=entity_text,
                query=query,
            )
            if settings.AI_PROVIDER == "groq" and settings.GROQ_API_KEY:
                return await self._call_groq(prompt)
            elif settings.OPENAI_API_KEY:
                return await self._call_openai(prompt)
        except Exception as e:
            logger.warning("product_answer_generation_failed", error=str(e))
        return None

    async def _call_openai(self, prompt: str) -> str:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": settings.OPENAI_MINI_MODEL,
                    "messages": [
                        {"role": "system", "content": PRODUCT_ANSWER_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": 600,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    async def _call_groq(self, prompt: str) -> str:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                json={
                    "model": settings.GROQ_SMART_MODEL,
                    "messages": [
                        {"role": "system", "content": PRODUCT_ANSWER_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": 600,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    # ── No-results response ───────────────────────────────────────────────────

    def _no_results_response(self, query: str) -> Dict[str, Any]:
        return {
            "query": query,
            "mode": "FALLBACK",
            "result_count": 0,
            "products": [],
            "answer": "No matching products found in the knowledge base.",
            "primary_product_url": None,
        }


product_intelligence = ProductIntelligenceService()
