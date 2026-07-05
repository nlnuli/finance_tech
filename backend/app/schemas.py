from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateThreadRequest(BaseModel):
    title: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class AuthRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    display_name: Optional[str] = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ThreadResponse(BaseModel):
    id: str
    user_id: str
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
    user_id: str
    assistant_id: str
    original_name: str
    saved_name: str
    file_path: str
    content_type: Optional[str] = None
    size_bytes: int
    status: str = "ready"
    page_count: Optional[int] = None
    chunk_count: int = 0
    artifact_dir: Optional[str] = None
    processing_error: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ChunkResponse(BaseModel):
    content: str
    metadata: dict


class ProcessingSummaryResponse(BaseModel):
    status: str
    page_count: int
    chunk_count: int
    text_block_count: int = 0
    table_count: int = 0
    physical_table_count: int = 0
    logical_table_count: int = 0
    stitched_table_count: int = 0
    form_field_count: int = 0
    fusion_warning_count: int = 0
    duration_seconds: float = 0.0
    ocr_processor_id: Optional[str] = None
    form_processor_id: Optional[str] = None
    artifacts: dict[str, str] = Field(default_factory=dict)


class FileUploadResponse(BaseModel):
    file: FileResponse
    chunks: list[ChunkResponse]
    processing_summary: ProcessingSummaryResponse


class ChatStreamRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: Optional[str] = None
    rag_enabled: bool = False
    mode: Literal["chat", "react", "plan_solve"] = "react"
