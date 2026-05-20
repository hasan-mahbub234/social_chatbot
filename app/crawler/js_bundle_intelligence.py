"""
JS Bundle Intelligence Layer

Extracts product data and API endpoints from JavaScript bundles without
requiring browser rendering. Performs static analysis on JS files.

Capabilities:
  - Extract embedded product models (window.product, __NEXT_DATA__, etc.)
  - Detect API endpoints from fetch()/axios()/XHR patterns
  - Recover storefront state objects
  - Parse chunked bundles (webpack, Vite, Rollup)
  - Extract GraphQL query strings
  - Identify authentication tokens/headers in API calls
"""
from __future__ import annotations
import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import httpx
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_BUNDLE_SIZE = 5 * 1024 * 1024   # 5 MB per bundle
MAX_BUNDLES_PER_PAGE = 10
CHUNK_SIZE = 50_000                  # parse in 50KB chunks for large files

# ── Regex patterns ────────────────────────────────────────────────────────────

# API endpoint patterns
API_PATTERNS = [
    re.compile(r'fetch\s*\(\s*["`\']([^"`\'?\s]{5,120})["`\']', re.S),
    re.compile(r'axios\.[a-z]+\s*\(\s*["`\']([^"`\'?\s]{5,120})["`\']', re.S),
    re.compile(r'["`\'](/(?:api|graphql|storefront)[^"`\'?\s]{0,80})["`\']'),
    re.compile(r'baseURL\s*[:=]\s*["`\']([^"`\'?\s]{5,100})["`\']'),
    re.compile(r'endpoint\s*[:=]\s*["`\']([^"`\'?\s]{5,100})["`\']'),
]

# GraphQL query patterns
GRAPHQL_PATTERNS = [
    re.compile(r'gql`(.*?)`', re.S),
    re.compile(r'graphql`(.*?)`', re.S),
    re.compile(r'query\s+\w+\s*\{.*?\}', re.S),
    re.compile(r'mutation\s+\w+\s*\{.*?\}', re.S),
]

# Embedded product state patterns
PRODUCT_STATE_PATTERNS = [
    re.compile(r'window\.product\s*=\s*(\{[^;]{20,5000}\})\s*;', re.S),
    re.compile(r'window\.__PRODUCT__\s*=\s*(\{[^;]{20,5000}\})\s*;', re.S),
    re.compile(r'productData\s*[:=]\s*(\{[^;]{20,5000}\})\s*[,;]', re.S),
    re.compile(r'"product"\s*:\s*(\{[^}]{20,3000}\})', re.S),
]

# Storefront API token patterns
STOREFRONT_TOKEN_PATTERNS = [
    re.compile(r'X-Shopify-Storefront-Access-Token["\s:]+["\']([a-f0-9]{32})["\']', re.I),
    re.compile(r'storefrontAccessToken["\s:=]+["\']([a-f0-9]{32})["\']', re.I),
    re.compile(r'publicStorefrontToken["\s:=]+["\']([a-f0-9]{32})["\']', re.I),
]

# Webpack/Vite chunk URL patterns
CHUNK_URL_PATTERNS = [
    re.compile(r'["\'](_next/static/chunks/[^"\']+\.js)["\']'),
    re.compile(r'["\'](/assets/[^"\']+\.js)["\']'),
    re.compile(r'["\'](/static/js/[^"\']+\.js)["\']'),
    re.compile(r'chunkId\s*\+\s*["\']([^"\']+\.js)["\']'),
]


