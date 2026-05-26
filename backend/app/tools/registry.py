from typing import Optional

from .tool import rag_search


TOOL_REGISTRY = {
    rag_search.name: {
        "type": "langchain_tool",
        "name": rag_search.name,
        "description": rag_search.description,
        "args_schema": rag_search.args,
        "callable": rag_search,
    }
}


def get_enabled_tools(enabled_names: Optional[list[str]] = None) -> list[dict]:
    if not enabled_names:
        return list(TOOL_REGISTRY.values())

    enabled = []
    for name in enabled_names:
        tool_config = TOOL_REGISTRY.get(name)
        if tool_config:
            enabled.append(tool_config)

    return enabled


def serialize_tool(tool_config: dict) -> dict:
    return {
        "type": tool_config["type"],
        "name": tool_config["name"],
        "description": tool_config["description"],
        "args_schema": tool_config["args_schema"],
    }
