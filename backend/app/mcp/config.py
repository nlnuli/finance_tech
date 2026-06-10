import json
from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


McpTransport = Literal["stdio", "http"]
McpSource = Literal["local_mcp", "external_mcp"]


class McpBaseServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    transport: McpTransport
    enabled: bool = True


class McpStdioServerConfig(McpBaseServerConfig):
    transport: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: Optional[dict[str, str]] = None
    cwd: Optional[str] = None


class McpHttpServerConfig(McpBaseServerConfig):
    transport: Literal["http"] = "http"
    url: str
    headers: Optional[dict[str, str]] = None
    timeout_seconds: float = 30
    sse_read_timeout_seconds: float = 300
    retry_attempts: int = 3


McpServerConfig = Union[McpStdioServerConfig, McpHttpServerConfig]


class McpSettingsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    servers: list[McpServerConfig] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "McpSettingsFile":
        if not path.exists():
            return cls()

        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            data = {"servers": data}
        return cls.model_validate(data)


class McpToolMetadata(BaseModel):
    type: Literal["mcp_tool"] = "mcp_tool"
    name: str
    description: str = ""
    args_schema: dict = Field(default_factory=dict)
    source: McpSource
    server_name: str
    transport: McpTransport
