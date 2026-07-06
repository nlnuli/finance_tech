from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.messages import BaseMessage

from .auth import current_user
from .model import storage
from .runtime import get_app_services
from .schemas import CreateThreadRequest, MessageResponse, ThreadResponse


router = APIRouter(prefix="/api/threads", tags=["threads"])


def get_graph_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def serialize_message(message: BaseMessage) -> dict:
    return {
        "type": message.type,
        "content": message.content,
    }


def serialize_values(values: dict) -> dict:
    result = {}

    for key, value in values.items():
        if key == "messages":
            result[key] = [serialize_message(message) for message in value]
        else:
            result[key] = value

    return result


def serialize_state(state) -> dict:
    return {
        "values": serialize_values(state.values or {}),
        "next": list(state.next or []),
        "metadata": state.metadata,
    }


def ensure_thread_exists(user_id: str, thread_id: str) -> None:
    thread = storage.get_thread(user_id, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")


@router.post("", response_model=ThreadResponse)
def create_thread(request: CreateThreadRequest, user: dict = Depends(current_user)) -> dict:
    return storage.create_thread(user["id"], title=request.title)


@router.get("", response_model=list[ThreadResponse])
def list_threads(user: dict = Depends(current_user)) -> list[dict]:
    return storage.list_threads(user["id"])


@router.get("/{thread_id}/messages", response_model=list[MessageResponse])
def list_thread_messages(
    thread_id: str,
    user: dict = Depends(current_user),
) -> list[dict]:
    ensure_thread_exists(user["id"], thread_id)

    return storage.list_messages(user["id"], thread_id)


@router.get("/{thread_id}/state")
async def get_thread_state(
    request: Request,
    thread_id: str,
    user: dict = Depends(current_user),
) -> dict:
    ensure_thread_exists(user["id"], thread_id)

    plan_solve_graph = get_app_services(request.app).chat_strategy.plan_solve_graph
    state = await plan_solve_graph.aget_state(get_graph_config(thread_id))
    return serialize_state(state)


@router.get("/{thread_id}/history")
async def get_thread_history(
    request: Request,
    thread_id: str,
    user: dict = Depends(current_user),
) -> list[dict]:
    ensure_thread_exists(user["id"], thread_id)

    plan_solve_graph = get_app_services(request.app).chat_strategy.plan_solve_graph
    history = []
    async for state in plan_solve_graph.aget_state_history(get_graph_config(thread_id)):
        history.append(serialize_state(state))

    return history
