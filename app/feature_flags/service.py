"""Feature flag service — plan-level defaults with per-org overrides."""
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.feature_flag import FeatureFlag
from app.tenancy.context import TenantContext
from app.core.logging import get_logger

logger = get_logger(__name__)

# All known feature keys
FEATURE_GPT4O = "gpt4o_access"
FEATURE_VOICE = "voice_access"
FEATURE_ADVANCED_GOVERNANCE = "advanced_governance"
FEATURE_AUDIT_EXPORT = "audit_export"
FEATURE_CUSTOM_MODELS = "custom_models"
FEATURE_PRIORITY_SUPPORT = "priority_support"
FEATURE_SSO = "sso"
FEATURE_DEDICATED_INFRA = "dedicated_infrastructure"
FEATURE_WEBHOOKS = "webhook_integrations"
FEATURE_ANALYTICS = "analytics_dashboard"
FEATURE_SEMANTIC_CACHE = "semantic_cache"
FEATURE_RAG = "rag_access"
FEATURE_HALLUCINATION = "hallucination_check"
FEATURE_RISK = "risk_assessment"


class FeatureFlagService:
    """Resolve feature access for a tenant."""

    def is_enabled(
        self,
        feature_key: str,
        tenant: TenantContext,
        db: Session,
    ) -> bool:
        """
        Check if a feature is enabled for a tenant.
        Priority: org-level override > plan-level default.
        """
        # 1. Check org-level override in DB
        org_override = db.query(FeatureFlag).filter(
            FeatureFlag.key == feature_key,
            FeatureFlag.organization_id == tenant.organization_id,
        ).first()

        if org_override is not None:
            return org_override.is_enabled

        # 2. Fall back to plan features dict
        features_dict = self._plan_features_dict(tenant)
        return features_dict.get(feature_key, False)

    def require(
        self,
        feature_key: str,
        tenant: TenantContext,
        db: Session,
        upgrade_message: Optional[str] = None,
    ) -> None:
        """Raise 403 if feature is not enabled for tenant."""
        if not self.is_enabled(feature_key, tenant, db):
            plan = tenant.plan_name
            msg = upgrade_message or (
                f"Feature '{feature_key}' is not available on the {plan} plan. "
                f"Please upgrade to access this feature."
            )
            logger.warning("feature_access_denied", feature=feature_key, plan=plan, org=tenant.organization_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FEATURE_NOT_AVAILABLE", "message": msg, "feature": feature_key},
            )

    def get_all(self, tenant: TenantContext, db: Session) -> Dict[str, bool]:
        """Get all feature flags for a tenant."""
        base = self._plan_features_dict(tenant)

        # Apply org-level overrides
        overrides = db.query(FeatureFlag).filter(
            FeatureFlag.organization_id == tenant.organization_id,
        ).all()

        for override in overrides:
            base[override.key] = override.is_enabled

        return base

    def set_override(
        self,
        feature_key: str,
        organization_id: str,
        is_enabled: bool,
        db: Session,
        config: Optional[Dict[str, Any]] = None,
    ) -> FeatureFlag:
        """Set or update an org-level feature override."""
        existing = db.query(FeatureFlag).filter(
            FeatureFlag.key == feature_key,
            FeatureFlag.organization_id == organization_id,
        ).first()

        if existing:
            existing.is_enabled = is_enabled
            if config:
                existing.config = config
        else:
            existing = FeatureFlag(
                key=feature_key,
                name=feature_key.replace("_", " ").title(),
                organization_id=organization_id,
                is_enabled=is_enabled,
                config=config or {},
            )
            db.add(existing)

        db.commit()
        db.refresh(existing)
        return existing

    def _plan_features_dict(self, tenant: TenantContext) -> Dict[str, bool]:
        f = tenant.plan.features
        return {
            FEATURE_GPT4O: f.gpt4o_access,
            FEATURE_VOICE: f.voice_access,
            FEATURE_ADVANCED_GOVERNANCE: f.advanced_governance,
            FEATURE_AUDIT_EXPORT: f.audit_export,
            FEATURE_CUSTOM_MODELS: f.custom_models,
            FEATURE_PRIORITY_SUPPORT: f.priority_support,
            FEATURE_SSO: f.sso,
            FEATURE_DEDICATED_INFRA: f.dedicated_infrastructure,
            FEATURE_WEBHOOKS: f.webhook_integrations,
            FEATURE_ANALYTICS: f.analytics_dashboard,
            FEATURE_SEMANTIC_CACHE: f.semantic_cache,
            FEATURE_RAG: f.rag_access,
            FEATURE_HALLUCINATION: f.hallucination_check,
            FEATURE_RISK: f.risk_assessment,
        }


feature_flag_service = FeatureFlagService()
