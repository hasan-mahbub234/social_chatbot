"""JSON utilities."""
import json
from typing import Any, Optional
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class CustomEncoder(json.JSONEncoder):
    """JSON encoder that handles UUID, datetime, Decimal."""

    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def dumps(obj: Any, **kwargs) -> str:
    return json.dumps(obj, cls=CustomEncoder, **kwargs)


def loads(s: str, **kwargs) -> Any:
    return json.loads(s, **kwargs)


def safe_loads(s: str, default: Any = None) -> Any:
    """Parse JSON without raising exceptions."""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default
