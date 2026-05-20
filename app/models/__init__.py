"""Database models package — single import point for all models.

Import order matters: tables with no FK dependencies first,
then tables that reference them. This prevents SQLAlchemy
mapper configuration errors on startup.
"""
# ── No FK dependencies ────────────────────────────────────
from app.models.user import User
from app.models.organization import Organization, OrganizationMember
from app.models.subscription import SubscriptionPlan, Subscription, Invoice, Payment
from app.models.feature_flag import FeatureFlag

# ── Depend on org / user ──────────────────────────────────
from app.models.agent import Agent, RiskPolicy
from app.models.uploaded_file import UploadedFile
from app.models.audit_log import AuditLog
from app.models.usage import UsageLog, APIKey, CostTracking
from app.models.usage_meter import UsageMeter, TenantUsage, QuotaEvent, APIUsage

# ── Depend on agent ───────────────────────────────────────
from app.models.conversation import Conversation
from app.models.escalation import Escalation          # no CacheEntry here
from app.models.cache_entry import CacheEntry         # single canonical definition

# ── Depend on conversation ────────────────────────────────
from app.models.message import Message
from app.models.embedding import Embedding
from app.models.governance_log import GovernanceLog
from app.models.hallucination_log import HallucinationLog
from app.models.risk_assessment import RiskAssessment

# ── Crawler models ───────────────────────────────────────
from app.models.crawl_job import CrawlJob, CrawledPage, CrawlError, CrawlMetric

__all__ = [
    "User",
    "Organization",
    "OrganizationMember",
    "SubscriptionPlan",
    "Subscription",
    "Invoice",
    "Payment",
    "FeatureFlag",
    "Agent",
    "RiskPolicy",
    "UploadedFile",
    "AuditLog",
    "UsageLog",
    "APIKey",
    "CostTracking",
    "UsageMeter",
    "TenantUsage",
    "QuotaEvent",
    "APIUsage",
    "Conversation",
    "Escalation",
    "CacheEntry",
    "Message",
    "Embedding",
    "GovernanceLog",
    "HallucinationLog",
    "RiskAssessment",
    "CrawlJob",
    "CrawledPage",
    "CrawlError",
    "CrawlMetric",
]
