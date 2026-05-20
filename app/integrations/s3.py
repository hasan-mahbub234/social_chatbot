"""AWS S3 integration."""
import boto3
from botocore.exceptions import ClientError
from typing import Optional, BinaryIO
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class S3Service:
    """AWS S3 file storage service."""

    def __init__(self):
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.bucket = settings.S3_BUCKET_NAME

    async def upload(self, file_data: bytes, key: str, content_type: str = "application/octet-stream") -> str:
        """Upload file to S3, return S3 key."""
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=file_data,
                ContentType=content_type,
            )
            logger.info("s3_upload_success", key=key)
            return key
        except ClientError as e:
            logger.error("s3_upload_failed", key=key, error=str(e))
            raise

    def get_presigned_url(self, key: str, expiry: int = 3600) -> str:
        """Generate presigned URL for file download."""
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expiry,
            )
            return url
        except ClientError as e:
            logger.error("s3_presigned_url_failed", key=key, error=str(e))
            raise

    def get_upload_presigned_url(self, key: str, expiry: int = 3600) -> str:
        """Generate presigned URL for direct upload."""
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expiry,
        )

    async def delete(self, key: str):
        """Delete file from S3."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            logger.info("s3_delete_success", key=key)
        except ClientError as e:
            logger.error("s3_delete_failed", key=key, error=str(e))
            raise

    def build_key(self, organization_id: str, filename: str, prefix: str = "uploads") -> str:
        """Build S3 object key."""
        return f"{prefix}/{organization_id}/{filename}"


s3_service = S3Service()
