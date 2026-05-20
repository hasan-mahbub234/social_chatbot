"""Slack integration."""
import httpx
from typing import Optional
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SlackService:
    """Send notifications and messages via Slack."""

    def __init__(self):
        self.webhook_url: Optional[str] = None
        self.bot_token: Optional[str] = None

    def configure(self, webhook_url: str = None, bot_token: str = None):
        self.webhook_url = webhook_url
        self.bot_token = bot_token

    async def send_message(self, channel: str, text: str, blocks: list = None) -> bool:
        """Send message to Slack channel."""
        if not self.bot_token:
            logger.warning("slack_not_configured")
            return False

        payload = {"channel": channel, "text": text}
        if blocks:
            payload["blocks"] = blocks

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    timeout=10,
                )
                data = resp.json()
                if not data.get("ok"):
                    logger.error("slack_send_failed", error=data.get("error"))
                    return False
                return True
        except Exception as e:
            logger.error("slack_send_error", error=str(e))
            return False

    async def send_escalation_alert(self, conversation_id: str, reason: str, severity: str):
        """Send escalation alert to Slack."""
        text = f":warning: *Escalation Alert* [{severity.upper()}]\nConversation: {conversation_id}\nReason: {reason}"
        return await self.send_message("#escalations", text)

    async def send_webhook(self, text: str) -> bool:
        """Send message via incoming webhook."""
        if not self.webhook_url:
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json={"text": text}, timeout=10)
                return resp.status_code == 200
        except Exception as e:
            logger.error("slack_webhook_error", error=str(e))
            return False


slack_service = SlackService()
