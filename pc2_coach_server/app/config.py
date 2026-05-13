import os

from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, ".env"))


def _env(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    return value if value else default


def _env_chain(names: list[str], default: str) -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        value = raw.strip()
        if value:
            return value
    return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _env_int(names: list[str], default: int) -> int:
    raw = _env_chain(names, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(names: list[str], default: float) -> float:
    raw = _env_chain(names, str(default))
    try:
        return float(raw)
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
    "Qwen/Qwen2.5-1.5B-Instruct-AWQ",
)
FALLBACK_LLM_API_KEY = _env_chain(
    ["FALLBACK_LLM_API_KEY", "VLLM_API_KEY"],
    "EMPTY",
)
LLM_TIMEOUT_SECONDS = _env_float(["LLM_TIMEOUT_SECONDS", "VLLM_TIMEOUT_SECONDS"], 30.0)
PRIMARY_LLM_TIMEOUT_SECONDS = _env_float(["PRIMARY_LLM_TIMEOUT_SECONDS"], LLM_TIMEOUT_SECONDS)
FALLBACK_LLM_TIMEOUT_SECONDS = _env_float(["FALLBACK_LLM_TIMEOUT_SECONDS"], min(12.0, LLM_TIMEOUT_SECONDS))
ROUTINE_PROFILE_TIMEOUT_SECONDS = _env_float(
    ["ROUTINE_PROFILE_TIMEOUT_SECONDS"],
    max(180.0, PRIMARY_LLM_TIMEOUT_SECONDS),
)
LLM_HEALTH_TIMEOUT_SECONDS = _env_float(
    ["LLM_HEALTH_TIMEOUT_SECONDS", "VLLM_HEALTH_TIMEOUT_SECONDS"],
    5.0,
)
LLM_MAX_RETRIES = _env_int(["LLM_MAX_RETRIES", "VLLM_MAX_RETRIES"], 1)
LLM_MAX_TOKENS = _env_int(["LLM_MAX_TOKENS", "VLLM_MAX_TOKENS"], 500)
ROUTINE_PROFILE_MAX_TOKENS = _env_int(
    ["ROUTINE_PROFILE_MAX_TOKENS"],
    max(1800, LLM_MAX_TOKENS),
)
LLM_TEMPERATURE = _env_float(["LLM_TEMPERATURE", "VLLM_TEMPERATURE"], 0.3)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    DATABASE_URL = "postgresql+psycopg://pc2:pc2pass@127.0.0.1:5430/pc2_coach"
SERVICE_NAME = _env("SERVICE_NAME", "pc2-coach-api")
HOST = _env("HOST", "0.0.0.0")
PORT = _env_int(["PORT"], 7000)
LOG_LEVEL = _env("LOG_LEVEL", "info")
