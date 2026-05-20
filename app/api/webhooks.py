"""Webhook routes for WhatsApp, Instagram, and generic webhooks."""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_webhook_signature
from app.core.config import settings
from app.integrations.whatsapp import whatsapp_service
from app.integrations.instagram import instagram_service
from app.integrations.messenger import messenger_service
from app.orchestrator.orchestrator import orchestrator
from app.core.logging import get_logger
from uuid import UUID
import logging

logger = get_logger(__name__)
_std_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── WhatsApp ──────────────────────────────────────────────────────────────────

@router.get("/whatsapp")
async def whatsapp_verify(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    """WhatsApp webhook verification."""
    from fastapi.responses import PlainTextResponse
    challenge = whatsapp_service.verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    if challenge:
        return PlainTextResponse(content=challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")


WHATSAPP_SYSTEM_PROMPT = "You are a helpful AI assistant on WhatsApp. Keep responses concise, friendly, and suited for mobile chat."
MAX_HISTORY = 6  # kept for Messenger Redis fallback


def _channel_ids(org_id: str, agent_id: str) -> tuple[UUID, UUID]:
    """Parse org/agent UUIDs, raise ValueError if not configured."""
    if not org_id or not agent_id:
        raise ValueError("Channel org/agent IDs not configured in .env")
    return UUID(org_id), UUID(agent_id)


async def _is_duplicate(event_id: str) -> bool:
    """Return True if this webhook event was already processed (dedup via Redis).
    Returns False (not duplicate) if Redis is unavailable — fail open.
    """
    try:
        from app.core.redis_client import redis_client
        if redis_client.client is None:
            return False
        key = f"webhook_dedup:{event_id}"
        result = await redis_client.client.set(key, "1", ex=60, nx=True)
        return result is None
    except Exception:
        return False  # Redis unavailable — allow processing


async def _save_messages_to_db(conversation_id: str, user_text: str, bot_reply: str, db, agent_id: str = None) -> None:
    """Persist user + assistant messages to DB so history survives server restarts."""
    try:
        from app.models.message import Message
        from app.models.conversation import Conversation
        import uuid as _uuid
        conv_id = _uuid.UUID(conversation_id)
        # Ensure conversation row exists
        existing = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if not existing:
            conv = Conversation(
                id=conv_id,
                agent_id=_uuid.UUID(agent_id) if agent_id else _uuid.uuid4(),
            )
            db.add(conv)
            db.flush()
        db.add(Message(conversation_id=conv_id, role="user", content=user_text))
        db.add(Message(conversation_id=conv_id, role="assistant", content=bot_reply))
        db.commit()
    except Exception as e:
        logger.warning("message_db_save_failed", error=str(e))
        try:
            db.rollback()
        except Exception:
            pass


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle incoming WhatsApp messages via full orchestrator pipeline."""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}
    try:
        payload = await request.json()
        msg = whatsapp_service.parse_message(payload)
        if not msg or not msg.get("text"):
            return {"status": "ok"}

        phone = msg["from"]
        text = msg["text"]
        msg_id = msg.get("message_id")
        if msg_id and await _is_duplicate(msg_id):
            return {"status": "ok"}
        _std_logger.info(f"WhatsApp message from {phone}: {text[:50]}")

        try:
            org_uuid, agent_uuid = _channel_ids(settings.WHATSAPP_ORG_ID, settings.WHATSAPP_AGENT_ID)
        except ValueError:
            logger.warning("whatsapp_channel_not_configured")
            return {"status": "ok"}

        # Use phone as stable conversation/user UUID seed
        import uuid
        conv_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"wa:{phone}")
        user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"wa_user:{phone}")

        result = await orchestrator.process(
            query=text,
            agent_id=agent_uuid,
            conversation_id=conv_uuid,
            user_id=user_uuid,
            organization_id=org_uuid,
            db=db,
            is_new_conversation=False,
        )

        ai_reply = result.get("content") or result.get("response") or result.get("message")
        if not ai_reply:
            logger.warning("whatsapp_empty_reply", result_keys=list(result.keys()))
            return {"status": "ok"}
        # Save conversation memory (Redis + DB)
        from app.memory.conversation_memory import conversation_memory
        await conversation_memory.add(str(conv_uuid), "user", text)
        await conversation_memory.add(str(conv_uuid), "assistant", ai_reply)
        await _save_messages_to_db(str(conv_uuid), text, ai_reply, db, str(agent_uuid))
        _std_logger.info(f"WhatsApp bot reply to {phone}: {ai_reply}")
        await whatsapp_service.send_message(
            phone_number_id=msg["phone_number_id"],
            to=phone,
            text=ai_reply,
        )
        return {"status": "ok"}
    except Exception as e:
        import traceback
        _std_logger.error(f"WhatsApp webhook error: {e}\n{traceback.format_exc()}")
        return {"status": "ok"}


# ── Instagram ─────────────────────────────────────────────────────────────────

@router.get("/instagram")
async def instagram_verify(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    """Instagram webhook verification."""
    from fastapi.responses import PlainTextResponse
    challenge = instagram_service.verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    if challenge:
        return PlainTextResponse(content=challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/instagram")
async def instagram_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle incoming Instagram DMs."""
    try:
        payload = await request.json()
        msg = instagram_service.parse_message(payload)

        if not msg or not msg.get("text"):
            return {"status": "ok"}

        logger.info(f"Instagram DM from {msg['sender_id']}: {msg['text'][:50]}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Instagram webhook error: {e}")
        return {"status": "error"}


# ── Facebook Messenger ───────────────────────────────────────────────────────

@router.get("/messenger")
async def messenger_verify(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    """Facebook Messenger webhook verification."""
    from fastapi.responses import PlainTextResponse
    from app.core.config import settings as _s
    if hub_mode in ("subscribe", "subscription") and hub_verify_token == _s.MESSENGER_VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")


MESSENGER_SYSTEM_PROMPT = "You are a helpful AI assistant on Facebook Messenger. Keep responses concise and friendly."


@router.post("/messenger")
async def messenger_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle incoming Facebook Messenger messages via full orchestrator pipeline."""
    # Read body ONCE at the top — prevents ClientDisconnect on Facebook retries
    try:
        body = await request.body()
    except Exception:
        return {"status": "ok"}

    if not body:
        return {"status": "ok"}

    try:
        import json as _json
        payload = _json.loads(body)
    except Exception:
        return {"status": "ok"}

    try:
        # Log raw payload for debugging — remove after confirmed working
        _std_logger.info(f"Messenger raw payload: {payload}")

        if payload.get("object") != "page":
            _std_logger.warning(f"Messenger unexpected object type: {payload.get('object')}")
            return {"status": "ok"}

        msg = messenger_service.parse_message(payload)
        if not msg or not msg.get("text"):
            _std_logger.info(f"Messenger no text message parsed — payload keys: {list(payload.keys())}")
            return {"status": "ok"}

        sender_id = msg["sender_id"]
        text = msg["text"]
        msg_id = msg.get("message_id")
        if msg_id and await _is_duplicate(msg_id):
            return {"status": "ok"}
        _std_logger.info(f"Messenger message from {sender_id}: {text[:50]}")

        try:
            org_uuid, agent_uuid = _channel_ids(settings.MESSENGER_ORG_ID, settings.MESSENGER_AGENT_ID)
        except ValueError:
            logger.warning("messenger_channel_not_configured")
            return {"status": "ok"}

        import uuid
        conv_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"ms:{sender_id}")
        user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"ms_user:{sender_id}")

        result = await orchestrator.process(
            query=text,
            agent_id=agent_uuid,
            conversation_id=conv_uuid,
            user_id=user_uuid,
            organization_id=org_uuid,
            db=db,
            is_new_conversation=False,
        )

        ai_reply = result.get("content") or result.get("response") or result.get("message")
        if not ai_reply:
            logger.warning("messenger_empty_reply", result_keys=list(result.keys()))
            return {"status": "ok"}

        from app.memory.conversation_memory import conversation_memory
        await conversation_memory.add(str(conv_uuid), "user", text)
        await conversation_memory.add(str(conv_uuid), "assistant", ai_reply)
        await _save_messages_to_db(str(conv_uuid), text, ai_reply, db, str(agent_uuid))
        _std_logger.info(f"Messenger bot reply to {sender_id}: {ai_reply}")
        await messenger_service.send_message(recipient_id=sender_id, text=ai_reply)
        return {"status": "ok"}
    except Exception as e:
        import traceback
        _std_logger.error(f"Messenger webhook error: {e}\n{traceback.format_exc()}")
        return {"status": "ok"}  # always return 200 to Facebook to prevent retries


# ── Slack ─────────────────────────────────────────────────────────────────────

@router.post("/slack")
async def slack_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Slack webhook events."""
    try:
        body = await request.body()
        headers = dict(request.headers)
        if not verify_webhook_signature(body, headers):
            raise HTTPException(status_code=401, detail="Invalid signature")

        payload = await request.json()
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}

        logger.info(f"Slack event: {payload.get('type')}")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Slack webhook error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


# ── Generic ───────────────────────────────────────────────────────────────────

@router.post("/generic")
async def generic_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle generic webhook events."""
    try:
        payload = await request.json()
        logger.info(f"Generic webhook received: {list(payload.keys())}")
        return {"status": "ok", "received": True}
    except Exception as e:
        logger.error(f"Generic webhook error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")
