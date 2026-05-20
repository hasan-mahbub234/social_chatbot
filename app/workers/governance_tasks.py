"""Governance background tasks."""
from app.workers.celery_config import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger
import asyncio

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=2, queue="governance")
def run_governance_check(self, text: str, organization_id: str, conversation_id: str = None):
    """Run governance evaluation asynchronously."""
    db = SessionLocal()
    try:
        from app.governance.governance_service import governance_service
        from app.observability.audit_logger import audit_logger

        result = asyncio.get_event_loop().run_until_complete(
            governance_service.evaluate(text, organization_id)
        )

        if not result["allowed"]:
            audit_logger.log_governance(
                db=db,
                organization_id=organization_id,
                policy_name="governance_check",
                policy_type="content",
                action_taken=result["action"],
                severity=result["risk_level"],
                description=result["reason"],
                is_blocked=True,
                details=result,
            )

        logger.info("governance_task_complete", allowed=result["allowed"])
        return result
    except Exception as exc:
        logger.error("governance_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=5)
    finally:
        db.close()
