import json
import re
from typing import Any

from app.schemas import CoachingResponse, EXERCISE_TYPE_VALUES, RoutineProfileResponse, normalize_exercise_type_name


HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")

EXERCISE_LABELS = {
    "squat": "\uc2a4\ucffc\ud2b8",
    "lunge": "\ub7f0\uc9c0",
    "pushup": "\ud478\uc2dc\uc5c5",
    "jumping_jack": "\uc810\ud551\uc7ad",
    "knee_raise": "\ub2c8 \ub808\uc774\uc988",
}
CATEGORY_LABELS = {
    "form_basics": "\uae30\ubcf8 \uc790\uc138",
    "common_error": "\ud754\ud55c \uc624\ub958",
    "correction_cue": "\uad50\uc815 \ud050",
    "safety": "\uc548\uc804 \uc8fc\uc758",
    "progression": "\uac15\ub3c4 \uc870\uc808",
    "regression": "\ub300\uccb4/\uc644\ud654 \ub3d9\uc791",
    "post_workout": "\uc6b4\ub3d9 \ud6c4 \ud53c\ub4dc\ubc31",
}
SOURCE_LABELS = {
    "ACSM Progression Models in Resistance Training": "ACSM \uc800\ud56d \uc6b4\ub3d9 \uc810\uc9c4 \ubaa8\ub378",
    "A Biomechanical Review of the Squat Exercise": "\uc2a4\ucffc\ud2b8 \uc0dd\uccb4\uc5ed\ud559 \ub9ac\ubdf0",
    "Physical Activity Guidelines for Americans, 2nd edition": "\ubbf8\uad6d \uc2e0\uccb4\ud65c\ub3d9 \uac00\uc774\ub4dc\ub77c\uc778 2\ud310",
    "WHO Guidelines on Physical Activity and Sedentary Behaviour": "WHO \uc2e0\uccb4\ud65c\ub3d9 \ubc0f \uc88c\uc2dd \ud589\ub3d9 \uac00\uc774\ub4dc\ub77c\uc778",
    "Patellofemoral Pain Clinical Practice Guideline": "\ubb34\ub98e \uc55e\ucabd \ud1b5\uc99d \uc784\uc0c1 \uac00\uc774\ub4dc\ub77c\uc778",
}


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


def _to_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_plan(plan: Any, *, enforce_known_exercise: bool = False) -> list[dict[str, Any]]:
    if plan is None:
        return []
    if isinstance(plan, dict):
        if isinstance(plan.get("exercise_plan"), list):
            plan = plan.get("exercise_plan")
        elif isinstance(plan.get("exercises"), list):
            plan = plan.get("exercises")
        elif plan.get("exercise") is not None:
            plan = [plan]
        else:
            raise ValueError("exercise_plan must be an array.")
    if not isinstance(plan, list):
        raise ValueError("exercise_plan must be an array.")

    normalized: list[dict[str, Any]] = []
    for item in plan:
        if not isinstance(item, dict):
            raise ValueError("exercise_plan items must be objects.")
        exercise_name = str(item.get("exercise") or "").strip()
        if enforce_known_exercise:
            normalized_name = normalize_exercise_type_name(exercise_name)
            if not normalized_name:
                raise ValueError(
                    "routine exercise must be one of: " + ", ".join(EXERCISE_TYPE_VALUES)
                )
            exercise_name = normalized_name
        normalized.append(
            {
                "exercise": exercise_name,
                "sets": _to_int(item.get("sets"), 1) or 1,
                "reps": _to_int(item.get("reps")),
                "duration_sec": _to_int(item.get("duration_sec")),
                "rest_sec": _to_int(item.get("rest_sec")),
                "focus": str(item.get("focus") or "").strip(),
                "reason": str(item.get("reason") or "").strip(),
                "how_to": str(item.get("how_to") or "").strip(),
                "tips": str(item.get("tips") or "").strip(),
            }
        )
    return normalized


