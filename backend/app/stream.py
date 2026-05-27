import json
from collections.abc import AsyncIterator
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .agent import ChatStrategy
from .model.storage import ensure_thread, save_message
from .schemas import ChatStreamRequest


router = APIRouter(prefix="/api/chat", tags=["chat"])
chat_strategy = ChatStrategy()


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


def to_sse_text(value: object) -> str:
    """把工具输入/输出转换成可以放进 SSE JSON 里的文本。"""
    if value is None:
        return ""

    content = getattr(value, "content", None)
    if content is not None:
        return to_sse_text(content)

    if isinstance(value, str):
        return value

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


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

    if event_type == "on_chain_stream" and event.get("name") == "LangGraph":
        data = event.get("data", {})
        chunk = data.get("chunk", {})

        if not isinstance(chunk, dict):
            return ""

        messages = chunk.get("messages", [])
        if not messages:
            return ""

        return get_text_from_message_chunk(messages[-1])

    return ""


def is_plan_solve_solver_event(event: dict) -> bool:
    metadata = event.get("metadata", {})
    return metadata.get("langgraph_node") == "solver"


def get_langgraph_node(event: dict) -> str:
    metadata = event.get("metadata", {})
    return metadata.get("langgraph_node", "")


def get_event_payload(event: dict) -> dict:
    data = event.get("data", {})
    payload = data.get("output") or data.get("chunk") or data.get("input") or {}

    if isinstance(payload, dict):
        return payload

    return {}


def get_nested_payload(payload: dict, node_name: str) -> dict:
    nested_payload = payload.get(node_name)

    if isinstance(nested_payload, dict):
        return nested_payload

    return payload


def get_plan_from_event(event: dict) -> list[str]:
    payload = get_nested_payload(get_event_payload(event), "planner")
    plan = payload.get("plan")

    if isinstance(plan, list):
        return [str(step) for step in plan]

    return []


def get_step_start_from_event(event: dict) -> Optional[dict]:
    payload = get_nested_payload(get_event_payload(event), "executor")
    plan = payload.get("plan", [])
    step_index = payload.get("current_step", 0)

    if not isinstance(plan, list) or not isinstance(step_index, int):
        return None

    if step_index >= len(plan):
        return None

    return {
        "step_index": step_index,
        "step": str(plan[step_index]),
    }


def get_step_result_from_event(event: dict) -> Optional[dict]:
    payload = get_nested_payload(get_event_payload(event), "executor")
    current_step = payload.get("current_step")
    observations = payload.get("observations", [])

    if not isinstance(current_step, int) or not isinstance(observations, list):
        return None

    if current_step <= 0 or not observations:
        return None

    return {
        "step_index": current_step - 1,
        "result": str(observations[-1]),
    }


async def chat_event_stream(request: ChatStreamRequest) -> AsyncIterator[str]:
    """执行 graph，并把 graph 事件持续转换成 SSE 事件。"""
    is_new_thread = request.thread_id is None
    thread_id = request.thread_id or str(uuid4())
    final_answer = ""
    has_token_stream = False
    sent_plan = False
    started_step_indexes = set()
    finished_step_indexes = set()

    yield make_sse_event("metadata", {"thread_id": thread_id})

    try:
        title = request.message[:50] if is_new_thread else None
        ensure_thread(thread_id, title=title)
        save_message(thread_id, "user", request.message)
        graph, graph_input, graph_name = chat_strategy.select_graph_input(request.message)

        async for graph_event in graph.astream_events(
            graph_input,
            config={"configurable": {"thread_id": thread_id}},
            version="v2",
        ):
            event_type = graph_event.get("event")

            if graph_name == "plan_solve":
                node_name = get_langgraph_node(graph_event)

                if node_name == "planner" and not sent_plan:
                    plan = get_plan_from_event(graph_event)
                    if plan:
                        sent_plan = True
                        yield make_sse_event("plan", {"steps": plan})

                if node_name == "executor" and event_type == "on_chain_start":
                    step_start = get_step_start_from_event(graph_event)
                    if step_start and step_start["step_index"] not in started_step_indexes:
                        started_step_indexes.add(step_start["step_index"])
                        yield make_sse_event("step_start", step_start)

                if node_name == "executor" and event_type in {
                    "on_chain_stream",
                    "on_chain_end",
                }:
                    step_result = get_step_result_from_event(graph_event)
                    if step_result and step_result["step_index"] not in finished_step_indexes:
                        finished_step_indexes.add(step_result["step_index"])
                        yield make_sse_event("step_result", step_result)

                if event_type == "on_chat_model_stream":
                    if not is_plan_solve_solver_event(graph_event):
                        continue
                    has_token_stream = True
                elif event_type == "on_chain_stream":
                    continue

            if event_type == "on_chat_model_stream":
                has_token_stream = True

            if event_type == "on_tool_start":
                data = graph_event.get("data", {})
                yield make_sse_event(
                    "tool_start",
                    {
                        "tool": graph_event.get("name", ""),
                        "input": to_sse_text(data.get("input")),
                    },
                )
                continue

            if event_type == "on_tool_end":
                data = graph_event.get("data", {})
                yield make_sse_event(
                    "tool_result",
                    {
                        "tool": graph_event.get("name", ""),
                        "output": to_sse_text(data.get("output")),
                    },
                )
                continue

            if event_type == "on_tool_error":
                data = graph_event.get("data", {})
                yield make_sse_event(
                    "tool_result",
                    {
                        "tool": graph_event.get("name", ""),
                        "output": to_sse_text(data.get("error")),
                    },
                )
                continue

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
