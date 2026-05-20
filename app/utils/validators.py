"""Validation utilities."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ValidationError, field_validator
import re


class ValidationError(Exception):
    """Validation error."""
    pass


def validate_required_fields(data: Dict, required_fields: List[str]) -> None:
    """Validate required fields exist."""
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        raise ValidationError(f"Missing required fields: {', '.join(missing)}")


def validate_field_type(field_value: Any, expected_type: type) -> None:
    """Validate field type."""
    if not isinstance(field_value, expected_type):
        raise ValidationError(
            f"Field type mismatch: expected {expected_type.__name__}, "
            f"got {type(field_value).__name__}"
        )


def validate_field_length(text: str, min_length: int = 0, max_length: Optional[int] = None) -> None:
    """Validate text length."""
    if len(text) < min_length:
        raise ValidationError(f"Text too short: minimum {min_length} characters")
    if max_length and len(text) > max_length:
        raise ValidationError(f"Text too long: maximum {max_length} characters")


def validate_field_pattern(text: str, pattern: str, field_name: str = "Field") -> None:
    """Validate field matches pattern."""
    if not re.match(pattern, text):
        raise ValidationError(f"{field_name} format is invalid")


def validate_numeric_range(value: float, min_val: float = 0, max_val: float = 100) -> None:
    """Validate number is in range."""
    if not min_val <= value <= max_val:
        raise ValidationError(f"Value must be between {min_val} and {max_val}")


def validate_choice(value: str, choices: List[str]) -> None:
    """Validate value is in choices."""
    if value not in choices:
        raise ValidationError(f"Value must be one of: {', '.join(choices)}")


class QueryValidator(BaseModel):
    """Validate query parameters."""
    
    skip: int = 0
    limit: int = 100
    sort: Optional[str] = None
    order: str = "asc"
    
    @field_validator("skip")
    def validate_skip(cls, v):
        if v < 0:
            raise ValueError("skip must be >= 0")
        return v
    
    @field_validator("limit")
    def validate_limit(cls, v):
        if v < 1 or v > 1000:
            raise ValueError("limit must be between 1 and 1000")
        return v
    
    @field_validator("order")
    def validate_order(cls, v):
        if v not in ["asc", "desc"]:
            raise ValueError("order must be 'asc' or 'desc'")
        return v
