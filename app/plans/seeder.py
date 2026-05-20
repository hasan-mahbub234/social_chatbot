"""Seed subscription plans into the database."""
from sqlalchemy.orm import Session
from app.models.subscription import SubscriptionPlan
from app.plans.definitions import ALL_PLANS, get_plan_features_dict
from app.core.logging import get_logger

logger = get_logger(__name__)


def seed_plans(db: Session) -> None:
    """Upsert all plan definitions into subscription_plans table."""
    for order, (name, plan) in enumerate(ALL_PLANS.items()):
        existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == name).first()
        if existing:
            existing.display_name = plan.display_name
            existing.description = plan.description
            existing.price_monthly = plan.price_monthly
            existing.price_yearly = plan.price_yearly
            existing.max_conversations_per_month = plan.limits.max_conversations_per_month
            existing.max_tokens_per_month = plan.limits.max_tokens_per_month
            existing.max_agents = plan.limits.max_agents
            existing.max_api_calls_per_day = plan.limits.max_api_calls_per_day
            existing.max_storage_mb = plan.limits.max_storage_mb
            existing.max_voice_minutes_per_month = plan.limits.max_voice_minutes_per_month
            existing.max_team_members = plan.limits.max_team_members
            existing.rate_limit_per_minute = plan.limits.rate_limit_per_minute
            existing.features = get_plan_features_dict(plan)
            existing.sort_order = order
        else:
            record = SubscriptionPlan(
                name=name,
                display_name=plan.display_name,
                description=plan.description,
                price_monthly=plan.price_monthly,
                price_yearly=plan.price_yearly,
                max_conversations_per_month=plan.limits.max_conversations_per_month,
                max_tokens_per_month=plan.limits.max_tokens_per_month,
                max_agents=plan.limits.max_agents,
                max_api_calls_per_day=plan.limits.max_api_calls_per_day,
                max_storage_mb=plan.limits.max_storage_mb,
                max_voice_minutes_per_month=plan.limits.max_voice_minutes_per_month,
                max_team_members=plan.limits.max_team_members,
                rate_limit_per_minute=plan.limits.rate_limit_per_minute,
                features=get_plan_features_dict(plan),
                sort_order=order,
            )
            db.add(record)

    db.commit()
