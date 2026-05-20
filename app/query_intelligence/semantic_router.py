"""
Semantic Router — decides which retrieval path to use based on
query intelligence signals from the full query intelligence pipeline.

Routes:
  VECTOR_ONLY      — pure semantic queries (descriptions, feelings, concepts)
  BM25_ONLY        — exact match queries (SKU, model number, exact phrase)
  HYBRID           — most product/policy queries (default)
  STRUCTURED       — queries needing filtered/faceted retrieval
  GRAPH            — relationship/comparison queries
  TOOL             — queries needing live data (order status, inventory)
  DIRECT_ANSWER    — queries answerable without retrieval (greetings, math)
"""
from dataclasses import dataclass
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RoutingDecision:
    route: str              # VECTOR_ONLY | BM25_ONLY | HYBRID | STRUCTURED | GRAPH | TOOL | DIRECT_ANSWER
    use_reranker: bool
    top_k: int
    threshold: float
    reason: str
    use_query_expansion: bool = True
    use_parent_retrieval: bool = False


class SemanticRouter:
    """
    Route queries to the optimal retrieval strategy.

    Decision logic:
    - SKU / exact model number → BM25_ONLY (exact match)
    - Comparison queries → GRAPH (entity graph traversal)
    - Price/availability → STRUCTURED (filtered retrieval)
    - Order/inventory → TOOL (live data lookup)
    - General product/policy → HYBRID (vector + BM25)
    - Pure semantic → VECTOR_ONLY
    """

    def route(
        self,
        intent: str,
        has_sku: bool = False,
        has_entities: bool = False,
        requires_comparison: bool = False,
        requires_structured: bool = False,
        is_tool_query: bool = False,
        query_length: int = 10,
    ) -> RoutingDecision:
        """Return the optimal routing decision for a query."""

        # SKU lookup — exact match, BM25 wins
        if has_sku:
            return RoutingDecision(
                route="BM25_ONLY",
                use_reranker=False,
                top_k=5,
                threshold=0.0,
                reason="sku_exact_match",
                use_query_expansion=False,
            )

        # Tool queries — need live data, not RAG
        if is_tool_query or intent in ("order_lookup", "inventory_check"):
            return RoutingDecision(
                route="TOOL",
                use_reranker=False,
                top_k=0,
                threshold=0.0,
                reason="requires_live_data",
                use_query_expansion=False,
            )

        # Comparison queries — use entity graph
        if requires_comparison or intent == "comparison":
            return RoutingDecision(
                route="GRAPH",
                use_reranker=True,
                top_k=10,
                threshold=0.3,
                reason="comparison_requires_graph",
                use_parent_retrieval=True,
            )

        # Structured queries (price/availability with constraints)
        if requires_structured and intent in ("price_query", "availability_query"):
            return RoutingDecision(
                route="STRUCTURED",
                use_reranker=True,
                top_k=8,
                threshold=0.25,
                reason="structured_field_query",
            )

        # Policy/FAQ — hybrid with parent retrieval for full context
        if intent in ("policy_lookup", "faq"):
            return RoutingDecision(
                route="HYBRID",
                use_reranker=True,
                top_k=6,
                threshold=0.25,
                reason="policy_faq_hybrid",
                use_parent_retrieval=True,
            )

        # Product search — full hybrid
        if intent in ("product_search", "general") and has_entities:
            return RoutingDecision(
                route="HYBRID",
                use_reranker=True,
                top_k=8,
                threshold=0.25,
                reason="product_search_hybrid",
            )

        # Short queries — vector only (BM25 hurts on 1-2 word queries)
        if query_length <= 3:
            return RoutingDecision(
                route="VECTOR_ONLY",
                use_reranker=False,
                top_k=5,
                threshold=0.35,
                reason="short_query_vector_only",
                use_query_expansion=False,
            )

        # Default — hybrid
        return RoutingDecision(
            route="HYBRID",
            use_reranker=True,
            top_k=6,
            threshold=0.25,
            reason="default_hybrid",
        )


semantic_router = SemanticRouter()
