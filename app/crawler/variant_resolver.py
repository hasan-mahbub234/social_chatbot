"""
Variant Graph Resolver

Merges variants across all sources (GraphQL, Shopify JSON, inventory APIs,
recommendation APIs) with per-field confidence scoring and SKU conflict resolution.

Resolution rules:
  1. SKU is the canonical variant identity key
  2. Higher-priority source wins per field (same as entity model)
  3. Inventory data (available/stock_level) always overrides older data
  4. Conflicting prices are flagged, highest-confidence source wins
  5. Variants without SKU are matched by title similarity
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from app.crawler.entity_model import ProductVariant, SOURCE_PRIORITY
from app.core.logging import get_logger

logger = get_logger(__name__)

# Confidence per source (0-1)
SOURCE_CONFIDENCE: Dict[str, float] = {
    "shopify_json": 1.00,
    "graphql":      0.95,
    "xhr_api":      0.90,
    "inventory_api":0.98,   # inventory APIs are authoritative for stock
    "jsonld":       0.80,
    "hydration":    0.70,
    "dom":          0.50,
    "llm":          0.15,
}


@dataclass
class ResolvedVariant:
    """A variant with per-field confidence tracking."""
    sku: str = ""
    title: str = ""
    price: float = 0.0
    currency: str = ""
    available: bool = True
    stock_level: Optional[int] = None
    options: Dict[str, str] = field(default_factory=dict)
    barcode: str = ""
    weight: float = 0.0
    image_url: str = ""

    # Per-field provenance
    field_sources: Dict[str, str] = field(default_factory=dict)       # field → source
    field_confidence: Dict[str, float] = field(default_factory=dict)  # field → confidence
    conflicts: List[Dict[str, Any]] = field(default_factory=list)     # detected conflicts


class VariantResolver:
    """
    Merge and resolve variants from multiple sources into a canonical set.
    """

    def resolve(
        self,
        sources: Dict[str, List[Dict]],
    ) -> List[ResolvedVariant]:
        """
        Merge variants from multiple sources.

        Args:
            sources: {source_name: [variant_dict, ...]}

        Returns:
            List of ResolvedVariant, deduplicated by SKU.
        """
        # Collect all variants with their source
        all_variants: List[Tuple[str, Dict]] = []
        for source_name, variants in sources.items():
            for v in variants:
                all_variants.append((source_name, v))

        # Sort by source priority (highest first) so high-priority sources
        # establish the base and lower-priority sources only fill gaps
        all_variants.sort(
            key=lambda x: SOURCE_PRIORITY.get(x[0], 0),
            reverse=True,
        )

        # Build resolved map keyed by SKU
        resolved_by_sku: Dict[str, ResolvedVariant] = {}
        # For variants without SKU, key by normalized title
        resolved_by_title: Dict[str, ResolvedVariant] = {}

        for source_name, vd in all_variants:
            sku = str(vd.get("sku", "")).strip()
            title = str(vd.get("title", "")).strip()
            norm_title = self._normalize_title(title)

            if sku:
                if sku in resolved_by_sku:
                    self._merge_into(resolved_by_sku[sku], vd, source_name)
                else:
                    resolved_by_sku[sku] = self._create_resolved(vd, source_name)
            elif norm_title:
                if norm_title in resolved_by_title:
                    self._merge_into(resolved_by_title[norm_title], vd, source_name)
                else:
                    rv = self._create_resolved(vd, source_name)
                    resolved_by_title[norm_title] = rv
            else:
                # No SKU, no title — create with generated key
                key = f"_unknown_{len(resolved_by_sku) + len(resolved_by_title)}"
                resolved_by_sku[key] = self._create_resolved(vd, source_name)

        result = list(resolved_by_sku.values()) + list(resolved_by_title.values())

        # Reconcile inventory: if inventory_api source present, it's authoritative for availability
        result = self._reconcile_inventory(result, sources)

        logger.debug(
            "variants_resolved",
            input_count=len(all_variants),
            output_count=len(result),
            sources=list(sources.keys()),
        )
        return result

    def _create_resolved(self, vd: Dict, source_name: str) -> ResolvedVariant:
        """Create a new ResolvedVariant from a raw variant dict."""
        conf = SOURCE_CONFIDENCE.get(source_name, 0.5)
        rv = ResolvedVariant(
            sku=str(vd.get("sku", "")).strip(),
            title=str(vd.get("title", "")).strip(),
            price=self._to_float(vd.get("price", 0)),
            currency=str(vd.get("currency", "")),
            available=bool(vd.get("available", True)),
            stock_level=vd.get("stock_level"),
            options=dict(vd.get("options", {})),
            barcode=str(vd.get("barcode", "")),
            weight=self._to_float(vd.get("weight", 0)),
            image_url=str(vd.get("image_url", "")),
        )
        for f in ("sku", "title", "price", "currency", "available", "options", "barcode"):
            if getattr(rv, f, None) not in (None, "", {}, 0.0):
                rv.field_sources[f] = source_name
                rv.field_confidence[f] = conf
        return rv

    def _merge_into(self, rv: ResolvedVariant, vd: Dict, source_name: str):
        """Merge a lower-or-equal priority source into an existing ResolvedVariant."""
        conf = SOURCE_CONFIDENCE.get(source_name, 0.5)
        src_priority = SOURCE_PRIORITY.get(source_name, 0)

        field_map = {
            "title":    "title",
            "price":    "price",
            "currency": "currency",
            "barcode":  "barcode",
            "weight":   "weight",
            "image_url":"image_url",
        }

        for vd_key, rv_attr in field_map.items():
            new_val = vd.get(vd_key)
            if new_val in (None, "", 0, 0.0):
                continue
            existing_source = rv.field_sources.get(rv_attr, "")
            existing_priority = SOURCE_PRIORITY.get(existing_source, 0)

            if src_priority > existing_priority:
                # Higher priority source — overwrite
                old_val = getattr(rv, rv_attr)
                if old_val and old_val != new_val:
                    rv.conflicts.append({
                        "field": rv_attr,
                        "old_value": old_val,
                        "old_source": existing_source,
                        "new_value": new_val,
                        "new_source": source_name,
                    })
                setattr(rv, rv_attr, new_val if rv_attr != "price" else self._to_float(new_val))
                rv.field_sources[rv_attr] = source_name
                rv.field_confidence[rv_attr] = conf
            elif not getattr(rv, rv_attr, None):
                # Fill empty field regardless of priority
                setattr(rv, rv_attr, new_val if rv_attr != "price" else self._to_float(new_val))
                rv.field_sources[rv_attr] = source_name
                rv.field_confidence[rv_attr] = conf

        # Availability: inventory_api is always authoritative
        new_avail = vd.get("available")
        if new_avail is not None:
            if source_name == "inventory_api" or src_priority > SOURCE_PRIORITY.get(rv.field_sources.get("available", ""), 0):
                rv.available = bool(new_avail)
                rv.field_sources["available"] = source_name
                rv.field_confidence["available"] = conf

        # Stock level: always take the most recent inventory data
        new_stock = vd.get("stock_level")
        if new_stock is not None and source_name in ("inventory_api", "xhr_api", "graphql"):
            rv.stock_level = int(new_stock)
            rv.field_sources["stock_level"] = source_name

        # Options: merge additively (add missing option keys)
        new_opts = vd.get("options", {})
        if new_opts:
            for k, v in new_opts.items():
                if k not in rv.options:
                    rv.options[k] = v

    def _reconcile_inventory(
        self,
        variants: List[ResolvedVariant],
        sources: Dict[str, List[Dict]],
    ) -> List[ResolvedVariant]:
        """
        If an inventory_api source is present, reconcile availability
        for all variants against it.
        """
        inventory_source = sources.get("inventory_api", [])
        if not inventory_source:
            return variants

        # Build inventory map by SKU
        inv_by_sku: Dict[str, Dict] = {}
        for inv in inventory_source:
            sku = str(inv.get("sku", "")).strip()
            if sku:
                inv_by_sku[sku] = inv

        for rv in variants:
            if rv.sku in inv_by_sku:
                inv = inv_by_sku[rv.sku]
                rv.available = bool(inv.get("available", rv.available))
                if inv.get("stock_level") is not None:
                    rv.stock_level = int(inv["stock_level"])
                rv.field_sources["available"] = "inventory_api"
                rv.field_confidence["available"] = SOURCE_CONFIDENCE["inventory_api"]

        return variants

    def to_product_variants(
        self, resolved: List[ResolvedVariant]
    ) -> List[ProductVariant]:
        """Convert ResolvedVariants to ProductVariant objects for entity merging."""
        return [
            ProductVariant(
                sku=rv.sku,
                title=rv.title,
                price=rv.price,
                currency=rv.currency,
                available=rv.available,
                options=rv.options,
                barcode=rv.barcode,
                weight=rv.weight,
                source=rv.field_sources.get("price", "dom"),
            )
            for rv in resolved
        ]

    def get_conflict_report(
        self, resolved: List[ResolvedVariant]
    ) -> List[Dict[str, Any]]:
        """Return all field conflicts detected during resolution."""
        conflicts = []
        for rv in resolved:
            for c in rv.conflicts:
                conflicts.append({"sku": rv.sku, **c})
        return conflicts

    def confidence_summary(
        self, resolved: List[ResolvedVariant]
    ) -> Dict[str, Any]:
        """Aggregate confidence statistics across all resolved variants."""
        if not resolved:
            return {}
        all_conf = [c for rv in resolved for c in rv.field_confidence.values()]
        avg_conf = sum(all_conf) / len(all_conf) if all_conf else 0.0
        low_conf_variants = [
            rv.sku for rv in resolved
            if any(c < 0.5 for c in rv.field_confidence.values())
        ]
        return {
            "avg_confidence": round(avg_conf, 3),
            "low_confidence_variants": low_conf_variants,
            "total_conflicts": sum(len(rv.conflicts) for rv in resolved),
        }

    @staticmethod
    def _normalize_title(title: str) -> str:
        return re.sub(r'\s+', ' ', title.lower().strip())

    @staticmethod
    def _to_float(val: Any) -> float:
        try:
            return float(str(val).replace(",", ""))
        except (ValueError, TypeError):
            return 0.0


variant_resolver = VariantResolver()
