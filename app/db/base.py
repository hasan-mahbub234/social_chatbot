"""Database base — single source of truth for SQLAlchemy Base.

All models must import Base from here or from app.core.database.
Never call declarative_base() again anywhere else in the project.
"""
# Re-export the single Base instance defined in core/database.py
from app.core.database import Base  # noqa: F401

from sqlalchemy.orm import declared_attr
from sqlalchemy import Column, DateTime, Boolean, func


class TimestampMixin:
    """Mixin that adds created_at / updated_at to any model."""

    @declared_attr
    def created_at(cls):
        return Column(DateTime, default=func.now(), nullable=False)

    @declared_attr
    def updated_at(cls):
        return Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


__all__ = ["Base", "TimestampMixin"]
