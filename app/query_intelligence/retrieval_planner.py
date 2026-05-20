"""
Retrieval Planner — orchestrates the full query intelligence pipeline
and produces a final RetrievalPlan consumed by the RAG retriever.

Pipeline:
  raw query
    → multilingual_normalizer   (Bengali/Banglish → English)
    → typo_corrector            (fix misspellings)
    → query_rewriter            (expand abbreviations, shorthand)
    → entity_extractor          (find SKUs, brands, product names)
    → intent_decomposer         (classify intent, extract constraints)
    → ambiguity_detector        (flag vague queries)
    → query_expander            (add synonyms for BM25)
    → semantic_router           (choose retrieval path)
    → RetrievalPlan             (consumed by retriever)
"""
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.query_intelligence.multilingual_normalizer import multilingual_normalizer
from app.query_intelligence.typo_corrector import typo_corrector
from app.query_intelligence.query_rewriter import query_rewriter
from app.query_intelligence.query_expander import query_expander
from app.query_intelligence.entity_extractor import entity_extractor, ExtractedEntity
from app.query_intelligence.intent_decomposer import intent_decomposer, DecomposedIntent
from app.query_intelligence.ambiguity_detector import ambiguity_detector, AmbiguityResult
from app.query_intelligence.semantic_router import semantic_router, RoutingDecision
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalPlan:
    """
    Complete retrieval plan produced by the query intelligence pipeline.
    Consumed by RAGRetriever.retrieve() and the orchestrator.
    """
    # Original and processed queries
    original_query: str
    normalized_query: str           # after multilingual + typo + rewrite
    retrieval_query: str            # optimized for vector search
    bm25_query: str                 # optimized for BM25/FTS (expanded)

    # Intent and entities
    intent: str
    entities: List[ExtractedEntity] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    sub_queries: List[str] = field(default_factory=list)

    # Routing decision
    route: str = "HYBRID"
    use_reranker: bool = True
    top_k: int = 6
    threshold: float = 0.25
    use_parent_retrieval: bool = False

    # Ambiguity
    is_ambiguous: bool = False
    ambiguity_suggestion: Optional[str] = None

    # Pipeline metadata
    pipeline_ms: float = 0.0
    transformations_applied: List[str] = field(default_factory=list)


class RetrievalPlanner:
    """
    Orchestrate the full query intelligence pipeline.
    Returns a RetrievalPlan ready for the retriever.
    """

    def plan(
        self,
        query: str,
        has_conversation_history: bool = False,
    ) -> RetrievalPlan:
        """Run the full query intelligence pipeline and return a RetrievalPlan."""
        t0 = time.monotonic()
        transformations: List[str] = []

        # Step 1: Multilingual normalization
        normalized = multilingual_normalizer.normalize(query)
        if normalized != query:
            transformations.append("multilingual_normalized")

        # Step 2: Typo correction
        corrected = typo_corrector.correct(normalized)
        if corrected != normalized:
            transformations.append("typo_corrected")

        # Step 3: Query rewriting (abbreviations, shorthand)
        rewritten = query_rewriter.rewrite(corrected)
        if rewritten != corrected.lower():
            transformations.append("rewritten")

        # Step 4: Entity extraction
        entities = entity_extractor.extract(rewritten)
        has_sku = any(e.entity_type == "sku" for e in entities)
        has_entities = len(entities) > 0

        # Step 5: Intent decomposition
        decomposed: DecomposedIntent = intent_decomposer.decompose(rewritten)

        # Step 6: Ambiguity detection
        ambiguity: AmbiguityResult = ambiguity_detector.detect(
            rewritten, has_conversation_history=has_conversation_history
        )

        # Step 7: Query expansion for BM25
        bm25_query = query_expander.expand(
            query_rewriter.rewrite_for_bm25(rewritten)
        )
        if bm25_query != rewritten:
            transformations.append("expanded")

        # Step 8: Semantic routing
        routing: RoutingDecision = semantic_router.route(
            intent=decomposed.intent,
            has_sku=has_sku,
            has_entities=has_entities,
            requires_comparison=decomposed.requires_comparison,
            requires_structured=decomposed.requires_structured_data,
            query_length=len(rewritten.split()),
        )

        pipeline_ms = (time.monotonic() - t0) * 1000

        plan = RetrievalPlan(
            original_query=query,
            normalized_query=corrected,
            retrieval_query=decomposed.retrieval_query or rewritten,
            bm25_query=bm25_query,
            intent=decomposed.intent,
            entities=entities,
            constraints=decomposed.constraints,
            sub_queries=decomposed.sub_queries,
            route=routing.route,
            use_reranker=routing.use_reranker,
            top_k=routing.top_k,
            threshold=routing.threshold,
            use_parent_retrieval=routing.use_parent_retrieval,
            is_ambiguous=ambiguity.is_ambiguous,
            ambiguity_suggestion=ambiguity.suggestion,
            pipeline_ms=round(pipeline_ms, 2),
            transformations_applied=transformations,
        )

        logger.info(
            "retrieval_plan_built",
            intent=plan.intent,
            route=plan.route,
            top_k=plan.top_k,
            transformations=transformations,
            pipeline_ms=plan.pipeline_ms,
            query=query[:60],
        )

        return plan


retrieval_planner = RetrievalPlanner()
