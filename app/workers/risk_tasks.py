"""Risk assessment background tasks."""
from app.workers.celery_config import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger
import asyncio

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=2, queue="risk_assessment")
def run_risk_assessment(self, text: str, user_id: str, organization_id: str, conversation_id: str = None):
    """Run risk assessment asynchronously."""
    db = SessionLocal()
    try:
        from app.risk.risk_engine import risk_engine

        result = asyncio.get_event_loop().run_until_complete(
            risk_engine.score(text, user_id, organization_id)
        )

        if result["escalate"] and conversation_id:
            from app.models.escalation import Escalation
            escalation = Escalation(
                reason=result["reason"],
                severity=result["risk_category"],
                status="pending",
                context=result,
            )
            db.add(escalation)
            db.commit()
            logger.warning("risk_escalation_created", conversation_id=conversation_id)

        return result
    except Exception as exc:
        logger.error("risk_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=5)
    finally:
        db.close()
