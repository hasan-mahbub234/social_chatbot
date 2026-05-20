"""Dependency injection for FastAPI.

User is imported inside functions (not at module level) to prevent
circular imports: core/dependencies → models/user → core/database → core/dependencies
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Get current authenticated user."""
    from app.models.user import User  # local import — breaks circular chain

    token = credentials.credentials
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )
    return user


async def get_current_superuser(
    current_user=Depends(get_current_user),
):
    """Require superuser role."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can access this endpoint",
        )
    return current_user


async def get_current_org_member(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Require user to belong to an organization."""
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not part of an organization",
        )
    return current_user
