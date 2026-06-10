from dataclasses import dataclass

from fastapi import FastAPI

from .agent import ChatStrategy
from .graph_chat import graph as chat_graph
from .graph_react import create_react_graph
from .graph_plan_solve import create_plan_solve_graph
from .mcp import McpToolProvider
from .config import get_settings


@dataclass
class AppServices:
    mcp_provider: McpToolProvider
    chat_strategy: ChatStrategy


async def build_app_services() -> AppServices:
    settings = get_settings()
    mcp_provider = McpToolProvider(settings)
    await mcp_provider.initialize()

    tools = mcp_provider.get_tool_callables()
    chat_strategy = ChatStrategy(
        chat_graph=chat_graph,
        react_graph=create_react_graph(tools),
        plan_solve_graph=create_plan_solve_graph(tools),
    )
    return AppServices(
        mcp_provider=mcp_provider,
        chat_strategy=chat_strategy,
    )


def get_app_services(app: FastAPI) -> AppServices:
    services = getattr(app.state, "services", None)
    if services is None:
        raise RuntimeError("Application services are not initialized.")
    return services
