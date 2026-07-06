import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

load_dotenv(ENV_FILE)


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set in backend/.env")

    return value


def get_first_env(names: list[str]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def get_required_first_env(names: list[str]) -> str:
    value = get_first_env(names)
    if not value:
        joined_names = " or ".join(names)
        raise RuntimeError(f"{joined_names} is not set in backend/.env")
    return value


def get_env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def apply_optional_llm_options(options: dict, prefix: str = "OPENAI") -> dict:
    temperature = os.getenv(f"{prefix}_TEMPERATURE")
    if temperature:
        options["temperature"] = float(temperature)

    reasoning_effort = os.getenv(f"{prefix}_REASONING_EFFORT")
    if reasoning_effort:
        options["reasoning_effort"] = reasoning_effort

    return options


@lru_cache(maxsize=3)
def get_llm() -> ChatOpenAI:
    options = {
        "model": os.getenv("OPENAI_RELAY_MODEL")
        or os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        "api_key": get_required_first_env(
            ["OPENAI_RELAY_API_KEY", "OPENAI_API_KEY"]
        ),
        "base_url": get_first_env(
            ["OPENAI_RELAY_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE"]
        ),
        "store": get_env_bool(
            "OPENAI_RELAY_STORE",
            get_env_bool("OPENAI_STORE", False),
        ),
        "streaming": True,
    }

    return ChatOpenAI(
        **apply_optional_llm_options(
            apply_optional_llm_options(options),
            prefix="OPENAI_RELAY",
        )
    )


@lru_cache(maxsize=1)
def get_official_llm() -> ChatOpenAI:
    """备用官方 OpenAI 入口；当前业务 graph 不会主动调用它。"""
    options = {
        "model": os.getenv("OPENAI_OFFICIAL_MODEL", "gpt-3.5-turbo"),
        "api_key": get_required_env("OPENAI_OFFICIAL_API_KEY"),
        "store": get_env_bool("OPENAI_OFFICIAL_STORE", False),
        "streaming": True,
    }

    return ChatOpenAI(**apply_optional_llm_options(options, prefix="OPENAI_OFFICIAL"))


@lru_cache(maxsize=1)
def get_ragas_llm() -> ChatOpenAI:
    """Stable non-streaming LLM for Ragas generation and judging."""
    options = {
        "model": os.getenv("RAGAS_OPENAI_MODEL", "gpt-4o-mini"),
        "api_key": get_required_first_env(
            ["RAGAS_OPENAI_API_KEY", "OPENAI_OFFICIAL_API_KEY"]
        ),
        "base_url": os.getenv("RAGAS_OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL,
        "store": get_env_bool("RAGAS_OPENAI_STORE", False),
        "streaming": False,
    }

    return ChatOpenAI(**apply_optional_llm_options(options, prefix="RAGAS_OPENAI"))
