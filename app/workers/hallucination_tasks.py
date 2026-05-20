"""Hallucination validation background tasks."""
from app.workers.celery_config import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger
import asyncio

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=2, queue="hallucination")
def validate_response(self, query: str, response: str, context: list, message_id: str = None):
    """Validate response for hallucinations asynchronously."""
    db = SessionLocal()
    try:
        from app.hallucination.validator import hallucination_validator

        result = asyncio.get_event_loop().run_until_complete(
            hallucination_validator.validate(query, response, context)
        )

        # Update message record if provided
        if message_id:
            from app.models.message import Message
            msg = db.query(Message).filter(Message.id == message_id).first()
            if msg:
                msg.is_hallucination_checked = True
                msg.hallucination_score = result["hallucination_score"]
                db.commit()

        logger.info("hallucination_task_complete", score=result["hallucination_score"])
        return result
    except Exception as exc:
        logger.error("hallucination_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=5)
    finally:
        db.close()
