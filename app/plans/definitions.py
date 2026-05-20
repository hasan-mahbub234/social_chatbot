"""Subscription plan definitions — single source of truth for limits and features."""
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass(frozen=True)
class PlanLimits:
    max_conversations_per_month: int
    max_tokens_per_month: int
    max_agents: int
    max_api_calls_per_day: int
    max_storage_mb: int
    max_voice_minutes_per_month: int
    max_team_members: int
    rate_limit_per_minute: int
    max_crawl_pages: int = 10
    soft_limit_pct: float = 0.80


@dataclass(frozen=True)
class PlanFeatures:
    gpt4o_access: bool = False
    voice_access: bool = False
    advanced_governance: bool = False
    audit_export: bool = False
    custom_models: bool = False
    priority_support: bool = False
    sso: bool = False
    dedicated_infrastructure: bool = False
    webhook_integrations: bool = False
    analytics_dashboard: bool = False
    semantic_cache: bool = True
    rag_access: bool = True
    hallucination_check: bool = True
    risk_assessment: bool = True


@dataclass(frozen=True)
class Plan:
    name: str
    display_name: str
    description: str
    price_monthly: float
    price_yearly: float
    limits: PlanLimits
    features: PlanFeatures


# ── Free Plan ─────────────────────────────────────────────────────────────────
FREE = Plan(
    name="free",
    display_name="Free",
    description="Get started with AI agents — no credit card required.",
    price_monthly=0.0,
    price_yearly=0.0,
    limits=PlanLimits(
        max_conversations_per_month=100,
        max_tokens_per_month=200_000,
        max_agents=1,
        max_api_calls_per_day=200,
        max_storage_mb=50,
        max_voice_minutes_per_month=0,
        max_team_members=1,
        rate_limit_per_minute=10,
        max_crawl_pages=10_000,
    ),
    features=PlanFeatures(
        gpt4o_access=False,
        voice_access=False,
        advanced_governance=False,
        audit_export=False,
        webhook_integrations=False,
        analytics_dashboard=False,
    ),
)

# ── Growth Plan ───────────────────────────────────────────────────────────────
GROWTH = Plan(
    name="growth",
    display_name="Growth",
    description="For growing teams that need more power, voice, and GPT-4o access.",
    price_monthly=99.0,
    price_yearly=990.0,
    limits=PlanLimits(
        max_conversations_per_month=5_000,
        max_tokens_per_month=10_000_000,
        max_agents=5,
        max_api_calls_per_day=10_000,
        max_storage_mb=5_000,
        max_voice_minutes_per_month=120,
        max_team_members=5,
        rate_limit_per_minute=60,
        max_crawl_pages=50,
    ),
    features=PlanFeatures(
        gpt4o_access=True,
        voice_access=True,
        advanced_governance=False,
        audit_export=False,
        webhook_integrations=True,
        analytics_dashboard=True,
    ),
)

# ── Dedicated Plan (Client Infrastructure) ───────────────────────────────────
DEDICATED = Plan(
    name="dedicated",
    display_name="Dedicated",
    description="Unlimited scale on dedicated infrastructure — tailored to client demand.",
    price_monthly=0.0,   # Custom pricing — set per client
    price_yearly=0.0,
    limits=PlanLimits(
        max_conversations_per_month=10_000_000,
        max_tokens_per_month=1_000_000_000,
        max_agents=10_000,
        max_api_calls_per_day=10_000_000,
        max_storage_mb=10_000_000,
        max_voice_minutes_per_month=1_000_000,
        max_team_members=10_000,
        rate_limit_per_minute=10_000,
        max_crawl_pages=500,
    ),
    features=PlanFeatures(
        gpt4o_access=True,
        voice_access=True,
        advanced_governance=True,
        audit_export=True,
        custom_models=True,
        priority_support=True,
        sso=True,
        dedicated_infrastructure=True,
        webhook_integrations=True,
        analytics_dashboard=True,
    ),
)

ALL_PLANS: Dict[str, Plan] = {
    "free": FREE,
    "growth": GROWTH,
    "dedicated": DEDICATED,
}


def get_plan(name: str) -> Plan:
    return ALL_PLANS.get(name, FREE)


def get_plan_features_dict(plan: Plan) -> Dict[str, Any]:
    return {
        "gpt4o_access": plan.features.gpt4o_access,
        "voice_access": plan.features.voice_access,
        "advanced_governance": plan.features.advanced_governance,
        "audit_export": plan.features.audit_export,
        "custom_models": plan.features.custom_models,
        "priority_support": plan.features.priority_support,
        "sso": plan.features.sso,
        "dedicated_infrastructure": plan.features.dedicated_infrastructure,
        "webhook_integrations": plan.features.webhook_integrations,
        "analytics_dashboard": plan.features.analytics_dashboard,
        "semantic_cache": plan.features.semantic_cache,
        "rag_access": plan.features.rag_access,
        "hallucination_check": plan.features.hallucination_check,
        "risk_assessment": plan.features.risk_assessment,
    }
