"""Upload service — handle file uploads to S3 and DB."""
from typing import Optional
from sqlalchemy.orm import Session
from app.integrations.s3 import s3_service
from app.models.uploaded_file import UploadedFile
from app.core.logging import get_logger
from uuid import uuid4

logger = get_logger(__name__)


class UploadService:
    """Handle file upload, S3 storage, and DB record creation."""

    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
        organization_id: str,
        db: Session,
        agent_id: Optional[str] = None,
    ) -> UploadedFile:
        """Upload file to S3 and create DB record."""
        file_id = str(uuid4())
        s3_key = s3_service.build_key(organization_id, f"{file_id}_{filename}")

        # Upload to S3
        try:
            await s3_service.upload(file_data, s3_key, content_type)
        except Exception as e:
            logger.error("s3_upload_failed", filename=filename, error=str(e))
            s3_key = None  # Store locally if S3 fails

        storage_path = s3_key or f"local/{organization_id}/{file_id}"

        record = UploadedFile(
            organization_id=organization_id,
            agent_id=agent_id,
            filename=filename,
            file_type=content_type,
            file_size=len(file_data),
            storage_path=storage_path,
            s3_key=s3_key,
            content_preview=file_data[:500].decode("utf-8", errors="ignore"),
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        logger.info("file_uploaded", filename=filename, size=len(file_data))
        return record

    def get_download_url(self, s3_key: str, expiry: int = 3600) -> str:
        """Get presigned download URL."""
        return s3_service.get_presigned_url(s3_key, expiry)


upload_service = UploadService()
