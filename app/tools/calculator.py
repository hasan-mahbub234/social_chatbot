"""
Calculator Tool — handles math queries that should NOT use RAG.

Examples:
  "10% discount on 1500 taka"  → 150 taka discount, 1350 taka total
  "3 items at 890 each"        → 2670 taka total
  "convert 50 USD to BDT"      → approximate conversion
"""
import re
from dataclasses import dataclass
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# Approximate exchange rates (update via config in production)
EXCHANGE_RATES = {
    "usd_to_bdt": 110.0,
    "eur_to_bdt": 120.0,
    "gbp_to_bdt": 140.0,
    "inr_to_bdt": 1.32,
}


@dataclass
class CalculatorResult:
    success: bool
    result: Optional[float]
    formatted: str
    expression: str


class CalculatorTool:
    """Safe math evaluator for price calculations and conversions."""

    def can_handle(self, query: str) -> bool:
        """Check if this query is a math/calculation query."""
        lower = query.lower()
        math_signals = [
            r'\d+\s*[+\-*/×÷]\s*\d+',
            r'\d+%\s*(off|discount|of)',
            r'(total|sum|calculate|how much is)\s+\d+',
            r'\d+\s*(items?|pcs?|pieces?)\s+(at|@|×)\s*\d+',
            r'convert\s+\d+\s*(usd|eur|gbp|inr)\s+to\s+(bdt|taka)',
        ]
        return any(re.search(p, lower) for p in math_signals)

    def calculate(self, query: str) -> CalculatorResult:
        """Evaluate a math query safely."""
        lower = query.lower()

        # Discount calculation
        m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:off|discount)\s+(?:on\s+)?(\d+(?:\.\d+)?)', lower)
        if m:
            pct = float(m.group(1))
            amount = float(m.group(2))
            discount = amount * pct / 100
            total = amount - discount
            return CalculatorResult(
                success=True,
                result=total,
                formatted=f"{pct}% off {amount:.0f} = {discount:.0f} discount, {total:.0f} total",
                expression=f"{amount} - {pct}% = {total}",
            )

        # Items × price
        m = re.search(r'(\d+)\s*(?:items?|pcs?|pieces?)\s*(?:at|@|×|x)\s*(\d+(?:\.\d+)?)', lower)
        if m:
            qty = int(m.group(1))
            price = float(m.group(2))
            total = qty * price
            return CalculatorResult(
                success=True,
                result=total,
                formatted=f"{qty} × {price:.0f} = {total:.0f}",
                expression=f"{qty} * {price}",
            )

        # Currency conversion
        m = re.search(r'convert\s+(\d+(?:\.\d+)?)\s*(usd|eur|gbp|inr)\s+to\s+(?:bdt|taka)', lower)
        if m:
            amount = float(m.group(1))
            currency = m.group(2)
            rate = EXCHANGE_RATES.get(f"{currency}_to_bdt", 1.0)
            result = amount * rate
            return CalculatorResult(
                success=True,
                result=result,
                formatted=f"{amount} {currency.upper()} ≈ {result:.0f} BDT (approx.)",
                expression=f"{amount} × {rate}",
            )

        return CalculatorResult(success=False, result=None, formatted="", expression=query)


calculator_tool = CalculatorTool()
