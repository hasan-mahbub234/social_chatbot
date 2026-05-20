"""Extraction validator — platform-aware quality scoring. Does NOT trigger browser for structured-data platforms."""
import re
from typing import Dict, Any, Tuple
from app.core.logging import get_logger

logger = get_logger(__name__)

# Platforms that use structured data (JSON-LD / API) — DOM signals are irrelevant
STRUCTURED_DATA_PLATFORMS = {"shopify", "woocommerce"}

# DOM signals only checked for generic/unknown platforms
PRODUCT_SIGNALS = [
    (r'add.to.cart|buy.now', "add_to_cart"),
    (r'price|৳|\$|£|€', "price"),
    (r'in.stock|out.of.stock|availability', "availability"),
    (r'sku|product.?id', "sku"),
]
FAQ_SIGNAL = re.compile(r'<details|accordion|faq|frequently.asked', re.I)
TABLE_SIGNAL = re.compile(r'<table', re.I)

# JS framework markers — only these justify browser rendering
JS_MARKERS = ("__next_f", "data-reactroot", "ng-version", "v-app", "__nuxt", "ember-application")

MIN_CONTENT_LENGTH = 150
QUALITY_THRESHOLD = 0.5


class ExtractionValidator:
    """
    Score extraction quality.

    Rules:
    - Structured data platforms (Shopify, WooCommerce): always high quality — skip DOM checks
    - JSON-LD present in content: boost score
    - Generic platforms: check for missing DOM signals
    - JS-heavy detection is separate from quality score
    """

    def validate(self, html: str, extracted: Dict[str, Any]) -> Tuple[float, bool, str]:
        """
        Returns (quality_score 0-1, needs_browser_render, reason).

        needs_browser_render is True ONLY when:
          - quality is low AND
          - JS framework markers are present in HTML
        """
        platform = extracted.get("platform", "generic")
        content = extracted.get("content", "")
        content_type = extracted.get("content_type", "page")

        # Structured data platforms — trust the extraction, no DOM validation
        if platform in STRUCTURED_DATA_PLATFORMS:
            return 0.9, False, "structured_data_platform"

        # JSON-LD product/article extracted — high confidence
        if content_type in ("product", "faq", "article", "business", "restaurant", "event"):
            if len(content) > 100:
                return 0.85, False, "jsonld_extracted"

        if not content or len(content) < MIN_CONTENT_LENGTH:
            js_heavy = any(m in html for m in JS_MARKERS)
            return 0.1, js_heavy, "content_too_short"

        score = 1.0
        reasons = []
        html_lower = html.lower()
        content_lower = content.lower()

        # Only check DOM signals for generic/unknown platforms
        missing = 0
        for pattern, name in PRODUCT_SIGNALS:
            in_html = bool(re.search(pattern, html_lower))
            in_content = bool(re.search(pattern, content_lower))
            if in_html and not in_content:
                missing += 1
                reasons.append(f"missing_{name}")

        if missing >= 2:
            score -= 0.3

        # Missing FAQ/accordion
        if FAQ_SIGNAL.search(html_lower) and "q:" not in content_lower and "faq" not in content_lower:
            score -= 0.15
            reasons.append("missing_faq")

        # Missing tables
        if TABLE_SIGNAL.search(html) and "|" not in content:
            score -= 0.1
            reasons.append("missing_table")

        score = max(0.0, min(1.0, score))

        # Browser rendering only justified when JS markers are present
        js_heavy = any(m in html for m in JS_MARKERS)
        needs_render = score < QUALITY_THRESHOLD and js_heavy

        reason = ", ".join(reasons) if reasons else "ok"
        if needs_render:
            logger.info("browser_render_justified", score=score, reason=reason, url="")

        return score, needs_render, reason


extraction_validator = ExtractionValidator()
