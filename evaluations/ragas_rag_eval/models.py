from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RagasCase:
    id: str
    question: str
    reference: str
    reference_contexts: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedContext:
    id: str
    content: str
    filename: str | None = None
    file_id: int | str | None = None
    chunk_index: int | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    output: str | None = None
    error: str | None = None


@dataclass
class AgentTrace:
    case_id: str
    final_answer: str = ""
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    retrieved_contexts: list[RetrievedContext] = field(default_factory=list)
    latency_seconds: float = 0.0
    error: str | None = None
    timed_out: bool = False


@dataclass
class CaseScore:
    id: str
    question: str
    reference: str
    response: str
    source_files: list[str]
    retrieved_contexts: list[dict[str, Any]]
    direct_retrieved_contexts: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    ragas_metrics: dict[str, float | None]
    custom_metrics: dict[str, float | bool | int | None]
    latency_seconds: float
    error: str | None = None
    timed_out: bool = False
