from __future__ import annotations

from typing import Any


def extract_text(value: Any) -> str:
    if value is None:
        return ""

    content = getattr(value, "content", None)
    if content is not None:
        return extract_text(content)

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return "".join(extract_text(item) for item in value)

    if isinstance(value, dict):
        messages = value.get("messages")
        if messages:
            return extract_text(messages[-1])
        return ""

    return str(value)


def text_from_graph_event(event: dict[str, Any]) -> tuple[str, bool]:
    event_type = event.get("event")
    if event_type == "on_chat_model_stream":
        return extract_text(event.get("data", {}).get("chunk")), False

    if event_type == "on_chain_end":
        output = event.get("data", {}).get("output")
        if isinstance(output, dict) and "messages" in output:
            return extract_text(output["messages"][-1]), True

    return "", False
