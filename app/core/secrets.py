"""Secret management utilities."""
import os
from typing import Optional
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get secret from environment or settings."""
    value = os.environ.get(key) or getattr(settings, key, default)
    if not value:
        logger.warning(f"Secret '{key}' not configured")
    return value


def get_openai_key() -> str:
    """Get OpenAI API key."""
    key = get_secret("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY is not configured")
    return key


def get_aws_credentials() -> dict:
    """Get AWS credentials."""
    return {
        "aws_access_key_id": get_secret("AWS_ACCESS_KEY_ID", ""),
        "aws_secret_access_key": get_secret("AWS_SECRET_ACCESS_KEY", ""),
        "region_name": get_secret("AWS_REGION", "us-east-1"),
    }


def get_slack_secret() -> str:
    """Get Slack signing secret."""
    return get_secret("SLACK_SIGNING_SECRET", "")


def get_webhook_secret() -> str:
    """Get generic webhook secret."""
    return get_secret("WEBHOOK_SECRET", "")
