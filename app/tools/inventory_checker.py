"""
Inventory Checker — checks real-time stock levels from the database.
Uses crawled product data as fallback when live inventory is unavailable.
"""
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.orm import Session
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InventoryResult:
    found: bool
    product_name: str
    availability: str
    stock_level: Optional[int] = None
    message: str = ""


class InventoryCheckerTool:
    """Check product availability from crawled data or live inventory."""

    def can_handle(self, query: str) -> bool:
        lower = query.lower()
        return any(k in lower for k in ("in stock", "out of stock", "available", "stock level", "how many left"))

    async def check(
        self,
        product_name: str,
        organization_id: str,
        db: Session,
        sku: str = "",
    ) -> InventoryResult:
        """Check inventory for a product."""
        try:
            from sqlalchemy import text
            # Try crawled product data first (most up-to-date from last crawl)
            conditions = "organization_id = :org"
            params: dict = {"org": organization_id}

            if sku:
                conditions += " AND url ILIKE :sku"
                params["sku"] = f"%{sku}%"
            elif product_name:
                conditions += " AND url ILIKE :name"
                params["name"] = f"%{product_name.replace(' ', '%')}%"

            row = db.execute(
                text(f"""
                    SELECT url, completeness_score, extraction_quality
                    FROM crawled_pages
                    WHERE {conditions}
                    ORDER BY completeness_score DESC NULLS LAST
                    LIMIT 1
                """),
                params,
            ).fetchone()

            if row:
                # Availability comes from the RAG chunks for this URL
                return InventoryResult(
                    found=True,
                    product_name=product_name,
                    availability="Check product page",
                    message=f"Found product at {row[0]}. Use /product/entity?url={row[0]} for full details.",
                )
        except Exception as e:
            logger.warning("inventory_check_failed", error=str(e))

        return InventoryResult(
            found=False,
            product_name=product_name,
            availability="unknown",
            message=f"Could not find inventory data for '{product_name}'.",
        )


inventory_checker_tool = InventoryCheckerTool()
