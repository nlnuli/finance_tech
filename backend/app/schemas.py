from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateThreadRequest(BaseModel):
    title: Optional[str] = None


class ThreadResponse(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: int
    thread_id: str
    role: str
    content: str
    created_at: datetime


class FileResponse(BaseModel):
    id: int
    assistant_id: str
    original_name: str
    saved_name: str
    file_path: str
    content_type: Optional[str] = None
    size_bytes: int
    created_at: datetime


class ChunkResponse(BaseModel):
    content: str
    metadata: dict


class FileUploadResponse(BaseModel):
    file: FileResponse
    chunks: list[ChunkResponse]


class ChatStreamRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: Optional[str] = None
    rag_enabled: bool = False
