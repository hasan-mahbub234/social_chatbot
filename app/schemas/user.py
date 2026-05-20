"""Pydantic schemas for user operations."""
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from uuid import UUID
from typing import Optional


class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=255)
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """User creation schema."""
    password: str = Field(..., min_length=8, max_length=255)


class UserUpdate(BaseModel):
    """User update schema."""
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, max_length=255)


class UserResponse(UserBase):
    """User response schema."""
    id: UUID
    is_active: bool
    is_superuser: bool
    organization_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserProfile(UserResponse):
    """User profile with organization info."""
    organization: Optional[dict] = None


class LoginRequest(BaseModel):
    """Login request schema."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response schema."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRequest(BaseModel):
    """Token refresh request schema."""
    refresh_token: str
