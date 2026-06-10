from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import BaseMessage

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


def ensure_thread_exists(thread_id: str) -> None:
    thread = storage.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")


@router.post("", response_model=ThreadResponse)
def create_thread(request: CreateThreadRequest) -> dict:
    return storage.create_thread(title=request.title)


@router.get("", response_model=list[ThreadResponse])
def list_threads() -> list[dict]:
    return storage.list_threads()


@router.get("/{thread_id}/messages", response_model=list[MessageResponse])
def list_thread_messages(thread_id: str) -> list[dict]:
    ensure_thread_exists(thread_id)

    return storage.list_messages(thread_id)


@router.get("/{thread_id}/state")
async def get_thread_state(request: Request, thread_id: str) -> dict:
    ensure_thread_exists(thread_id)

    plan_solve_graph = get_app_services(request.app).chat_strategy.plan_solve_graph
    state = await plan_solve_graph.aget_state(get_graph_config(thread_id))
    return serialize_state(state)


@router.get("/{thread_id}/history")
async def get_thread_history(request: Request, thread_id: str) -> list[dict]:
    ensure_thread_exists(thread_id)

    plan_solve_graph = get_app_services(request.app).chat_strategy.plan_solve_graph
    history = []
    async for state in plan_solve_graph.aget_state_history(get_graph_config(thread_id)):
        history.append(serialize_state(state))

    return history
