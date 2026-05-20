"""Utility helper functions."""
import json
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import re


def generate_id() -> str:
    """Generate unique ID."""
    return str(uuid.uuid4())


def generate_request_id() -> str:
    """Generate request ID."""
    return f"req_{uuid.uuid4().hex[:12]}"


def hash_password(password: str) -> str:
    """Hash password."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hash_value: str) -> bool:
    """Verify password hash."""
    return hash_password(password) == hash_value


def serialize_json(obj: Any) -> str:
    """Serialize object to JSON."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return json.dumps(obj, default=str)


def parse_json(data: str) -> Dict:
    """Parse JSON string."""
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return {}


def slugify(text: str) -> str:
    """Convert text to slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-")


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to max length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def get_expiry_time(minutes: int = 30) -> datetime:
    """Get expiry time in future."""
    return datetime.utcnow() + timedelta(minutes=minutes)


def is_within_hours(dt: datetime, hours: int = 24) -> bool:
    """Check if datetime is within hours."""
    return (datetime.utcnow() - dt).total_seconds() < (hours * 3600)


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """Mask sensitive data."""
    if len(data) <= visible_chars:
        return "*" * len(data)
    return data[:visible_chars] + "*" * (len(data) - visible_chars)


def format_error(error: Exception) -> Dict[str, str]:
    """Format error for response."""
    return {
        "error": error.__class__.__name__,
        "message": str(error),
    }


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_phone(phone: str) -> bool:
    """Validate phone number format."""
    pattern = r"^\+?1?\d{9,15}$"
    return re.match(pattern, phone) is not None


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    pattern = r"https?://[^\s]+"
    return re.findall(pattern, text)


def extract_emails(text: str) -> list[str]:
    """Extract emails from text."""
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return re.findall(pattern, text)
