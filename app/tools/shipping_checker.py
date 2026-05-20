"""Shipping checker — estimates delivery time based on location."""
from dataclasses import dataclass
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# Delivery estimates by region (Bangladesh)
DELIVERY_ESTIMATES = {
    "dhaka":        "1-2 business days",
    "chittagong":   "2-3 business days",
    "ctg":          "2-3 business days",
    "sylhet":       "3-4 business days",
    "rajshahi":     "3-4 business days",
    "khulna":       "3-4 business days",
    "barisal":      "3-5 business days",
    "mymensingh":   "2-3 business days",
    "gazipur":      "1-2 business days",
    "narayanganj":  "1-2 business days",
    "default":      "3-5 business days",
}


@dataclass
class ShippingResult:
    location: str
    estimate: str
    has_free_shipping: bool
    message: str


class ShippingCheckerTool:
    """Estimate shipping time and cost based on location."""

    def can_handle(self, query: str) -> bool:
        lower = query.lower()
        return any(k in lower for k in ("delivery time", "how long", "shipping time", "when will", "how many days"))

    def check(self, location: str, order_amount: float = 0.0) -> ShippingResult:
        """Estimate delivery for a location."""
        loc_lower = location.lower().strip()
        estimate = DELIVERY_ESTIMATES.get(loc_lower, DELIVERY_ESTIMATES["default"])
        # Free shipping threshold (example: 1000 BDT)
        has_free = order_amount >= 1000.0

        return ShippingResult(
            location=location,
            estimate=estimate,
            has_free_shipping=has_free,
            message=f"Delivery to {location}: {estimate}. {'Free shipping applied.' if has_free else 'Shipping charges apply.'}",
        )


shipping_checker_tool = ShippingCheckerTool()
