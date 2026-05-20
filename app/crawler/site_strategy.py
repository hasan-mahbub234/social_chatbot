"""
Adaptive Site Strategy Engine

Classifies a site before crawling and selects the optimal extraction strategy.
Minimizes Playwright usage by preferring API-first extraction.

Site types:
  shopify          → /products.json + Storefront API
  headless_nextjs  → __NEXT_DATA__ hydration + GraphQL
  nuxt             → __NUXT__ hydration + REST API
  woocommerce      → WC REST API + JSON-LD
  magento          → REST API + GraphQL
  custom_graphql   → GraphQL introspection + endpoint discovery
  generic          → trafilatura + DOM fallback

Strategy budget:
  Each strategy has a cost score (1=cheap, 5=expensive).
  Browser rendering is cost=5 and only used when all cheaper strategies fail.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import httpx
from app.core.logging import get_logger

logger = get_logger(__name__)


class SiteType(str, Enum):
    SHOPIFY         = "shopify"
    HEADLESS_NEXTJS = "headless_nextjs"
    NUXT            = "nuxt"
    WOOCOMMERCE     = "woocommerce"
    MAGENTO         = "magento"
    CUSTOM_GRAPHQL  = "custom_graphql"
    WORDPRESS       = "wordpress"
    GENERIC         = "generic"


class ExtractionStrategy(str, Enum):
    SHOPIFY_JSON_API    = "shopify_json_api"        # cost 1
    SHOPIFY_STOREFRONT  = "shopify_storefront_api"  # cost 2
    GRAPHQL_INTROSPECT  = "graphql_introspect"      # cost 2
    HYDRATION_STATE     = "hydration_state"         # cost 1
    WOOCOMMERCE_API     = "woocommerce_api"         # cost 1
    MAGENTO_API         = "magento_api"             # cost 1
    JSONLD              = "jsonld"                  # cost 1
    DOM_EXTRACTION      = "dom_extraction"          # cost 2
    NETWORK_INTERCEPT   = "network_intercept"       # cost 3
    BROWSER_RENDER      = "browser_render"          # cost 5
    LLM_FALLBACK        = "llm_fallback"            # cost 4


STRATEGY_COST: Dict[ExtractionStrategy, int] = {
    ExtractionStrategy.SHOPIFY_JSON_API:   1,
    ExtractionStrategy.HYDRATION_STATE:    1,
    ExtractionStrategy.WOOCOMMERCE_API:    1,
    ExtractionStrategy.MAGENTO_API:        1,
    ExtractionStrategy.JSONLD:             1,
    ExtractionStrategy.SHOPIFY_STOREFRONT: 2,
    ExtractionStrategy.GRAPHQL_INTROSPECT: 2,
    ExtractionStrategy.DOM_EXTRACTION:     2,
    ExtractionStrategy.NETWORK_INTERCEPT:  3,
    ExtractionStrategy.LLM_FALLBACK:       4,
    ExtractionStrategy.BROWSER_RENDER:     5,
}


@dataclass
class SiteProfile:
    site_type: SiteType
    base_url: str
    strategies: List[ExtractionStrategy]        # ordered by preference
    api_endpoints: Dict[str, str] = field(default_factory=dict)  # name → url
    graphql_endpoint: Optional[str] = None
    storefront_token: Optional[str] = None
    has_sitemap: bool = True
    has_products_json: bool = False
    js_framework: Optional[str] = None
    detection_signals: List[str] = field(default_factory=list)
    extraction_budget: int = 10                 # max total cost units per page


class SiteStrategyEngine:
    """
    Classify a site and return an ordered extraction strategy plan.
    """

    async def classify(self, url: str, html: Optional[str] = None) -> SiteProfile:
        """
        Classify a site and build its extraction strategy profile.
        Fetches the homepage if html is not provided.
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        if html is None:
            html = await self._fetch_html(base_url)

        if not html:
            return self._generic_profile(base_url)

        site_type, signals = self._detect_site_type(html, base_url)
        profile = self._build_profile(site_type, base_url, html, signals)

        logger.info(
            "site_classified",
            base_url=base_url,
            site_type=site_type.value,
            signals=signals[:5],
            strategies=[s.value for s in profile.strategies[:3]],
        )
        return profile

    def _detect_site_type(
        self, html: str, base_url: str
    ) -> Tuple[SiteType, List[str]]:
        """Detect site type from HTML signals."""
        signals: List[str] = []

        # Shopify
        if any(s in html for s in ("Shopify.theme", "/cdn/shop/", "cdn.shopify.com")):
            signals.append("shopify_cdn")
            return SiteType.SHOPIFY, signals

        # WooCommerce
        if any(s in html for s in ("wp-content/plugins/woocommerce", "woocommerce")):
            signals.append("woocommerce_plugin")
            return SiteType.WOOCOMMERCE, signals

        # WordPress (non-WooCommerce)
        if any(s in html for s in ("wp-content", "wp-includes")):
            signals.append("wordpress_assets")
            return SiteType.WORDPRESS, signals

        # Headless Next.js
        if "__NEXT_DATA__" in html or "_next/static" in html:
            signals.append("nextjs_hydration")
            if "graphql" in html.lower() or "/api/graphql" in html:
                signals.append("graphql_endpoint")
                return SiteType.HEADLESS_NEXTJS, signals
            return SiteType.HEADLESS_NEXTJS, signals

        # Nuxt
        if "__NUXT__" in html or "_nuxt/" in html:
            signals.append("nuxt_hydration")
            return SiteType.NUXT, signals

        # Magento
        if any(s in html for s in ("Magento", "mage/cookies", "mage-init")):
            signals.append("magento_markers")
            return SiteType.MAGENTO, signals

        # Custom GraphQL (detected from JS bundle references)
        if re.search(r'["\']/?graphql["\']|/api/graphql', html, re.I):
            signals.append("graphql_reference")
            return SiteType.CUSTOM_GRAPHQL, signals

        return SiteType.GENERIC, signals

    def _build_profile(
        self,
        site_type: SiteType,
        base_url: str,
        html: str,
        signals: List[str],
    ) -> SiteProfile:
        """Build a SiteProfile with ordered strategies for the detected site type."""

        if site_type == SiteType.SHOPIFY:
            return SiteProfile(
                site_type=site_type,
                base_url=base_url,
                strategies=[
                    ExtractionStrategy.SHOPIFY_JSON_API,
                    ExtractionStrategy.HYDRATION_STATE,
                    ExtractionStrategy.SHOPIFY_STOREFRONT,
                    ExtractionStrategy.JSONLD,
                    ExtractionStrategy.DOM_EXTRACTION,
                    ExtractionStrategy.NETWORK_INTERCEPT,
                    ExtractionStrategy.LLM_FALLBACK,
                ],
                api_endpoints={
                    "products_json": f"{base_url}/products.json",
                    "product_json":  f"{base_url}/products/{{handle}}.json",
                },
                has_products_json=True,
                detection_signals=signals,
            )

        if site_type == SiteType.HEADLESS_NEXTJS:
            graphql_ep = self._find_graphql_endpoint(html, base_url)
            return SiteProfile(
                site_type=site_type,
                base_url=base_url,
                strategies=[
                    ExtractionStrategy.HYDRATION_STATE,
                    ExtractionStrategy.GRAPHQL_INTROSPECT,
                    ExtractionStrategy.JSONLD,
                    ExtractionStrategy.NETWORK_INTERCEPT,
                    ExtractionStrategy.DOM_EXTRACTION,
                    ExtractionStrategy.BROWSER_RENDER,
                    ExtractionStrategy.LLM_FALLBACK,
                ],
                graphql_endpoint=graphql_ep,
                js_framework="nextjs",
                detection_signals=signals,
            )

        if site_type == SiteType.NUXT:
            return SiteProfile(
                site_type=site_type,
                base_url=base_url,
                strategies=[
                    ExtractionStrategy.HYDRATION_STATE,
                    ExtractionStrategy.JSONLD,
                    ExtractionStrategy.NETWORK_INTERCEPT,
                    ExtractionStrategy.DOM_EXTRACTION,
                    ExtractionStrategy.BROWSER_RENDER,
                    ExtractionStrategy.LLM_FALLBACK,
                ],
                js_framework="nuxt",
                detection_signals=signals,
            )

        if site_type == SiteType.WOOCOMMERCE:
            return SiteProfile(
                site_type=site_type,
                base_url=base_url,
                strategies=[
                    ExtractionStrategy.WOOCOMMERCE_API,
                    ExtractionStrategy.JSONLD,
                    ExtractionStrategy.DOM_EXTRACTION,
                    ExtractionStrategy.LLM_FALLBACK,
                ],
                api_endpoints={
                    "products": f"{base_url}/wp-json/wc/v3/products",
                },
                detection_signals=signals,
            )

        if site_type == SiteType.MAGENTO:
            return SiteProfile(
                site_type=site_type,
                base_url=base_url,
                strategies=[
                    ExtractionStrategy.MAGENTO_API,
                    ExtractionStrategy.GRAPHQL_INTROSPECT,
                    ExtractionStrategy.JSONLD,
                    ExtractionStrategy.DOM_EXTRACTION,
                    ExtractionStrategy.NETWORK_INTERCEPT,
                    ExtractionStrategy.LLM_FALLBACK,
                ],
                api_endpoints={
                    "products": f"{base_url}/rest/V1/products",
                },
                graphql_endpoint=f"{base_url}/graphql",
                detection_signals=signals,
            )

        if site_type == SiteType.CUSTOM_GRAPHQL:
            graphql_ep = self._find_graphql_endpoint(html, base_url)
            return SiteProfile(
                site_type=site_type,
                base_url=base_url,
                strategies=[
                    ExtractionStrategy.GRAPHQL_INTROSPECT,
                    ExtractionStrategy.HYDRATION_STATE,
                    ExtractionStrategy.JSONLD,
                    ExtractionStrategy.NETWORK_INTERCEPT,
                    ExtractionStrategy.DOM_EXTRACTION,
                    ExtractionStrategy.LLM_FALLBACK,
                ],
                graphql_endpoint=graphql_ep,
                detection_signals=signals,
            )

        if site_type == SiteType.WORDPRESS:
            return SiteProfile(
                site_type=site_type,
                base_url=base_url,
                strategies=[
                    ExtractionStrategy.JSONLD,
                    ExtractionStrategy.DOM_EXTRACTION,
                    ExtractionStrategy.LLM_FALLBACK,
                ],
                api_endpoints={"rest": f"{base_url}/wp-json/wp/v2"},
                detection_signals=signals,
            )

        return self._generic_profile(base_url, signals)

    def _generic_profile(
        self, base_url: str, signals: Optional[List[str]] = None
    ) -> SiteProfile:
        return SiteProfile(
            site_type=SiteType.GENERIC,
            base_url=base_url,
            strategies=[
                ExtractionStrategy.JSONLD,
                ExtractionStrategy.HYDRATION_STATE,
                ExtractionStrategy.DOM_EXTRACTION,
                ExtractionStrategy.NETWORK_INTERCEPT,
                ExtractionStrategy.LLM_FALLBACK,
            ],
            detection_signals=signals or [],
        )

    def get_strategies_within_budget(
        self, profile: SiteProfile, budget: Optional[int] = None
    ) -> List[ExtractionStrategy]:
        """Return strategies that fit within the extraction budget."""
        budget = budget or profile.extraction_budget
        result = []
        spent = 0
        for strategy in profile.strategies:
            cost = STRATEGY_COST.get(strategy, 3)
            if spent + cost <= budget:
                result.append(strategy)
                spent += cost
        return result

    def should_use_browser(self, profile: SiteProfile, completeness_score: float) -> bool:
        """
        Decide whether browser rendering is justified.
        Only use browser when:
          - Site is headless JS framework AND
          - Completeness score is below threshold AND
          - Browser is in the strategy list
        """
        is_js_heavy = profile.site_type in (
            SiteType.HEADLESS_NEXTJS, SiteType.NUXT, SiteType.CUSTOM_GRAPHQL
        )
        return (
            is_js_heavy
            and completeness_score < 0.72
            and ExtractionStrategy.BROWSER_RENDER in profile.strategies
        )

    def _find_graphql_endpoint(self, html: str, base_url: str) -> Optional[str]:
        """Extract GraphQL endpoint URL from HTML/JS references."""
        patterns = [
            re.compile(r'["\'](/(?:api/)?graphql)["\']'),
            re.compile(r'["\'](' + re.escape(base_url) + r'/(?:api/)?graphql)["\']'),
            re.compile(r'graphqlEndpoint["\s:=]+["\']([^"\']+)["\']'),
        ]
        for pattern in patterns:
            m = pattern.search(html)
            if m:
                ep = m.group(1)
                if not ep.startswith("http"):
                    ep = base_url.rstrip("/") + "/" + ep.lstrip("/")
                return ep
        # Common defaults
        for candidate in ("/graphql", "/api/graphql", "/api/2023-10/graphql.json"):
            return base_url.rstrip("/") + candidate
        return None

    async def _fetch_html(self, url: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; EnterpriseAIBot/2.0)",
                    "Accept": "text/html",
                })
                if resp.status_code == 200:
                    return resp.text
        except Exception as e:
            logger.debug("site_strategy_fetch_failed", url=url, error=str(e))
        return None


site_strategy_engine = SiteStrategyEngine()
