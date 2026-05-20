"""
Completeness Scoring Engine + Deep Extraction Loop

Evaluates how complete a ProductEntity is across 6 dimensions and decides
whether to trigger a deeper extraction pass.

Completeness dimensions (weighted):
  - core_fields      (title, price, availability, brand)       weight 0.30
  - sku_coverage     (sku present + per-variant SKUs)          weight 0.20
  - variant_coverage (all variants have price + availability)  weight 0.20
  - attribute_coverage (material, color, size_options)         weight 0.15
  - logistics        (shipping_info, return_policy)            weight 0.10
  - content_quality  (description length)                      weight 0.05

Score ≥ COMPLETENESS_THRESHOLD → accept and ingest
Score <  COMPLETENESS_THRESHOLD → trigger deep extraction loop
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from app.crawler.entity_model import ProductEntity, FieldValue
from app.core.logging import get_logger

logger = get_logger(__name__)

COMPLETENESS_THRESHOLD = 0.72   # minimum acceptable completeness
MAX_DEEP_PASSES = 3             # max re-extraction attempts per URL


class CompletenessScore:
    """Detailed completeness breakdown for a ProductEntity."""

    def __init__(self, entity: ProductEntity):
        self.entity = entity
        self.dimensions: Dict[str, float] = {}
        self.missing_fields: List[str] = []
        self.total: float = 0.0
        self._evaluate()

    def _has(self, fv: Optional[FieldValue]) -> bool:
        return fv is not None and fv.value not in (None, "", [], {})

    def _evaluate(self):
        e = self.entity

        # 1. Core fields (0.30)
        core_checks = {
            "title":        self._has(e.title),
            "price":        self._has(e.price),
            "availability": self._has(e.availability),
            "brand":        self._has(e.brand),
        }
        core_score = sum(core_checks.values()) / len(core_checks)
        self.dimensions["core_fields"] = core_score
        self.missing_fields += [k for k, ok in core_checks.items() if not ok]

        # 2. SKU coverage (0.20)
        has_root_sku = self._has(e.sku)
        if e.variants:
            variants_with_sku = sum(1 for v in e.variants if v.sku)
            sku_score = (0.4 * has_root_sku + 0.6 * (variants_with_sku / len(e.variants)))
        else:
            sku_score = float(has_root_sku)
        self.dimensions["sku_coverage"] = sku_score
        if not has_root_sku:
            self.missing_fields.append("sku")

        # 3. Variant coverage (0.20)
        if e.variants:
            complete_variants = sum(
                1 for v in e.variants
                if v.price > 0 and v.title
            )
            variant_score = complete_variants / len(e.variants)
        else:
            # No variants is acceptable for simple products
            variant_score = 1.0 if self._has(e.price) else 0.0
        self.dimensions["variant_coverage"] = variant_score
        if e.variants and variant_score < 0.8:
            self.missing_fields.append("variant_details")

        # 4. Attribute coverage (0.15)
        attr_checks = {
            "material":     self._has(e.material),
            "color":        self._has(e.color),
            "size_options": self._has(e.size_options),
        }
        attr_score = sum(attr_checks.values()) / len(attr_checks)
        self.dimensions["attribute_coverage"] = attr_score
        self.missing_fields += [k for k, ok in attr_checks.items() if not ok]

        # 5. Logistics (0.10)
        logistics_checks = {
            "shipping_info": self._has(e.shipping_info),
            "return_policy": self._has(e.return_policy),
        }
        logistics_score = sum(logistics_checks.values()) / len(logistics_checks)
        self.dimensions["logistics"] = logistics_score
        self.missing_fields += [k for k, ok in logistics_checks.items() if not ok]

        # 6. Content quality (0.05)
        desc = e.description.value if e.description else ""
        desc_len = len(str(desc)) if desc else 0
        content_score = min(1.0, desc_len / 200)
        self.dimensions["content_quality"] = content_score
        if desc_len < 50:
            self.missing_fields.append("description")

        # Weighted total
        weights = {
            "core_fields":       0.30,
            "sku_coverage":      0.20,
            "variant_coverage":  0.20,
            "attribute_coverage":0.15,
            "logistics":         0.10,
            "content_quality":   0.05,
        }
        self.total = sum(self.dimensions[k] * w for k, w in weights.items())

    @property
    def is_complete(self) -> bool:
        return self.total >= COMPLETENESS_THRESHOLD

    @property
    def needs_deep_extraction(self) -> bool:
        return not self.is_complete

    def extraction_strategy(self) -> List[str]:
        """
        Return ordered list of extraction strategies to try next,
        based on which dimensions are weakest.
        """
        strategies = []
        dims = self.dimensions

        if dims["core_fields"] < 0.75:
            strategies.append("hydration_state")   # Next.js / Nuxt embedded JSON
            strategies.append("jsonld_reparse")

        if dims["sku_coverage"] < 0.5 or dims["variant_coverage"] < 0.8:
            strategies.append("network_intercept")  # XHR/GraphQL variant APIs
            strategies.append("shopify_variants_api")

        if dims["attribute_coverage"] < 0.5:
            strategies.append("dom_deep_scan")      # metafield tabs, accordions
            strategies.append("network_intercept")

        if dims["logistics"] < 0.5:
            strategies.append("dom_deep_scan")

        if dims["content_quality"] < 0.5:
            strategies.append("browser_render")     # JS-rendered description

        # LLM fallback is always last resort
        strategies.append("llm_fallback")

        # Deduplicate while preserving order
        seen = set()
        return [s for s in strategies if not (s in seen or seen.add(s))]

    def to_dict(self) -> Dict:
        return {
            "total": round(self.total, 3),
            "is_complete": self.is_complete,
            "dimensions": {k: round(v, 3) for k, v in self.dimensions.items()},
            "missing_fields": list(set(self.missing_fields)),
        }


class DeepExtractionLoop:
    """
    Orchestrates iterative re-extraction passes until completeness threshold
    is met or max passes are exhausted.

    Each pass applies the next recommended strategy from CompletenessScore.
    """

    async def run(
        self,
        entity: ProductEntity,
        url: str,
        html: str,
        organization_id: str,
    ) -> Tuple[ProductEntity, CompletenessScore]:
        """
        Run up to MAX_DEEP_PASSES extraction passes.
        Returns the final entity and its completeness score.
        """
        score = CompletenessScore(entity)
        if score.is_complete:
            return entity, score

        strategies_tried: List[str] = list(entity.sources_used)
        passes = 0

        while not score.is_complete and passes < MAX_DEEP_PASSES:
            passes += 1
            next_strategies = [
                s for s in score.extraction_strategy()
                if s not in strategies_tried
            ]
            if not next_strategies:
                logger.info("deep_extraction_no_more_strategies", url=url, score=score.total)
                break

            strategy = next_strategies[0]
            strategies_tried.append(strategy)

            logger.info(
                "deep_extraction_pass",
                url=url, pass_num=passes, strategy=strategy,
                score_before=round(score.total, 3),
                missing=score.missing_fields,
            )

            try:
                entity = await self._apply_strategy(strategy, entity, url, html, organization_id)
            except Exception as e:
                logger.warning("deep_extraction_strategy_failed", strategy=strategy, url=url, error=str(e))
                continue

            score = CompletenessScore(entity)

        logger.info(
            "deep_extraction_complete",
            url=url, passes=passes, final_score=round(score.total, 3),
            is_complete=score.is_complete, sources=entity.sources_used,
        )
        return entity, score

    async def _apply_strategy(
        self,
        strategy: str,
        entity: ProductEntity,
        url: str,
        html: str,
        organization_id: str,
    ) -> ProductEntity:
        if strategy == "hydration_state":
            from app.crawler.hydration_extractor import hydration_extractor
            data = hydration_extractor.extract(html, url)
            if data:
                entity.merge("hydration", data)

        elif strategy == "jsonld_reparse":
            from app.crawler.universal_extractor import universal_extractor
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            jsonld = universal_extractor._extract_jsonld(soup)
            if jsonld and jsonld.get("@type") == "Product":
                data = _jsonld_to_entity_dict(jsonld)
                entity.merge("jsonld", data)

        elif strategy == "network_intercept":
            from app.crawler.network_interceptor import network_interceptor
            captured = await network_interceptor.intercept(url)
            for source_name, data in captured.items():
                entity.merge(source_name, data)

        elif strategy == "shopify_variants_api":
            import re as _re
            m = _re.match(r'(https?://[^/]+)/products/([^/?#]+)', url)
            if m:
                import httpx
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.get(f"{m.group(1)}/products/{m.group(2)}.json")
                        if resp.status_code == 200:
                            product = resp.json().get("product", {})
                            if product:
                                data = _shopify_json_to_entity_dict(product)
                                entity.merge("shopify_json", data)
                except Exception:
                    pass

        elif strategy == "dom_deep_scan":
            from app.crawler.hydration_extractor import hydration_extractor
            metafields = hydration_extractor.extract_metafields_dom(html)
            if metafields:
                entity.merge("dom", metafields)

        elif strategy == "browser_render":
            from app.crawler.scraper import browser_pool
            rendered_html = await browser_pool.render(url)
            if rendered_html and len(rendered_html) > len(html):
                from app.crawler.hydration_extractor import hydration_extractor
                data = hydration_extractor.extract(rendered_html, url)
                if data:
                    entity.merge("hydration", data)
                # Also re-run DOM scan on rendered HTML
                metafields = hydration_extractor.extract_metafields_dom(rendered_html)
                if metafields:
                    entity.merge("dom", metafields)

        elif strategy == "llm_fallback":
            from app.crawler.llm_extractor import llm_extractor
            data = await llm_extractor.extract(html, url, entity)
            if data:
                entity.merge("llm", data)

        return entity


# ── Helpers ───────────────────────────────────────────────────────────────────

def _jsonld_to_entity_dict(d: Dict) -> Dict:
    """Convert a JSON-LD Product block to entity merge dict."""
    offers = d.get("offers", [])
    if isinstance(offers, dict):
        offers = [offers]
    price = None
    currency = None
    availability = None
    if offers:
        prices = [float(o["price"]) for o in offers if o.get("price")]
        if prices:
            price = min(prices)
        currency = offers[0].get("priceCurrency", "")
        avail = offers[0].get("availability", "")
        availability = "In Stock" if "InStock" in avail else ("Out of Stock" if "OutOfStock" in avail else None)

    brand = d.get("brand", {})
    if isinstance(brand, dict):
        brand = brand.get("name", "")

    import re
    desc_raw = d.get("description", "")
    desc = re.sub(r"<[^>]+>", " ", desc_raw).strip() if desc_raw else ""

    return {
        "title":        d.get("name", ""),
        "sku":          d.get("sku", ""),
        "price":        price,
        "currency":     currency,
        "availability": availability,
        "brand":        brand,
        "description":  desc,
        "material":     d.get("material", ""),
        "color":        d.get("color", ""),
    }


def _shopify_json_to_entity_dict(product: Dict) -> Dict:
    """Convert Shopify /products.json product block to entity merge dict."""
    variants_raw = product.get("variants", [])
    options = product.get("options", [])

    # Build option name map: position → name
    opt_names = {o["position"]: o["name"] for o in options}

    variants = []
    for v in variants_raw:
        opts = {}
        for i in range(1, 4):
            opt_val = v.get(f"option{i}")
            opt_name = opt_names.get(i)
            if opt_name and opt_val:
                opts[opt_name] = opt_val
        variants.append({
            "sku":       v.get("sku", ""),
            "title":     v.get("title", ""),
            "price":     v.get("price", 0),
            "currency":  "BDT",
            "available": v.get("available", True),
            "options":   opts,
            "barcode":   v.get("barcode", ""),
            "weight":    v.get("weight", 0),
        })

    prices = [float(v.get("price", 0)) for v in variants_raw if v.get("price")]
    price = min(prices) if prices else None
    in_stock = any(v.get("available", True) for v in variants_raw)

    import re
    desc_html = product.get("body_html", "") or ""
    desc = re.sub(r"<[^>]+>", " ", desc_html).strip()

    size_opts = []
    color_opts = []
    for o in options:
        name_lower = o["name"].lower()
        if "size" in name_lower:
            size_opts = o.get("values", [])
        elif "color" in name_lower or "colour" in name_lower:
            color_opts = o.get("values", [])

    return {
        "title":        product.get("title", ""),
        "handle":       product.get("handle", ""),
        "sku":          variants_raw[0].get("sku", "") if variants_raw else "",
        "price":        price,
        "currency":     "BDT",
        "availability": "In Stock" if in_stock else "Out of Stock",
        "brand":        product.get("vendor", ""),
        "product_type": product.get("product_type", ""),
        "tags":         ", ".join(product.get("tags", [])),
        "description":  desc,
        "size_options": ", ".join(size_opts) if size_opts else "",
        "color":        ", ".join(color_opts) if color_opts else "",
        "variants":     variants,
    }


deep_extraction_loop = DeepExtractionLoop()
