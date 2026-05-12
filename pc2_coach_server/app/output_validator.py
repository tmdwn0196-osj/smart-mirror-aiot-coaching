import json
import re
from typing import Any

from app.schemas import CoachingResponse
from app.schemas import EXERCISE_TYPE_VALUES, RoutineProfileResponse, normalize_exercise_type_name


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


def _normalize_routine_plan(plan: Any) -> list[dict[str, Any]]:
    normalized = _normalize_plan(plan)
    for item in normalized:
        normalized_name = normalize_exercise_type_name(str(item.get("exercise") or ""))
        if not normalized_name:
            raise ValueError(
                "프로필 루틴의 exercise는 "
                + ", ".join(EXERCISE_TYPE_VALUES)
                + " 중 하나여야 합니다."
            )
        item["exercise"] = normalized_name
    return normalized


def _normalize_weekly_routine(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("weekly_routine은 배열이어야 합니다.")

    weekly_routine: list[dict[str, Any]] = []
    for day in value:
        if not isinstance(day, dict):
            raise ValueError("weekly_routine item은 객체여야 합니다.")
        weekly_routine.append(
            {
                "day_index": int(day.get("day_index") or 0),
                "day_label": str(day.get("day_label") or ""),
                "focus": str(day.get("focus") or ""),
                "exercises": _normalize_routine_plan(day.get("exercises")),
            }
        )
    return weekly_routine


def _as_warning_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = []
        for item in value:
            if item:
                items.append(str(item))
        return items
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []

def _normalize_pc2_payload(parsed: dict[str, Any], summary: str, priority: str, mirror_message: str) -> dict[str, Any]:
    pc2_payload = parsed.get("pc2_payload")
    if isinstance(pc2_payload, dict):
        message = str(pc2_payload.get("message") or mirror_message or summary or priority or "").strip()
        lines = []
        for item in pc2_payload.get("display_lines", []):
            if item:
                lines.append(str(item))
        if not lines and message:
            lines = [message]
        return {
            "message": message,
            "display_lines": lines[:3],
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


def _merge_warnings(base_response: dict[str, Any], parsed: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    items = []
    items.extend(base_response.get("warnings", []) or [])
    items.extend(_as_warning_list(parsed.get("warnings")))
    for item in items:
        text = str(item)
        if text and text not in warnings:
            warnings.append(text)
    return warnings


def _pick_summary(parsed: dict[str, Any]) -> str:
    pc2_payload = parsed.get("pc2_payload")
    message = ""
    if isinstance(pc2_payload, dict):
        message = pc2_payload.get("message") or ""
    text = (
        parsed.get("summary")
        or parsed.get("mirror_message")
        or parsed.get("priority")
        or message
        or ""
    )
    return str(text).strip()


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

    summary = _pick_summary(parsed)
    priority = str(parsed.get("priority") or summary).strip()
    mirror_message = str(parsed.get("mirror_message") or summary or priority).strip()
    warnings = _merge_warnings(base_response, parsed)

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


def parse_profile_routine_json(raw_text: str, base_response: dict[str, Any]) -> dict[str, Any]:
    parsed = _extract_json_object(raw_text) if raw_text else None
    if parsed is None:
        raise ValueError("LLM 응답에서 JSON 객체를 찾지 못했습니다.")

    if "RoutineProfileResponse" in parsed and isinstance(parsed.get("RoutineProfileResponse"), dict):
        parsed = parsed["RoutineProfileResponse"]

    summary = str(parsed.get("summary") or "").strip()
    weekly_focus = str(parsed.get("weekly_focus") or summary).strip()
    weekly_routine = _normalize_weekly_routine(parsed.get("weekly_routine"))

    cautions = _as_warning_list(parsed.get("cautions"))
    base_cautions = _as_warning_list(base_response.get("cautions"))
    merged_cautions: list[str] = []
    for item in [*base_cautions, *cautions]:
        if item and item not in merged_cautions:
            merged_cautions.append(item)

    request_available_days = base_response.get("available_days_per_week")
    request_restricted_parts = base_response.get("restricted_body_parts") or []
    if not summary:
        raise ValueError("프로필 루틴 응답에는 summary가 필요합니다.")
    if not weekly_focus:
        raise ValueError("프로필 루틴 응답에는 weekly_focus가 필요합니다.")
    if not weekly_routine:
        raise ValueError("프로필 루틴 응답에는 최소 1일 이상의 weekly_routine이 필요합니다.")
    if request_available_days is not None and len(weekly_routine) > int(request_available_days):
        raise ValueError("weekly_routine 일수는 available_days_per_week 이하여야 합니다.")

    merged_pc3_payload = {
        "summary": summary,
        "weekly_focus": weekly_focus,
        "available_days_per_week": request_available_days,
        "restricted_body_parts": request_restricted_parts,
        "weekly_routine": weekly_routine,
    }

    merged = {
        "summary": summary,
        "weekly_focus": weekly_focus,
        "weekly_routine": weekly_routine,
        "cautions": merged_cautions,
        "pc3_payload": merged_pc3_payload,
    }

    if hasattr(RoutineProfileResponse, "model_validate"):
        return RoutineProfileResponse.model_validate(merged).model_dump()
    return RoutineProfileResponse.parse_obj(merged).dict()