class JSBundleIntelligence:
    """
    Static JS bundle analyzer — extracts product data and API intelligence
    without launching a browser.
    """

    async def analyze_page(
        self,
        html: str,
        base_url: str,
    ) -> Dict[str, Any]:
        """
        Analyze all JS bundles referenced in an HTML page.
        Returns extracted product data, API endpoints, and GraphQL queries.
        """
        bundle_urls = self._extract_bundle_urls(html, base_url)
        bundle_urls = bundle_urls[:MAX_BUNDLES_PER_PAGE]

        results: Dict[str, Any] = {
            "api_endpoints": [],
            "graphql_queries": [],
            "product_states": [],
            "storefront_tokens": [],
            "graphql_endpoints": [],
        }

        # Analyze inline scripts first (no HTTP cost)
        inline_results = self._analyze_js_content(self._extract_inline_scripts(html), base_url)
        self._merge_results(results, inline_results)

        # Fetch and analyze external bundles
        bundle_contents = await self._fetch_bundles(bundle_urls)
        for url, content in bundle_contents:
            if content:
                bundle_results = self._analyze_js_content(content, base_url)
                self._merge_results(results, bundle_results)

        # Deduplicate
        results["api_endpoints"] = list(dict.fromkeys(results["api_endpoints"]))
        results["graphql_endpoints"] = list(dict.fromkeys(results["graphql_endpoints"]))
        results["storefront_tokens"] = list(dict.fromkeys(results["storefront_tokens"]))

        logger.info(
            "js_bundle_analysis_complete",
            base_url=base_url,
            bundles_analyzed=len(bundle_contents),
            api_endpoints=len(results["api_endpoints"]),
            product_states=len(results["product_states"]),
        )
        return results

    def _analyze_js_content(self, content: str, base_url: str) -> Dict[str, Any]:
        """Analyze a single JS content string."""
        results: Dict[str, Any] = {
            "api_endpoints": [],
            "graphql_queries": [],
            "product_states": [],
            "storefront_tokens": [],
            "graphql_endpoints": [],
        }

        if not content or len(content) < 50:
            return results

        # Process in chunks for large bundles
        chunks = self._chunk_content(content)

        for chunk in chunks:
            # API endpoints
            for pattern in API_PATTERNS:
                for m in pattern.finditer(chunk):
                    ep = m.group(1)
                    ep = self._resolve_url(ep, base_url)
                    if ep and self._is_valid_endpoint(ep):
                        results["api_endpoints"].append(ep)
                        if "graphql" in ep.lower():
                            results["graphql_endpoints"].append(ep)

            # GraphQL queries
            for pattern in GRAPHQL_PATTERNS:
                for m in pattern.finditer(chunk):
                    query_text = m.group(1).strip() if m.lastindex else m.group(0).strip()
                    if len(query_text) > 20:
                        results["graphql_queries"].append(query_text[:2000])

            # Product state objects
            for pattern in PRODUCT_STATE_PATTERNS:
                for m in pattern.finditer(chunk):
                    try:
                        obj = json.loads(m.group(1))
                        if isinstance(obj, dict) and self._looks_like_product(obj):
                            results["product_states"].append(obj)
                    except json.JSONDecodeError:
                        pass

            # Storefront tokens
            for pattern in STOREFRONT_TOKEN_PATTERNS:
                for m in pattern.finditer(chunk):
                    token = m.group(1)
                    if len(token) == 32:
                        results["storefront_tokens"].append(token)

        return results

    def extract_product_data(
        self, analysis_result: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Extract the richest product entity dict from bundle analysis results.
        Returns entity merge dict or None.
        """
        product_states = analysis_result.get("product_states", [])
        if not product_states:
            return None

        # Score each state by richness
        best = max(product_states, key=self._product_richness)
        if self._product_richness(best) < 2:
            return None

        return self._normalize_product_state(best)

    def get_storefront_headers(
        self, analysis_result: Dict[str, Any]
    ) -> Dict[str, str]:
        """Build Shopify Storefront API headers from discovered tokens."""
        tokens = analysis_result.get("storefront_tokens", [])
        if tokens:
            return {"X-Shopify-Storefront-Access-Token": tokens[0]}
        return {}

    # ── Bundle fetching ───────────────────────────────────────────────────────

    async def _fetch_bundles(
        self, urls: List[str]
    ) -> List[Tuple[str, Optional[str]]]:
        """Fetch multiple JS bundles concurrently."""
        async def fetch_one(url: str) -> Tuple[str, Optional[str]]:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url, headers={
                        "User-Agent": "Mozilla/5.0 (compatible; EnterpriseAIBot/2.0)",
                    })
                    if resp.status_code == 200:
                        content = resp.text
                        if len(content) > MAX_BUNDLE_SIZE:
                            content = content[:MAX_BUNDLE_SIZE]
                        return url, content
            except Exception as e:
                logger.debug("bundle_fetch_failed", url=url, error=str(e))
            return url, None

        tasks = [fetch_one(url) for url in urls]
        return await asyncio.gather(*tasks)

    # ── HTML parsing helpers ──────────────────────────────────────────────────

    def _extract_bundle_urls(self, html: str, base_url: str) -> List[str]:
        """Extract all JS bundle URLs from HTML."""
        urls: List[str] = []
        seen: Set[str] = set()

        # <script src="..."> tags
        for m in re.finditer(r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']', html, re.I):
            url = self._resolve_url(m.group(1), base_url)
            if url and url not in seen:
                urls.append(url)
                seen.add(url)

        # Webpack chunk references in HTML
        for pattern in CHUNK_URL_PATTERNS:
            for m in pattern.finditer(html):
                url = self._resolve_url(m.group(1), base_url)
                if url and url not in seen:
                    urls.append(url)
                    seen.add(url)

        # Prioritize: main/app bundles first, vendor/polyfill last
        def priority(url: str) -> int:
            u = url.lower()
            if any(k in u for k in ("main", "app", "index", "product")):
                return 0
            if any(k in u for k in ("chunk", "page")):
                return 1
            if any(k in u for k in ("vendor", "polyfill", "runtime")):
                return 3
            return 2

        return sorted(urls, key=priority)

    def _extract_inline_scripts(self, html: str) -> str:
        """Extract all inline <script> content."""
        parts = []
        for m in re.finditer(r'<script(?![^>]+src=)[^>]*>(.*?)</script>', html, re.S | re.I):
            parts.append(m.group(1))
        return "\n".join(parts)

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _chunk_content(self, content: str) -> List[str]:
        """Split large JS content into overlapping chunks for pattern matching."""
        if len(content) <= CHUNK_SIZE:
            return [content]
        chunks = []
        overlap = 500
        for i in range(0, len(content), CHUNK_SIZE - overlap):
            chunks.append(content[i:i + CHUNK_SIZE])
        return chunks

    def _resolve_url(self, url: str, base_url: str) -> Optional[str]:
        if not url:
            return None
        if url.startswith("http"):
            return url
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        return None

    def _is_valid_endpoint(self, url: str) -> bool:
        skip = (".css", ".png", ".jpg", ".svg", ".woff", ".ico", "localhost")
        return not any(s in url.lower() for s in skip) and len(url) > 5

    def _looks_like_product(self, obj: Dict) -> bool:
        product_keys = {"title", "price", "sku", "variants", "handle", "vendor", "product_type"}
        return len(product_keys & set(obj.keys())) >= 2

    def _product_richness(self, obj: Dict) -> int:
        keys = {"title", "price", "sku", "variants", "handle", "vendor",
                "product_type", "description", "availability", "brand"}
        score = len(keys & set(obj.keys()))
        if obj.get("variants"):
            score += len(obj["variants"]) if isinstance(obj["variants"], list) else 1
        return score

    def _normalize_product_state(self, obj: Dict) -> Dict[str, Any]:
        """Normalize a JS product state object to entity merge dict."""
        result: Dict[str, Any] = {}
        for src, dst in [
            ("title", "title"), ("handle", "handle"), ("sku", "sku"),
            ("vendor", "brand"), ("brand", "brand"),
            ("product_type", "product_type"), ("productType", "product_type"),
            ("description", "description"), ("body_html", "description"),
        ]:
            if obj.get(src) and dst not in result:
                result[dst] = obj[src]

        price = obj.get("price") or obj.get("price_min")
        if price:
            try:
                result["price"] = float(str(price).replace(",", ""))
            except (ValueError, TypeError):
                pass

        avail = obj.get("available")
        if avail is not None:
            result["availability"] = "In Stock" if avail else "Out of Stock"

        variants = obj.get("variants", [])
        if variants and isinstance(variants, list):
            result["variants"] = [
                {
                    "sku": v.get("sku", ""),
                    "title": v.get("title", ""),
                    "price": float(str(v.get("price", 0)).replace(",", "") or 0),
                    "available": v.get("available", True),
                    "options": {f"option{i}": v.get(f"option{i}") for i in range(1, 4)
                                if v.get(f"option{i}")},
                }
                for v in variants if isinstance(v, dict)
            ]

        return result

    def _merge_results(self, base: Dict, new: Dict):
        for key in base:
            if key in new:
                if isinstance(base[key], list):
                    base[key].extend(new[key])
                elif isinstance(base[key], dict):
                    base[key].update(new[key])


js_bundle_intelligence = JSBundleIntelligence()
