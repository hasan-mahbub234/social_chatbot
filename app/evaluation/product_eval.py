"""
Retrieval Quality Evaluation Engine

Metrics:
  - Precision@K, Recall@K, F1@K
  - MRR (Mean Reciprocal Rank)
  - Completeness-weighted ranking
  - Hallucination detection checks
  - Missing-field analysis
  - Source-quality analytics

Supports benchmark datasets via gold_queries.json.
"""
from __future__ import annotations
import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.crawler.entity_model import ProductEntity
from app.crawler.completeness_engine import CompletenessScore
from app.rag.product_retriever import ProductRetriever
from app.core.logging import get_logger

logger = get_logger(__name__)

BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class GoldQuery:
    query_id: str
    query: str
    expected_urls: List[str]
    expected_skus: List[str] = field(default_factory=list)
    expected_prices: Dict[str, float] = field(default_factory=dict)   # url → price
    expected_fields: Dict[str, List[str]] = field(default_factory=dict)  # url → [field names]
    notes: str = ""


@dataclass
class RetrievalResult:
    query_id: str
    query: str
    retrieved_urls: List[str]
    retrieved_entities: List[Dict[str, Any]]
    latency_ms: float
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    f1_at_k: float = 0.0
    mrr: float = 0.0
    completeness_weighted_score: float = 0.0
    hallucination_flags: List[str] = field(default_factory=list)
    missing_field_report: Dict[str, List[str]] = field(default_factory=dict)
    source_quality_report: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalReport:
    total_queries: int
    avg_precision_at_k: float
    avg_recall_at_k: float
    avg_f1_at_k: float
    avg_mrr: float
    avg_completeness_weighted: float
    avg_latency_ms: float
    hallucination_rate: float
    source_quality_summary: Dict[str, Any]
    missing_field_frequency: Dict[str, int]
    per_query_results: List[RetrievalResult]


# ── Evaluator ─────────────────────────────────────────────────────────────────

