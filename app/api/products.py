"""
Product Intelligence API

Endpoints:
  POST /product/query          — natural language product query
  GET  /product/entity         — retrieve product entity by URL
  GET  /product/completeness   — check completeness score for a URL
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.product_intelligence import product_intelligence
from app.observability.crawler_observability import crawler_observability
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/product", tags=["product-intelligence"])


# ── Request / Response schemas ────────────────────────────────────────────────

class ProductQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500, description="Natural language product query")
    top_k: int = Field(default=3, ge=1, le=10, description="Max number of products to return")
    enable_deep_extraction: bool = Field(
        default=False,
        description="Trigger deep extraction for incomplete products (slower, uses browser/API)"
    )


class VariantSchema(BaseModel):
    sku: str
    title: str
    price: Optional[float]
    currency: Optional[str]
    available: bool
    options: Dict[str, str]


class ProductStructuredSchema(BaseModel):
    title: Optional[str]
    price: Optional[float]
    currency: Optional[str]
    availability: Optional[str]
    brand: Optional[str]
    sku: Optional[str]
    product_type: Optional[str]
    material: Optional[str]
    color: Optional[str]
    size_options: Optional[str]
    description: Optional[str]
    shipping_info: Optional[str]
    return_policy: Optional[str]
    care_instructions: Optional[str]
    tags: Optional[str]
    variants: List[VariantSchema]
    url: str
    completeness: float
    completeness_dimensions: Dict[str, float]
    missing_fields: List[str]
    sources_used: List[str]


class ProductResultSchema(BaseModel):
    mode: str                           # FULL | PARTIAL | FALLBACK
    completeness_score: float
    text: str                           # formatted human-readable output
    product_url: str
    relevance_score: Optional[float]
    missing_fields: Optional[List[str]]
    sources_used: List[str]
    structured: ProductStructuredSchema


class ProductQueryResponse(BaseModel):
    query: str
    mode: str                           # overall mode of top result
    result_count: int
    products: List[ProductResultSchema]
    answer: Optional[str]               # LLM-grounded natural language answer
    primary_product_url: Optional[str]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/query", response_model=ProductQueryResponse)
async def query_products(
    body: ProductQueryRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Natural language product query.

    Returns structured product entities from the knowledge base with:
    - FULL response when completeness ≥ 0.85
    - PARTIAL response when 0.75 ≤ completeness < 0.85
    - FALLBACK (URL only) when completeness < 0.75

    Never hallucinate missing product data.
    """
    org_id = str(current_user.organization_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="User must belong to an organization")

    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        result = await product_intelligence.query(
            query=body.query,
            organization_id=org_id,
            db=db,
            top_k=body.top_k,
            enable_deep_extraction=body.enable_deep_extraction,
        )
        return result
    except Exception as e:
        logger.error("product_query_endpoint_failed", error=str(e), query=body.query[:60])
        raise HTTPException(status_code=500, detail="Product query failed")


