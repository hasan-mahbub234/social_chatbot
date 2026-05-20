"""Usage metering service — records per-request usage events."""
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.usage_meter import UsageMeter, TenantUsage, APIUsage
from app.quota.enforcer import quota_enforcer, QUOTA_TOKENS, QUOTA_CONVERSATIONS, QUOTA_API_CALLS, QUOTA_VOICE
from app.core.logging import get_logger
from app.utils.time_utils import current_month

logger = get_logger(__name__)


class UsageMeteringService:
    """Record and aggregate usage for billing and quota enforcement."""

    async def record_chat(
        self,
        organization_id: str,
        user_id: str,
        agent_id: str,
        conversation_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        duration_ms: int,
        from_cache: bool,
        db: Session,
        is_new_conversation: bool = False,
    ) -> None:
        """Record a chat completion usage event."""
        period = current_month()
        total_tokens = input_tokens + output_tokens
        is_gpt4o = "gpt-4o" in model and "mini" not in model

        try:
            # Persist granular event
            event = TenantUsage(
                organization_id=organization_id,
                user_id=None,
                agent_id=agent_id,
                conversation_id=conversation_id,
                usage_type="chat",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
                from_cache=from_cache,
                period=period,
            )
            db.add(event)

            # Update aggregated meter
            meter = self._get_or_create_meter(organization_id, period, db)
            meter.total_tokens += total_tokens
            meter.total_cost_usd = float(meter.total_cost_usd or 0) + cost_usd
            meter.api_calls += 1

            if is_gpt4o:
                meter.gpt4o_tokens += total_tokens
                meter.gpt4o_cost_usd = float(meter.gpt4o_cost_usd or 0) + cost_usd
            else:
                meter.gpt4o_mini_tokens += total_tokens
                meter.gpt4o_mini_cost_usd = float(meter.gpt4o_mini_cost_usd or 0) + cost_usd

            if is_new_conversation:
                meter.conversations_count += 1

            db.commit()
        except Exception as e:
            logger.warning("metering_record_failed", error=str(e))
            try:
                db.rollback()
            except Exception:
                pass

        # Increment Redis quota counters — always runs, even if DB write failed
        await quota_enforcer.increment(organization_id, QUOTA_TOKENS, total_tokens)
        await quota_enforcer.increment(organization_id, QUOTA_API_CALLS, 1)
        if is_new_conversation:
            await quota_enforcer.increment(organization_id, QUOTA_CONVERSATIONS, 1)

    async def record_embedding(
        self,
        organization_id: str,
        tokens: int,
        cost_usd: float,
        db: Session,
    ) -> None:
        """Record embedding usage."""
        period = current_month()
        try:
            event = TenantUsage(
                organization_id=organization_id,
                usage_type="embedding",
                input_tokens=tokens,
                total_tokens=tokens,
                cost_usd=cost_usd,
                period=period,
            )
            db.add(event)
            meter = self._get_or_create_meter(organization_id, period, db)
            meter.embedding_tokens += tokens
            meter.embedding_cost_usd = float(meter.embedding_cost_usd or 0) + cost_usd
            meter.total_tokens += tokens
            meter.total_cost_usd = float(meter.total_cost_usd or 0) + cost_usd
            db.commit()
        except Exception as e:
            logger.warning("metering_embedding_failed", error=str(e))
            try:
                db.rollback()
            except Exception:
                pass
        await quota_enforcer.increment(organization_id, QUOTA_TOKENS, tokens)

    async def record_voice(
        self,
        organization_id: str,
        voice_seconds: float,
        cost_usd: float,
        usage_type: str,
        db: Session,
    ) -> None:
        """Record voice transcription or TTS usage."""
        period = current_month()
        voice_minutes = voice_seconds / 60.0
        try:
            event = TenantUsage(
                organization_id=organization_id,
                usage_type=usage_type,
                voice_seconds=voice_seconds,
                cost_usd=cost_usd,
                period=period,
            )
            db.add(event)
            meter = self._get_or_create_meter(organization_id, period, db)
            meter.voice_minutes = float(meter.voice_minutes or 0) + voice_minutes
            meter.voice_cost_usd = float(meter.voice_cost_usd or 0) + cost_usd
            meter.total_cost_usd = float(meter.total_cost_usd or 0) + cost_usd
            db.commit()
        except Exception as e:
            logger.warning("metering_voice_failed", error=str(e))
            try:
                db.rollback()
            except Exception:
                pass
        await quota_enforcer.increment(organization_id, QUOTA_VOICE, voice_minutes)

    async def record_api_call(
        self,
        organization_id: str,
        user_id: Optional[str],
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: int,
        db: Session,
        ip_address: Optional[str] = None,
        request_id: Optional[str] = None,
        was_rate_limited: bool = False,
    ) -> None:
        """Record an API call for usage tracking."""
        period = current_month()
        record = APIUsage(
            organization_id=organization_id,
            user_id=user_id,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            response_time_ms=response_time_ms,
            period=period,
            ip_address=ip_address,
            request_id=request_id,
            was_rate_limited=was_rate_limited,
        )
        db.add(record)
        db.commit()

    def get_meter(self, organization_id: str, period: str, db: Session) -> Optional[UsageMeter]:
        return db.query(UsageMeter).filter(
            UsageMeter.organization_id == organization_id,
            UsageMeter.period == period,
        ).first()

    def _get_or_create_meter(self, organization_id: str, period: str, db: Session) -> UsageMeter:
        """
        Get or create a UsageMeter row safely.

        Uses SELECT-first to avoid UniqueViolation on concurrent requests.
        The unique index ix_usage_meters_org_period means two concurrent requests
        for the same (org, period) will race on INSERT — SELECT-first prevents that.
        If a race still occurs (extremely rare), we catch the IntegrityError,
        rollback the savepoint, and re-fetch the row that the other request inserted.
        """
        # Always SELECT first — avoids the race in the common case
        meter = self.get_meter(organization_id, period, db)
        if meter:
            return meter

        # Row doesn't exist yet — try to INSERT
        try:
            meter = UsageMeter(organization_id=organization_id, period=period)
            db.add(meter)
            db.flush()   # flush only, not commit — caller commits
            return meter
        except Exception:
            # UniqueViolation: another request inserted the row between our SELECT and INSERT.
            # Rollback the failed flush so the session is usable again, then re-fetch.
            db.rollback()
            meter = self.get_meter(organization_id, period, db)
            if meter:
                return meter
            # Should never reach here, but create a fresh object as last resort
            meter = UsageMeter(organization_id=organization_id, period=period)
            db.add(meter)
            db.flush()
            return meter


usage_metering_service = UsageMeteringService()
