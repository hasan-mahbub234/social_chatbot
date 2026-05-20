"""Analytics background tasks."""
from app.workers.celery_config import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(queue="analytics")
def aggregate_daily_metrics():
    """Aggregate daily metrics for all organizations (used by beat schedule)."""
    db = SessionLocal()
    try:
        from app.models.usage_meter import UsageMeter
        from app.utils.time_utils import current_month
        period = current_month()
        count = db.query(UsageMeter).filter(UsageMeter.period == period).count()
        logger.info("daily_metrics_aggregated", period=period, orgs=count)
        return {"period": period, "organizations": count}
    except Exception as exc:
        logger.error("aggregate_metrics_failed", error=str(exc))
        return {"error": str(exc)}
    finally:
        db.close()


@celery_app.task(queue="analytics")
def record_usage(user_id: str, agent_id: str, endpoint: str, tokens: int, cost: float, model: str):
    """Record API usage asynchronously."""
    db = SessionLocal()
    try:
        from app.models.usage import UsageLog
        from decimal import Decimal
        log = UsageLog(
            user_id=user_id,
            agent_id=agent_id,
            endpoint=endpoint,
            method="POST",
            status_code=200,
            tokens_used=tokens,
            cost=Decimal(str(cost)),
        )
        db.add(log)
        db.commit()
        logger.info("usage_recorded", tokens=tokens, cost=cost)
    except Exception as exc:
        logger.error("usage_record_failed", error=str(exc))
    finally:
        db.close()


@celery_app.task(queue="analytics")
def update_cost_tracking(organization_id: str, model: str, input_tokens: int, output_tokens: int, cost: float):
    """Update cost tracking for organization."""
    import asyncio
    try:
        from app.observability.cost_tracking import cost_tracker
        asyncio.get_event_loop().run_until_complete(
            cost_tracker.record(organization_id, model, input_tokens, output_tokens, cost)
        )
    except Exception as exc:
        logger.error("cost_tracking_failed", error=str(exc))
