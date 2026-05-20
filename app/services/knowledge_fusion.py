"""
Cross-Page Knowledge Fusion Service

Merges product knowledge from multiple page types into a single canonical entity:
  - product pages
  - collection pages (hints: title, price, availability)
  - recommendation widgets (related products)
  - search endpoint results
  - review APIs (rating, review count)

Applies confidence-aware field fusion with conflict detection and provenance tracking.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from app.crawler.entity_model import ProductEntity, SOURCE_PRIORITY
from app.crawler.completeness_engine import CompletenessScore
from app.core.logging import get_logger

logger = get_logger(__name__)

# Source confidence for cross-page sources
CROSS_PAGE_CONFIDENCE: Dict[str, float] = {
    "product_page":     1.00,
    "shopify_json":     1.00,
    "graphql":          0.95,
    "search_api":       0.85,
    "collection_page":  0.60,
    "recommendation":   0.50,
    "review_api":       0.70,
    "sitemap_hint":     0.30,
}


@dataclass
class FusionSource:
    source_type: str        # product_page | collection_page | recommendation | search_api | review_api
    url: str
    data: Dict[str, Any]
    confidence: float = 1.0


@dataclass
class FusionResult:
    entity: ProductEntity
    completeness_score: float
    sources_fused: List[str]
    conflicts_detected: List[Dict[str, Any]]
    provenance: Dict[str, str]   # field → source_type


class KnowledgeFusionService:
    """
    Fuse product knowledge from multiple page types into a single entity.
    """

    def fuse(
        self,
        canonical_url: str,
        organization_id: str,
        sources: List[FusionSource],
    ) -> FusionResult:
        """
        Fuse all sources into a single ProductEntity.

        Sources are processed in confidence order (highest first).
        Field-level conflicts are detected and logged.
        """
        entity = ProductEntity(url=canonical_url, organization_id=organization_id)
        conflicts: List[Dict[str, Any]] = []
        provenance: Dict[str, str] = {}

        # Sort by confidence descending
        sorted_sources = sorted(sources, key=lambda s: s.confidence, reverse=True)

        for source in sorted_sources:
            before_fields = self._snapshot_fields(entity)
            entity = self._apply_source(entity, source)
            after_fields = self._snapshot_fields(entity)

            # Detect conflicts: field changed by lower-confidence source
            for field_name, new_val in after_fields.items():
                old_val = before_fields.get(field_name)
                if old_val and new_val and old_val != new_val:
                    conflicts.append({
                        "field": field_name,
                        "old_value": old_val,
                        "old_source": provenance.get(field_name, "unknown"),
                        "new_value": new_val,
                        "new_source": source.source_type,
                        "confidence_delta": source.confidence - CROSS_PAGE_CONFIDENCE.get(
                            provenance.get(field_name, ""), 0
                        ),
                    })
                if new_val and field_name not in provenance:
                    provenance[field_name] = source.source_type

        score = CompletenessScore(entity)

        logger.info(
            "knowledge_fusion_complete",
            url=canonical_url,
            sources=[s.source_type for s in sorted_sources],
            completeness=round(score.total, 3),
            conflicts=len(conflicts),
        )

        return FusionResult(
            entity=entity,
            completeness_score=round(score.total, 3),
            sources_fused=[s.source_type for s in sorted_sources],
            conflicts_detected=conflicts,
            provenance=provenance,
        )

    def fuse_collection_hints(
        self,
        entity: ProductEntity,
        collection_data: Dict[str, Any],
        collection_url: str,
    ) -> ProductEntity:
        """
        Merge collection page hints into an existing entity.
        Collection pages typically provide: title, price, availability, image.
        These are lower confidence than product page data.
        """
        source = FusionSource(
            source_type="collection_page",
            url=collection_url,
            data=collection_data,
            confidence=CROSS_PAGE_CONFIDENCE["collection_page"],
        )
        return self._apply_source(entity, source)

    def fuse_search_results(
        self,
        entities: List[ProductEntity],
        search_results: List[Dict[str, Any]],
        organization_id: str,
    ) -> List[ProductEntity]:
        """
        Enrich a list of entities with data from search API results.
        Matches by URL or title similarity.
        """
        enriched = []
        for entity in entities:
            match = self._find_search_match(entity, search_results)
            if match:
                source = FusionSource(
                    source_type="search_api",
                    url=entity.url,
                    data=match,
                    confidence=CROSS_PAGE_CONFIDENCE["search_api"],
                )
                entity = self._apply_source(entity, source)
            enriched.append(entity)
        return enriched

    def fuse_reviews(
        self,
        entity: ProductEntity,
        review_data: Dict[str, Any],
    ) -> ProductEntity:
        """
        Merge review metadata (rating, count) into entity metadata.
        Reviews don't affect completeness score but enrich the content string.
        """
        rating = review_data.get("average_rating") or review_data.get("rating")
        count = review_data.get("review_count") or review_data.get("count")
        if rating or count:
            existing_desc = entity.description.value if entity.description else ""
            review_str = ""
            if rating:
                review_str += f"Rating: {rating}/5"
            if count:
                review_str += f" ({count} reviews)"
            if review_str and existing_desc:
                from app.crawler.entity_model import FieldValue
                entity.description = FieldValue(
                    value=f"{existing_desc}\n{review_str}",
                    source="review_api",
                    confidence=CROSS_PAGE_CONFIDENCE["review_api"],
                )
        return entity

    def detect_duplicate_products(
        self,
        entities: List[ProductEntity],
    ) -> List[Tuple[ProductEntity, ProductEntity, float]]:
        """
        Detect potential duplicate products by comparing titles and SKUs.
        Returns list of (entity_a, entity_b, similarity_score) tuples.
        """
        duplicates = []
        for i, a in enumerate(entities):
            for b in entities[i + 1:]:
                sim = self._entity_similarity(a, b)
                if sim > 0.85:
                    duplicates.append((a, b, sim))
        return duplicates

    def merge_duplicates(
        self,
        primary: ProductEntity,
        secondary: ProductEntity,
    ) -> ProductEntity:
        """
        Merge a secondary entity into a primary entity.
        Primary entity's fields take precedence.
        """
        for source_name, raw_data in secondary.raw_sources.items():
            if source_name not in primary.sources_used:
                primary.merge(source_name, raw_data)
        return primary

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _apply_source(
        self, entity: ProductEntity, source: FusionSource
    ) -> ProductEntity:
        """Apply a FusionSource to an entity using the entity's merge logic."""
        # Map source_type to entity source name for priority lookup
        source_name = self._map_source_name(source.source_type)
        entity.merge(source_name, source.data)
        return entity

    def _map_source_name(self, source_type: str) -> str:
        mapping = {
            "product_page":    "dom",
            "collection_page": "dom",
            "recommendation":  "dom",
            "search_api":      "xhr_api",
            "review_api":      "dom",
            "sitemap_hint":    "og_meta",
        }
        return mapping.get(source_type, "dom")

    def _snapshot_fields(self, entity: ProductEntity) -> Dict[str, Any]:
        """Snapshot current field values for conflict detection."""
        snapshot = {}
        for attr in ("title", "price", "availability", "brand", "sku",
                     "material", "shipping_info", "return_policy"):
            fv = getattr(entity, attr, None)
            if fv and fv.value:
                snapshot[attr] = str(fv.value)
        return snapshot

    def _find_search_match(
        self, entity: ProductEntity, search_results: List[Dict]
    ) -> Optional[Dict]:
        """Find a search result matching this entity by URL or title."""
        entity_url = entity.url.rstrip("/")
        entity_title = entity.title.value.lower() if entity.title else ""

        for result in search_results:
            result_url = str(result.get("url", "")).rstrip("/")
            result_title = str(result.get("title", "")).lower()

            if result_url == entity_url:
                return result
            if entity_title and result_title and self._title_similarity(entity_title, result_title) > 0.85:
                return result
        return None

    def _entity_similarity(self, a: ProductEntity, b: ProductEntity) -> float:
        """Compute similarity score between two entities."""
        score = 0.0

        # SKU match (definitive)
        a_sku = a.sku.value if a.sku else ""
        b_sku = b.sku.value if b.sku else ""
        if a_sku and b_sku and a_sku == b_sku:
            return 1.0

        # Title similarity
        a_title = a.title.value.lower() if a.title else ""
        b_title = b.title.value.lower() if b.title else ""
        if a_title and b_title:
            score += self._title_similarity(a_title, b_title) * 0.6

        # Price match
        a_price = float(a.price.value) if a.price and a.price.value else 0
        b_price = float(b.price.value) if b.price and b.price.value else 0
        if a_price and b_price and abs(a_price - b_price) / max(a_price, 1) < 0.01:
            score += 0.2

        # Brand match
        a_brand = a.brand.value if a.brand else ""
        b_brand = b.brand.value if b.brand else ""
        if a_brand and b_brand and a_brand.lower() == b_brand.lower():
            score += 0.2

        return min(1.0, score)

    def _title_similarity(self, a: str, b: str) -> float:
        """Simple token overlap similarity."""
        a_tokens = set(re.findall(r'\w+', a.lower()))
        b_tokens = set(re.findall(r'\w+', b.lower()))
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = a_tokens & b_tokens
        union = a_tokens | b_tokens
        return len(intersection) / len(union)


knowledge_fusion = KnowledgeFusionService()
