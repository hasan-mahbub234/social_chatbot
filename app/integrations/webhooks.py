"""Outbound webhook dispatcher."""
import httpx
import hmac
import hashlib
from typing import Dict, Any, Optional
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class WebhookDispatcher:
    """Dispatch outbound webhook events to registered endpoints."""

    def _sign(self, payload: str) -> str:
        """Sign payload with HMAC-SHA256."""
        secret = settings.WEBHOOK_SECRET
        if not secret:
            return ""
        return "sha256=" + hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    async def dispatch(
        self,
        url: str,
        event: str,
        data: Dict[str, Any],
        timeout: int = 10,
    ) -> bool:
        """Send webhook event to URL."""
        import json
        payload = json.dumps({"event": event, "data": data})
        signature = self._sign(payload)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
        }
        if signature:
            headers["X-Webhook-Signature"] = signature

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, content=payload, headers=headers, timeout=timeout)
                success = resp.status_code < 300
                logger.info("webhook_dispatched", url=url, event=event, status=resp.status_code)
                return success
        except Exception as e:
            logger.error("webhook_dispatch_failed", url=url, event=event, error=str(e))
            return False


webhook_dispatcher = WebhookDispatcher()
