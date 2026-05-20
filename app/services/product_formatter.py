"""
ProductEntityFormatter — strict structured output formatter.

Implements the three response modes defined in the system prompt:
  FULL MODE    (completeness ≥ 0.85) — all fields, full SKU graph
  PARTIAL MODE (0.75 ≤ score < 0.85) — available fields + missing field list
  FALLBACK MODE (score < 0.75)       — URL only, no hallucination

Every response includes:
  - canonical product URL
  - completeness score
  - sources used
  - field-level confidence indicators
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from app.crawler.entity_model import ProductEntity, FieldValue, SOURCE_PRIORITY
from app.crawler.completeness_engine import CompletenessScore
from app.core.logging import get_logger

logger = get_logger(__name__)

FULL_THRESHOLD    = 0.85
PARTIAL_THRESHOLD = 0.75

# Human-readable confidence labels
CONFIDENCE_LABELS: Dict[str, str] = {
    "shopify_json": "high",
    "graphql":      "high",
    "xhr_api":      "high",
    "jsonld":       "high",
    "hydration":    "medium",
    "dom":          "low",
    "og_meta":      "low",
    "llm":          "very low",
}


class ProductEntityFormatter:
    """Format ProductEntity objects into structured response strings."""

    def format(
        self,
        entity: ProductEntity,
        score: CompletenessScore,
    ) -> Dict[str, Any]:
        """
        Format a single product entity.
        Returns a dict with 'mode', 'text', and structured fields.
        """
        if score.total >= FULL_THRESHOLD:
            return self._full_mode(entity, score)
        elif score.total >= PARTIAL_THRESHOLD:
            return self._partial_mode(entity, score)
        else:
            return self._fallback_mode(entity, score)

    def format_multi(
        self,
        results: List[Tuple[ProductEntity, float]],
    ) -> Dict[str, Any]:
        """
        Format up to 3 product results for a multi-product query.
        Each result includes its own completeness score and source URL.
        """
        from app.crawler.completeness_engine import CompletenessScore

        formatted = []
        for entity, relevance in results[:3]:
            score = CompletenessScore(entity)
            item = self.format(entity, score)
            item["relevance_score"] = round(relevance, 3)
            formatted.append(item)

        return {
            "result_count": len(formatted),
            "products": formatted,
        }

    # ── FULL MODE ─────────────────────────────────────────────────────────────

    def _full_mode(self, entity: ProductEntity, score: CompletenessScore) -> Dict[str, Any]:
        def v(fv: Optional[FieldValue], default: str = "Not available") -> str:
            return str(fv.value) if fv and fv.value not in (None, "", [], {}) else default

        def conf(fv: Optional[FieldValue]) -> str:
            if not fv:
                return ""
            return CONFIDENCE_LABELS.get(fv.source, "medium")

        lines = ["## Product Entity — FULL"]
        lines.append(f"Product:      {v(entity.title)}")

        price_str = v(entity.price, "Not available")
        currency = v(entity.currency, "")
        if price_str != "Not available" and currency:
            price_str = f"{price_str} {currency}"
        lines.append(f"Price:        {price_str}  [{conf(entity.price)} confidence]")

        lines.append(f"Availability: {v(entity.availability)}")
        lines.append(f"Brand:        {v(entity.brand)}")
        lines.append(f"SKU:          {v(entity.sku)}")
        lines.append(f"Type:         {v(entity.product_type)}")

        # Variants — full SKU graph
        if entity.variants:
            lines.append("\nVariants:")
            for var in entity.variants:
                avail = "In Stock" if var.available else "Out of Stock"
                opts = ", ".join(f"{k}: {val}" for k, val in var.options.items()) if var.options else var.title
                price = f"{var.price:.2f} {var.currency}".strip() if var.price else "N/A"
                sku_str = f"  SKU: {var.sku}" if var.sku else ""
                lines.append(f"  • {opts} — {price} — {avail}{sku_str}")
        else:
            lines.append("Variants:     Not available")

        # Attributes
        attrs = []
        if entity.material and entity.material.value:
            attrs.append(f"Material: {entity.material.value}")
        if entity.color and entity.color.value:
            attrs.append(f"Color: {entity.color.value}")
        if entity.size_options and entity.size_options.value:
            attrs.append(f"Sizes: {entity.size_options.value}")
        if entity.weight and entity.weight.value:
            attrs.append(f"Weight: {entity.weight.value}")
        if attrs:
            lines.append("\nAttributes:")
            lines.extend(f"  {a}" for a in attrs)

        # Description
        desc = v(entity.description, "")
        if desc:
            lines.append(f"\nDescription:\n  {desc[:500]}")

        # Logistics
        if entity.shipping_info and entity.shipping_info.value:
            lines.append(f"\nShipping:\n  {str(entity.shipping_info.value)[:300]}")
        if entity.return_policy and entity.return_policy.value:
            lines.append(f"\nReturn Policy:\n  {str(entity.return_policy.value)[:300]}")
        if entity.care_instructions and entity.care_instructions.value:
            lines.append(f"\nCare Instructions:\n  {str(entity.care_instructions.value)[:200]}")

        # Footer
        lines.append(f"\nCompleteness Score: {score.total:.2f}")
        lines.append(f"Sources: {', '.join(entity.sources_used)}")
        lines.append(f"\nSource:\n{entity.url}")

        return {
            "mode": "FULL",
            "completeness_score": round(score.total, 3),
            "text": "\n".join(lines),
            "product_url": entity.url,
            "sources_used": entity.sources_used,
            "structured": self._to_structured_dict(entity, score),
        }

    # ── PARTIAL MODE ──────────────────────────────────────────────────────────

    def _partial_mode(self, entity: ProductEntity, score: CompletenessScore) -> Dict[str, Any]:
        def v(fv: Optional[FieldValue], default: str = "Not available") -> str:
            return str(fv.value) if fv and fv.value not in (None, "", [], {}) else default

        lines = ["## Product Entity — PARTIAL"]
        lines.append(f"Product:      {v(entity.title)}")

        price_str = v(entity.price, "Not available")
        currency = v(entity.currency, "")
        if price_str != "Not available" and currency:
            price_str = f"{price_str} {currency}"
        lines.append(f"Price:        {price_str}")
        lines.append(f"Availability: {v(entity.availability)}")
        lines.append(f"Brand:        {v(entity.brand)}")
        lines.append(f"SKU:          {v(entity.sku)}")

        # Partial variants — flag missing SKUs
        if entity.variants:
            lines.append("\nVariants:")
            for var in entity.variants:
                avail = "In Stock" if var.available else "Out of Stock"
                opts = ", ".join(f"{k}: {val}" for k, val in var.options.items()) if var.options else var.title
                price = f"{var.price:.2f} {var.currency}".strip() if var.price else "N/A"
                sku_str = f"  SKU: {var.sku}" if var.sku else "  ⚠ SKU missing"
                lines.append(f"  • {opts} — {price} — {avail}{sku_str}")
        else:
            lines.append("Variants:     Not available")

        desc = v(entity.description, "")
        if desc:
            lines.append(f"\nDescription:\n  {desc[:300]}")

        # Missing fields warning
        if score.missing_fields:
            lines.append("\n⚠ Missing Fields:")
            for field in score.missing_fields:
                lines.append(f"  - {field}")

        lines.append("\nMore details available at official product page.")
        lines.append(f"\nCompleteness Score: {score.total:.2f}")
        lines.append(f"Sources: {', '.join(entity.sources_used)}")
        lines.append(f"\nSource:\n{entity.url}")

        return {
            "mode": "PARTIAL",
            "completeness_score": round(score.total, 3),
            "text": "\n".join(lines),
            "product_url": entity.url,
            "missing_fields": score.missing_fields,
            "sources_used": entity.sources_used,
            "structured": self._to_structured_dict(entity, score),
        }

    # ── FALLBACK MODE ─────────────────────────────────────────────────────────

    def _fallback_mode(self, entity: ProductEntity, score: CompletenessScore) -> Dict[str, Any]:
        def v(fv: Optional[FieldValue], default: str = "") -> str:
            return str(fv.value) if fv and fv.value not in (None, "", [], {}) else default

        title = v(entity.title, "Unknown Product")

        lines = [f"## Product Entity — FALLBACK"]
        lines.append(f"Product: {title}")
        lines.append("")
        lines.append("Data incomplete — requires API or network extraction.")
        lines.append("")
        lines.append(f"👉 Official Product URL:")
        lines.append(f"{entity.url}")

        # Include any partial data we do have — never invent
        partial_fields = []
        if entity.price and entity.price.value:
            currency = v(entity.currency, "")
            partial_fields.append(f"Price: {entity.price.value} {currency}".strip())
        if entity.availability and entity.availability.value:
            partial_fields.append(f"Availability: {entity.availability.value}")
        if entity.brand and entity.brand.value:
            partial_fields.append(f"Brand: {entity.brand.value}")

        if partial_fields:
            lines.append("\nPartially available data:")
            lines.extend(f"  {f}" for f in partial_fields)

        lines.append(f"\nCompleteness Score: {score.total:.2f}")
        if entity.sources_used:
            lines.append(f"Sources: {', '.join(entity.sources_used)}")

        return {
            "mode": "FALLBACK",
            "completeness_score": round(score.total, 3),
            "text": "\n".join(lines),
            "product_url": entity.url,
            "missing_fields": score.missing_fields,
            "sources_used": entity.sources_used,
            "structured": self._to_structured_dict(entity, score),
        }

    # ── Structured dict ───────────────────────────────────────────────────────

    def _to_structured_dict(
        self,
        entity: ProductEntity,
        score: CompletenessScore,
    ) -> Dict[str, Any]:
        """Machine-readable structured representation."""
        def v(fv: Optional[FieldValue]):
            return fv.value if fv else None

        return {
            "title":          v(entity.title),
            "price":          v(entity.price),
            "currency":       v(entity.currency),
            "availability":   v(entity.availability),
            "brand":          v(entity.brand),
            "sku":            v(entity.sku),
            "product_type":   v(entity.product_type),
            "material":       v(entity.material),
            "color":          v(entity.color),
            "size_options":   v(entity.size_options),
            "description":    v(entity.description),
            "shipping_info":  v(entity.shipping_info),
            "return_policy":  v(entity.return_policy),
            "care_instructions": v(entity.care_instructions),
            "tags":           v(entity.tags),
            "variants": [
                {
                    "sku":       var.sku,
                    "title":     var.title,
                    "price":     var.price,
                    "currency":  var.currency,
                    "available": var.available,
                    "options":   var.options,
                }
                for var in entity.variants
            ],
            "url":              entity.url,
            "completeness":     round(score.total, 3),
            "completeness_dimensions": score.dimensions,
            "missing_fields":   score.missing_fields,
            "sources_used":     entity.sources_used,
        }


product_formatter = ProductEntityFormatter()
