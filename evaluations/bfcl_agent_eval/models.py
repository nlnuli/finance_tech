from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExpectedCall:
    name: str
    arguments: dict[str, list[Any]]


@dataclass(frozen=True)
class BFCLCase:
    id: str
    category: str
    messages: list[dict[str, str]]
    functions: list[dict[str, Any]]
    expected_calls: list[ExpectedCall]

    @property
    def user_text(self) -> str:
        return "\n".join(
            message.get("content", "")
            for message in self.messages
            if message.get("role") == "user"
        ).strip()


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    output: str | None = None
    error: str | None = None


@dataclass
class AgentTrace:
    case_id: str
    category: str
    final_answer: str = ""
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    latency_seconds: float = 0.0
    error: str | None = None


@dataclass
class CaseScore:
    id: str
    category: str
    exact_match: bool
    call_count_correct: bool
    tool_name_accuracy: float
    argument_key_accuracy: float
    argument_value_accuracy: float
    no_call_correct: bool | None
    expected_calls: list[dict[str, Any]]
    actual_calls: list[dict[str, Any]]
    final_answer: str
    latency_seconds: float
    error: str | None
