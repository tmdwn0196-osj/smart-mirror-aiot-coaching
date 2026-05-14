import httpx
from openai import OpenAI

from app.config import (
    FALLBACK_LLM_API_KEY,
    FALLBACK_LLM_BASE_URL,
    FALLBACK_LLM_ENABLED,
    FALLBACK_LLM_MODEL_NAME,
    FALLBACK_LLM_TIMEOUT_SECONDS,
    LLM_HEALTH_TIMEOUT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    PRIMARY_LLM_TIMEOUT_SECONDS,
    PRIMARY_LLM_API_KEY,
    PRIMARY_LLM_BASE_URL,
    PRIMARY_LLM_MODEL_NAME,
    ROUTINE_PROFILE_MAX_TOKENS,
    ROUTINE_PROFILE_TIMEOUT_SECONDS,
)


def is_primary_llm_configured() -> bool:
    return bool(PRIMARY_LLM_API_KEY.strip())


def is_fallback_llm_configured() -> bool:
    return FALLBACK_LLM_ENABLED and bool(FALLBACK_LLM_BASE_URL.strip()) and bool(FALLBACK_LLM_MODEL_NAME.strip())


def _health_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        LLM_HEALTH_TIMEOUT_SECONDS,
        connect=min(2.0, LLM_HEALTH_TIMEOUT_SECONDS),
        read=LLM_HEALTH_TIMEOUT_SECONDS,
        write=LLM_HEALTH_TIMEOUT_SECONDS,
        pool=1.0,
    )


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
        with httpx.Client(timeout=_health_timeout(), trust_env=False) as client:
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

    model_ids = []
    for item in payload.get("data", []):
        if isinstance(item, dict) and item.get("id"):
            model_ids.append(item.get("id"))
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
    expect_json: bool = True,
    timeout_seconds: float = 30.0,
) -> str:
    http_client = httpx.Client(timeout=timeout_seconds, trust_env=False)
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=LLM_MAX_RETRIES,
        http_client=http_client,
    )
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=LLM_TEMPERATURE,
            max_tokens=max_tokens or LLM_MAX_TOKENS,
            response_format={"type": "json_object"} if expect_json else None,
        )
        message = response.choices[0].message
        content = message.content or ""
        if content.strip():
            return content

        reasoning_content = getattr(message, "reasoning_content", None) or ""
        if expect_json and reasoning_content.strip():
            raise RuntimeError(
                f"{model_name} returned reasoning_content without final content; "
                "structured JSON output is unavailable on this route."
            )

        return content
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
        raise RuntimeError("기본 LLM이 설정되어 있지 않습니다.")
    content = _call_openai_compatible(
        base_url=PRIMARY_LLM_BASE_URL,
        api_key=PRIMARY_LLM_API_KEY,
        model_name=PRIMARY_LLM_MODEL_NAME,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens or LLM_MAX_TOKENS,
        expect_json=True,
        timeout_seconds=timeout_seconds or PRIMARY_LLM_TIMEOUT_SECONDS,
    )
    return {
        "content": content,
        "served_by": "primary",
        "model_name": PRIMARY_LLM_MODEL_NAME,
        "fallback_used": False,
        "primary_error": None,
    }


def call_primary_profile_routine_llm(system_prompt: str, user_prompt: str) -> dict:
    return call_primary_llm(
        system_prompt,
        user_prompt,
        max_tokens=ROUTINE_PROFILE_MAX_TOKENS,
        timeout_seconds=ROUTINE_PROFILE_TIMEOUT_SECONDS,
    )


def call_fallback_llm(system_prompt: str, user_prompt: str, primary_error: str) -> dict:
    if not FALLBACK_LLM_ENABLED:
        raise RuntimeError("보조 LLM이 비활성화되어 있습니다.")
    if not FALLBACK_LLM_API_KEY.strip():
        raise RuntimeError("보조 LLM이 설정되어 있지 않습니다.")
    content = _call_openai_compatible(
        base_url=FALLBACK_LLM_BASE_URL,
        api_key=FALLBACK_LLM_API_KEY,
        model_name=FALLBACK_LLM_MODEL_NAME,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=min(24, LLM_MAX_TOKENS),
        expect_json=False,
        timeout_seconds=FALLBACK_LLM_TIMEOUT_SECONDS,
    )
    return {
        "content": content,
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
        raise RuntimeError("기본 LLM 응답이 비어 있습니다.")
    except Exception as primary_exc:
        if not is_fallback_llm_configured():
            raise
        return call_fallback_llm(
            fallback_system_prompt or system_prompt,
            fallback_user_prompt or user_prompt,
            primary_error=str(primary_exc),
        )
