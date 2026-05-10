import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_chain(names: list[str], default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        value = value.strip()
        if value:
            return value
    return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(names: list[str], default: int) -> int:
    value = _env_chain(names, str(default))
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(names: list[str], default: float) -> float:
    value = _env_chain(names, str(default))
    try:
        return float(value)
    except ValueError:
        return default


PRIMARY_LLM_BASE_URL = _env_chain(
    ["PRIMARY_LLM_BASE_URL", "LLM_BASE_URL"],
    "https://integrate.api.nvidia.com/v1",
)
PRIMARY_LLM_MODEL_NAME = _env_chain(
    ["PRIMARY_LLM_MODEL_NAME", "LLM_MODEL_NAME"],
    "google/gemma-4-31b-it",
)
PRIMARY_LLM_API_KEY = _env_chain(
    ["PRIMARY_LLM_API_KEY", "NVIDIA_API_KEY", "LLM_API_KEY"],
    "",
)
FALLBACK_LLM_ENABLED = _env_bool("FALLBACK_LLM_ENABLED", False)
FALLBACK_LLM_BASE_URL = _env_chain(
    ["FALLBACK_LLM_BASE_URL", "VLLM_BASE_URL"],
    "http://127.0.0.1:8000/v1",
)
FALLBACK_LLM_MODEL_NAME = _env_chain(
    ["FALLBACK_LLM_MODEL_NAME", "VLLM_MODEL_NAME"],
    "Qwen/Qwen2.5-3B-Instruct",
)
FALLBACK_LLM_API_KEY = _env_chain(
    ["FALLBACK_LLM_API_KEY", "VLLM_API_KEY"],
    "EMPTY",
)
LLM_TIMEOUT_SECONDS = _env_float(["LLM_TIMEOUT_SECONDS", "VLLM_TIMEOUT_SECONDS"], 30.0)
PRIMARY_LLM_TIMEOUT_SECONDS = _env_float(["PRIMARY_LLM_TIMEOUT_SECONDS"], LLM_TIMEOUT_SECONDS)
FALLBACK_LLM_TIMEOUT_SECONDS = _env_float(["FALLBACK_LLM_TIMEOUT_SECONDS"], min(12.0, LLM_TIMEOUT_SECONDS))
LLM_HEALTH_TIMEOUT_SECONDS = _env_float(
    ["LLM_HEALTH_TIMEOUT_SECONDS", "VLLM_HEALTH_TIMEOUT_SECONDS"],
    5.0,
)
LLM_MAX_RETRIES = _env_int(["LLM_MAX_RETRIES", "VLLM_MAX_RETRIES"], 1)
LLM_MAX_TOKENS = _env_int(["LLM_MAX_TOKENS", "VLLM_MAX_TOKENS"], 500)
LLM_TEMPERATURE = _env_float(["LLM_TEMPERATURE", "VLLM_TEMPERATURE"], 0.3)

DB_PATH = Path(_env("DB_PATH", str(DATA_DIR / "pc2_coach.db")))
SERVICE_NAME = _env("SERVICE_NAME", "pc2-coach-api")
HOST = _env("HOST", "0.0.0.0")
PORT = _env_int(["PORT"], 7000)
LOG_LEVEL = _env("LOG_LEVEL", "info")
