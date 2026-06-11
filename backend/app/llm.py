import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

load_dotenv(ENV_FILE)


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set in backend/.env")

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
        "model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        "api_key": get_required_env("OPENAI_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE"),
        "store": get_env_bool("OPENAI_STORE", False),
        "streaming": True,
    }

    return ChatOpenAI(**apply_optional_llm_options(options))


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
