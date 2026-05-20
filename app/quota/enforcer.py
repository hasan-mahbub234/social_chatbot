"""Quota enforcement engine — soft limits, hard limits, budget alerts."""
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.usage_meter import UsageMeter, QuotaEvent
from app.tenancy.context import TenantContext
from app.core.redis_client import redis_client
from app.core.logging import get_logger
from app.utils.time_utils import current_month

logger = get_logger(__name__)

# Quota types
QUOTA_CONVERSATIONS = "conversations"
QUOTA_TOKENS = "tokens"
QUOTA_API_CALLS = "api_calls"
QUOTA_STORAGE = "storage"
QUOTA_VOICE = "voice"
QUOTA_AGENTS = "agents"


class QuotaResult:
    def __init__(
        self,
        allowed: bool,
        quota_type: str,
        current: float,
        limit: float,
        pct_used: float,
        is_soft_limit: bool = False,
        is_hard_limit: bool = False,
        message: str = "",
    ):
        self.allowed = allowed
        self.quota_type = quota_type
        self.current = current
        self.limit = limit
        self.pct_used = pct_used
        self.is_soft_limit = is_soft_limit
        self.is_hard_limit = is_hard_limit
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "quota_type": self.quota_type,
            "current": self.current,
            "limit": self.limit,
            "pct_used": round(self.pct_used, 2),
            "is_soft_limit": self.is_soft_limit,
            "is_hard_limit": self.is_hard_limit,
            "message": self.message,
        }


class QuotaEnforcer:
    """Enforce per-plan quotas with Redis-backed counters and DB persistence."""

    # ── Redis key helpers ─────────────────────────────────────────────────────

    def _meter_key(self, org_id: str, quota_type: str, period: str) -> str:
        return f"quota:{org_id}:{quota_type}:{period}"

    # ── Read current usage ────────────────────────────────────────────────────

    async def _get_current(self, org_id: str, quota_type: str, period: str) -> float:
        key = self._meter_key(org_id, quota_type, period)
        val = await redis_client.get(key)
        return float(val) if val else 0.0

    async def _increment(self, org_id: str, quota_type: str, period: str, amount: float = 1.0) -> float:
        key = self._meter_key(org_id, quota_type, period)
        # Use Redis INCRBYFLOAT for float support
        try:
            new_val = await redis_client.client.incrbyfloat(key, amount)
            # Set expiry to 35 days (covers full billing period)
            await redis_client.client.expire(key, 86400 * 35)
            return float(new_val)
        except Exception as e:
            logger.warning("quota_increment_failed", error=str(e))
            return 0.0

    # ── Core check ────────────────────────────────────────────────────────────

    async def check(
        self,
        tenant: TenantContext,
        quota_type: str,
        db: Session,
        increment_by: float = 0.0,
    ) -> QuotaResult:
        """Check quota and optionally increment. Returns QuotaResult."""
        period = current_month()
        org_id = tenant.organization_id
        limits = tenant.limits
        soft_pct = limits.soft_limit_pct

        limit = self._get_limit(limits, quota_type)
        if limit <= 0:
            # Unlimited
            return QuotaResult(True, quota_type, 0, 0, 0.0)

        current = await self._get_current(org_id, quota_type, period)
        pct = (current / limit) * 100.0

        # Hard limit — block
        if current >= limit:
            await self._log_event(db, org_id, quota_type, "hard_limit_hit", current, limit, pct)
            return QuotaResult(
                allowed=False,
                quota_type=quota_type,
                current=current,
                limit=limit,
                pct_used=pct,
                is_hard_limit=True,
                message=f"Monthly {quota_type} quota exhausted ({int(current)}/{int(limit)}). Upgrade your plan.",
            )

        # Soft limit — warn but allow
        is_soft = pct >= (soft_pct * 100)
        if is_soft:
            await self._log_event(db, org_id, quota_type, "soft_limit_hit", current, limit, pct)
            logger.warning("quota_soft_limit", org=org_id, type=quota_type, pct=pct)

        # Increment if requested
        if increment_by > 0:
            current = await self._increment(org_id, quota_type, period, increment_by)
            pct = (current / limit) * 100.0

        return QuotaResult(
            allowed=True,
            quota_type=quota_type,
            current=current,
            limit=limit,
            pct_used=pct,
            is_soft_limit=is_soft,
            message=f"Approaching {quota_type} limit ({int(pct)}% used)." if is_soft else "",
        )

    async def increment(
        self,
        org_id: str,
        quota_type: str,
        amount: float = 1.0,
    ) -> float:
        """Increment a quota counter without checking limits."""
        period = current_month()
        return await self._increment(org_id, quota_type, period, amount)

    async def get_all_usage(self, org_id: str) -> Dict[str, float]:
        """Get all quota usage for current period."""
        period = current_month()
        types = [QUOTA_CONVERSATIONS, QUOTA_TOKENS, QUOTA_API_CALLS, QUOTA_STORAGE, QUOTA_VOICE]
        result = {}
        for qt in types:
            result[qt] = await self._get_current(org_id, qt, period)
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_limit(self, limits, quota_type: str) -> float:
        mapping = {
            QUOTA_CONVERSATIONS: limits.max_conversations_per_month,
            QUOTA_TOKENS: limits.max_tokens_per_month,
            QUOTA_API_CALLS: limits.max_api_calls_per_day * 30,
            QUOTA_STORAGE: limits.max_storage_mb,
            QUOTA_VOICE: limits.max_voice_minutes_per_month,
            QUOTA_AGENTS: limits.max_agents,
        }
        return float(mapping.get(quota_type, 0))

    async def _log_event(
        self,
        db: Session,
        org_id: str,
        quota_type: str,
        event_type: str,
        current: float,
        limit: float,
        pct: float,
    ):
        """Persist quota event to DB (fire-and-forget style)."""
        try:
            event = QuotaEvent(
                organization_id=org_id,
                quota_type=quota_type,
                event_type=event_type,
                current_value=current,
                limit_value=limit,
                percentage_used=round(pct, 2),
                message=f"{quota_type} at {pct:.1f}% of limit",
            )
            db.add(event)
            db.commit()
        except Exception as e:
            logger.error("quota_event_log_failed", error=str(e))


quota_enforcer = QuotaEnforcer()
