import json
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from .graph_chat import graph
from .model.storage import ensure_thread, save_message
from .schemas import ChatStreamRequest


router = APIRouter(prefix="/api/chat", tags=["chat"])


def make_sse_event(event_name: str, data: dict) -> str:
    """把普通 dict 包装成浏览器能识别的 SSE 文本格式。
    前端识别event，获取data数据，一个dict
    """
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_name}\ndata: {json_data}\n\n"


def get_text_from_message_chunk(chunk: object) -> str:
    """从 LangChain 返回的消息 chunk 里取出文本。"""
    content = getattr(chunk, "content", "")

    if content is None:
        return ""

    if isinstance(content, str):
        return content

    return str(content)


def get_text_from_graph_event(event: dict) -> str:
    """把 LangGraph 事件转换成要发给前端的文本片段。"""
    event_type = event.get("event")

    if event_type == "on_chat_model_stream":
        chunk = event.get("data", {}).get("chunk")
        return get_text_from_message_chunk(chunk)

    if event_type == "on_chain_stream" and event.get("name") == "chat":
        data = event.get("data", {})
        chunk = data.get("chunk", {})

        if not isinstance(chunk, dict):
            return ""

        messages = chunk.get("messages", [])
        if not messages:
            return ""

        return get_text_from_message_chunk(messages[-1])

    return ""


async def chat_event_stream(request: ChatStreamRequest) -> AsyncIterator[str]:
    """执行 graph，并把 graph 事件持续转换成 SSE 事件。"""
    is_new_thread = request.thread_id is None
    thread_id = request.thread_id or str(uuid4())
    final_answer = ""
    has_token_stream = False

    yield make_sse_event("metadata", {"thread_id": thread_id})

    try:
        title = request.message[:50] if is_new_thread else None
        ensure_thread(thread_id, title=title)
        save_message(thread_id, "user", request.message)

        async for graph_event in graph.astream_events(
            {"messages": [HumanMessage(content=request.message)]},
            config={"configurable": {"thread_id": thread_id}},
            version="v2",
        ):
            event_type = graph_event.get("event")

            if event_type == "on_chat_model_stream":
                has_token_stream = True

            if event_type == "on_chain_stream" and has_token_stream:
                continue

            text = get_text_from_graph_event(graph_event)
            if not text:
                continue

            final_answer += text
            yield make_sse_event("token", {"content": text})

        if final_answer:
            save_message(thread_id, "assistant", final_answer)

        yield make_sse_event("message", {"content": final_answer})
        yield make_sse_event("end", {"thread_id": thread_id})
    except Exception as exc:
        yield make_sse_event("error", {"message": str(exc)})
        yield make_sse_event("end", {"thread_id": thread_id})


@router.post("/stream")
async def stream_chat(request: ChatStreamRequest) -> StreamingResponse:
    """POST /api/chat/stream：返回 text/event-stream。"""
    event_iterator = chat_event_stream(request)

    return StreamingResponse(
        event_iterator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
