from typing import Optional

from .tool import get_all_tools


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, tool) -> None:
        self.tools[tool.name] = {
            "type": "langchain_tool",
            "name": tool.name,
            "description": tool.description,
            "args_schema": tool.args,
            "callable": tool,
        }

    def register_many(self, tools: list) -> None:
        for tool in tools:
            self.register(tool)

    def get_enabled_tools(self, enabled_names: Optional[list[str]] = None) -> list[dict]:
        if not enabled_names:
            return list(self.tools.values())

        enabled = []
        for name in enabled_names:
            tool_config = self.tools.get(name)
            if tool_config:
                enabled.append(tool_config)

        return enabled

    def get_tool_callables(self, enabled_names: Optional[list[str]] = None) -> list:
        return [
            tool_config["callable"]
            for tool_config in self.get_enabled_tools(enabled_names)
        ]

    def serialize_tool(self, tool_config: dict) -> dict:
        return {
            "type": tool_config["type"],
            "name": tool_config["name"],
            "description": tool_config["description"],
            "args_schema": tool_config["args_schema"],
        }

    def list_tools(self, enabled_names: Optional[list[str]] = None) -> list[dict]:
        return [
            self.serialize_tool(tool_config)
            for tool_config in self.get_enabled_tools(enabled_names)
        ]


def create_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_many(get_all_tools())
    return registry


TOOL_REGISTRY_MANAGER = create_default_tool_registry()

TOOL_REGISTRY = TOOL_REGISTRY_MANAGER.tools


def get_enabled_tools(enabled_names: Optional[list[str]] = None) -> list[dict]:
    return TOOL_REGISTRY_MANAGER.get_enabled_tools(enabled_names)


def get_tool_callables(enabled_names: Optional[list[str]] = None) -> list:
    return TOOL_REGISTRY_MANAGER.get_tool_callables(enabled_names)


def serialize_tool(tool_config: dict) -> dict:
    return TOOL_REGISTRY_MANAGER.serialize_tool(tool_config)


def list_registered_tools(enabled_names: Optional[list[str]] = None) -> list[dict]:
    return TOOL_REGISTRY_MANAGER.list_tools(enabled_names)
