import httpx
from openai import OpenAI

from app.config import (
    EMBEDDING_API_URL,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
    LLM_HEALTH_TIMEOUT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    PRIMARY_LLM_API_KEY,
    PRIMARY_LLM_BASE_URL,
    PRIMARY_LLM_MODEL_NAME,
    PRIMARY_LLM_TIMEOUT_SECONDS,
    RERANK_API_URL,
    RERANK_MODEL_NAME,
)


def is_primary_llm_configured() -> bool:
    return bool(PRIMARY_LLM_API_KEY.strip())


def _health_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        LLM_HEALTH_TIMEOUT_SECONDS,
        connect=min(2.0, LLM_HEALTH_TIMEOUT_SECONDS),
        read=LLM_HEALTH_TIMEOUT_SECONDS,
        write=LLM_HEALTH_TIMEOUT_SECONDS,
        pool=1.0,
    )


def check_primary_llm_health() -> dict:
    if not PRIMARY_LLM_API_KEY.strip():
        return {
            "status": "unconfigured",
            "base_url": PRIMARY_LLM_BASE_URL,
            "model": PRIMARY_LLM_MODEL_NAME,
            "error": "missing api key",
        }

    models_url = PRIMARY_LLM_BASE_URL.rstrip("/") + "/models"
    try:
        with httpx.Client(timeout=_health_timeout(), trust_env=False) as client:
            response = client.get(
                models_url,
                headers={"Authorization": f"Bearer {PRIMARY_LLM_API_KEY}"},
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {
            "status": "unhealthy",
            "base_url": PRIMARY_LLM_BASE_URL,
            "model": PRIMARY_LLM_MODEL_NAME,
            "error": str(exc),
        }

    model_ids = [
        item.get("id")
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]
    return {
        "status": "ok" if not model_ids or PRIMARY_LLM_MODEL_NAME in model_ids else "model_missing",
        "base_url": PRIMARY_LLM_BASE_URL,
        "model": PRIMARY_LLM_MODEL_NAME,
        "available_models": model_ids[:10],
    }


def _call_openai_compatible(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int | None = None,
    timeout_seconds: float = 30.0,
) -> str:
    http_client = httpx.Client(timeout=timeout_seconds, trust_env=False)
    client = OpenAI(
        base_url=PRIMARY_LLM_BASE_URL,
        api_key=PRIMARY_LLM_API_KEY,
        timeout=timeout_seconds,
        max_retries=LLM_MAX_RETRIES,
        http_client=http_client,
    )
    try:
        response = client.chat.completions.create(
            model=PRIMARY_LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=LLM_TEMPERATURE,
            max_tokens=max_tokens or LLM_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        message = response.choices[0].message
        content = message.content or ""
        if content.strip():
            return content

        reasoning_content = getattr(message, "reasoning_content", None) or ""
        if reasoning_content.strip():
            raise RuntimeError(
                f"{PRIMARY_LLM_MODEL_NAME} returned reasoning_content without final JSON content."
            )
        raise RuntimeError(f"{PRIMARY_LLM_MODEL_NAME} returned an empty response.")
    finally:
        client.close()


def call_primary_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
) -> dict:
    if not is_primary_llm_configured():
        raise RuntimeError("primary LLM is not configured")

    content = _call_openai_compatible(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens or LLM_MAX_TOKENS,
        timeout_seconds=timeout_seconds or PRIMARY_LLM_TIMEOUT_SECONDS,
    )
    return {
        "content": content,
        "served_by": "primary",
        "model_name": PRIMARY_LLM_MODEL_NAME,
    }


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {PRIMARY_LLM_API_KEY}",
        "Content-Type": "application/json",
    }


def call_embedding(texts: list[str], *, input_type: str) -> list[list[float]]:
    if not is_primary_llm_configured():
        raise RuntimeError("primary LLM API key is not configured")
    if input_type not in {"passage", "query"}:
        raise ValueError("input_type must be passage or query")
    if not texts:
        return []

    payload = {
        "model": EMBEDDING_MODEL_NAME,
        "input": texts,
        "input_type": input_type,
        "dimensions": EMBEDDING_DIMENSIONS,
        "encoding_format": "float",
        "truncate": "END",
    }
    timeout = max(30.0, PRIMARY_LLM_TIMEOUT_SECONDS)
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        response = client.post(EMBEDDING_API_URL, headers=_headers(), json=payload)
    response.raise_for_status()
    data = response.json().get("data")
    if not isinstance(data, list):
        raise RuntimeError("embedding response did not contain data")

    embeddings: list[list[float]] = []
    for item in data:
        embedding = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(embedding, list):
            raise RuntimeError("embedding response item did not contain embedding")
        embeddings.append([float(value) for value in embedding])
    return embeddings


def call_rerank(query: str, passages: list[str]) -> list[dict]:
    if not is_primary_llm_configured():
        raise RuntimeError("primary LLM API key is not configured")
    if not passages:
        return []

    payload = {
        "model": RERANK_MODEL_NAME,
        "query": {"text": query},
        "passages": [{"text": text} for text in passages],
        "truncate": "END",
    }
    timeout = max(30.0, PRIMARY_LLM_TIMEOUT_SECONDS)
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        response = client.post(RERANK_API_URL, headers=_headers(), json=payload)
    response.raise_for_status()
    rankings = response.json().get("rankings")
    if not isinstance(rankings, list):
        raise RuntimeError("rerank response did not contain rankings")
    return [
        {
            "index": int(item.get("index")),
            "logit": float(item.get("logit", 0.0)),
        }
        for item in rankings
        if isinstance(item, dict) and item.get("index") is not None
    ]
