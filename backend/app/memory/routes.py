from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .service import get_memory_store


router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
def get_memory_index(
    user_id: Optional[str] = Query(default=None),
) -> dict:
    return get_memory_store().get_index_response(user_id)


@router.get("/topic/{topic_name}")
def get_memory_topic(
    topic_name: str,
    user_id: Optional[str] = Query(default=None),
) -> dict:
    try:
        return get_memory_store().get_topic_response(topic_name, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/compact")
def compact_memory(
    user_id: Optional[str] = Query(default=None),
) -> dict:
    result = get_memory_store().compact(user_id)
    return {
        "user_id": get_memory_store().user_id(user_id),
        "result": result,
    }
