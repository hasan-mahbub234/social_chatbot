"""
Hydration State Extractor

Extracts product data from client-side hydration state objects embedded in HTML:
  - Next.js  __NEXT_DATA__  (window.__NEXT_DATA__ = {...})
  - Nuxt     __NUXT__       (window.__NUXT__ = {...})
  - Shopify  ShopifyAnalytics.meta / window.ShopifyAnalytics
  - Shopify  theme.js product JSON (window.product = {...})
  - Generic  window.__STATE__, window.__INITIAL_STATE__, window.__APP_STATE__
  - Embedded <script type="application/json"> blocks
  - Shopify metafield DOM tabs/accordions

These sources often contain the most complete product data because they are
the exact payload the frontend uses to render the page.
"""
from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# Patterns for window-level state objects
HYDRATION_PATTERNS = [
    # Next.js
    (re.compile(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.S), "nextjs"),
    # Nuxt
    (re.compile(r'window\.__NUXT__\s*=\s*(\{.*?\})\s*;', re.S), "nuxt"),
    # Shopify Analytics meta
    (re.compile(r'window\.ShopifyAnalytics\s*=\s*(\{.*?\})\s*;', re.S), "shopify_analytics"),
    # Shopify theme product object
    (re.compile(r'window\.product\s*=\s*(\{.*?\})\s*;', re.S), "shopify_theme"),
    # Generic state objects
    (re.compile(r'window\.__(?:INITIAL_STATE|APP_STATE|STATE|REDUX_STATE|STORE_STATE)__\s*=\s*(\{.*?\})\s*;', re.S), "generic_state"),
    # Preloaded state (Redux)
    (re.compile(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;', re.S), "redux_state"),
]

# Shopify metafield DOM selectors
METAFIELD_SELECTORS = [
    "[data-tab]", ".product__accordion", ".product-accordion",
    ".product__tab-content", ".product-single__description",
    ".product-description", ".product__description",
    "[class*='metafield']", "[class*='tab-content']",
    "[class*='accordion']", "[class*='product-detail']",
    "[class*='product-info']", "[class*='product-spec']",
]

METAFIELD_LABEL_RE = re.compile(
    r'material|fabric|composition|wash|care|instruction|shipping|delivery|return|exchange|size.guide|fit|dimension',
    re.I,
)


class HydrationExtractor:
    """Extract product data from hydration state objects in HTML."""

    def extract(self, html: str, url: str = "") -> Optional[Dict]:
        """
        Try all hydration patterns in priority order.
        Returns the richest entity merge dict found, or None.
        """
        best: Optional[Dict] = None
        best_richness = 0

        for pattern, source_type in HYDRATION_PATTERNS:
            match = pattern.search(html)
            if not match:
                continue
            try:
                raw_json = match.group(1)
                obj = json.loads(raw_json)
                data = self._extract_from_state(obj, source_type, url)
                if data:
                    richness = _richness(data)
                    if richness > best_richness:
                        best = data
                        best_richness = richness
                        logger.debug("hydration_extracted", source=source_type, url=url, richness=richness)
            except (json.JSONDecodeError, IndexError):
                # Try to extract truncated JSON
                raw_json = match.group(1)
                data = self._try_partial_json(raw_json, source_type, url)
                if data:
                    richness = _richness(data)
                    if richness > best_richness:
                        best = data
                        best_richness = richness

        # Also scan <script type="application/json"> blocks
        json_blocks = self._extract_json_script_blocks(html)
        for obj in json_blocks:
            data = self._extract_from_state(obj, "embedded_json", url)
            if data:
                richness = _richness(data)
                if richness > best_richness:
                    best = data
                    best_richness = richness

        return best

    def extract_metafields_dom(self, html: str) -> Optional[Dict]:
        """
        Extract Shopify metafields and product attributes from DOM
        (tabs, accordions, hidden sections).
        Returns a partial entity dict with logistics/attribute fields.
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            sections: List[str] = []

            # CSS selector-based extraction
            for selector in METAFIELD_SELECTORS:
                for el in soup.select(selector):
                    text = el.get_text(separator="\n", strip=True)
                    if len(text) > 20:
                        sections.append(text[:800])

            # Label-based scanning
            text_lines = [l.strip() for l in soup.get_text(separator="\n").split("\n") if l.strip()]
            i = 0
            while i < len(text_lines):
                line = text_lines[i]
                if METAFIELD_LABEL_RE.search(line) and len(line) < 80:
                    content_lines = []
                    j = i + 1
                    while j < len(text_lines) and len(content_lines) < 10:
                        candidate = text_lines[j]
                        if METAFIELD_LABEL_RE.search(candidate) and len(candidate) < 80 and j > i + 1:
                            break
                        if len(candidate) > 5:
                            content_lines.append(candidate)
                        j += 1
                    if content_lines:
                        sections.append(f"{line}:\n" + "\n".join(content_lines))
                    i = j
                else:
                    i += 1

            if not sections:
                return None

            # Classify sections into entity fields
            result: Dict[str, str] = {}
            combined = "\n\n".join(dict.fromkeys(sections))  # deduplicate

            shipping_re = re.compile(r'shipping|delivery', re.I)
            return_re = re.compile(r'return|exchange|refund', re.I)
            material_re = re.compile(r'material|fabric|composition', re.I)
            care_re = re.compile(r'care|wash|instruction', re.I)

            for section in sections:
                section_lower = section.lower()
                if shipping_re.search(section_lower) and "shipping_info" not in result:
                    result["shipping_info"] = section[:500]
                elif return_re.search(section_lower) and "return_policy" not in result:
                    result["return_policy"] = section[:500]
                elif material_re.search(section_lower) and "material" not in result:
                    result["material"] = section[:300]
                elif care_re.search(section_lower) and "care_instructions" not in result:
                    result["care_instructions"] = section[:300]

            return result if result else None

        except Exception as e:
            logger.debug("metafields_dom_failed", error=str(e))
            return None

    def _extract_from_state(self, obj: Any, source_type: str, url: str) -> Optional[Dict]:
        """Route extraction based on state object type."""
        if source_type == "nextjs":
            return self._from_nextjs(obj)
        elif source_type == "nuxt":
            return self._from_nuxt(obj)
        elif source_type in ("shopify_analytics", "shopify_theme"):
            return self._from_shopify_state(obj)
        elif source_type in ("generic_state", "redux_state", "embedded_json"):
            return self._from_generic_state(obj)
        return None

    def _from_nextjs(self, obj: Dict) -> Optional[Dict]:
        """Extract from Next.js __NEXT_DATA__ structure."""
        try:
            # Standard Next.js: props.pageProps.product
            page_props = obj.get("props", {}).get("pageProps", {})
            product = (
                page_props.get("product")
                or page_props.get("productData")
                or page_props.get("data", {}).get("product")
                or self._find_product_node(page_props)
            )
            if product and isinstance(product, dict):
                return self._normalize_product_node(product)

            # Dehydrated state (React Query / SWR)
            dehydrated = page_props.get("dehydratedState", {})
            if dehydrated:
                queries = dehydrated.get("queries", [])
                for q in queries:
                    data = q.get("state", {}).get("data", {})
                    product = self._find_product_node(data)
                    if product:
                        return self._normalize_product_node(product)
        except Exception:
            pass
        return None

    def _from_nuxt(self, obj: Dict) -> Optional[Dict]:
        """Extract from Nuxt __NUXT__ structure."""
        try:
            # Nuxt 2: data array
            data_arr = obj.get("data", [])
            for item in (data_arr if isinstance(data_arr, list) else [data_arr]):
                product = item.get("product") or self._find_product_node(item)
                if product:
                    return self._normalize_product_node(product)
            # Nuxt 3: payload
            payload = obj.get("payload", {})
            product = self._find_product_node(payload)
            if product:
                return self._normalize_product_node(product)
        except Exception:
            pass
        return None

    def _from_shopify_state(self, obj: Dict) -> Optional[Dict]:
        """Extract from Shopify Analytics or theme product state."""
        try:
            # ShopifyAnalytics.meta.product
            product = (
                obj.get("meta", {}).get("product")
                or obj.get("product")
                or obj.get("data", {}).get("product")
            )
            if product and isinstance(product, dict):
                return self._normalize_product_node(product)
        except Exception:
            pass
        return None

    def _from_generic_state(self, obj: Any) -> Optional[Dict]:
        """Walk a generic state tree looking for product-shaped nodes."""
        product = self._find_product_node(obj)
        if product:
            return self._normalize_product_node(product)
        return None

    def _find_product_node(self, obj: Any, depth: int = 0) -> Optional[Dict]:
        """Recursively find a product-shaped node."""
        if depth > 8 or not obj:
            return None
        if isinstance(obj, dict):
            # Product-shaped: has title + (price or variants or sku)
            has_title = bool(obj.get("title") or obj.get("name"))
            has_product_fields = any(obj.get(k) for k in ("price", "variants", "sku", "priceRange", "handle"))
            if has_title and has_product_fields:
                return obj
            for val in obj.values():
                result = self._find_product_node(val, depth + 1)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj[:5]:
                result = self._find_product_node(item, depth + 1)
                if result:
                    return result
        return None

    def _normalize_product_node(self, node: Dict) -> Optional[Dict]:
        """Normalize any product-shaped dict to entity merge format."""
        result: Dict[str, Any] = {}

        for src, dst in [("title", "title"), ("name", "title"), ("handle", "handle"),
                         ("sku", "sku"), ("vendor", "brand"), ("brand", "brand"),
                         ("productType", "product_type"), ("product_type", "product_type"),
                         ("description", "description"), ("body_html", "description"),
                         ("material", "material"), ("color", "color")]:
            val = node.get(src)
            if val and dst not in result:
                result[dst] = val

        # Price normalization
        price = node.get("price") or node.get("price_min")
        if price:
            try:
                result["price"] = float(str(price).replace(",", ""))
            except (ValueError, TypeError):
                pass

        # Availability
        avail = node.get("available") or node.get("availability")
        if avail is not None:
            if isinstance(avail, bool):
                result["availability"] = "In Stock" if avail else "Out of Stock"
            elif isinstance(avail, str):
                result["availability"] = avail

        # Tags
        tags = node.get("tags")
        if tags:
            result["tags"] = ", ".join(tags) if isinstance(tags, list) else str(tags)

        # Variants
        variants_raw = node.get("variants", [])
        if variants_raw and isinstance(variants_raw, list):
            variants = []
            for v in variants_raw:
                if not isinstance(v, dict):
                    continue
                opts = {}
                # Shopify REST variant options
                for i in range(1, 4):
                    opt_val = v.get(f"option{i}")
                    if opt_val:
                        opts[f"option{i}"] = opt_val
                # Shopify Storefront selectedOptions
                for sel in v.get("selectedOptions", []):
                    opts[sel.get("name", "")] = sel.get("value", "")

                v_price = v.get("price", 0)
                if isinstance(v_price, dict):
                    v_price = v_price.get("amount", 0)

                variants.append({
                    "sku":       v.get("sku", ""),
                    "title":     v.get("title", ""),
                    "price":     float(str(v_price).replace(",", "") or 0),
                    "available": v.get("available", v.get("availableForSale", True)),
                    "options":   opts,
                    "barcode":   v.get("barcode", ""),
                })
            if variants:
                result["variants"] = variants

        return result if len(result) >= 2 else None

    def _extract_json_script_blocks(self, html: str) -> List[Dict]:
        """Extract all <script type="application/json"> blocks."""
        results = []
        pattern = re.compile(
            r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>',
            re.S | re.I,
        )
        for match in pattern.finditer(html):
            try:
                obj = json.loads(match.group(1))
                if isinstance(obj, dict) and len(obj) > 1:
                    results.append(obj)
            except Exception:
                pass
        return results

    def _try_partial_json(self, raw: str, source_type: str, url: str) -> Optional[Dict]:
        """Attempt to parse truncated JSON by finding the last valid closing brace."""
        for end in range(len(raw), max(len(raw) - 5000, 0), -1):
            try:
                obj = json.loads(raw[:end])
                return self._extract_from_state(obj, source_type, url)
            except json.JSONDecodeError:
                continue
        return None


def _richness(data: Dict) -> int:
    if not data:
        return 0
    score = sum(1 for v in data.values() if v not in (None, "", [], {}))
    if data.get("variants"):
        score += len(data["variants"]) * 2
    return score


hydration_extractor = HydrationExtractor()
