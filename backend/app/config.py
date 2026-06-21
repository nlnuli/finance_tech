from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_MCP_CONFIG_PATH = Path(__file__).resolve().parents[1] / "mcp_servers.json"
DEFAULT_MEMORY_DIR = Path(__file__).resolve().parents[1] / "memory"


class Settings(BaseSettings):
    app_name: str = "Finance Tech API"
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="APP_DEBUG")
    cors_origins: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
        alias="CORS_ORIGINS",
    )
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_official_api_key: Optional[str] = Field(
        default=None,
        alias="OPENAI_OFFICIAL_API_KEY",
    )
    qdrant_url: Optional[str] = Field(default=None, alias="QDRANT_URL")
    qdrant_api_key: Optional[str] = Field(default=None, alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(
        default="finance_tech_chunks",
        alias="QDRANT_COLLECTION",
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="OPENAI_EMBEDDING_MODEL",
    )
    openai_embedding_api_key: Optional[str] = Field(
        default=None,
        alias="OPENAI_EMBEDDING_API_KEY",
    )
    openai_embedding_base_url: Optional[str] = Field(
        default=None,
        alias="OPENAI_EMBEDDING_BASE_URL",
    )
    mcp_config_path: str = Field(
        default=str(DEFAULT_MCP_CONFIG_PATH),
        alias="MCP_CONFIG_PATH",
    )
    memory_enabled: bool = Field(default=True, alias="MEMORY_ENABLED")
    memory_dir: str = Field(default=str(DEFAULT_MEMORY_DIR), alias="MEMORY_DIR")
    memory_default_user_id: str = Field(
        default="default",
        alias="MEMORY_DEFAULT_USER_ID",
    )
    memory_auto_trigger_message_count: int = Field(
        default=10,
        alias="MEMORY_AUTO_TRIGGER_MESSAGE_COUNT",
    )
    memory_index_max_lines: int = Field(
        default=200,
        alias="MEMORY_INDEX_MAX_LINES",
    )
    memory_index_max_bytes: int = Field(
        default=25600,
        alias="MEMORY_INDEX_MAX_BYTES",
    )

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
