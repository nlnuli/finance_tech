from fastapi import APIRouter, HTTPException

from .model import storage
from .schemas import CreateThreadRequest, MessageResponse, ThreadResponse


router = APIRouter(prefix="/api/threads", tags=["threads"])


@router.post("", response_model=ThreadResponse)
def create_thread(request: CreateThreadRequest) -> dict:
    return storage.create_thread(title=request.title)


@router.get("", response_model=list[ThreadResponse])
def list_threads() -> list[dict]:
    return storage.list_threads()


@router.get("/{thread_id}/messages", response_model=list[MessageResponse])
def list_thread_messages(thread_id: str) -> list[dict]:
    thread = storage.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    return storage.list_messages(thread_id)
