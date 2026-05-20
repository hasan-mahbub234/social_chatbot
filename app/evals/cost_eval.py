"""
Cost Evaluator — tracks and analyzes AI inference costs per organization.

Metrics:
  - Cost per query (avg, p95)
  - Cost per token (input vs output)
  - Monthly cost projection
  - Cost by model
  - Cost efficiency: quality score per dollar
  - Budget utilization rate
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List
from app.core.logging import get_logger

logger = get_logger(__name__)

# OpenAI pricing per 1M tokens (USD) — update as pricing changes
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o": {
        "input_per_1m": 2.50,
        "output_per_1m": 10.00,
    },
    "gpt-4o-mini": {
        "input_per_1m": 0.15,
        "output_per_1m": 0.60,
    },
    "groq/llama-3.1-8b-instant": {
        "input_per_1m": 0.05,
        "output_per_1m": 0.08,
    },
    "groq/llama-3.3-70b-versatile": {
        "input_per_1m": 0.59,
        "output_per_1m": 0.79,
    },
}


@dataclass
class CostRecord:
    organization_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    from_cache: bool


@dataclass
class CostSummary:
    total_cost_usd: float
    total_queries: int
    avg_cost_per_query: float
    cache_savings_usd: float        # estimated savings from cache hits
    cost_by_model: Dict[str, float] = field(default_factory=dict)
    monthly_projection_usd: float = 0.0
    budget_utilization_pct: float = 0.0
    most_expensive_model: str = ""


class CostEvaluator:
    """Track and analyze AI inference costs."""

    def __init__(self):
        self._records: List[CostRecord] = []

    def record(self, record: CostRecord) -> None:
        self._records.append(record)
        if len(self._records) > 5000:
            self._records = self._records[-5000:]

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a model call."""
        pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-4o-mini", {}))
        input_cost = (input_tokens / 1_000_000) * pricing.get("input_per_1m", 0.15)
        output_cost = (output_tokens / 1_000_000) * pricing.get("output_per_1m", 0.60)
        return round(input_cost + output_cost, 6)

    def get_summary(
        self,
        organization_id: str,
        monthly_budget: float = 500.0,
        days_elapsed: int = 30,
    ) -> CostSummary:
        """Get cost summary for an organization."""
        org_records = [r for r in self._records if r.organization_id == organization_id]
        if not org_records:
            return CostSummary(0.0, 0, 0.0, 0.0)

        total_cost = sum(r.cost_usd for r in org_records)
        total_queries = len(org_records)
        avg_cost = total_cost / max(total_queries, 1)

        # Cache savings: estimate what cache hits would have cost
        cache_hits = [r for r in org_records if r.from_cache]
        cache_savings = len(cache_hits) * avg_cost  # rough estimate

        # Cost by model
        cost_by_model: Dict[str, float] = {}
        for r in org_records:
            cost_by_model[r.model] = cost_by_model.get(r.model, 0.0) + r.cost_usd

        most_expensive = max(cost_by_model, key=cost_by_model.get) if cost_by_model else ""

        # Monthly projection (linear extrapolation)
        daily_cost = total_cost / max(days_elapsed, 1)
        monthly_projection = daily_cost * 30

        budget_utilization = (total_cost / max(monthly_budget, 0.01)) * 100

        return CostSummary(
            total_cost_usd=round(total_cost, 4),
            total_queries=total_queries,
            avg_cost_per_query=round(avg_cost, 6),
            cache_savings_usd=round(cache_savings, 4),
            cost_by_model={k: round(v, 4) for k, v in cost_by_model.items()},
            monthly_projection_usd=round(monthly_projection, 2),
            budget_utilization_pct=round(budget_utilization, 1),
            most_expensive_model=most_expensive,
        )


cost_evaluator = CostEvaluator()
