"""
Order Lookup Tool — queries the database for order status.
"Where is my order?" should NEVER use RAG — it needs live DB data.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.core.logging import get_logger

logger = get_logger(__name__)

_ORDER_ID_RE = re.compile(r'\b([A-Z]{2,4}-?\d{4,12}|ORD-?\d{4,12}|\d{8,12})\b')


@dataclass
class OrderResult:
    found: bool
    order_id: str
    status: Optional[str] = None
    message: str = ""


class OrderLookupTool:
    """Look up order status from the database."""

    def can_handle(self, query: str) -> bool:
        lower = query.lower()
        return any(k in lower for k in ("my order", "order status", "where is my", "track order", "order id"))

    def extract_order_id(self, query: str) -> str:
        m = _ORDER_ID_RE.search(query)
        return m.group(1) if m else ""

    async def lookup(
        self,
        query: str,
        user_id: str,
        organization_id: str,
        db: Session,
    ) -> OrderResult:
        """Look up order status. Returns structured result."""
        order_id = self.extract_order_id(query)

        if not order_id:
            return OrderResult(
                found=False,
                order_id="",
                message="Please provide your order ID to check the status.",
            )

        # In production: query your orders table
        # This is a stub — replace with actual order model query
        try:
            from sqlalchemy import text
            row = db.execute(
                text("SELECT id, status, created_at FROM orders WHERE id = :oid AND organization_id = :org LIMIT 1"),
                {"oid": order_id, "org": organization_id},
            ).fetchone()

            if row:
                return OrderResult(
                    found=True,
                    order_id=order_id,
                    status=row[1],
                    message=f"Order {order_id}: {row[1]}",
                )
        except Exception:
            pass  # orders table may not exist yet

        return OrderResult(
            found=False,
            order_id=order_id,
            message=f"Order {order_id} not found. Please contact support.",
        )


order_lookup_tool = OrderLookupTool()