def _normalize_weekly_routine(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("weekly_routine must be an array.")

    weekly_routine: list[dict[str, Any]] = []
    for index, day in enumerate(value, start=1):
        if not isinstance(day, dict):
            raise ValueError("weekly_routine items must be objects.")
        weekly_routine.append(
            {
                "day_index": _to_int(day.get("day_index"), index) or index,
                "day_label": str(day.get("day_label") or f"{index}일차").strip(),
                "focus": str(day.get("focus") or "").strip(),
                "exercises": _normalize_plan(day.get("exercises"), enforce_known_exercise=True),
            }
        )
    return weekly_routine


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _localize_evidence(items: Any) -> list[dict[str, Any]]:
    localized: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        exercise = str(item.get("exercise") or "").strip()
        category = str(item.get("category") or "").strip()
        source = str(item.get("source") or "").strip()
        exercise_label = EXERCISE_LABELS.get(exercise, exercise or "\uc6b4\ub3d9")
        category_label = CATEGORY_LABELS.get(category, category or "\uadfc\uac70")
        source_label = SOURCE_LABELS.get(source, source or "\uc6b4\ub3d9 \uc9c0\uc2dd \uc790\ub8cc")
        localized.append(
            {
                **item,
                "exercise_label": exercise_label,
                "category_label": category_label,
                "title": f"{exercise_label} {category_label}",
                "source": source_label,
                "original_title": item.get("title"),
                "original_source": source,
            }
        )
    return localized


def _require_korean_text(value: Any, field_path: str, *, allow_empty: bool = False) -> None:
    text = str(value or "").strip()
    if not text:
        if allow_empty:
            return
        raise ValueError(f"{field_path} must contain Korean text.")
    if not HANGUL_RE.search(text):
        raise ValueError(f"{field_path} must be Korean user-facing text.")


def _require_korean_list(values: list[str], field_path: str) -> None:
    for index, value in enumerate(values):
        _require_korean_text(value, f"{field_path}[{index}]")


def _require_korean_plan(plan: list[dict[str, Any]], field_path: str) -> None:
    for index, item in enumerate(plan):
        for key in ("focus", "reason", "how_to", "tips"):
            _require_korean_text(item.get(key), f"{field_path}[{index}].{key}", allow_empty=key in {"how_to", "tips"})


def _split_display_text(value: str) -> list[str]:
    lines: list[str] = []
    for chunk in re.split(r"[\n\r]+", value or ""):
        text = chunk.strip(" -\t")
        if text:
            lines.append(text)
    return lines


def _normalize_pc2_payload(
    parsed: dict[str, Any],
    summary: str,
    priority: str,
    mirror_message: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    pc2_payload = parsed.get("pc2_payload")
    if isinstance(pc2_payload, dict):
        message = str(pc2_payload.get("message") or mirror_message or summary or priority or "").strip()
        lines = _as_text_list(pc2_payload.get("display_lines"))
        if not lines and message:
            lines = _split_display_text(message)
        if len(lines) < 4 and mirror_message:
            lines.extend(_split_display_text(mirror_message))
        if len(lines) < 4:
            raise ValueError("pc2_payload.display_lines must contain at least 4 lines.")
        return {"message": message, "display_lines": lines[:6], "evidence": evidence[:5]}

    message = mirror_message or summary or priority
    lines = _split_display_text(str(message or ""))
    if len(lines) < 4:
        raise ValueError("pc2_payload.display_lines must contain at least 4 lines.")
    return {
        "message": str(message or "").strip(),
        "display_lines": lines[:6],
        "evidence": evidence[:5],
    }


def parse_coaching_json(raw_text: str, base_response: dict[str, Any]) -> dict[str, Any]:
    parsed = _extract_json_object(raw_text) if raw_text else None
    if parsed is None:
        raise ValueError("LLM response did not contain a JSON object.")

    if "CoachingResponse" in parsed and isinstance(parsed.get("CoachingResponse"), dict):
        parsed = parsed["CoachingResponse"]

    if "exercise_plan" not in parsed and "plan" in parsed:
        parsed["exercise_plan"] = parsed.get("plan")
    if "mirror_message" not in parsed and "message" in parsed:
        parsed["mirror_message"] = parsed.get("message")

    summary = str(parsed.get("summary") or parsed.get("mirror_message") or parsed.get("priority") or "").strip()
    priority = str(parsed.get("priority") or summary).strip()
    mirror_message = str(parsed.get("mirror_message") or summary or priority).strip()
    warnings = []
    for item in [*_as_text_list(base_response.get("warnings")), *_as_text_list(parsed.get("warnings"))]:
        if item not in warnings:
            warnings.append(item)
    evidence = _localize_evidence(base_response.get("evidence"))

    merged = {
        "summary": summary,
        "priority": priority,
        "exercise_plan": _normalize_plan(parsed.get("exercise_plan")),
        "mirror_message": mirror_message,
        "warnings": warnings,
        "pc2_payload": _normalize_pc2_payload(parsed, summary, priority, mirror_message, evidence),
    }
    if not (summary or priority or mirror_message or merged["exercise_plan"]):
        raise ValueError("LLM response did not contain usable coaching content.")

    _require_korean_text(merged["summary"], "summary")
    _require_korean_text(merged["mirror_message"], "mirror_message")
    _require_korean_list(merged["warnings"], "warnings")
    _require_korean_text(merged["pc2_payload"]["message"], "pc2_payload.message")
    _require_korean_list(merged["pc2_payload"]["display_lines"], "pc2_payload.display_lines")
    _require_korean_plan(merged["exercise_plan"], "exercise_plan")

    if hasattr(CoachingResponse, "model_validate"):
        return CoachingResponse.model_validate(merged).model_dump()
    return CoachingResponse.parse_obj(merged).dict()


def parse_profile_routine_json(raw_text: str, base_response: dict[str, Any]) -> dict[str, Any]:
    parsed = _extract_json_object(raw_text) if raw_text else None
    if parsed is None:
        raise ValueError("LLM response did not contain a JSON object.")

    if "RoutineProfileResponse" in parsed and isinstance(parsed.get("RoutineProfileResponse"), dict):
        parsed = parsed["RoutineProfileResponse"]

    summary = str(parsed.get("summary") or "").strip()
    weekly_focus = str(parsed.get("weekly_focus") or summary).strip()
    weekly_routine = _normalize_weekly_routine(parsed.get("weekly_routine"))
    cautions: list[str] = []
    for item in [*_as_text_list(base_response.get("cautions")), *_as_text_list(parsed.get("cautions"))]:
        if item not in cautions:
            cautions.append(item)

    available_days = base_response.get("available_days_per_week")
    restricted_parts = base_response.get("restricted_body_parts") or []
    evidence = _localize_evidence(base_response.get("evidence"))
    if not summary:
        raise ValueError("routine response requires summary.")
    if not weekly_focus:
        raise ValueError("routine response requires weekly_focus.")
    if not weekly_routine:
        raise ValueError("routine response requires at least one weekly_routine day.")
    if available_days is not None and len(weekly_routine) > int(available_days):
        raise ValueError("weekly_routine cannot exceed available_days_per_week.")

    _require_korean_text(summary, "summary")
    _require_korean_text(weekly_focus, "weekly_focus")
    _require_korean_list(cautions, "cautions")
    for index, day in enumerate(weekly_routine):
        _require_korean_text(day.get("day_label"), f"weekly_routine[{index}].day_label")
        _require_korean_text(day.get("focus"), f"weekly_routine[{index}].focus")
        _require_korean_plan(day.get("exercises") or [], f"weekly_routine[{index}].exercises")

    merged = {
        "summary": summary,
        "weekly_focus": weekly_focus,
        "weekly_routine": weekly_routine,
        "cautions": cautions,
        "pc3_payload": {
            "summary": summary,
            "weekly_focus": weekly_focus,
            "available_days_per_week": available_days,
            "restricted_body_parts": restricted_parts,
            "weekly_routine": weekly_routine,
            "evidence": evidence[:5],
            "history_summary": base_response.get("history_summary") or {},
            "weekly_adjustment": base_response.get("weekly_adjustment") or {},
        },
    }

    if hasattr(RoutineProfileResponse, "model_validate"):
        return RoutineProfileResponse.model_validate(merged).model_dump()
    return RoutineProfileResponse.parse_obj(merged).dict()
