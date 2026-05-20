"""SaaS analytics — MRR, token spend, active tenants, quota usage, cache hit rate."""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models.subscription import Subscription, SubscriptionPlan
from app.models.usage_meter import UsageMeter, TenantUsage
from app.core.logging import get_logger
from app.utils.time_utils import current_month

logger = get_logger(__name__)


class SaaSAnalyticsService:
    """Aggregate SaaS-level metrics for the platform dashboard."""

    def get_mrr(self, db: Session) -> Dict[str, Any]:
        """Calculate Monthly Recurring Revenue by plan."""
        rows = (
            db.query(
                SubscriptionPlan.name,
                SubscriptionPlan.price_monthly,
                func.count(Subscription.id).label("count"),
            )
            .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
            .filter(Subscription.status.in_(["active", "trialing"]))
            .group_by(SubscriptionPlan.name, SubscriptionPlan.price_monthly)
            .all()
        )

        total_mrr = 0.0
        breakdown = {}
        for plan_name, price, count in rows:
            plan_mrr = float(price) * count
            breakdown[plan_name] = {"subscribers": count, "mrr": plan_mrr}
            total_mrr += plan_mrr

        return {"total_mrr": round(total_mrr, 2), "by_plan": breakdown}

    def get_active_tenants(self, db: Session) -> Dict[str, Any]:
        """Count active tenants by plan."""
        rows = (
            db.query(
                SubscriptionPlan.name,
                func.count(Subscription.id).label("count"),
            )
            .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
            .filter(Subscription.status.in_(["active", "trialing"]))
            .group_by(SubscriptionPlan.name)
            .all()
        )
        total = sum(r.count for r in rows)
        return {
            "total": total,
            "by_plan": {r.name: r.count for r in rows},
        }

    def get_token_spend(self, db: Session, period: str = None) -> Dict[str, Any]:
        """Aggregate token usage and cost for a billing period."""
        period = period or current_month()
        row = db.query(
            func.sum(UsageMeter.total_tokens).label("total_tokens"),
            func.sum(UsageMeter.gpt4o_tokens).label("gpt4o_tokens"),
            func.sum(UsageMeter.gpt4o_mini_tokens).label("gpt4o_mini_tokens"),
            func.sum(UsageMeter.embedding_tokens).label("embedding_tokens"),
            func.sum(UsageMeter.total_cost_usd).label("total_cost"),
            func.sum(UsageMeter.gpt4o_cost_usd).label("gpt4o_cost"),
            func.sum(UsageMeter.gpt4o_mini_cost_usd).label("gpt4o_mini_cost"),
        ).filter(UsageMeter.period == period).first()

        return {
            "period": period,
            "total_tokens": int(row.total_tokens or 0),
            "gpt4o_tokens": int(row.gpt4o_tokens or 0),
            "gpt4o_mini_tokens": int(row.gpt4o_mini_tokens or 0),
            "embedding_tokens": int(row.embedding_tokens or 0),
            "total_cost_usd": float(row.total_cost or 0),
            "gpt4o_cost_usd": float(row.gpt4o_cost or 0),
            "gpt4o_mini_cost_usd": float(row.gpt4o_mini_cost or 0),
        }

    def get_quota_usage_summary(self, db: Session, period: str = None) -> List[Dict[str, Any]]:
        """Per-org quota usage summary for current period."""
        period = period or current_month()
        rows = (
            db.query(
                UsageMeter.organization_id,
                UsageMeter.conversations_count,
                UsageMeter.total_tokens,
                UsageMeter.api_calls,
                UsageMeter.voice_minutes,
                UsageMeter.total_cost_usd,
            )
            .filter(UsageMeter.period == period)
            .order_by(UsageMeter.total_cost_usd.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "organization_id": str(r.organization_id),
                "conversations": r.conversations_count,
                "tokens": int(r.total_tokens),
                "api_calls": r.api_calls,
                "voice_minutes": float(r.voice_minutes or 0),
                "cost_usd": float(r.total_cost_usd or 0),
            }
            for r in rows
        ]

    def get_cache_hit_rate(self, db: Session, period: str = None) -> Dict[str, Any]:
        """Calculate semantic cache hit rate for the period."""
        period = period or current_month()
        total = db.query(func.count(TenantUsage.id)).filter(
            TenantUsage.period == period,
            TenantUsage.usage_type == "chat",
        ).scalar() or 0

        hits = db.query(func.count(TenantUsage.id)).filter(
            TenantUsage.period == period,
            TenantUsage.usage_type == "chat",
            TenantUsage.from_cache == True,
        ).scalar() or 0

        rate = round(hits / total, 4) if total > 0 else 0.0
        return {"total_requests": total, "cache_hits": hits, "hit_rate": rate}

    def get_hallucination_rate(self, db: Session, period: str = None) -> Dict[str, Any]:
        """Hallucination detection rate for the period."""
        from app.models.hallucination_log import HallucinationLog
        period = period or current_month()
        start = datetime.strptime(period + "-01", "%Y-%m-%d")
        end = datetime(start.year + (start.month // 12), ((start.month % 12) + 1), 1)

        total = db.query(func.count(HallucinationLog.id)).filter(
            HallucinationLog.created_at >= start,
            HallucinationLog.created_at < end,
        ).scalar() or 0

        high_risk = db.query(func.count(HallucinationLog.id)).filter(
            HallucinationLog.created_at >= start,
            HallucinationLog.created_at < end,
            HallucinationLog.risk_level.in_(["high", "medium"]),
        ).scalar() or 0

        return {
            "total_checked": total,
            "high_risk_count": high_risk,
            "hallucination_rate": round(high_risk / total, 4) if total > 0 else 0.0,
        }

    def get_overview(self, db: Session) -> Dict[str, Any]:
        """Full SaaS dashboard overview."""
        period = current_month()
        return {
            "period": period,
            "mrr": self.get_mrr(db),
            "active_tenants": self.get_active_tenants(db),
            "token_spend": self.get_token_spend(db, period),
            "cache_hit_rate": self.get_cache_hit_rate(db, period),
            "hallucination_rate": self.get_hallucination_rate(db, period),
        }


saas_analytics = SaaSAnalyticsService()
