from __future__ import annotations

import sys
import time
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import HumanMessage

from .models import AgentTrace, BFCLCase
from .tool_factory import make_stub_tools
from .trace import text_from_graph_event


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.graph_react import create_react_graph  # noqa: E402


async def run_case(case: BFCLCase, recursion_limit: int) -> AgentTrace:
    tools, recorder = make_stub_tools(case.functions)
    graph = create_react_graph(tools)
    thread_id = f"eval-{case.id}-{uuid4()}"
    final_answer = ""
    started_at = time.perf_counter()
    error = None

    try:
        async for event in graph.astream_events(
            {"messages": [HumanMessage(content=case.user_text)]},
            config={
                "configurable": {"thread_id": thread_id},
                "recursion_limit": recursion_limit,
            },
            version="v2",
        ):
            text = text_from_graph_event(event)
            if text:
                final_answer += text
    except Exception as exc:
        error = str(exc)

    latency = time.perf_counter() - started_at
    return AgentTrace(
        case_id=case.id,
        category=case.category,
        final_answer=final_answer,
        tool_calls=recorder.calls,
        latency_seconds=latency,
        error=error,
    )
