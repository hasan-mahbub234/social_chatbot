"""Raw HTML storage — saves compressed HTML to S3 for debugging and pipeline replay."""
import gzip
import json
from datetime import datetime
from typing import Dict, Any, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


class RawHTMLStorage:
    """Store raw HTML + metadata to S3 as gzip-compressed JSON."""

    def _build_key(self, organization_id: str, job_id: str, url_hash: str) -> str:
        date = datetime.utcnow().strftime("%Y/%m/%d")
        return f"crawler/raw/{organization_id}/{date}/{job_id}/{url_hash}.json.gz"

    async def store(
        self,
        organization_id: str,
        job_id: str,
        url: str,
        html: str,
        status_code: int,
        headers: Dict[str, str],
        url_hash: str,
    ) -> Optional[str]:
        """Compress and upload raw HTML to S3. Returns S3 key or None on failure."""
        try:
            from app.integrations.s3 import s3_service
            payload = {
                "url": url,
                "status_code": status_code,
                "headers": dict(headers),
                "html": html,
                "fetched_at": datetime.utcnow().isoformat(),
            }
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            compressed = gzip.compress(raw, compresslevel=6)
            key = self._build_key(organization_id, job_id, url_hash)
            await s3_service.upload(compressed, key, content_type="application/gzip")
            logger.debug("raw_html_stored", key=key, original_bytes=len(raw), compressed_bytes=len(compressed))
            return key
        except Exception as e:
            logger.warning("raw_html_storage_failed", url=url, error=str(e))
            return None

    async def retrieve(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """Download and decompress raw HTML from S3."""
        try:
            from app.integrations.s3 import s3_service
            # Use boto3 directly for download
            import boto3
            from app.core.config import settings
            client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
            obj = client.get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
            compressed = obj["Body"].read()
            raw = gzip.decompress(compressed)
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            logger.error("raw_html_retrieve_failed", key=s3_key, error=str(e))
            return None


raw_html_storage = RawHTMLStorage()
