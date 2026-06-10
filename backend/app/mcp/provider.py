import logging
import asyncio
import os
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from ..config import Settings
from .config import (
    McpServerConfig,
    McpSettingsFile,
    McpSource,
    McpHttpServerConfig,
    McpStdioServerConfig,
    McpToolMetadata,
)


logger = logging.getLogger(__name__)

LOCAL_MCP_SERVER_NAME = "local"
ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def create_mcp_http_client(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    kwargs = {
        "follow_redirects": True,
        "trust_env": False,
    }
    if headers is not None:
        kwargs["headers"] = headers
    if timeout is not None:
        kwargs["timeout"] = timeout
    if auth is not None:
        kwargs["auth"] = auth
    return httpx.AsyncClient(**kwargs)


class McpToolProvider:
    def __init__(self, settings: Settings):
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        self.settings = settings
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: list[BaseTool] = []
        self.tool_metadata: list[McpToolMetadata] = []

    async def initialize(self) -> None:
        discovered_tools: list[BaseTool] = []
        discovered_metadata: list[McpToolMetadata] = []
        available_connections = {}
        seen_tool_names: set[str] = set()

        server_configs = self._load_server_configs()

        for config in server_configs:
            if not config.enabled:
                continue

            source = self._get_source(config)
            try:
                connection = self._to_connection_dict(config)
                candidate_client = MultiServerMCPClient({config.name: connection})
                raw_tools, langchain_tools = await self._load_server_tools(
                    candidate_client,
                    config,
                )
                langchain_tools = [
                    self._wrap_tool_errors(tool) for tool in langchain_tools
                ]
                tool_names = [tool.name for tool in raw_tools]
                duplicate_names = [
                    tool_name for tool_name in tool_names if tool_name in seen_tool_names
                ]
                if duplicate_names:
                    raise RuntimeError(
                        f"duplicate MCP tool names found on server '{config.name}': "
                        f"{', '.join(duplicate_names)}"
                    )

            except Exception as exc:
                if source == "local_mcp":
                    raise RuntimeError(
                        f"failed to initialize required local MCP server '{config.name}'"
                    ) from exc

                logger.warning(
                    "Skipping MCP server '%s' because it could not be loaded: %s",
                    config.name,
                    self._safe_error_message(exc),
                )
                continue

            available_connections[config.name] = connection
            discovered_tools.extend(langchain_tools)
            for tool in raw_tools:
                discovered_metadata.append(
                    McpToolMetadata(
                        name=tool.name,
                        description=tool.description or "",
                        args_schema=tool.inputSchema or {},
                        source=source,
                        server_name=config.name,
                        transport=config.transport,
                    )
                )
                seen_tool_names.add(tool.name)

        self.client = MultiServerMCPClient(available_connections)
        self.tools = discovered_tools
        self.tool_metadata = sorted(discovered_metadata, key=lambda item: item.name)

    def get_tool_callables(
        self,
        enabled_names: Optional[list[str]] = None,
    ) -> list[BaseTool]:
        if not enabled_names:
            return list(self.tools)

        enabled_set = set(enabled_names)
        return [tool for tool in self.tools if tool.name in enabled_set]

    def list_tools(self, enabled_names: Optional[list[str]] = None) -> list[dict]:
        metadata = self.tool_metadata
        if enabled_names:
            enabled_set = set(enabled_names)
            metadata = [item for item in metadata if item.name in enabled_set]
        return [item.model_dump() for item in metadata]

    def _load_server_configs(self) -> list[McpServerConfig]:
        config_path = Path(self.settings.mcp_config_path)
        config_file = McpSettingsFile.load(config_path)
        configs = [self._build_local_server_config(), *config_file.servers]
        seen_names = set()
        for config in configs:
            if config.name in seen_names:
                raise RuntimeError(f"duplicate MCP server name: {config.name}")
            seen_names.add(config.name)
        return configs

    def _build_local_server_config(self) -> McpStdioServerConfig:
        backend_dir = Path(__file__).resolve().parents[2]
        return McpStdioServerConfig(
            name=LOCAL_MCP_SERVER_NAME,
            command=sys.executable,
            args=["-m", "app.mcp.local_server"],
            cwd=str(backend_dir),
        )

    async def _load_server_tools(
        self,
        client: MultiServerMCPClient,
        config: McpServerConfig,
    ) -> tuple[list, list[BaseTool]]:
        attempts = self._get_retry_attempts(config)
        last_exc: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            try:
                raw_tools = await self._list_server_tools(client, config.name)
                langchain_tools = await client.get_tools(server_name=config.name)
                return raw_tools, langchain_tools
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts:
                    break

                logger.warning(
                    "Retrying MCP server '%s' initialization after error "
                    "(attempt %s/%s): %s",
                    config.name,
                    attempt,
                    attempts,
                    self._safe_error_message(exc),
                )
                await asyncio.sleep(min(2 ** (attempt - 1), 5))

        assert last_exc is not None
        raise last_exc

    async def _list_server_tools(
        self,
        client: MultiServerMCPClient,
        server_name: str,
    ) -> list:
        all_tools = []
        async with client.session(server_name) as session:
            current_cursor = None
            while True:
                result = await session.list_tools(cursor=current_cursor)
                all_tools.extend(result.tools or [])
                if not result.nextCursor:
                    break
                current_cursor = result.nextCursor
        return all_tools

    def _get_source(self, config: McpServerConfig) -> McpSource:
        if config.name == LOCAL_MCP_SERVER_NAME:
            return "local_mcp"
        return "external_mcp"

    def _to_connection_dict(self, config: McpServerConfig) -> dict:
        data = config.model_dump(
            exclude={
                "enabled",
                "name",
                "timeout_seconds",
                "sse_read_timeout_seconds",
                "retry_attempts",
            }
        )
        data = self._expand_env_vars(data)
        if config.transport == "http":
            data["transport"] = "http"
            if isinstance(config, McpHttpServerConfig):
                data["timeout"] = timedelta(seconds=config.timeout_seconds)
                data["sse_read_timeout"] = timedelta(
                    seconds=config.sse_read_timeout_seconds
                )
                data["httpx_client_factory"] = create_mcp_http_client
        return data

    def _get_retry_attempts(self, config: McpServerConfig) -> int:
        if isinstance(config, McpHttpServerConfig):
            return max(1, config.retry_attempts)
        return 1

    def _wrap_tool_errors(self, tool: BaseTool) -> BaseTool:
        async def safe_tool(**kwargs):
            try:
                return await tool.ainvoke(kwargs)
            except Exception as exc:
                logger.exception("MCP tool '%s' failed", tool.name)
                return f"{tool.name} error: {self._safe_error_message(exc)}"

        safe_tool.__name__ = f"safe_{tool.name}"
        return StructuredTool.from_function(
            coroutine=safe_tool,
            name=tool.name,
            description=tool.description or "",
            args_schema=getattr(tool, "args_schema", None),
        )

    def _expand_env_vars(self, value):
        if isinstance(value, str):
            return ENV_VAR_PATTERN.sub(
                lambda match: self._get_required_env_var(match.group(1)),
                value,
            )
        if isinstance(value, dict):
            return {key: self._expand_env_vars(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._expand_env_vars(item) for item in value]
        return value

    def _get_required_env_var(self, name: str) -> str:
        value = os.environ.get(name)
        if value is None:
            raise RuntimeError(f"environment variable {name} is not set")
        return value

    def _safe_error_message(self, exc: Exception) -> str:
        message = str(exc)
        message = re.sub(r"tavilyApiKey=[^\s&)\]}']+", "tavilyApiKey=<redacted>", message)
        message = re.sub(
            r"Authorization['\"]?:\s*['\"]?Bearer\s+[^,'\"\s}]+",
            "Authorization: Bearer <redacted>",
            message,
        )
        return message
