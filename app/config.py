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


def _env_bool(names: list[str], default: bool) -> bool:
    raw = _env_chain(names, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


PRIMARY_LLM_BASE_URL = _env_chain(
    ["PRIMARY_LLM_BASE_URL", "LLM_BASE_URL"],
    "https://integrate.api.nvidia.com/v1",
)
PRIMARY_LLM_MODEL_NAME = _env_chain(
    ["PRIMARY_LLM_MODEL_NAME", "LLM_MODEL_NAME"],
    "meta/llama-3.3-70b-instruct",
)
PRIMARY_LLM_API_KEY = _env_chain(
    ["PRIMARY_LLM_API_KEY", "NVIDIA_API_KEY", "LLM_API_KEY"],
    "",
)
LLM_TIMEOUT_SECONDS = _env_float(["LLM_TIMEOUT_SECONDS"], 30.0)
PRIMARY_LLM_TIMEOUT_SECONDS = _env_float(["PRIMARY_LLM_TIMEOUT_SECONDS"], max(45.0, LLM_TIMEOUT_SECONDS))
ROUTINE_PROFILE_TIMEOUT_SECONDS = _env_float(
    ["ROUTINE_PROFILE_TIMEOUT_SECONDS"],
    min(45.0, PRIMARY_LLM_TIMEOUT_SECONDS),
)
REQUEST_DEADLINE_SECONDS = _env_float(["REQUEST_DEADLINE_SECONDS"], 90.0)
LLM_HEALTH_TIMEOUT_SECONDS = _env_float(["LLM_HEALTH_TIMEOUT_SECONDS"], 10.0)
LLM_MAX_RETRIES = _env_int(["LLM_MAX_RETRIES"], 0)
LLM_MAX_TOKENS = _env_int(["LLM_MAX_TOKENS"], 500)
ROUTINE_PROFILE_MAX_TOKENS = _env_int(
    ["ROUTINE_PROFILE_MAX_TOKENS"],
    max(1800, LLM_MAX_TOKENS),
)
LLM_TEMPERATURE = _env_float(["LLM_TEMPERATURE"], 0.3)

RAG_ENABLED = _env_bool(["RAG_ENABLED"], True)
EMBEDDING_MODEL_NAME = _env_chain(
    ["EMBEDDING_MODEL_NAME"],
    "nvidia/llama-nemotron-embed-1b-v2",
)
RERANK_MODEL_NAME = _env_chain(
    ["RERANK_MODEL_NAME"],
    "nvidia/llama-nemotron-rerank-1b-v2",
)
EMBEDDING_DIMENSIONS = _env_int(["EMBEDDING_DIMENSIONS"], 512)
RAG_VECTOR_TOP_K = _env_int(["RAG_VECTOR_TOP_K"], 30)
RAG_CONTEXT_K = _env_int(["RAG_CONTEXT_K"], 5)
EMBEDDING_API_URL = _env(
    "EMBEDDING_API_URL",
    PRIMARY_LLM_BASE_URL.rstrip("/") + "/embeddings",
)
RERANK_API_URL = _env(
    "RERANK_API_URL",
    "https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking",
)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./data/pc2_local.sqlite3"
SERVICE_NAME = _env("SERVICE_NAME", "pc2-coach-api")
HOST = _env("HOST", "0.0.0.0")
PORT = _env_int(["PORT"], 7000)
LOG_LEVEL = _env("LOG_LEVEL", "info")
