"""Product detector — identifies product/pricing pages for specialized extraction."""
import re
from typing import Dict, Any
from app.core.logging import get_logger

logger = get_logger(__name__)

PRODUCT_SIGNALS = [
    r"\$\d+", r"price", r"buy now", r"add to cart", r"checkout",
    r"product", r"sku", r"in stock", r"out of stock", r"shipping",
]

PRICING_SIGNALS = [
    r"per month", r"per year", r"/mo", r"/yr", r"pricing",
    r"plan", r"subscription", r"free trial", r"upgrade",
]


class ProductDetector:
    """Detect if a page is a product or pricing page."""

    def detect(self, text: str, url: str = "") -> Dict[str, Any]:
        """Detect page type and extract relevant signals."""
        lower = text.lower()
        url_lower = url.lower()

        product_hits = sum(1 for p in PRODUCT_SIGNALS if re.search(p, lower))
        pricing_hits = sum(1 for p in PRICING_SIGNALS if re.search(p, lower))

        is_product = product_hits >= 2
        is_pricing = pricing_hits >= 2 or "pricing" in url_lower or "plans" in url_lower

        page_type = "pricing" if is_pricing else ("product" if is_product else "general")

        return {
            "page_type": page_type,
            "is_product": is_product,
            "is_pricing": is_pricing,
            "product_signals": product_hits,
            "pricing_signals": pricing_hits,
        }


product_detector = ProductDetector()