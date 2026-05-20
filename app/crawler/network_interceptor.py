"""
Network Intelligence Layer

Intercepts all network traffic during Playwright page load to capture:
  - XHR/fetch API responses (JSON)
  - GraphQL query responses
  - Shopify Storefront API responses
  - Any JSON payload > 200 bytes that looks like product data

Also performs static JS bundle scanning to discover undocumented API endpoints.

Design principles:
  - Browser is only launched when static extraction is incomplete
  - Captured responses are classified and routed to the entity merger
  - GraphQL responses are parsed for product/variant fragments
  - All captures are org-scoped and never persisted beyond the request
"""
from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from app.core.logging import get_logger

logger = get_logger(__name__)

# Patterns that indicate a JSON response contains product data
PRODUCT_JSON_SIGNALS = re.compile(
    r'"(title|price|sku|variant|availability|product_type|vendor|handle)"',
    re.I,
)

# GraphQL operation names that contain product data
GRAPHQL_PRODUCT_OPS = re.compile(
    r'(product|variant|catalog|pdp|item)',
    re.I,
)

# API endpoint patterns to discover from JS bundles
API_ENDPOINT_PATTERNS = [
    re.compile(r'["\'](/api/[^"\'?\s]{3,60})["\']'),
    re.compile(r'["\'](https?://[^"\'?\s]+/api/[^"\'?\s]{3,60})["\']'),
    re.compile(r'fetch\(["\']([^"\'?\s]{5,80})["\']'),
    re.compile(r'axios\.[a-z]+\(["\']([^"\'?\s]{5,80})["\']'),
]

