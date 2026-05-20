"""Integrations package."""
from app.integrations.s3 import s3_service
from app.integrations.slack import slack_service
from app.integrations.whatsapp import whatsapp_service
from app.integrations.instagram import instagram_service
from app.integrations.email import email_service
from app.integrations.webhooks import webhook_dispatcher

__all__ = [
    "s3_service",
    "slack_service",
    "whatsapp_service",
    "instagram_service",
    "email_service",
    "webhook_dispatcher",
]
