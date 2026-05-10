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


def parse_coaching_json(raw_text: str, base_response: dict[str, Any]) -> dict[str, Any]:
    parsed = _extract_json_object(raw_text) if raw_text else None
    if parsed is None:
        raise ValueError("LLM 응답에서 JSON 객체를 찾지 못했습니다.")

    required = ("summary", "priority", "exercise_plan", "mirror_message", "warnings", "pc2_payload")
    missing = [field for field in required if field not in parsed]
    if missing:
        raise ValueError(f"LLM JSON 필드 누락: {', '.join(missing)}")

    parsed_warnings = parsed.get("warnings") or []
    if not isinstance(parsed_warnings, list):
        raise ValueError("warnings는 배열이어야 합니다.")

    warnings: list[str] = []
    for item in [*(base_response.get("warnings", []) or []), *parsed_warnings]:
        if item and str(item) not in warnings:
            warnings.append(str(item))

    pc2_payload = parsed.get("pc2_payload")
    if not isinstance(pc2_payload, dict):
        raise ValueError("pc2_payload는 객체여야 합니다.")

    merged = {
        "summary": str(parsed["summary"]),
        "priority": str(parsed["priority"]),
        "exercise_plan": _normalize_plan(parsed["exercise_plan"]),
        "mirror_message": str(parsed["mirror_message"]),
        "warnings": warnings,
        "pc2_payload": {
            "message": str(pc2_payload.get("message") or ""),
            "display_lines": [str(item) for item in pc2_payload.get("display_lines", []) if item],
        },
    }

    if hasattr(CoachingResponse, "model_validate"):
        return CoachingResponse.model_validate(merged).model_dump()
    return CoachingResponse.parse_obj(merged).dict()
