"""Common/shared schemas."""
from pydantic import BaseModel
from typing import Optional, Any, Dict
from datetime import datetime


class PaginationParams(BaseModel):
    skip: int = 0
    limit: int = 50


class PaginatedResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list


class SuccessResponse(BaseModel):
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    error: Dict[str, Any]


class HealthStatus(BaseModel):
    status: str
    version: str
    database: str
    redis: str
    timestamp: datetime = None
