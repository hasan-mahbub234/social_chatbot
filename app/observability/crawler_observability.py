"""
Crawler Observability — completeness dashboards, extraction source analytics,
low-confidence field tracking, failed extraction metrics, crawl-quality trends.

Extends the existing MetricsCollector and DashboardService.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.observability.metrics import metrics_collector
from app.core.logging import get_logger

logger = get_logger(__name__)


class CrawlerObservability:
    """
    Crawler-specific metrics collection and dashboard aggregation.
    All metrics are org-scoped.
    """

    # ── Metric recording ──────────────────────────────────────────────────────

    def record_extraction(
        self,
        org_id: str,
        url: str,
        completeness_score: float,
        sources_used: List[str],
        missing_fields: List[str],
        extraction_quality: float,
        used_browser: bool,
        used_llm: bool,
        latency_ms: float,
    ):
        """Record a single page extraction event."""
        metrics_collector.record_histogram("crawler.completeness_score", completeness_score)
        metrics_collector.record_histogram("crawler.extraction_quality", extraction_quality)
        metrics_collector.record_histogram("crawler.fetch_latency_ms", latency_ms)
        metrics_collector.increment_counter("crawler.pages_extracted")

        if completeness_score >= 0.85:
            metrics_collector.increment_counter("crawler.completeness.full")
        elif completeness_score >= 0.75:
            metrics_collector.increment_counter("crawler.completeness.partial")
        else:
            metrics_collector.increment_counter("crawler.completeness.fallback")

        if used_browser:
            metrics_collector.increment_counter("crawler.browser_renders")
        if used_llm:
            metrics_collector.increment_counter("crawler.llm_extractions")

        for source in sources_used:
            metrics_collector.increment_counter(f"crawler.source.{source}")

        for field in missing_fields:
            metrics_collector.increment_counter(f"crawler.missing_field.{field}")

    def record_deep_extraction(
        self,
        org_id: str,
        url: str,
        passes: int,
        score_before: float,
        score_after: float,
        strategies_used: List[str],
    ):
        """Record a deep extraction loop event."""
        metrics_collector.increment_counter("crawler.deep_extractions")
        metrics_collector.record_histogram("crawler.deep_extraction_passes", passes)
        improvement = score_after - score_before
        metrics_collector.record_histogram("crawler.completeness_improvement", improvement)
        for strategy in strategies_used:
            metrics_collector.increment_counter(f"crawler.strategy.{strategy}")

    def record_entity_graph_event(self, event_type: str, org_id: str):
        """Record entity graph operations."""
        metrics_collector.increment_counter(f"entity_graph.{event_type}")

    def record_variant_resolution(
        self,
        org_id: str,
        variant_count: int,
        conflict_count: int,
        avg_confidence: float,
    ):
        """Record variant resolution metrics."""
        metrics_collector.record_histogram("variants.resolved_count", variant_count)
        metrics_collector.record_histogram("variants.conflict_count", conflict_count)
        metrics_collector.record_histogram("variants.avg_confidence", avg_confidence)

    # ── Dashboard aggregation ─────────────────────────────────────────────────

    def get_completeness_dashboard(self, db: Session, org_id: str) -> Dict[str, Any]:
        """
        Aggregate completeness metrics from crawled_pages table.
        Returns dashboard-ready dict.
        """
        try:
            rows = db.execute(text("""
                SELECT
                    COUNT(*) AS total_pages,
                    AVG(completeness_score) AS avg_completeness,
                    COUNT(*) FILTER (WHERE completeness_score >= 0.85) AS full_count,
                    COUNT(*) FILTER (WHERE completeness_score >= 0.75 AND completeness_score < 0.85) AS partial_count,
                    COUNT(*) FILTER (WHERE completeness_score < 0.75 OR completeness_score IS NULL) AS fallback_count,
                    AVG(extraction_quality) AS avg_quality,
                    COUNT(*) FILTER (WHERE used_browser = true) AS browser_renders,
                    MAX(crawled_at) AS last_crawl
                FROM crawled_pages
                WHERE organization_id = :org
            """), {"org": org_id}).fetchone()

            if not rows or not rows[0]:
                return {"status": "no_data"}

            total = rows[0] or 0
            return {
                "total_pages": total,
                "avg_completeness_score": round(float(rows[1] or 0), 3),
                "completeness_distribution": {
                    "full":     rows[2] or 0,
                    "partial":  rows[3] or 0,
                    "fallback": rows[4] or 0,
                },
                "completeness_rates": {
                    "full_rate":    round((rows[2] or 0) / max(total, 1), 3),
                    "partial_rate": round((rows[3] or 0) / max(total, 1), 3),
                    "fallback_rate":round((rows[4] or 0) / max(total, 1), 3),
                },
                "avg_extraction_quality": round(float(rows[5] or 0), 3),
                "browser_render_count": rows[6] or 0,
                "browser_render_rate": round((rows[6] or 0) / max(total, 1), 3),
                "last_crawl": str(rows[7]) if rows[7] else None,
            }
        except Exception as e:
            logger.error("completeness_dashboard_failed", error=str(e))
            return {"error": str(e)}

    def get_source_analytics(self, db: Session, org_id: str) -> Dict[str, Any]:
        """Analyze extraction source distribution across all crawled pages."""
        try:
            rows = db.execute(text("""
                SELECT extraction_sources, COUNT(*) as cnt
                FROM crawled_pages
                WHERE organization_id = :org
                  AND extraction_sources IS NOT NULL
                GROUP BY extraction_sources
                LIMIT 200
            """), {"org": org_id}).fetchall()

            source_counts: Dict[str, int] = defaultdict(int)
            multi_source_count = 0

            for row in rows:
                sources = row[0] or []
                cnt = row[1]
                if isinstance(sources, list):
                    for src in sources:
                        source_counts[src] += cnt
                    if len(sources) > 1:
                        multi_source_count += cnt

            total = sum(source_counts.values())
            return {
                "source_distribution": dict(sorted(source_counts.items(), key=lambda x: -x[1])),
                "source_rates": {
                    src: round(cnt / max(total, 1), 3)
                    for src, cnt in source_counts.items()
                },
                "multi_source_pages": multi_source_count,
                "api_first_rate": round(
                    (source_counts.get("shopify_json", 0) +
                     source_counts.get("graphql", 0) +
                     source_counts.get("xhr_api", 0)) / max(total, 1), 3
                ),
            }
        except Exception as e:
            logger.error("source_analytics_failed", error=str(e))
            return {"error": str(e)}

    def get_low_confidence_report(self, db: Session, org_id: str) -> Dict[str, Any]:
        """Report pages with low completeness scores and their missing fields."""
        try:
            rows = db.execute(text("""
                SELECT url, completeness_score, extraction_sources, extraction_quality
                FROM crawled_pages
                WHERE organization_id = :org
                  AND completeness_score < 0.75
                ORDER BY completeness_score ASC
                LIMIT 50
            """), {"org": org_id}).fetchall()

            pages = [
                {
                    "url": r[0],
                    "completeness_score": round(float(r[1]), 3) if r[1] else None,
                    "extraction_sources": r[2],
                    "extraction_quality": round(float(r[3]), 3) if r[3] else None,
                }
                for r in rows
            ]

            return {
                "low_confidence_page_count": len(pages),
                "pages": pages,
                "recommendation": "Re-crawl these URLs with enable_deep_extraction=true",
            }
        except Exception as e:
            logger.error("low_confidence_report_failed", error=str(e))
            return {"error": str(e)}

    def get_failed_extraction_metrics(self, db: Session, org_id: str) -> Dict[str, Any]:
        """Aggregate failed extraction metrics from crawl_errors table."""
        try:
            rows = db.execute(text("""
                SELECT error_type, COUNT(*) as cnt, MAX(created_at) as last_seen
                FROM crawl_errors
                WHERE organization_id = :org
                GROUP BY error_type
                ORDER BY cnt DESC
                LIMIT 20
            """), {"org": org_id}).fetchall()

            total_errors = db.execute(text("""
                SELECT COUNT(*) FROM crawl_errors WHERE organization_id = :org
            """), {"org": org_id}).scalar() or 0

            return {
                "total_errors": total_errors,
                "error_breakdown": [
                    {"error_type": r[0], "count": r[1], "last_seen": str(r[2])}
                    for r in rows
                ],
            }
        except Exception as e:
            logger.error("failed_extraction_metrics_failed", error=str(e))
            return {"error": str(e)}

    def get_crawl_quality_trend(
        self, db: Session, org_id: str, days: int = 7
    ) -> Dict[str, Any]:
        """Crawl quality trend over the last N days."""
        try:
            rows = db.execute(text("""
                SELECT
                    DATE(crawled_at) AS crawl_date,
                    COUNT(*) AS pages,
                    AVG(completeness_score) AS avg_completeness,
                    AVG(extraction_quality) AS avg_quality,
                    COUNT(*) FILTER (WHERE used_browser = true) AS browser_renders
                FROM crawled_pages
                WHERE organization_id = :org
                  AND crawled_at >= NOW() - INTERVAL ':days days'
                GROUP BY DATE(crawled_at)
                ORDER BY crawl_date ASC
            """), {"org": org_id, "days": days}).fetchall()

            return {
                "days": days,
                "trend": [
                    {
                        "date": str(r[0]),
                        "pages_crawled": r[1],
                        "avg_completeness": round(float(r[2] or 0), 3),
                        "avg_quality": round(float(r[3] or 0), 3),
                        "browser_renders": r[4] or 0,
                    }
                    for r in rows
                ],
            }
        except Exception as e:
            logger.error("crawl_quality_trend_failed", error=str(e))
            return {"error": str(e)}

    def get_price_change_summary(self, db: Session, org_id: str) -> Dict[str, Any]:
        """Summary of recent price changes from product_price_history."""
        try:
            rows = db.execute(text("""
                SELECT url, old_price, new_price, currency, is_promotion, changed_at
                FROM product_price_history
                WHERE organization_id = :org
                ORDER BY changed_at DESC
                LIMIT 20
            """), {"org": org_id}).fetchall()

            return {
                "recent_price_changes": [
                    {
                        "url": r[0],
                        "old_price": r[1],
                        "new_price": r[2],
                        "currency": r[3],
                        "is_promotion": r[4],
                        "changed_at": str(r[5]),
                        "change_pct": round((r[2] - r[1]) / max(r[1], 1) * 100, 1) if r[1] else None,
                    }
                    for r in rows
                ],
            }
        except Exception as e:
            return {"error": str(e)}

    def get_full_dashboard(self, db: Session, org_id: str) -> Dict[str, Any]:
        """Aggregate all crawler observability metrics into one response."""
        return {
            "completeness":       self.get_completeness_dashboard(db, org_id),
            "source_analytics":   self.get_source_analytics(db, org_id),
            "low_confidence":     self.get_low_confidence_report(db, org_id),
            "failed_extractions": self.get_failed_extraction_metrics(db, org_id),
            "quality_trend":      self.get_crawl_quality_trend(db, org_id),
            "price_changes":      self.get_price_change_summary(db, org_id),
            "realtime_counters":  self._get_realtime_counters(),
        }

    def _get_realtime_counters(self) -> Dict[str, Any]:
        """Pull in-memory counters from MetricsCollector."""
        counters = metrics_collector.counters
        histograms = metrics_collector.histograms

        def hist_avg(key: str) -> float:
            vals = histograms.get(key, [])
            return round(sum(vals) / len(vals), 3) if vals else 0.0

        return {
            "pages_extracted":      counters.get("crawler.pages_extracted", 0),
            "browser_renders":      counters.get("crawler.browser_renders", 0),
            "llm_extractions":      counters.get("crawler.llm_extractions", 0),
            "deep_extractions":     counters.get("crawler.deep_extractions", 0),
            "completeness_full":    counters.get("crawler.completeness.full", 0),
            "completeness_partial": counters.get("crawler.completeness.partial", 0),
            "completeness_fallback":counters.get("crawler.completeness.fallback", 0),
            "avg_completeness":     hist_avg("crawler.completeness_score"),
            "avg_fetch_latency_ms": hist_avg("crawler.fetch_latency_ms"),
        }


crawler_observability = CrawlerObservability()
