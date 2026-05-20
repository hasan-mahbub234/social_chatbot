"""Authentication schemas."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
import uuid


class SignupRequest(BaseModel):
    """User signup request."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str


class UserResponse(BaseModel):
    """User response."""
    id: uuid.UUID
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PasswordChangeRequest(BaseModel):
    """Password change request."""
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=100)


class PasswordResetRequest(BaseModel):
    """Password reset request."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation."""
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
