"""Instagram Messaging API integration."""
import httpx
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

INSTAGRAM_API_URL = "https://graph.facebook.com/v18.0"


class InstagramService:
    """Instagram Messaging API integration."""

    def __init__(self):
        self.access_token = settings.INSTAGRAM_ACCESS_TOKEN
        self.verify_token = settings.INSTAGRAM_VERIFY_TOKEN

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        if mode in ("subscribe", "subscription") and token == self.verify_token:
            return challenge
        return None

    def parse_message(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse incoming Instagram DM."""
        try:
            entry = payload.get("entry", [{}])[0]
            messaging = entry.get("messaging", [{}])[0]
            return {
                "sender_id": messaging.get("sender", {}).get("id"),
                "recipient_id": messaging.get("recipient", {}).get("id"),
                "text": messaging.get("message", {}).get("text", ""),
                "message_id": messaging.get("message", {}).get("mid"),
            }
        except Exception as e:
            logger.error("instagram_parse_failed", error=str(e))
            return None

    async def send_message(self, recipient_id: str, text: str, page_id: str) -> bool:
        """Send Instagram DM reply."""
        if not self.access_token:
            logger.warning("instagram_not_configured")
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{INSTAGRAM_API_URL}/{page_id}/messages",
                    json={
                        "recipient": {"id": recipient_id},
                        "message": {"text": text},
                    },
                    params={"access_token": self.access_token},
                    timeout=10,
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error("instagram_send_failed", error=str(e))
            return False


instagram_service = InstagramService()
