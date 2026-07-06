from typing import Optional


class ToolRegistry:
    """兼容保留层。

    工具真实来源已经迁移到 MCP provider，这里只保留最小结构，
    避免旧代码导入时报错。
    """

    def __init__(self):
        self.tools = {}

    def register(self, tool) -> None:
        self.tools[getattr(tool, "name", str(tool))] = tool

    def register_many(self, tools: list) -> None:
        for tool in tools:
            self.register(tool)

    def get_enabled_tools(self, enabled_names: Optional[list[str]] = None) -> list[dict]:
        if not enabled_names:
            return list(self.tools.values())
        return [self.tools[name] for name in enabled_names if name in self.tools]

    def get_tool_callables(self, enabled_names: Optional[list[str]] = None) -> list:
        return self.get_enabled_tools(enabled_names)

    def serialize_tool(self, tool_config: dict) -> dict:
        return tool_config

    def list_tools(self, enabled_names: Optional[list[str]] = None) -> list[dict]:
        return self.get_enabled_tools(enabled_names)


def create_default_tool_registry() -> ToolRegistry:
    return ToolRegistry()


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
