"""Time utilities."""
from datetime import datetime, timedelta, timezone
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_naive() -> datetime:
    return datetime.utcnow()


def add_seconds(dt: datetime, seconds: int) -> datetime:
    return dt + timedelta(seconds=seconds)


def add_days(dt: datetime, days: int) -> datetime:
    return dt + timedelta(days=days)


def is_expired(dt: datetime) -> bool:
    """Check if a datetime is in the past."""
    now = datetime.utcnow()
    if dt.tzinfo:
        now = datetime.now(timezone.utc)
    return dt < now


def format_iso(dt: datetime) -> str:
    return dt.isoformat()


def current_month() -> str:
    """Return current month as YYYY-MM string."""
    return datetime.utcnow().strftime("%Y-%m")


def seconds_until(dt: datetime) -> int:
    """Seconds until a future datetime."""
    delta = dt - datetime.utcnow()
    return max(0, int(delta.total_seconds()))
