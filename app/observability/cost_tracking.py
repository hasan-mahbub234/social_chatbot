"""Cost tracking — track and enforce LLM cost budgets."""
from typing import Dict, Any
from app.core.redis_client import redis_client
from app.core.config import settings
from app.cache.cache_keys import org_cost_key
from app.core.logging import get_logger
from datetime import datetime

logger = get_logger(__name__)


class CostTracker:
    """Track LLM costs per organization with budget enforcement."""

    async def record(
        self,
        organization_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
    ):
        """Record cost for an organization."""
        period = datetime.utcnow().strftime("%Y-%m")
        key = org_cost_key(organization_id, period)

        try:
            current = await redis_client.get(key)
            current_cost = float(current) if current else 0.0
            new_cost = current_cost + cost
            await redis_client.set(key, str(new_cost), ex=86400 * 35)  # 35 days

            logger.info(
                "cost_recorded",
                org=organization_id,
                model=model,
                cost=cost,
                monthly_total=new_cost,
            )

            # Budget alert
            if new_cost > settings.MONTHLY_BUDGET_LIMIT * 0.9:
                logger.warning(
                    "budget_threshold_warning",
                    org=organization_id,
                    monthly_cost=new_cost,
                    budget=settings.MONTHLY_BUDGET_LIMIT,
                )
        except Exception as e:
            logger.error("cost_record_failed", error=str(e))

    async def get_monthly_cost(self, organization_id: str) -> float:
        """Get current month's cost for organization."""
        period = datetime.utcnow().strftime("%Y-%m")
        key = org_cost_key(organization_id, period)
        value = await redis_client.get(key)
        return float(value) if value else 0.0

    async def is_over_budget(self, organization_id: str) -> bool:
        """Check if organization has exceeded monthly budget."""
        cost = await self.get_monthly_cost(organization_id)
        return cost >= settings.MONTHLY_BUDGET_LIMIT


cost_tracker = CostTracker()
