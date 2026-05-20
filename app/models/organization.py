"""Organization model."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class Organization(Base):
    """Organization model."""

    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Cost control
    monthly_budget = Column(Numeric(10, 2), default=1000.0)
    current_month_cost = Column(Numeric(10, 2), default=0.0)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id])
    users = relationship("User", back_populates="organization", foreign_keys="User.organization_id")
    agents = relationship("Agent", back_populates="organization")
    members = relationship("OrganizationMember", back_populates="organization")
    subscription = relationship("Subscription", back_populates="organization", uselist=False)

    def __repr__(self):
        return f"<Organization {self.name}>"


class OrganizationMember(Base):
    """Organization member model."""

    __tablename__ = "organization_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(String(50), default="member")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="members")

    def __repr__(self):
        return f"<OrganizationMember {self.organization_id} - {self.user_id}>"