class ProductEvaluator:
    """
    Evaluate retrieval quality against a gold benchmark dataset.
    """

    def __init__(self):
        self._retriever = ProductRetriever()
        self._field_criticality: Dict[str, str] = {}
        self._eval_config: Dict[str, Any] = {}

    # ── Benchmark loading ─────────────────────────────────────────────────────

    def load_benchmark(
        self,
        path: Optional[str] = None,
        platform_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
    ) -> List[GoldQuery]:
        """
        Load gold queries from JSON file.

        Args:
            platform_filter: Only load queries tagged for this platform
                             (shopify | woocommerce | magento | headless_nextjs | generic)
            category_filter: Only load queries in this category
                             (product_lookup | variant_query | price_query | etc.)
        """
        p = Path(path) if path else BENCHMARKS_DIR / "gold_queries.json"
        if not p.exists():
            logger.warning("benchmark_file_not_found", path=str(p))
            return []
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Support both old flat list and new {queries: [...]} format
        items = raw.get("queries", raw) if isinstance(raw, dict) else raw
        self._field_criticality = raw.get("field_criticality", {}) if isinstance(raw, dict) else {}
        self._eval_config = raw.get("evaluation_config", {}) if isinstance(raw, dict) else {}
        platform_coverage = raw.get("platform_coverage", {}) if isinstance(raw, dict) else {}

        # Build platform-filtered query ID set
        allowed_ids: Optional[set] = None
        if platform_filter and platform_coverage:
            allowed_ids = set(platform_coverage.get(platform_filter, []))

        queries = []
        for item in items:
            query_id = item.get("query_id", "")

            # Platform filter
            if allowed_ids is not None and query_id not in allowed_ids:
                continue

            # Category filter
            if category_filter and item.get("category", "") != category_filter:
                continue

            queries.append(GoldQuery(
                query_id=query_id,
                query=item.get("query", ""),
                expected_urls=[u.rstrip("/") for u in item.get("expected_urls", [])],
                expected_skus=item.get("expected_skus", []),
                expected_prices=item.get("expected_prices", {}),
                expected_fields=item.get("expected_fields", {}),
                notes=item.get("notes", ""),
            ))
        return queries

    def resolve_urls_from_db(
        self,
        gold_queries: List[GoldQuery],
        organization_id: str,
        db,
        limit_per_query: int = 3,
    ) -> List[GoldQuery]:
        """
        Runtime URL resolution: since gold_queries.json uses empty expected_urls
        (platform-agnostic), this method populates them from the org's actual
        crawled_pages based on query keyword matching.

        This makes the benchmark work for ANY organization's crawled data.
        """
        try:
            from sqlalchemy import text
            for gq in gold_queries:
                if gq.expected_urls:
                    continue  # already has explicit URLs

                # Extract keywords from query
                stop = {"show", "me", "the", "what", "is", "are", "this", "does",
                        "how", "give", "all", "for", "do", "you", "a", "an", "in"}
                words = [w for w in re.findall(r'[a-zA-Z]{3,}', gq.query.lower())
                         if w not in stop]
                if not words:
                    continue

                conditions = " OR ".join(f"url ILIKE :kw{i}" for i in range(len(words)))
                params = {f"kw{i}": f"%{w}%" for i, w in enumerate(words)}
                params["org"] = organization_id
                params["limit"] = limit_per_query

                rows = db.execute(
                    text(f"""
                        SELECT url FROM crawled_pages
                        WHERE organization_id = :org AND ({conditions})
                        ORDER BY completeness_score DESC NULLS LAST
                        LIMIT :limit
                    """),
                    params,
                ).fetchall()

                if rows:
                    gq.expected_urls = [r[0].rstrip("/") for r in rows]
        except Exception as e:
            logger.warning("url_resolution_failed", error=str(e))
        return gold_queries

    # ── Full evaluation run ───────────────────────────────────────────────────

    async def evaluate(
        self,
        organization_id: str,
        db: Session,
        benchmark_path: Optional[str] = None,
        k: int = 3,
        platform_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        resolve_urls: bool = True,
    ) -> EvalReport:
        """Run full evaluation against benchmark dataset."""
        gold_queries = self.load_benchmark(
            benchmark_path,
            platform_filter=platform_filter,
            category_filter=category_filter,
        )
        if not gold_queries:
            logger.warning("no_benchmark_queries_loaded")
            return self._empty_report()

        # Runtime URL resolution for platform-agnostic queries
        if resolve_urls:
            gold_queries = self.resolve_urls_from_db(gold_queries, organization_id, db)

        results: List[RetrievalResult] = []
        for gq in gold_queries:
            result = await self._evaluate_query(gq, organization_id, db, k)
            results.append(result)

        return self._aggregate_report(results)

    async def _evaluate_query(
        self,
        gq: GoldQuery,
        organization_id: str,
        db: Session,
        k: int,
    ) -> RetrievalResult:
        t0 = time.monotonic()
        retrieved = await self._retriever.retrieve(
            query=gq.query,
            organization_id=organization_id,
            db=db,
            top_k=k,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        retrieved_urls = [e.url.rstrip("/") for e, _ in retrieved]
        entity_dicts = [self._entity_to_dict(e, s) for e, s in retrieved]

        precision = self._precision_at_k(retrieved_urls, gq.expected_urls, k)
        recall = self._recall_at_k(retrieved_urls, gq.expected_urls, k)
        f1 = self._f1(precision, recall)
        mrr = self._mrr(retrieved_urls, gq.expected_urls)
        cw_score = self._completeness_weighted_score(retrieved)
        hallucination_flags = self._check_hallucinations(retrieved, gq)
        missing_report = self._missing_field_report(retrieved, gq)
        source_quality = self._source_quality_report(retrieved)

        return RetrievalResult(
            query_id=gq.query_id,
            query=gq.query,
            retrieved_urls=retrieved_urls,
            retrieved_entities=entity_dicts,
            latency_ms=round(latency_ms, 2),
            precision_at_k=precision,
            recall_at_k=recall,
            f1_at_k=f1,
            mrr=mrr,
            completeness_weighted_score=cw_score,
            hallucination_flags=hallucination_flags,
            missing_field_report=missing_report,
            source_quality_report=source_quality,
        )

    # ── Metrics ───────────────────────────────────────────────────────────────

    def _precision_at_k(
        self, retrieved: List[str], expected: List[str], k: int
    ) -> float:
        if not retrieved or not expected:
            return 0.0
        top_k = retrieved[:k]
        hits = sum(1 for url in top_k if url in expected)
        return round(hits / k, 4)

    def _recall_at_k(
        self, retrieved: List[str], expected: List[str], k: int
    ) -> float:
        if not expected:
            return 1.0
        top_k = retrieved[:k]
        hits = sum(1 for url in expected if url in top_k)
        return round(hits / len(expected), 4)

    def _f1(self, precision: float, recall: float) -> float:
        if precision + recall == 0:
            return 0.0
        return round(2 * precision * recall / (precision + recall), 4)

    def _mrr(self, retrieved: List[str], expected: List[str]) -> float:
        """Mean Reciprocal Rank — rank of first relevant result."""
        for i, url in enumerate(retrieved):
            if url in expected:
                return round(1.0 / (i + 1), 4)
        return 0.0

    def _completeness_weighted_score(
        self, results: List[Tuple[ProductEntity, float]]
    ) -> float:
        """Average of (completeness × relevance) across retrieved entities."""
        if not results:
            return 0.0
        scores = []
        for entity, relevance in results:
            completeness = CompletenessScore(entity).total
            scores.append(completeness * relevance)
        return round(sum(scores) / len(scores), 4)

    # ── Hallucination detection ───────────────────────────────────────────────

    def _check_hallucinations(
        self,
        results: List[Tuple[ProductEntity, float]],
        gq: GoldQuery,
    ) -> List[str]:
        """
        Detect potential hallucinations by comparing retrieved values
        against gold expected values.
        """
        flags = []
        for entity, _ in results:
            url = entity.url.rstrip("/")
            if url not in gq.expected_urls:
                continue

            # Price hallucination check
            expected_price = gq.expected_prices.get(url)
            if expected_price is not None and entity.price and entity.price.value:
                try:
                    retrieved_price = float(entity.price.value)
                    if abs(retrieved_price - expected_price) / max(expected_price, 1) > 0.05:
                        flags.append(
                            f"price_mismatch:{url} "
                            f"expected={expected_price} got={retrieved_price}"
                        )
                except (ValueError, TypeError):
                    flags.append(f"price_unparseable:{url}")

            # SKU hallucination check
            if gq.expected_skus:
                retrieved_skus = {v.sku for v in entity.variants if v.sku}
                if entity.sku and entity.sku.value:
                    retrieved_skus.add(str(entity.sku.value))
                invented_skus = retrieved_skus - set(gq.expected_skus)
                if invented_skus:
                    flags.append(f"invented_skus:{url} skus={invented_skus}")

            # LLM-sourced field check (very low confidence)
            for attr in ("price", "sku", "availability", "variants"):
                fv = getattr(entity, attr, None)
                if fv and hasattr(fv, "source") and fv.source == "llm":
                    flags.append(f"llm_sourced_critical_field:{attr}:{url}")

        return flags

    # ── Missing field analysis ────────────────────────────────────────────────

    def _missing_field_report(
        self,
        results: List[Tuple[ProductEntity, float]],
        gq: GoldQuery,
    ) -> Dict[str, List[str]]:
        """Report which expected fields are missing per URL."""
        report: Dict[str, List[str]] = {}
        for entity, _ in results:
            url = entity.url.rstrip("/")
            expected_fields = gq.expected_fields.get(url, [])
            if not expected_fields:
                continue
            score = CompletenessScore(entity)
            missing = [f for f in expected_fields if f in score.missing_fields]
            if missing:
                report[url] = missing
        return report

    # ── Source quality analytics ──────────────────────────────────────────────

    def _source_quality_report(
        self, results: List[Tuple[ProductEntity, float]]
    ) -> Dict[str, Any]:
        """Analyze source distribution and confidence across retrieved entities."""
        source_counts: Dict[str, int] = {}
        field_source_map: Dict[str, Dict[str, int]] = {}
        low_confidence_fields: List[str] = []

        for entity, _ in results:
            for src in entity.sources_used:
                source_counts[src] = source_counts.get(src, 0) + 1

            for attr in ("title", "price", "sku", "availability", "brand",
                         "material", "shipping_info", "return_policy"):
                fv = getattr(entity, attr, None)
                if fv and hasattr(fv, "source"):
                    field_source_map.setdefault(attr, {})
                    field_source_map[attr][fv.source] = field_source_map[attr].get(fv.source, 0) + 1
                    if fv.source in ("dom", "llm", "og_meta"):
                        low_confidence_fields.append(f"{attr}:{fv.source}")

        return {
            "source_distribution": source_counts,
            "field_source_map": field_source_map,
            "low_confidence_fields": low_confidence_fields,
        }

    # ── Aggregation ───────────────────────────────────────────────────────────

    def _aggregate_report(self, results: List[RetrievalResult]) -> EvalReport:
        n = len(results)
        if n == 0:
            return self._empty_report()

        def avg(key: str) -> float:
            return round(sum(getattr(r, key) for r in results) / n, 4)

        # Missing field frequency across all queries
        field_freq: Dict[str, int] = {}
        for r in results:
            for url, fields in r.missing_field_report.items():
                for f in fields:
                    field_freq[f] = field_freq.get(f, 0) + 1

        # Source quality summary
        all_sources: Dict[str, int] = {}
        low_conf_count = 0
        for r in results:
            sq = r.source_quality_report
            for src, cnt in sq.get("source_distribution", {}).items():
                all_sources[src] = all_sources.get(src, 0) + cnt
            low_conf_count += len(sq.get("low_confidence_fields", []))

        # Hallucination rate
        queries_with_flags = sum(1 for r in results if r.hallucination_flags)
        hallucination_rate = round(queries_with_flags / n, 4)

        return EvalReport(
            total_queries=n,
            avg_precision_at_k=avg("precision_at_k"),
            avg_recall_at_k=avg("recall_at_k"),
            avg_f1_at_k=avg("f1_at_k"),
            avg_mrr=avg("mrr"),
            avg_completeness_weighted=avg("completeness_weighted_score"),
            avg_latency_ms=avg("latency_ms"),
            hallucination_rate=hallucination_rate,
            source_quality_summary={
                "source_distribution": all_sources,
                "low_confidence_field_count": low_conf_count,
            },
            missing_field_frequency=dict(sorted(field_freq.items(), key=lambda x: -x[1])),
            per_query_results=results,
        )

    def _empty_report(self) -> EvalReport:
        return EvalReport(
            total_queries=0, avg_precision_at_k=0.0, avg_recall_at_k=0.0,
            avg_f1_at_k=0.0, avg_mrr=0.0, avg_completeness_weighted=0.0,
            avg_latency_ms=0.0, hallucination_rate=0.0,
            source_quality_summary={}, missing_field_frequency={},
            per_query_results=[],
        )

    def _entity_to_dict(self, entity: ProductEntity, relevance: float) -> Dict:
        score = CompletenessScore(entity)
        return {
            "url": entity.url,
            "title": entity.title.value if entity.title else None,
            "completeness": round(score.total, 3),
            "sources": entity.sources_used,
            "relevance": round(relevance, 3),
        }

    # ── Single-query evaluation (for API use) ─────────────────────────────────

    def evaluate_single(
        self,
        retrieved: List[Tuple[ProductEntity, float]],
        expected_urls: List[str],
        k: int = 3,
    ) -> Dict[str, Any]:
        """Evaluate a single retrieval result without a full benchmark run."""
        retrieved_urls = [e.url.rstrip("/") for e, _ in retrieved]
        expected_urls = [u.rstrip("/") for u in expected_urls]
        precision = self._precision_at_k(retrieved_urls, expected_urls, k)
        recall = self._recall_at_k(retrieved_urls, expected_urls, k)
        return {
            "precision_at_k": precision,
            "recall_at_k": recall,
            "f1_at_k": self._f1(precision, recall),
            "mrr": self._mrr(retrieved_urls, expected_urls),
            "completeness_weighted": self._completeness_weighted_score(retrieved),
        }


product_evaluator = ProductEvaluator()