# Max response body size to parse (2 MB)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class NetworkInterceptor:
    """
    Uses Playwright's route interception to capture all JSON API responses
    during a page load, then classifies and extracts product data from them.
    """

    async def intercept(self, url: str) -> Dict[str, Any]:
        """
        Capture JSON API responses during page load.

        On Windows with SelectorEventLoop, Playwright subprocess creation
        raises NotImplementedError. In that case we fall back to static
        HTTP-only interception (fetches known API endpoints directly).
        """
        import sys
        import asyncio

        # Playwright requires ProactorEventLoop on Windows.
        # When running under uvicorn's default SelectorEventLoop, skip browser
        # and use HTTP-only fallback instead.
        loop = asyncio.get_event_loop()
        playwright_ok = not (
            sys.platform == "win32"
            and not isinstance(loop, asyncio.ProactorEventLoop)
        )

        if not playwright_ok:
            return await self._intercept_http_only(url)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("network_interceptor_playwright_unavailable")
            return await self._intercept_http_only(url)

        captured: Dict[str, Any] = {}

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                )
                context = await browser.new_context()
                page = await context.new_page()

                # Intercept all responses
                responses: List[Tuple[str, str, bytes]] = []

                async def handle_response(response):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" not in ct and "javascript" not in ct:
                            return
                        body = await response.body()
                        if len(body) > MAX_RESPONSE_BYTES:
                            return
                        responses.append((response.url, ct, body))
                    except Exception:
                        pass

                page.on("response", handle_response)

                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception as e:
                    logger.debug("network_intercept_navigation_error", url=url, error=str(e))

                await context.close()
                await browser.close()

            # Classify and extract from captured responses
            for resp_url, content_type, body in responses:
                result = self._classify_response(resp_url, content_type, body, url)
                if result:
                    source_name, data = result
                    # Merge: if same source captured multiple times, keep richest
                    if source_name not in captured or _richness(data) > _richness(captured[source_name]):
                        captured[source_name] = data

        except Exception as e:
            logger.warning("network_intercept_failed", url=url, error=str(e))

        if captured:
            logger.info("network_intercept_captured", url=url, sources=list(captured.keys()))

        return captured

    def _classify_response(
        self,
        resp_url: str,
        content_type: str,
        body: bytes,
        page_url: str,
    ) -> Optional[Tuple[str, Dict]]:
        """Classify a captured response and extract entity data from it."""
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception:
            return None

        # GraphQL responses
        if self._is_graphql(resp_url, text):
            data = self._extract_graphql(text, resp_url)
            if data:
                return ("graphql", data)

        # Shopify Storefront API
        if "shopify" in resp_url.lower() or "/api/" in resp_url:
            data = self._extract_shopify_api(text)
            if data:
                return ("xhr_api", data)

        # Generic JSON API — check if it looks like product data
        if "json" in content_type and PRODUCT_JSON_SIGNALS.search(text):
            data = self._extract_generic_json(text)
            if data:
                return ("xhr_api", data)

        return None

    def _is_graphql(self, url: str, body: str) -> bool:
        return (
            "graphql" in url.lower()
            or ('"data"' in body and '"errors"' in body)
            or ('"data"' in body and '"extensions"' in body)
        )

    def _extract_graphql(self, text: str, url: str) -> Optional[Dict]:
        """Parse GraphQL response for product/variant data."""
        try:
            payload = json.loads(text)
            data = payload.get("data", {})
            if not data:
                return None

            # Walk the data tree looking for product-shaped objects
            product_node = self._find_product_node(data)
            if not product_node:
                return None

            return self._normalize_graphql_product(product_node)
        except Exception:
            return None

    def _find_product_node(self, obj: Any, depth: int = 0) -> Optional[Dict]:
        """Recursively find a product-shaped node in a GraphQL response."""
        if depth > 6:
            return None
        if isinstance(obj, dict):
            # Direct product node
            if any(k in obj for k in ("title", "variants", "priceRange", "handle")):
                return obj
            # Nested: look inside edges/nodes (Shopify Storefront API pattern)
            if "edges" in obj:
                for edge in obj["edges"][:1]:
                    node = edge.get("node", {})
                    result = self._find_product_node(node, depth + 1)
                    if result:
                        return result
            for val in obj.values():
                result = self._find_product_node(val, depth + 1)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj[:3]:
                result = self._find_product_node(item, depth + 1)
                if result:
                    return result
        return None

    def _normalize_graphql_product(self, node: Dict) -> Optional[Dict]:
        """Normalize a GraphQL product node to entity merge dict."""
        result: Dict[str, Any] = {}

        if node.get("title"):
            result["title"] = node["title"]
        if node.get("handle"):
            result["handle"] = node["handle"]
        if node.get("vendor"):
            result["brand"] = node["vendor"]
        if node.get("productType"):
            result["product_type"] = node["productType"]
        if node.get("description"):
            result["description"] = node["description"]
        if node.get("tags"):
            result["tags"] = ", ".join(node["tags"]) if isinstance(node["tags"], list) else node["tags"]

        # Shopify Storefront API price range
        price_range = node.get("priceRange", {})
        min_price = price_range.get("minVariantPrice", {})
        if min_price.get("amount"):
            result["price"] = float(min_price["amount"])
            result["currency"] = min_price.get("currencyCode", "")

        # Variants via edges/nodes
        variants_conn = node.get("variants", {})
        if isinstance(variants_conn, dict):
            edges = variants_conn.get("edges", [])
            variants = []
            for edge in edges:
                vnode = edge.get("node", {})
                v_price = vnode.get("price", {})
                opts = {
                    sel.get("name", ""): sel.get("value", "")
                    for sel in vnode.get("selectedOptions", [])
                }
                variants.append({
                    "sku":       vnode.get("sku", ""),
                    "title":     vnode.get("title", ""),
                    "price":     float(v_price.get("amount", 0)) if isinstance(v_price, dict) else float(v_price or 0),
                    "currency":  v_price.get("currencyCode", "") if isinstance(v_price, dict) else "",
                    "available": vnode.get("availableForSale", True),
                    "options":   opts,
                    "barcode":   vnode.get("barcode", ""),
                })
            if variants:
                result["variants"] = variants

        return result if result else None

    def _extract_shopify_api(self, text: str) -> Optional[Dict]:
        """Extract from Shopify REST or Storefront API JSON."""
        try:
            payload = json.loads(text)
            product = payload.get("product") or payload.get("data", {}).get("product")
            if product and isinstance(product, dict):
                from app.crawler.completeness_engine import _shopify_json_to_entity_dict
                return _shopify_json_to_entity_dict(product)
        except Exception:
            pass
        return None

    def _extract_generic_json(self, text: str) -> Optional[Dict]:
        """Extract product fields from a generic JSON API response."""
        try:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                return None

            result: Dict[str, Any] = {}
            # Direct field mapping
            for src_key, dst_key in [
                ("title", "title"), ("name", "title"),
                ("price", "price"), ("sku", "sku"),
                ("brand", "brand"), ("vendor", "brand"),
                ("description", "description"), ("body_html", "description"),
                ("availability", "availability"),
                ("product_type", "product_type"),
                ("material", "material"),
                ("shipping", "shipping_info"),
            ]:
                if payload.get(src_key):
                    result[dst_key] = payload[src_key]

            return result if len(result) >= 2 else None
        except Exception:
            return None

    async def _intercept_http_only(self, url: str) -> Dict[str, Any]:
        """
        HTTP-only fallback for Windows / non-Playwright environments.
        Probes known API endpoints directly without launching a browser.
        """
        import httpx
        from urllib.parse import urlparse
        captured: Dict[str, Any] = {}
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        # Shopify: try /products/{handle}.json
        import re as _re
        m = _re.match(r'.*/products/([^/?#]+)$', url)
        if m:
            handle = m.group(1)
            try:
                async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                    resp = await client.get(f"{base}/products/{handle}.json")
                    if resp.status_code == 200:
                        data = resp.json()
                        product = data.get("product", {})
                        if product:
                            result = self._extract_shopify_api(resp.text)
                            if result:
                                captured["xhr_api"] = result
            except Exception as e:
                logger.debug("http_only_shopify_failed", url=url, error=str(e))

        # Try common GraphQL endpoints
        if not captured:
            for gql_path in ("/api/2023-10/graphql.json", "/graphql", "/api/graphql"):
                try:
                    async with httpx.AsyncClient(timeout=8) as client:
                        resp = await client.post(
                            f"{base}{gql_path}",
                            json={"query": "{ shop { name } }"},
                            headers={"Content-Type": "application/json"},
                        )
                        if resp.status_code == 200 and "data" in resp.text:
                            result = self._extract_graphql(resp.text, gql_path)
                            if result:
                                captured["graphql"] = result
                                break
                except Exception:
                    pass

        if captured:
            logger.info("http_only_intercept_captured", url=url, sources=list(captured.keys()))
        return captured

    def discover_api_endpoints(self, js_bundle: str, base_url: str) -> List[str]:
        """
        Scan a JS bundle for API endpoint patterns.
        Returns a list of discovered endpoint URLs.
        """
        endpoints = []
        for pattern in API_ENDPOINT_PATTERNS:
            for match in pattern.finditer(js_bundle):
                endpoint = match.group(1)
                if not endpoint.startswith("http"):
                    from urllib.parse import urljoin
                    endpoint = urljoin(base_url, endpoint)
                if endpoint not in endpoints:
                    endpoints.append(endpoint)
        return endpoints[:20]  # cap at 20 discovered endpoints


def _richness(data: Dict) -> int:
    """Score how rich a data dict is (number of non-empty fields)."""
    if not data:
        return 0
    score = sum(1 for v in data.values() if v not in (None, "", [], {}))
    if data.get("variants"):
        score += len(data["variants"]) * 2
    return score


network_interceptor = NetworkInterceptor()
