from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_MCP_CONFIG_PATH = Path(__file__).resolve().parents[1] / "mcp_servers.json"
DEFAULT_MEMORY_DIR = Path(__file__).resolve().parents[1] / "memory"
DEFAULT_DOCUMENT_AI_ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "processed"


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
            "http://localhost:5174",
            "http://127.0.0.1:5174",
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
        default="finance_tech_chunks_hybrid_v1",
        alias="QDRANT_COLLECTION",
    )
    qdrant_cloud_inference: bool = Field(
        default=True,
        alias="QDRANT_CLOUD_INFERENCE",
    )
    qdrant_dense_vector_name: str = Field(
        default="dense",
        alias="QDRANT_DENSE_VECTOR_NAME",
    )
    qdrant_bm25_vector_name: str = Field(
        default="bm25",
        alias="QDRANT_BM25_VECTOR_NAME",
    )
    qdrant_bm25_model: str = Field(
        default="Qdrant/bm25",
        alias="QDRANT_BM25_MODEL",
    )
    qdrant_bm25_language: str = Field(
        default="none",
        alias="QDRANT_BM25_LANGUAGE",
    )
    qdrant_bm25_tokenizer: str = Field(
        default="multilingual",
        alias="QDRANT_BM25_TOKENIZER",
    )
    qdrant_upsert_batch_size: int = Field(
        default=64,
        ge=1,
        alias="QDRANT_UPSERT_BATCH_SIZE",
    )
    rag_dense_candidate_count: int = Field(
        default=20,
        ge=1,
        alias="RAG_DENSE_CANDIDATE_COUNT",
    )
    rag_bm25_candidate_count: int = Field(
        default=20,
        ge=1,
        alias="RAG_BM25_CANDIDATE_COUNT",
    )
    rag_final_count: int = Field(
        default=4,
        ge=1,
        alias="RAG_FINAL_COUNT",
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
    document_ai_enabled: bool = Field(default=True, alias="DOCUMENT_AI_ENABLED")
    document_ai_project_id: str = Field(
        default="30831977495",
        alias="DOCUMENT_AI_PROJECT_ID",
    )
    document_ai_location: str = Field(
        default="asia-southeast1",
        alias="DOCUMENT_AI_LOCATION",
    )
    document_ai_ocr_processor_id: str = Field(
        default="7773275039618e5e",
        alias="DOCUMENT_AI_OCR_PROCESSOR_ID",
    )
    document_ai_form_processor_id: str = Field(
        default="1153f6581c99d3f3",
        alias="DOCUMENT_AI_FORM_PROCESSOR_ID",
    )
    document_ai_page_batch_size: int = Field(
        default=15,
        ge=1,
        le=15,
        alias="DOCUMENT_AI_PAGE_BATCH_SIZE",
    )
    document_ai_batch_concurrency: int = Field(
        default=2,
        ge=1,
        alias="DOCUMENT_AI_BATCH_CONCURRENCY",
    )
    document_ai_call_timeout_seconds: float = Field(
        default=120,
        gt=0,
        alias="DOCUMENT_AI_CALL_TIMEOUT_SECONDS",
    )
    document_ai_total_timeout_seconds: float = Field(
        default=600,
        gt=0,
        alias="DOCUMENT_AI_TOTAL_TIMEOUT_SECONDS",
    )
    document_ai_max_pages: int = Field(
        default=200,
        ge=1,
        alias="DOCUMENT_AI_MAX_PAGES",
    )
    document_ai_max_file_bytes: int = Field(
        default=104857600,
        ge=1,
        alias="DOCUMENT_AI_MAX_FILE_BYTES",
    )
    document_ai_artifact_dir: str = Field(
        default=str(DEFAULT_DOCUMENT_AI_ARTIFACT_DIR),
        alias="DOCUMENT_AI_ARTIFACT_DIR",
    )
    table_stitching_enabled: bool = Field(
        default=True,
        alias="TABLE_STITCHING_ENABLED",
    )
    table_stitching_min_score: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        alias="TABLE_STITCHING_MIN_SCORE",
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
    jwt_secret_key: Optional[str] = Field(default=None, alias="JWT_SECRET_KEY")
    jwt_expire_minutes: int = Field(
        default=10080,
        ge=1,
        alias="JWT_EXPIRE_MINUTES",
    )
    default_user_email: str = Field(
        default="default@example.local",
        alias="DEFAULT_USER_EMAIL",
    )
    default_user_password: Optional[str] = Field(
        default=None,
        alias="DEFAULT_USER_PASSWORD",
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
