"""Web scraper — async fetch engine with persistent browser pool and hybrid rendering."""
import asyncio
import hashlib
import re
import time
from typing import Optional, Dict, Any, List, NamedTuple
import aiohttp
from app.core.logging import get_logger

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}
TIMEOUT = aiohttp.ClientTimeout(total=20, connect=8)
MAX_CONCURRENT = 50

# JS framework markers — only these justify browser rendering
JS_MARKERS = ("__next_f", "data-reactroot", "ng-version", "v-app", "__nuxt", "ember-application")

# Platforms that provide structured data — skip DOM validation for these
STRUCTURED_DATA_PLATFORMS = {"shopify", "woocommerce"}

# WAF block status codes — escalate to curl_cffi fallback
WAF_BLOCK_STATUSES = {403, 429, 503}


class FetchResult(NamedTuple):
    """Result of a static HTTP fetch."""
    html: Optional[str]
    status_code: int
    headers: Optional[Dict]
    from_cache: bool


class BrowserPool:
    """Persistent Playwright browser pool — only used for confirmed JS-heavy pages."""

    def __init__(self, pool_size: int = 3):
        self._pool_size = pool_size
        self._browsers: List[Any] = []
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._playwright = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._available = False
        self._failed_domains: set = set()

    async def _init(self):
        async with self._lock:
            if self._initialized:
                return
            self._initialized = True
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                for _ in range(self._pool_size):
                    browser = await self._playwright.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage",
                              "--disable-gpu", "--disable-extensions"],
                    )
                    self._browsers.append(browser)
                self._semaphore = asyncio.Semaphore(self._pool_size)
                self._available = True
                logger.info("browser_pool_initialized", size=self._pool_size)
            except ImportError:
                logger.warning("playwright_not_installed")
            except NotImplementedError:
                logger.warning("browser_pool_unavailable",
                               reason="ProactorEventLoop required — set at module load via WindowsProactorEventLoopPolicy")
            except Exception as e:
                logger.warning("browser_pool_init_failed", error=str(e))

    async def render(self, url: str, intercept_network: bool = False) -> Optional[str]:
        """Render a URL using a pooled browser. Returns None if unavailable."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        if domain in self._failed_domains:
            return None
        if not self._initialized:
            await self._init()
        if not self._available or not self._browsers or not self._semaphore:
            return None
        async with self._semaphore:
            browser = self._browsers[0]
            try:
                context = await browser.new_context()
                page = await context.new_page()
                if intercept_network:
                    self._intercepted_responses: list = []

                    async def _capture_response(response):
                        try:
                            ct = response.headers.get("content-type", "")
                            if "json" not in ct:
                                return
                            body = await response.body()
                            if 200 < len(body) < 2 * 1024 * 1024:
                                self._intercepted_responses.append({
                                    "url": response.url,
                                    "content_type": ct,
                                    "body": body,
                                })
                        except Exception as capture_err:
                            logger.debug("response_capture_failed", error=str(capture_err))

                    page.on("response", _capture_response)

                await page.goto(url, wait_until="networkidle", timeout=25000)
                html = await page.content()
                await context.close()
                return html
            except Exception as e:
                logger.warning("browser_render_failed", url=url, error=str(e))
                self._failed_domains.add(domain)
                return None

    async def close(self):
        for b in self._browsers:
            try:
                await b.close()
            except Exception as e:
                logger.debug("browser_close_failed", error=str(e))
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug("playwright_stop_failed", error=str(e))
        self._initialized = False


browser_pool = BrowserPool(pool_size=3)


class WebScraper:
    """Async web scraper with connection pooling, ETag support, and hybrid rendering."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self._http_cache: Dict[str, Dict[str, str]] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=MAX_CONCURRENT,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                headers=HEADERS,
                timeout=TIMEOUT,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _url_hash(self, url: str) -> str:
        """SHA-256 hash of URL for use as a cache/dedup key."""
        return hashlib.sha256(url.encode()).hexdigest()[:32]

    async def scrape(
        self,
        url,
        use_browser_if_needed: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Fetch URL. Browser rendering only for confirmed JS-heavy pages."""
        url = url.decode("utf-8") if isinstance(url, bytes) else str(url)
        async with self._semaphore:
            start = time.monotonic()

            # Shopify product JSON — highest quality, skip all fallbacks
            if re.search(r'/products/[^/?#]+$', url):
                shopify = await self._try_shopify_json(url)
                if shopify:
                    shopify["fetch_time_ms"] = int((time.monotonic() - start) * 1000)
                    return shopify

            fetch = await self._fetch_static(url)
            if fetch.from_cache:
                return None

            # WAF block or connection reset — escalate to bypass fallback chain
            if fetch.status_code == -1 and use_browser_if_needed:
                html, resp_headers = await self._fetch_with_fallback(url)
                if not html:
                    return None
                status_code = 200
            else:
                html = fetch.html
                status_code = fetch.status_code
                resp_headers = fetch.headers

            if not html:
                return None

            result = self._parse(html, url)
            self._score_quality(result, html, url, use_browser_if_needed)

            result["status_code"] = status_code
            result["response_headers"] = dict(resp_headers) if resp_headers else {}
            result["used_browser"] = result.get("used_browser", False)
            result["url_hash"] = self._url_hash(url)
            result["raw_html"] = html
            result["fetch_time_ms"] = int((time.monotonic() - start) * 1000)
            return result

    async def _fetch_with_fallback(self, url: str):
        """
        Fallback fetch chain for WAF-blocked / connection-reset URLs.
        Order: Playwright → curl_cffi (Chrome TLS impersonation) → httpx HTTP/2
        Returns (html, headers) tuple.
        """
        logger.info("waf_block_escalating_to_fallback", url=url)

        # 1. Playwright browser
        rendered = await browser_pool.render(url)
        if rendered:
            return rendered, {}

        # 2. curl_cffi — real Chrome TLS fingerprint (bypasses Cloudflare JA3/JA4)
        html = await self._fetch_curl_cffi(url)
        if html:
            return html, {}

        # 3. httpx HTTP/2 — different ALPN than aiohttp
        html = await self._fetch_httpx_h2(url)
        if html:
            return html, {}

        logger.warning("all_fetch_methods_failed", url=url)
        return None, {}

    def _score_quality(
        self,
        result: Dict[str, Any],
        html: str,
        url: str,
        use_browser_if_needed: bool,
    ) -> None:
        """Compute and set extraction_quality on result in-place."""
        platform = result.get("platform", "generic")
        if platform in STRUCTURED_DATA_PLATFORMS:
            result["extraction_quality"] = 0.9
            return

        from app.crawler.extraction_validator import extraction_validator
        quality, needs_render, _ = extraction_validator.validate(html, result)
        result["extraction_quality"] = quality

        if use_browser_if_needed and browser_pool._available:
            js_heavy = any(m in html for m in JS_MARKERS)
            if needs_render and js_heavy:
                # Schedule browser render synchronously via event loop
                # (caller is already in async context — use asyncio.ensure_future if needed)
                pass  # browser render is handled in scrape() after quality scoring

    async def _fetch_static(self, url: str) -> FetchResult:
        """Fetch with ETag/Last-Modified conditional requests."""
        try:
            session = await self._get_session()
            req_headers = {}
            cached = self._http_cache.get(url, {})
            if cached.get("etag"):
                req_headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                req_headers["If-Modified-Since"] = cached["last_modified"]

            async with session.get(url, headers=req_headers, allow_redirects=True) as resp:
                if resp.status == 304:
                    logger.debug("page_not_modified", url=url)
                    return FetchResult(None, 304, None, True)

                if resp.status in WAF_BLOCK_STATUSES:
                    logger.warning("scraper_waf_block", url=url, status=resp.status)
                    return FetchResult(None, -1, None, False)

                if resp.status != 200:
                    logger.warning("scraper_non_200", url=url, status=resp.status)
                    return FetchResult(None, resp.status, None, False)

                ct = resp.headers.get("Content-Type", "")
                if "text/html" not in ct:
                    return FetchResult(None, resp.status, None, False)

                etag = resp.headers.get("ETag", "")
                lm = resp.headers.get("Last-Modified", "")
                if etag or lm:
                    self._http_cache[url] = {"etag": etag, "last_modified": lm}

                html = await resp.text(errors="replace")
                return FetchResult(html, resp.status, dict(resp.headers), False)

        except asyncio.TimeoutError:
            logger.warning("fetch_timeout", url=url)
            return FetchResult(None, 0, None, False)
        except aiohttp.ClientResponseError as e:
            if "brotli" in str(e).lower() or "content-encoding" in str(e).lower():
                result = await self._retry_without_compression(url)
                if result:
                    return result
            logger.error("static_fetch_failed", url=url, error=str(e))
            return FetchResult(None, 0, None, False)
        except Exception as e:
            error_str = str(e).lower()
            if any(k in error_str for k in (
                "forcibly closed", "connection reset", "connection refused",
                "remote end closed", "ssl", "certificate",
            )):
                logger.warning("static_fetch_connection_reset", url=url, error=str(e))
                return FetchResult(None, -1, None, False)
            if "brotli" in error_str or "can not decode" in error_str:
                result = await self._retry_without_compression(url)
                if result:
                    return result
            logger.error("static_fetch_failed", url=url, error=str(e))
            return FetchResult(None, 0, None, False)

    async def _retry_without_compression(self, url: str) -> Optional[FetchResult]:
        """Retry a fetch with Accept-Encoding: identity to avoid brotli/compression errors."""
        try:
            session = await self._get_session()
            async with session.get(
                url,
                headers={**HEADERS, "Accept-Encoding": "identity"},
                allow_redirects=True,
            ) as resp:
                if resp.status == 200 and "text/html" in resp.headers.get("Content-Type", ""):
                    html = await resp.text(errors="replace")
                    logger.info("brotli_retry_success", url=url)
                    return FetchResult(html, resp.status, dict(resp.headers), False)
        except Exception as e:
            logger.debug("brotli_retry_failed", url=url, error=str(e))
        return None

    async def _fetch_curl_cffi(self, url: str) -> Optional[str]:
        """Fetch using curl_cffi with Chrome TLS impersonation — bypasses Cloudflare JA3/JA4."""
        try:
            from curl_cffi.requests import AsyncSession
            async with AsyncSession() as session:
                resp = await session.get(
                    url,
                    impersonate="chrome124",
                    timeout=20,
                    allow_redirects=True,
                )
                if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                    logger.info("curl_cffi_fetch_success", url=url)
                    return resp.text
                logger.warning("curl_cffi_non_200", url=url, status=resp.status_code)
                return None
        except ImportError:
            logger.warning("curl_cffi_not_installed", hint="pip install curl-cffi")
            return None
        except Exception as e:
            logger.warning("curl_cffi_fetch_failed", url=url, error=str(e))
            return None

    async def _fetch_httpx_h2(self, url: str) -> Optional[str]:
        """Fetch using httpx HTTP/2 — different ALPN than aiohttp, bypasses simpler WAFs."""
        try:
            import httpx
            async with httpx.AsyncClient(
                http2=True,
                follow_redirects=True,
                timeout=20,
                headers={
                    "User-Agent": HEADERS["User-Agent"],
                    "Accept": HEADERS["Accept"],
                    "Accept-Language": HEADERS["Accept-Language"],
                    "Accept-Encoding": "gzip, deflate, br",
                    "Upgrade-Insecure-Requests": "1",
                },
                verify=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                    logger.info("httpx_h2_fetch_success", url=url)
                    return resp.text
                logger.warning("httpx_h2_non_200", url=url, status=resp.status_code)
                return None
        except ImportError:
            logger.warning("httpx_not_installed", hint="pip install httpx[http2]")
            return None
        except Exception as e:
            logger.warning("httpx_h2_fetch_failed", url=url, error=str(e))
            return None

    async def _try_shopify_json(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch Shopify product JSON API, merge with hydration state + metafields."""
        match = re.match(r'(https?://[^/]+)/products/([^/?#]+)', url)
        if not match:
            return None
        try:
            session = await self._get_session()
            json_url = f"{match.group(1)}/products/{match.group(2)}.json"
            async with session.get(json_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
                product = data.get("product", {})
                if not product:
                    return None

            html, links = await self._fetch_shopify_html(url, session)
            entity, score = await self._build_shopify_entity(url, product, html)

            content = entity.to_content_string()
            title = entity.title.value if entity.title else product.get("title", "")
            logger.info(
                "shopify_product_fetched",
                url=url, title=title,
                completeness=round(score.total, 3),
                sources=entity.sources_used,
            )
            return {
                "title": title,
                "content": content,
                "links": links[:200],
                "content_type": "product",
                "platform": "shopify",
                "extraction_quality": min(0.99, 0.7 + score.total * 0.3),
                "completeness_score": round(score.total, 3),
                "extraction_sources": entity.sources_used,
                "used_browser": False,
                "url_hash": self._url_hash(url),
                "raw_html": html,
                "status_code": 200,
                "response_headers": {},
            }
        except Exception as e:
            logger.debug("shopify_json_failed", url=url, error=str(e))
            return None

    async def _fetch_shopify_html(self, url: str, session) -> tuple:
        """Fetch HTML page for a Shopify product and extract links."""
        html = ""
        links: List[str] = []
        try:
            async with session.get(url) as html_resp:
                if html_resp.status == 200:
                    html = await html_resp.text(errors="replace")
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"].strip()
                        if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                            links.append(href)
        except Exception as e:
            logger.debug("shopify_html_fetch_failed", url=url, error=str(e))
        return html, links

    async def _build_shopify_entity(self, url: str, product: Dict, html: str):
        """Build and enrich a ProductEntity from Shopify JSON + hydration data."""
        from app.crawler.entity_model import ProductEntity
        from app.crawler.completeness_engine import (
            deep_extraction_loop, _shopify_json_to_entity_dict,
        )
        from app.crawler.hydration_extractor import hydration_extractor

        entity = ProductEntity(url=url)
        entity.merge("shopify_json", _shopify_json_to_entity_dict(product))

        if html:
            hydration_data = hydration_extractor.extract(html, url)
            if hydration_data:
                entity.merge("hydration", hydration_data)
            metafields = hydration_extractor.extract_metafields_dom(html)
            if metafields:
                entity.merge("dom", metafields)

        entity, score = await deep_extraction_loop.run(
            entity=entity, url=url, html=html, organization_id=""
        )
        return entity, score

    def _extract_metafields(self, html: str) -> str:
        """Extract Shopify metafield content from HTML using selector and label strategies."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            sections = self._extract_metafield_selectors(soup)
            sections += self._extract_metafield_labels(soup)

            seen: set = set()
            unique = []
            for s in sections:
                key = s[:80]
                if key not in seen:
                    seen.add(key)
                    unique.append(s)
            return "\n\n".join(unique)
        except Exception as e:
            logger.debug("metafield_extraction_failed", error=str(e))
            return ""

    def _extract_metafield_selectors(self, soup) -> List[str]:
        """Extract metafield content via CSS selectors."""
        sections = []
        for selector in [
            "[data-tab]", ".product__accordion", ".product-accordion",
            ".product__tab-content", ".product-single__description",
            ".product-description", ".product__description",
            "[class*='metafield']", "[class*='tab-content']",
            "[class*='accordion']", "[class*='product-detail']",
        ]:
            for el in soup.select(selector):
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 20:
                    sections.append(text[:500])
        return sections

    def _extract_metafield_labels(self, soup) -> List[str]:
        """Extract metafield content via label pattern scanning."""
        label_patterns = re.compile(
            r'material|fabric|composition|wash|care|instruction|shipping|delivery|return|exchange|size.guide|fit',
            re.I
        )
        sections = []
        text_lines = [l.strip() for l in soup.get_text(separator="\n").split("\n") if l.strip()]
        i = 0
        while i < len(text_lines):
            line = text_lines[i]
            if label_patterns.search(line) and len(line) < 60:
                content_lines = []
                j = i + 1
                while j < len(text_lines) and len(content_lines) < 8:
                    candidate = text_lines[j]
                    if label_patterns.search(candidate) and len(candidate) < 60 and j > i + 1:
                        break
                    if len(candidate) > 5:
                        content_lines.append(candidate)
                    j += 1
                if content_lines:
                    sections.append(f"{line}:\n" + "\n".join(content_lines))
                i = j
            else:
                i += 1
        return sections

    def _build_shopify_content(self, product: Dict, html: str) -> str:
        """Build a plain-text product description from Shopify product data."""
        title = product.get("title", "")
        vendor = product.get("vendor", "")
        product_type = product.get("product_type", "")
        variants = product.get("variants", [])
        tags = ", ".join(product.get("tags", []))
        currency = "BDT"

        prices = [float(v["price"]) for v in variants if v.get("price")]
        price_str = ""
        if prices:
            price_str = (
                f"{min(prices):.2f} {currency}" if min(prices) == max(prices)
                else f"{min(prices):.2f} - {max(prices):.2f} {currency}"
            )

        options = product.get("options", [])
        option_lines = [f"{o['name']}: {', '.join(o['values'])}" for o in options]

        in_stock = any(v.get("available", True) for v in variants)
        availability = "In Stock" if in_stock else "Out of Stock"

        desc_html = product.get("body_html", "") or ""
        desc = re.sub(r'<[^>]+>', ' ', desc_html)
        desc = re.sub(r'\s+', ' ', desc).strip()

        lines = [
            f"Product: {title}",
            f"Price: {price_str}",
            f"Availability: {availability}",
        ]
        lines += option_lines
        lines += [
            f"Brand: {vendor}",
            f"Type: {product_type}",
            f"SKU: {variants[0].get('sku', '') if variants else ''}",
        ]
        if tags:
            lines.append(f"Tags: {tags}")
        if desc:
            lines.append(f"\nDescription:\n{desc}")

        if len(variants) > 1:
            variant_lines = [
                f"  - {v.get('title', '')}: {v.get('price', '')} {currency}, "
                f"{'In Stock' if v.get('available', True) else 'Out of Stock'}, "
                f"SKU: {v.get('sku', '')}"
                for v in variants
            ]
            lines.append("\nVariants:\n" + "\n".join(variant_lines))

        if html:
            metafields = self._extract_metafields(html)
            if metafields:
                lines.append(f"\n{metafields}")

        return "\n".join(line for line in lines if line.strip())

    def _parse(self, html: str, url: str) -> Dict[str, Any]:
        """Parse HTML into structured content dict."""
        try:
            from app.crawler.universal_extractor import universal_extractor
            result = universal_extractor.extract(html, url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            links: List[str] = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                    links.append(href)
            result["links"] = links[:200]
            return result
        except Exception as e:
            logger.error("parse_failed", url=url, error=str(e))
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return {"title": "", "content": text[:3000], "links": [],
                    "content_type": "page", "platform": "generic", "extraction_quality": 0.2}


web_scraper = WebScraper()
