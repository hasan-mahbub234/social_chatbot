"""WhatsApp Cloud API integration."""
import httpx
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

WHATSAPP_API_URL = "https://graph.facebook.com/v18.0"


class WhatsAppService:
    """WhatsApp Cloud API integration."""

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """Verify WhatsApp webhook."""
        if mode in ("subscribe", "subscription") and token == settings.WHATSAPP_VERIFY_TOKEN:
            return challenge
        return None

    def parse_message(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse incoming WhatsApp message."""
        try:
            entry = payload.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])
            if not messages:
                return None
            msg = messages[0]
            return {
                "from": msg.get("from"),
                "message_id": msg.get("id"),
                "text": msg.get("text", {}).get("body", ""),
                "type": msg.get("type"),
                "phone_number_id": value.get("metadata", {}).get("phone_number_id"),
            }
        except Exception as e:
            logger.error("whatsapp_parse_failed", error=str(e))
            return None

    async def send_message(self, phone_number_id: str, to: str, text: str) -> bool:
        """Send WhatsApp text message."""
        if not settings.WHATSAPP_ACCESS_TOKEN:
            logger.warning("whatsapp_not_configured")
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{WHATSAPP_API_URL}/{phone_number_id}/messages",
                    json={
                        "messaging_product": "whatsapp",
                        "to": to,
                        "type": "text",
                        "text": {"body": text},
                    },
                    headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
                    timeout=10,
                )
                if resp.status_code != 200:
                    logger.error("whatsapp_send_failed", status=resp.status_code, body=resp.text)
                return resp.status_code == 200
        except Exception as e:
            logger.error("whatsapp_send_failed", error=str(e))
            return False


whatsapp_service = WhatsAppService()
