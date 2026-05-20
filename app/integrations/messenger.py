"""Facebook Messenger integration."""
import httpx
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MESSENGER_API_URL = "https://graph.facebook.com/v18.0/me/messages"


class MessengerService:
    """Facebook Messenger Cloud API integration."""

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """Verify Messenger webhook."""
        if mode == "subscribe" and token == settings.MESSENGER_VERIFY_TOKEN:
            return challenge
        return None

    def parse_message(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse incoming Messenger message."""
        try:
            entry = payload.get("entry", [{}])[0]
            messaging = entry.get("messaging", [{}])[0]
            sender_id = messaging.get("sender", {}).get("id")
            message = messaging.get("message", {})
            text = message.get("text", "")
            if not sender_id or not text:
                return None
            return {
                "sender_id": sender_id,
                "text": text,
                "message_id": message.get("mid"),
            }
        except Exception as e:
            logger.error("messenger_parse_failed", error=str(e))
            return None

    async def send_message(self, recipient_id: str, text: str) -> bool:
        """Send a Messenger text message."""
        if not settings.MESSENGER_ACCESS_TOKEN:
            logger.warning("messenger_not_configured")
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    MESSENGER_API_URL,
                    params={"access_token": settings.MESSENGER_ACCESS_TOKEN},
                    json={
                        "recipient": {"id": recipient_id},
                        "message": {"text": text},
                    },
                )
                if resp.status_code != 200:
                    logger.error("messenger_send_failed", status=resp.status_code, body=resp.text)
                return resp.status_code == 200
        except Exception as e:
            logger.error("messenger_send_failed", error=str(e))
            return False


messenger_service = MessengerService()
