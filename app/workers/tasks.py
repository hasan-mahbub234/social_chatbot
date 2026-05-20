"""Celery background tasks — AI processing queue."""
from app.workers.celery_config import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, queue="ai_processing")
def process_message(self, conversation_id: str, agent_id: str, user_input: str, user_id: str) -> dict:
    """Process a chat message asynchronously through the AI pipeline."""
    import asyncio
    from uuid import UUID
    db = SessionLocal()
    try:
        from app.orchestrator.orchestrator import orchestrator
        result = asyncio.get_event_loop().run_until_complete(
            orchestrator.process(
                query=user_input,
                agent_id=UUID(agent_id),
                conversation_id=UUID(conversation_id),
                user_id=UUID(user_id),
                organization_id=UUID(user_id),  # resolved properly in orchestrator
                db=db,
            )
        )
        return {"status": "success", "conversation_id": conversation_id, "content": result.get("content")}
    except Exception as exc:
        logger.error("process_message_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    finally:
        db.close()


@celery_app.task(queue="escalation")
def escalate_issue(conversation_id: str, reason: str, severity: str) -> dict:
    """Create an escalation record for human review."""
    db = SessionLocal()
    try:
        from app.models.escalation import Escalation
        escalation = Escalation(
            conversation_id=conversation_id,
            reason=reason,
            severity=severity,
            status="pending",
        )
        db.add(escalation)
        db.commit()
        logger.info("escalation_created", conversation_id=conversation_id, severity=severity)
        return {"status": "success", "escalation_id": str(escalation.id)}
    except Exception as exc:
        logger.error("escalation_failed", error=str(exc))
        raise
    finally:
        db.close()


@celery_app.task(queue="ai_processing")
def batch_process_messages(agent_id: str, messages: list, user_id: str) -> dict:
    """Queue multiple messages for async processing."""
    task_ids = []
    for msg in messages:
        task = process_message.delay(
            conversation_id=msg.get("conversation_id", ""),
            agent_id=agent_id,
            user_input=msg.get("content", ""),
            user_id=user_id,
        )
        task_ids.append(task.id)
    return {"status": "queued", "count": len(task_ids), "task_ids": task_ids}
