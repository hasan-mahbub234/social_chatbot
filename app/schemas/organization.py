"""Organization schemas."""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class OrganizationBase(BaseModel):
    """Base organization schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    """Organization creation schema."""
    monthly_budget: Optional[Decimal] = Decimal("1000.00")


class OrganizationUpdate(BaseModel):
    """Organization update schema."""
    name: Optional[str] = None
    description: Optional[str] = None
    monthly_budget: Optional[Decimal] = None


class OrganizationResponse(OrganizationBase):
    """Organization response schema."""
    id: UUID
    owner_id: UUID
    is_active: bool
    monthly_budget: Decimal
    current_month_cost: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrganizationMemberBase(BaseModel):
    """Base organization member schema."""
    role: Literal["member", "admin", "owner"] = "member"


class OrganizationMemberCreate(OrganizationMemberBase):
    """Organization member creation schema."""
    user_id: UUID


class OrganizationMemberResponse(OrganizationMemberBase):
    """Organization member response schema."""
    id: UUID
    organization_id: UUID
    user_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
