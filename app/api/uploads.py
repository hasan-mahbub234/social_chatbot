"""File upload routes."""
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.uploaded_file import UploadedFile
from uuid import uuid4
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/file")
async def upload_file(
    file: UploadFile = File(...),
    agent_id: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a file for RAG context."""
    try:
        if not current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User must be part of an organization",
            )

        # Read file content
        content = await file.read()

        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file provided",
            )

        # Create file record
        file_id = str(uuid4())
        storage_path = f"uploads/{current_user.organization_id}/{file_id}"

        uploaded_file = UploadedFile(
            organization_id=current_user.organization_id,
            agent_id=agent_id,
            filename=file.filename,
            file_type=file.content_type or "unknown",
            file_size=len(content),
            storage_path=storage_path,
        )

        db.add(uploaded_file)
        db.commit()
        db.refresh(uploaded_file)

        logger.info(f"File uploaded: {file.filename} by {current_user.email}")

        return {
            "id": str(uploaded_file.id),
            "filename": uploaded_file.filename,
            "file_type": uploaded_file.file_type,
            "file_size": uploaded_file.file_size,
            "created_at": uploaded_file.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error uploading file",
        )


@router.get("/file/{file_id}")
async def get_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get uploaded file metadata."""
    try:
        uploaded_file = db.query(UploadedFile).filter(
            UploadedFile.id == file_id,
            UploadedFile.organization_id == current_user.organization_id,
        ).first()

        if not uploaded_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        return {
            "id": str(uploaded_file.id),
            "filename": uploaded_file.filename,
            "file_type": uploaded_file.file_type,
            "file_size": uploaded_file.file_size,
            "is_indexed": uploaded_file.is_indexed,
            "created_at": uploaded_file.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting file",
        )


@router.delete("/file/{file_id}")
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete uploaded file."""
    try:
        uploaded_file = db.query(UploadedFile).filter(
            UploadedFile.id == file_id,
            UploadedFile.organization_id == current_user.organization_id,
        ).first()

        if not uploaded_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        db.delete(uploaded_file)
        db.commit()

        logger.info(f"File deleted: {file_id} by {current_user.email}")

        return {"message": "File deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting file",
        )
