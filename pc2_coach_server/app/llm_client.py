import httpx
from openai import OpenAI

from app.config import (
    FALLBACK_LLM_API_KEY,
    FALLBACK_LLM_BASE_URL,
    FALLBACK_LLM_ENABLED,
    FALLBACK_LLM_MODEL_NAME,
    LLM_HEALTH_TIMEOUT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
    PRIMARY_LLM_API_KEY,
    PRIMARY_LLM_BASE_URL,
    PRIMARY_LLM_MODEL_NAME,
)


def is_primary_llm_configured() -> bool:
    return bool(PRIMARY_LLM_API_KEY.strip())


def is_fallback_llm_configured() -> bool:
    return FALLBACK_LLM_ENABLED and bool(FALLBACK_LLM_BASE_URL.strip()) and bool(FALLBACK_LLM_MODEL_NAME.strip())


def _check_llm_health(base_url: str, api_key: str, model_name: str) -> dict:
    if not api_key.strip():
        return {
            "status": "unconfigured",
            "base_url": base_url,
            "model": model_name,
            "error": "missing api key",
        }
    models_url = base_url.rstrip("/") + "/models"
    try:
        timeout = httpx.Timeout(
            LLM_HEALTH_TIMEOUT_SECONDS,
            connect=min(2.0, LLM_HEALTH_TIMEOUT_SECONDS),
            read=LLM_HEALTH_TIMEOUT_SECONDS,
            write=LLM_HEALTH_TIMEOUT_SECONDS,
            pool=1.0,
        )
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {
            "status": "unhealthy",
            "base_url": base_url,
            "model": model_name,
            "error": str(exc),
        }

    model_ids = [
        item.get("id")
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]
    return {
        "status": "ok" if not model_ids or model_name in model_ids else "model_missing",
        "base_url": base_url,
        "model": model_name,
        "available_models": model_ids[:10],
    }


def check_primary_llm_health() -> dict:
    return _check_llm_health(PRIMARY_LLM_BASE_URL, PRIMARY_LLM_API_KEY, PRIMARY_LLM_MODEL_NAME)


def check_fallback_llm_health() -> dict:
    if not FALLBACK_LLM_ENABLED:
        return {
            "status": "disabled",
            "base_url": FALLBACK_LLM_BASE_URL,
            "model": FALLBACK_LLM_MODEL_NAME,
        }
    if not FALLBACK_LLM_API_KEY.strip():
        return {
            "status": "unconfigured",
            "base_url": FALLBACK_LLM_BASE_URL,
            "model": FALLBACK_LLM_MODEL_NAME,
            "error": "missing api key",
        }
    return _check_llm_health(FALLBACK_LLM_BASE_URL, FALLBACK_LLM_API_KEY, FALLBACK_LLM_MODEL_NAME)


def _call_openai_compatible(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int | None = None,
) -> str:
    http_client = httpx.Client(timeout=LLM_TIMEOUT_SECONDS, trust_env=False)
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
        http_client=http_client,
    )
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=LLM_TEMPERATURE,
            max_tokens=max_tokens or LLM_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""
    finally:
        client.close()


def call_primary_llm(system_prompt: str, user_prompt: str) -> dict:
    if not is_primary_llm_configured():
        raise RuntimeError("primary llm is not configured")
    return {
        "content": _call_openai_compatible(
            base_url=PRIMARY_LLM_BASE_URL,
            api_key=PRIMARY_LLM_API_KEY,
            model_name=PRIMARY_LLM_MODEL_NAME,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=LLM_MAX_TOKENS,
        ),
        "served_by": "primary",
        "model_name": PRIMARY_LLM_MODEL_NAME,
        "fallback_used": False,
        "primary_error": None,
    }


def call_fallback_llm(system_prompt: str, user_prompt: str, primary_error: str) -> dict:
    if not FALLBACK_LLM_ENABLED:
        raise RuntimeError("fallback llm is disabled")
    if not FALLBACK_LLM_API_KEY.strip():
        raise RuntimeError("fallback llm is not configured")
    return {
        "content": _call_openai_compatible(
            base_url=FALLBACK_LLM_BASE_URL,
            api_key=FALLBACK_LLM_API_KEY,
            model_name=FALLBACK_LLM_MODEL_NAME,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=min(64, LLM_MAX_TOKENS),
        ),
        "served_by": "fallback",
        "model_name": FALLBACK_LLM_MODEL_NAME,
        "fallback_used": True,
        "primary_error": primary_error,
    }


def call_llm_with_fallback(
    system_prompt: str,
    user_prompt: str,
    *,
    fallback_system_prompt: str | None = None,
    fallback_user_prompt: str | None = None,
) -> dict:
    try:
        result = call_primary_llm(system_prompt, user_prompt)
        if result["content"].strip():
            return result
        raise RuntimeError("primary llm returned empty content")
    except Exception as primary_exc:
        if not is_fallback_llm_configured():
            raise
        return call_fallback_llm(
            fallback_system_prompt or system_prompt,
            fallback_user_prompt or user_prompt,
            primary_error=str(primary_exc),
        )
