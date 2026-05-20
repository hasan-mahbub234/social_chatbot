"""Upload schemas."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class UploadResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    file_size: int
    storage_path: str
    s3_url: Optional[str] = None
    is_indexed: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UploadedFileResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    file_size: int
    is_indexed: bool
    processed_chunks: int
    created_at: datetime

    class Config:
        from_attributes = True


class FileIndexRequest(BaseModel):
    file_id: UUID
    agent_id: Optional[UUID] = None
    chunk_size: int = 1000
    chunk_overlap: int = 200