@router.get("/entity")
async def get_product_entity(
    url: str = Query(..., description="Canonical product URL"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retrieve and reconstruct a ProductEntity for a specific URL.
    Returns structured data with completeness score and source provenance.
    """
    org_id = str(current_user.organization_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="User must belong to an organization")

    try:
        result = await product_intelligence.query_by_url(
            url=url,
            organization_id=org_id,
            db=db,
        )
        return result
    except Exception as e:
        logger.error("product_entity_endpoint_failed", error=str(e), url=url)
        raise HTTPException(status_code=500, detail="Entity retrieval failed")


@router.get("/completeness")
async def check_completeness(
    url: str = Query(..., description="Canonical product URL"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Check the completeness score for a product URL.
    Returns dimension breakdown and list of missing fields.
    Useful for identifying products that need re-crawling.
    """
    org_id = str(current_user.organization_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="User must belong to an organization")

    from app.rag.product_retriever import product_retriever
    from app.crawler.completeness_engine import CompletenessScore

    entity = await product_retriever.retrieve_by_url(url, org_id, db)
    if not entity:
        return {
            "url": url,
            "found": False,
            "completeness_score": 0.0,
            "mode": "FALLBACK",
            "message": "No chunks found for this URL in the knowledge base.",
        }

    score = CompletenessScore(entity)
    from app.services.product_formatter import FULL_THRESHOLD, PARTIAL_THRESHOLD
    if score.total >= FULL_THRESHOLD:
        mode = "FULL"
    elif score.total >= PARTIAL_THRESHOLD:
        mode = "PARTIAL"
    else:
        mode = "FALLBACK"

    return {
        "url": url,
        "found": True,
        "completeness_score": round(score.total, 3),
        "mode": mode,
        "dimensions": {k: round(v, 3) for k, v in score.dimensions.items()},
        "missing_fields": score.missing_fields,
        "sources_used": entity.sources_used,
        "variant_count": len(entity.variants),
    }


@router.get("/dashboard")
async def crawler_dashboard(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Full crawler observability dashboard — completeness, sources, trends, price changes."""
    org_id = str(current_user.organization_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="User must belong to an organization")
    return crawler_observability.get_full_dashboard(db, org_id)


@router.get("/eval")
async def run_evaluation(
    k: int = Query(default=3, ge=1, le=10),
    platform: Optional[str] = Query(
        default=None,
        description="Filter benchmark by platform: shopify | woocommerce | magento | headless_nextjs | generic"
    ),
    category: Optional[str] = Query(
        default=None,
        description="Filter benchmark by category: product_lookup | variant_query | price_query | availability_query | logistics_query | attribute_query | brand_query | category_query | comparison_query | faq_query"
    ),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Run retrieval quality evaluation against the universal benchmark dataset."""
    org_id = str(current_user.organization_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="User must belong to an organization")
    from app.evaluation.product_eval import product_evaluator
    report = await product_evaluator.evaluate(
        organization_id=org_id,
        db=db,
        k=k,
        platform_filter=platform,
        category_filter=category,
        resolve_urls=True,
    )
    return {
        "total_queries": report.total_queries,
        "platform_filter": platform,
        "category_filter": category,
        "avg_precision_at_k": report.avg_precision_at_k,
        "avg_recall_at_k": report.avg_recall_at_k,
        "avg_f1_at_k": report.avg_f1_at_k,
        "avg_mrr": report.avg_mrr,
        "avg_completeness_weighted": report.avg_completeness_weighted,
        "avg_latency_ms": report.avg_latency_ms,
        "hallucination_rate": report.hallucination_rate,
        "source_quality_summary": report.source_quality_summary,
        "missing_field_frequency": report.missing_field_frequency,
    }


@router.get("/price-history")
async def get_price_history(
    url: str = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get price change history for a product URL."""
    org_id = str(current_user.organization_id)
    from app.models.product_history import product_temporal_tracker
    rows = product_temporal_tracker.get_price_history(url, org_id, db, limit)
    return {
        "url": url,
        "price_history": [
            {"old_price": r.old_price, "new_price": r.new_price,
             "currency": r.currency, "is_promotion": r.is_promotion,
             "changed_at": str(r.changed_at)}
            for r in rows
        ],
    }


@router.get("/stock-history")
async def get_stock_history(
    url: str = Query(...),
    sku: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get stock/availability change history for a product URL."""
    org_id = str(current_user.organization_id)
    from app.models.product_history import product_temporal_tracker
    rows = product_temporal_tracker.get_stock_history(url, org_id, db, sku, limit)
    return {
        "url": url,
        "stock_history": [
            {"sku": r.sku, "variant_title": r.variant_title,
             "old_availability": r.old_availability,
             "new_availability": r.new_availability,
             "changed_at": str(r.changed_at)}
            for r in rows
        ],
    }


@router.get("/incomplete")
async def list_incomplete_products(
    threshold: float = Query(default=0.75, ge=0.0, le=1.0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List product URLs with completeness_score below threshold.
    Useful for targeting re-crawl jobs at incomplete products.
    """
    org_id = str(current_user.organization_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="User must belong to an organization")

    from sqlalchemy import text
    try:
        rows = db.execute(
            text("""
                SELECT url, completeness_score, extraction_sources, extraction_quality
                FROM crawled_pages
                WHERE organization_id = :org
                  AND completeness_score IS NOT NULL
                  AND completeness_score < :threshold
                ORDER BY completeness_score ASC
                LIMIT :limit
            """),
            {"org": org_id, "threshold": threshold, "limit": limit},
        ).fetchall()

        return {
            "threshold": threshold,
            "count": len(rows),
            "products": [
                {
                    "url": r[0],
                    "completeness_score": round(float(r[1]), 3) if r[1] else None,
                    "extraction_sources": r[2],
                    "extraction_quality": round(float(r[3]), 3) if r[3] else None,
                }
                for r in rows
            ],
        }
    except Exception as e:
        logger.error("list_incomplete_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list incomplete products")


@router.get("/retrieval-health")
async def retrieval_health(
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """
    RAG retrieval quality dashboard.

    Returns real-time metrics:
      - no_result_rate:           % of queries that returned 0 chunks
      - low_confidence_rate:      % of queries with top similarity < 0.5
      - bm25_hit_rate:            % of queries where BM25 added results
      - reranker_usage_rate:      % of queries that used cross-encoder reranker
      - cache_hit_rate:           % of queries served from semantic cache
      - avg_top_similarity:       average best similarity score across queries
      - hallucination_rate:       % of queries where hallucination was detected
      - hallucination_no_context_rate: % of hallucinations with no RAG context
        (high value = retrieval failure causing hallucinations)
      - hallucination_with_context_rate: % of hallucinations despite RAG context
        (high value = LLM or prompt issue, not retrieval)

    Use this endpoint to:
      1. Identify if BM25 is working (bm25_hit_rate > 0 after migration 004)
      2. Detect retrieval failures (no_result_rate > 0.1 = problem)
      3. Correlate hallucinations with retrieval quality
      4. Monitor reranker adoption
    """
    from app.observability.retrieval_observability import retrieval_observability
    return retrieval_observability.get_summary()
