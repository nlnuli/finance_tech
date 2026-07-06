from __future__ import annotations

import sys
import time
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool

from .models import AgentTrace, RagasCase, RetrievedContext, ToolCallRecord
from .retriever_runner import format_contexts, run_retrieval
from .trace import text_from_graph_event


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.graph_react import create_react_graph  # noqa: E402


class RagToolRecorder:
    def __init__(self):
        self.calls: list[ToolCallRecord] = []
        self.contexts: list[RetrievedContext] = []

    def append_contexts(self, contexts: list[RetrievedContext]) -> None:
        known_ids = {context.id for context in self.contexts}
        for context in contexts:
            if context.id not in known_ids:
                self.contexts.append(context)
                known_ids.add(context.id)


def make_eval_rag_tool(
    recorder: RagToolRecorder,
    assistant_id: str,
    retrieval_k: int,
) -> StructuredTool:
    async def rag_search(query: str) -> str:
        try:
            contexts = run_retrieval(
                query=query,
                assistant_id=assistant_id,
                retrieval_k=retrieval_k,
            )
            recorder.append_contexts(contexts)
            output = format_contexts(contexts)
            recorder.calls.append(
                ToolCallRecord(
                    name="rag_search",
                    arguments={"query": query},
                    output=output,
                )
            )
            return output
        except Exception as exc:
            message = f"rag_search error: {exc}"
            recorder.calls.append(
                ToolCallRecord(
                    name="rag_search",
                    arguments={"query": query},
                    error=str(exc),
                    output=message,
                )
            )
            return message

    return StructuredTool.from_function(
        coroutine=rag_search,
        name="rag_search",
        description=(
            "Search uploaded documents in the project Qdrant vector store. "
            "Use it for questions that require information from uploaded files."
        ),
    )


async def run_case(
    case: RagasCase,
    assistant_id: str,
    retrieval_k: int,
    recursion_limit: int,
) -> AgentTrace:
    recorder = RagToolRecorder()
    graph = create_react_graph(
        [
            make_eval_rag_tool(
                recorder=recorder,
                assistant_id=assistant_id,
                retrieval_k=retrieval_k,
            )
        ]
    )
    thread_id = f"ragas-eval-{case.id}-{uuid4()}"
    started_at = time.perf_counter()
    stream_answer = ""
    final_answer = ""
    error = None

    try:
        async for event in graph.astream_events(
            {"messages": [HumanMessage(content=case.question)]},
            config={
                "configurable": {"thread_id": thread_id},
                "recursion_limit": recursion_limit,
            },
            version="v2",
        ):
            text, is_final = text_from_graph_event(event)
            if not text:
                continue
            if is_final:
                final_answer = text
            else:
                stream_answer += text
    except Exception as exc:
        error = str(exc)

    latency = time.perf_counter() - started_at
    return AgentTrace(
        case_id=case.id,
        final_answer=final_answer or stream_answer,
        tool_calls=recorder.calls,
        retrieved_contexts=recorder.contexts,
        latency_seconds=latency,
        error=error,
    )
