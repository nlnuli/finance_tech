from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from .service import get_memory_store


router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
def get_memory_index(
    user: dict = Depends(current_user),
) -> dict:
    return get_memory_store().get_index_response(user["id"])


@router.get("/topic/{topic_name}")
def get_memory_topic(
    topic_name: str,
    user: dict = Depends(current_user),
) -> dict:
    try:
        return get_memory_store().get_topic_response(topic_name, user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/compact")
def compact_memory(
    user: dict = Depends(current_user),
) -> dict:
    result = get_memory_store().compact(user["id"])
    return {
        "user_id": get_memory_store().user_id(user["id"]),
        "result": result,
    }
