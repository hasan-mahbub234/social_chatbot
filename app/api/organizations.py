"""Organizations API — create, manage orgs and members."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID as PyUUID
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.organization import Organization, OrganizationMember
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrgCreate(BaseModel):
    name: str
    description: Optional[str] = None


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class MemberInvite(BaseModel):
    user_id: str
    role: str = "member"  # owner, admin, member, viewer


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrgCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new organization."""
    org = Organization(
        name=data.name,
        description=data.description,
        owner_id=current_user.id,
    )
    db.add(org)
    db.flush()

    # Add owner as member
    member = OrganizationMember(
        organization_id=org.id,
        user_id=current_user.id,
        role="owner",
    )
    db.add(member)

    # Assign org to user
    current_user.organization_id = org.id
    db.commit()
    db.refresh(org)

    logger.info(f"Organization created: {org.id} by {current_user.email}")
    return {
        "id": str(org.id),
        "name": org.name,
        "description": org.description,
        "owner_id": str(org.owner_id),
        "created_at": org.created_at,
    }


@router.get("/me")
async def get_my_organization(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=404, detail="User is not part of an organization")

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    members = db.query(OrganizationMember).filter(
        OrganizationMember.organization_id == org.id
    ).all()

    return {
        "id": str(org.id),
        "name": org.name,
        "description": org.description,
        "owner_id": str(org.owner_id),
        "member_count": len(members),
        "created_at": org.created_at,
    }


@router.patch("/{org_id}")
async def update_organization(
    org_id: PyUUID,
    data: OrgUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update organization details (owner/admin only)."""
    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.owner_id == current_user.id,
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found or not authorized")

    if data.name is not None:
        org.name = data.name
    if data.description is not None:
        org.description = data.description

    db.commit()
    db.refresh(org)
    return {"id": str(org.id), "name": org.name, "description": org.description}


@router.get("/{org_id}/members")
async def list_members(
    org_id: PyUUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List organization members."""
    # Verify user belongs to org
    member = db.query(OrganizationMember).filter(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == current_user.id,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Not authorized")

    members = db.query(OrganizationMember).filter(
        OrganizationMember.organization_id == org_id
    ).all()

    return [
        {
            "id": str(m.id),
            "user_id": str(m.user_id),
            "role": m.role,
            "created_at": m.created_at,
        }
        for m in members
    ]


@router.post("/{org_id}/members")
async def add_member(
    org_id: PyUUID,
    data: MemberInvite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a member to the organization (owner/admin only)."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Check requester is owner or admin
    requester = db.query(OrganizationMember).filter(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == current_user.id,
        OrganizationMember.role.in_(["owner", "admin"]),
    ).first()
    if not requester:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Check not already a member
    existing = db.query(OrganizationMember).filter(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == data.user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member")

    new_member = OrganizationMember(
        organization_id=org_id,
        user_id=data.user_id,
        role=data.role,
    )
    db.add(new_member)

    # Update user's org
    user = db.query(User).filter(User.id == data.user_id).first()
    if user:
        user.organization_id = org_id

    db.commit()
    return {"message": "Member added", "role": data.role}


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: PyUUID,
    user_id: PyUUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a member from the organization."""
    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.owner_id == current_user.id,
    ).first()
    if not org:
        raise HTTPException(status_code=403, detail="Not authorized")

    member = db.query(OrganizationMember).filter(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(member)
    db.commit()
