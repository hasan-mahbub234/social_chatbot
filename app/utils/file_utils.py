"""File utilities."""
import os
import hashlib
from typing import Optional
from app.core.constants import ALLOWED_FILE_TYPES, MAX_FILE_SIZE_MB


def get_file_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower().lstrip(".")


def is_allowed_file_type(content_type: str) -> bool:
    return content_type in ALLOWED_FILE_TYPES


def is_within_size_limit(size_bytes: int) -> bool:
    return size_bytes <= MAX_FILE_SIZE_MB * 1024 * 1024


def compute_file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_filename(filename: str) -> str:
    """Remove unsafe characters from filename."""
    import re
    name = os.path.basename(filename)
    name = re.sub(r"[^\w\s\-.]", "", name)
    return name[:255]


def build_storage_path(organization_id: str, file_id: str, filename: str, prefix: str = "uploads") -> str:
    ext = get_file_extension(filename)
    return f"{prefix}/{organization_id}/{file_id}.{ext}"
