"""Email integration via SMTP."""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import os
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailService:
    """Send emails via SMTP."""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_user)

    async def send(self, to: str, subject: str, body: str, html: bool = False) -> bool:
        """Send email."""
        if not self.smtp_user:
            logger.warning("email_not_configured")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to

            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to, msg.as_string())

            logger.info("email_sent", to=to, subject=subject)
            return True
        except Exception as e:
            logger.error("email_send_failed", to=to, error=str(e))
            return False

    async def send_escalation_email(self, to: str, conversation_id: str, reason: str) -> bool:
        """Send escalation notification email."""
        subject = f"[ESCALATION] Conversation {conversation_id}"
        body = f"An escalation has been triggered.\n\nConversation ID: {conversation_id}\nReason: {reason}"
        return await self.send(to, subject, body)


email_service = EmailService()
