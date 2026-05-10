import json
import re
from typing import Any

from app.schemas import CoachingResponse


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = _strip_code_fence(text)
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                parsed = json.loads(text[start : index + 1])
                return parsed if isinstance(parsed, dict) else None
    return None


def _normalize_plan(plan: Any) -> list[dict[str, Any]]:
    if plan is None:
        return []
    if not isinstance(plan, list):
        raise ValueError("exercise_plan은 배열이어야 합니다.")

    normalized: list[dict[str, Any]] = []
    for item in plan:
        if not isinstance(item, dict):
            raise ValueError("exercise_plan item은 객체여야 합니다.")
        normalized.append(
            {
                "exercise": str(item.get("exercise") or ""),
                "sets": int(item.get("sets") or 0),
                "reps": int(item["reps"]) if item.get("reps") is not None else None,
                "duration_sec": int(item["duration_sec"]) if item.get("duration_sec") is not None else None,
                "rest_sec": int(item["rest_sec"]) if item.get("rest_sec") is not None else None,
                "focus": str(item.get("focus") or ""),
                "reason": str(item.get("reason") or ""),
            }
        )
    return normalized


def _as_warning_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_pc2_payload(parsed: dict[str, Any], summary: str, priority: str, mirror_message: str) -> dict[str, Any]:
    pc2_payload = parsed.get("pc2_payload")
    if isinstance(pc2_payload, dict):
        message = str(pc2_payload.get("message") or mirror_message or summary or priority or "").strip()
        display_lines = [str(item) for item in pc2_payload.get("display_lines", []) if item]
        if not display_lines and message:
            display_lines = [message]
        return {
            "message": message,
            "display_lines": display_lines[:3],
        }

    message = mirror_message or summary or priority
    return {
        "message": str(message or "").strip(),
        "display_lines": [str(message).strip()] if message else [],
    }


def _has_meaningful_content(response: dict[str, Any]) -> bool:
    if str(response.get("summary") or "").strip():
        return True
    if str(response.get("priority") or "").strip():
        return True
    if str(response.get("mirror_message") or "").strip():
        return True
    if list(response.get("exercise_plan") or []):
        return True
    pc2_payload = response.get("pc2_payload") or {}
    if str(pc2_payload.get("message") or "").strip():
        return True
    if list(pc2_payload.get("display_lines") or []):
        return True
    return False


def parse_coaching_json(raw_text: str, base_response: dict[str, Any]) -> dict[str, Any]:
    parsed = _extract_json_object(raw_text) if raw_text else None
    if parsed is None:
        raise ValueError("LLM 응답에서 JSON 객체를 찾지 못했습니다.")

    if "CoachingResponse" in parsed and isinstance(parsed.get("CoachingResponse"), dict):
        parsed = parsed["CoachingResponse"]

    if "exercise_plan" not in parsed and "plan" in parsed:
        parsed["exercise_plan"] = parsed.get("plan")
    if "mirror_message" not in parsed and "message" in parsed:
        parsed["mirror_message"] = parsed.get("message")

    summary = str(
        parsed.get("summary")
        or parsed.get("mirror_message")
        or parsed.get("priority")
        or ((((parsed.get("pc2_payload") or {}) if isinstance(parsed.get("pc2_payload"), dict) else {})).get("message"))
        or ""
    ).strip()
    priority = str(parsed.get("priority") or summary).strip()
    mirror_message = str(parsed.get("mirror_message") or summary or priority).strip()

    warnings: list[str] = []
    for item in [*(base_response.get("warnings", []) or []), *_as_warning_list(parsed.get("warnings"))]:
        if item and str(item) not in warnings:
            warnings.append(str(item))

    merged = {
        "summary": summary,
        "priority": priority,
        "exercise_plan": _normalize_plan(parsed.get("exercise_plan")),
        "mirror_message": mirror_message,
        "warnings": warnings,
        "pc2_payload": _normalize_pc2_payload(parsed, summary, priority, mirror_message),
    }

    if not _has_meaningful_content(merged):
        raise ValueError("LLM 응답에 사용할 수 있는 내용이 없습니다.")

    if hasattr(CoachingResponse, "model_validate"):
        return CoachingResponse.model_validate(merged).model_dump()
    return CoachingResponse.parse_obj(merged).dict()
