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


class ChatStreamRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: Optional[str] = None
