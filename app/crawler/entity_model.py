"""
Unified Product Entity Model — merges data from all extraction sources with
conflict resolution and field-level provenance tracking.

Source priority (highest → lowest):
  shopify_json > graphql > xhr_api > jsonld > hydration > dom > og_meta
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Source priority ───────────────────────────────────────────────────────────
SOURCE_PRIORITY: Dict[str, int] = {
    "shopify_json": 100,
    "graphql":      90,
    "xhr_api":      80,
    "jsonld":       70,
    "hydration":    60,
    "dom":          40,
    "og_meta":      20,
    "llm":          10,
}


@dataclass
class FieldValue:
    """A single field value with its source and confidence."""
    value: Any
    source: str
    confidence: float = 1.0

    @property
    def priority(self) -> int:
        return SOURCE_PRIORITY.get(self.source, 0)


@dataclass
class ProductVariant:
    sku: str = ""
    title: str = ""
    price: float = 0.0
    currency: str = ""
    available: bool = True
    options: Dict[str, str] = field(default_factory=dict)   # {"Size": "M", "Color": "Black"}
    barcode: str = ""
    weight: float = 0.0
    source: str = ""


@dataclass
class ProductEntity:
    """
    Canonical product entity built from merged multi-source data.
    Each field stores the winning FieldValue; provenance is preserved.
    """
    url: str = ""
    organization_id: str = ""

    # Core identity
    title: Optional[FieldValue] = None
    handle: Optional[FieldValue] = None
    sku: Optional[FieldValue] = None
    barcode: Optional[FieldValue] = None

    # Pricing
    price: Optional[FieldValue] = None
    compare_at_price: Optional[FieldValue] = None
    currency: Optional[FieldValue] = None

    # Availability
    availability: Optional[FieldValue] = None

    # Classification
    brand: Optional[FieldValue] = None
    product_type: Optional[FieldValue] = None
    tags: Optional[FieldValue] = None
    categories: Optional[FieldValue] = None

    # Attributes
    material: Optional[FieldValue] = None
    color: Optional[FieldValue] = None
    size_options: Optional[FieldValue] = None
    weight: Optional[FieldValue] = None
    dimensions: Optional[FieldValue] = None

    # Content
    description: Optional[FieldValue] = None
    images: Optional[FieldValue] = None

    # Logistics
    shipping_info: Optional[FieldValue] = None
    return_policy: Optional[FieldValue] = None
    care_instructions: Optional[FieldValue] = None

    # Variants
    variants: List[ProductVariant] = field(default_factory=list)

    # Provenance
    sources_used: List[str] = field(default_factory=list)
    raw_sources: Dict[str, Any] = field(default_factory=dict)   # source_name → raw dict

    def merge(self, source_name: str, data: Dict[str, Any]) -> "ProductEntity":
        """
        Merge a new data source into this entity.
        Each field is only overwritten if the new source has higher priority.
        """
        self.raw_sources[source_name] = data
        if source_name not in self.sources_used:
            self.sources_used.append(source_name)

        field_map = {
            "title":            "title",
            "handle":           "handle",
            "sku":              "sku",
            "barcode":          "barcode",
            "price":            "price",
            "compare_at_price": "compare_at_price",
            "currency":         "currency",
            "availability":     "availability",
            "brand":            "brand",
            "product_type":     "product_type",
            "tags":             "tags",
            "categories":       "categories",
            "material":         "material",
            "color":            "color",
            "size_options":     "size_options",
            "weight":           "weight",
            "dimensions":       "dimensions",
            "description":      "description",
            "images":           "images",
            "shipping_info":    "shipping_info",
            "return_policy":    "return_policy",
            "care_instructions":"care_instructions",
        }

        for data_key, entity_attr in field_map.items():
            raw_val = data.get(data_key)
            if raw_val is None or raw_val == "" or raw_val == []:
                continue
            new_fv = FieldValue(value=raw_val, source=source_name)
            existing: Optional[FieldValue] = getattr(self, entity_attr)
            if existing is None or new_fv.priority > existing.priority:
                setattr(self, entity_attr, new_fv)

        # Variants: always merge additively — higher-priority source wins per SKU
        new_variants: List[Dict] = data.get("variants", [])
        if new_variants:
            self._merge_variants(new_variants, source_name)

        return self

    def _merge_variants(self, new_variants: List[Dict], source_name: str):
        """Merge variants by SKU — higher-priority source overwrites lower."""
        existing_by_sku = {v.sku: v for v in self.variants if v.sku}
        src_priority = SOURCE_PRIORITY.get(source_name, 0)

        for vd in new_variants:
            sku = vd.get("sku", "")
            variant = ProductVariant(
                sku=sku,
                title=vd.get("title", ""),
                price=_to_float(vd.get("price", 0)),
                currency=vd.get("currency", ""),
                available=vd.get("available", True),
                options=vd.get("options", {}),
                barcode=vd.get("barcode", ""),
                weight=_to_float(vd.get("weight", 0)),
                source=source_name,
            )
            if sku and sku in existing_by_sku:
                existing_src_priority = SOURCE_PRIORITY.get(existing_by_sku[sku].source, 0)
                if src_priority >= existing_src_priority:
                    existing_by_sku[sku] = variant
            else:
                existing_by_sku[sku or f"_nosku_{len(existing_by_sku)}"] = variant

        self.variants = list(existing_by_sku.values())

    def to_content_string(self) -> str:
        """Render the merged entity as a structured text string for RAG ingestion."""
        def v(fv: Optional[FieldValue], default: str = "") -> str:
            return str(fv.value) if fv and fv.value else default

        lines: List[str] = []

        title = v(self.title)
        if title:
            lines.append(f"Product: {title}")

        price = v(self.price)
        currency = v(self.currency, "")
        if price:
            lines.append(f"Price: {price} {currency}".strip())

        compare = v(self.compare_at_price)
        if compare:
            lines.append(f"Compare At Price: {compare} {currency}".strip())

        avail = v(self.availability)
        if avail:
            lines.append(f"Availability: {avail}")

        brand = v(self.brand)
        if brand:
            lines.append(f"Brand: {brand}")

        sku = v(self.sku)
        if sku:
            lines.append(f"SKU: {sku}")

        ptype = v(self.product_type)
        if ptype:
            lines.append(f"Type: {ptype}")

        tags = v(self.tags)
        if tags:
            lines.append(f"Tags: {tags}")

        material = v(self.material)
        if material:
            lines.append(f"Material: {material}")

        color = v(self.color)
        if color:
            lines.append(f"Color: {color}")

        sizes = v(self.size_options)
        if sizes:
            lines.append(f"Sizes: {sizes}")

        desc = v(self.description)
        if desc:
            lines.append(f"\nDescription:\n{desc}")

        if self.variants:
            variant_lines = []
            for var in self.variants:
                avail_str = "In Stock" if var.available else "Out of Stock"
                opts = ", ".join(f"{k}: {val}" for k, val in var.options.items()) if var.options else var.title
                price_str = f"{var.price:.2f} {var.currency}".strip() if var.price else ""
                parts = [opts, price_str, avail_str]
                if var.sku:
                    parts.append(f"SKU: {var.sku}")
                variant_lines.append("  - " + ", ".join(p for p in parts if p))
            lines.append("\nVariants:\n" + "\n".join(variant_lines))

        shipping = v(self.shipping_info)
        if shipping:
            lines.append(f"\nShipping:\n{shipping}")

        returns = v(self.return_policy)
        if returns:
            lines.append(f"\nReturn Policy:\n{returns}")

        care = v(self.care_instructions)
        if care:
            lines.append(f"\nCare Instructions:\n{care}")

        lines.append(f"\n[Sources: {', '.join(self.sources_used)}]")
        return "\n".join(l for l in lines if l.strip())

    def to_metadata(self) -> Dict[str, Any]:
        def v(fv: Optional[FieldValue], default=None):
            return fv.value if fv else default

        return {
            "title":          v(self.title, ""),
            "sku":            v(self.sku, ""),
            "brand":          v(self.brand, ""),
            "price":          v(self.price),
            "currency":       v(self.currency, ""),
            "availability":   v(self.availability, ""),
            "product_type":   v(self.product_type, ""),
            "variant_count":  len(self.variants),
            "sources_used":   self.sources_used,
        }


def _to_float(val: Any) -> float:
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0
