"""Authentication routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserResponse,
    LoginRequest,
    TokenResponse,
    TokenRequest,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    try:
        # Check if user exists
        existing_user = db.query(User).filter(
            (User.email == user.email) | (User.username == user.username)
        ).first()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email or username already exists",
            )

        # Create new user
        hashed_password = hash_password(user.password)
        new_user = User(
            email=user.email,
            username=user.username,
            hashed_password=hashed_password,
            full_name=user.full_name,
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info(f"New user registered: {new_user.email}")
        return new_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error registering user",
        )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """Login user."""
    try:
        # Find user by email
        user = db.query(User).filter(User.email == credentials.email).first()

        if not user or not verify_password(credentials.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive",
            )

        # Create tokens
        access_token = create_access_token({"sub": str(user.id)})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        logger.info(f"User logged in: {user.email}")
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during login",
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(token_request: TokenRequest):
    """Refresh access token."""
    try:
        # Decode refresh token
        payload = decode_token(token_request.refresh_token)
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        # Create new access token
        access_token = create_access_token({"sub": user_id})

        return {
            "access_token": access_token,
            "refresh_token": token_request.refresh_token,
            "token_type": "bearer",
        }
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    try:
        return current_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting user information",
        )
