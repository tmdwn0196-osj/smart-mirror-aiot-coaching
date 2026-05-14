import json
from typing import Any

from app.schemas import EXERCISE_TYPE_VALUES


SYSTEM_PROMPT = (
    "스마트미러 운동 계획 API다.\n"
    "입력은 PC3 feature, baseline, 검색 지식만 사용한다.\n"
    "latest_profile_routine가 있으면 방향 충돌을 피한다.\n"
    "안전한 범위에서 CoachingResponse JSON만 출력한다.\n"
    "진단/추측/Markdown/설명문은 금지한다.\n"
    "운동명, 세트 수, 반복 수 또는 시간을 반드시 포함한다."
)

COMPACT_SYSTEM_PROMPT = (
    "PC3용 짧은 한국어 한 문장만 출력한다.\n"
    "JSON, 코드블록, key 이름, 설명문은 금지한다."
)

PROFILE_ROUTINE_SYSTEM_PROMPT = (
    "스마트미러 개인화 루틴 추천 API다.\n"
    "입력은 사용자 프로필만 사용한다.\n"
    "user_goal, exercise_experience, available_days_per_week, restricted_body_parts 기준으로 "
    "현실적인 주간 루틴을 작성한다.\n"
    "제한 부위가 있으면 부담 큰 동작은 피하거나 강도를 낮춘다.\n"
    "운동 이름은 짧게 쓰고, 하루 exercises는 1개만 작성한다.\n"
    "정확히 하나의 JSON 객체만 출력하고 설명문/Markdown/코드블록은 금지한다."
)


def _pick_num(first: Any, second: Any) -> Any:
    if first is not None:
        return first
    return second


def _compact_payload(prompt_payload: dict[str, Any]) -> dict[str, Any]:
    feat_json = prompt_payload.get("feature_json") or {}
    feats = feat_json.get("features") or {}
    ex = feats.get("exercise") or {}
    base = prompt_payload.get("baseline_profile") or {}

    sigs = []
    for item in prompt_payload.get("detected_signals", []):
        if isinstance(item, dict):
            sigs.append(
                {
                    "label": item.get("label"),
                    "severity": item.get("severity"),
                }
            )

    return {
        "purpose": prompt_payload.get("purpose"),
        "exercise": {
            "type": ex.get("type"),
            "rep_count": _pick_num(ex.get("rep_count"), ex.get("count")),
            "stability_score": ex.get("stability_score"),
            "posture_errors": (ex.get("posture_errors") or [])[:1],
            "squat_depth": ex.get("squat_depth"),
            "knee_angle": ex.get("knee_angle"),
            "back_angle": ex.get("back_angle"),
            "duration_sec": _pick_num(ex.get("duration_sec"), ex.get("duration_seconds")),
            "tempo": ex.get("tempo"),
        },
        "baseline": {
            "recommended_sets": base.get("recommended_sets"),
            "recommended_reps": base.get("recommended_reps"),
            "stability_score_avg": base.get("stability_score_avg"),
        },
        "signals": sigs[:2],
    }


def _build_user_prompt(prompt_payload: dict[str, Any], *, compact: bool) -> str:
    if compact:
        slim_data = _compact_payload(prompt_payload)
        return (
            "/no_think\n"
            "짧은 한국어 한 문장만 출력. JSON/코드블록/설명문 금지. "
            + json.dumps(slim_data, ensure_ascii=False, separators=(",", ":"))
        )

    allowed_exercises = ", ".join(EXERCISE_TYPE_VALUES)
    return (
        "/no_think\n"
        "아래 입력만 사용해 정확히 하나의 JSON 객체만 반환한다. "
        "top-level key는 summary, priority, exercise_plan, mirror_message, warnings, pc2_payload만 허용한다. "
        f"exercise_plan.exercise는 반드시 {allowed_exercises} 중 하나만 사용한다. "
        "exercise_plan은 1~2개 item만 작성한다. "
        "각 item은 exercise, sets, reps, duration_sec, rest_sec, focus, reason, how_to, tips를 포함한다. "
        "반복 운동이면 reps 숫자, duration 운동이면 duration_sec 숫자만 넣는다. "
        "summary와 priority는 1문장, mirror_message는 1문장, warnings는 문자열 배열이다. "
        "pc2_payload는 message와 display_lines만 포함하고 display_lines는 2개 문자열 배열이다. "
        "latest_profile_routine와 충돌하지 않게 하고 baseline보다 낮은 지표는 보수적으로 반영한다. "
        + json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":"))
    )


def build_coach_prompt(prompt_payload: dict[str, Any], *, compact: bool = False) -> tuple[str, str]:
    if compact:
        return COMPACT_SYSTEM_PROMPT, _build_user_prompt(prompt_payload, compact=True)
    return SYSTEM_PROMPT, _build_user_prompt(prompt_payload, compact=False)


def build_profile_routine_prompt(profile_payload: dict[str, Any]) -> tuple[str, str]:
    allowed_exercises = ", ".join(EXERCISE_TYPE_VALUES)
    user_prompt = (
        "/no_think\n"
        "아래 프로필만 사용해서 정확히 하나의 JSON 객체를 작성한다. "
        "key는 summary, weekly_focus, weekly_routine, cautions만 사용한다. "
        f"루틴에 넣는 exercise 이름은 반드시 {allowed_exercises} 중 하나만 사용한다. "
        "다른 운동 이름, 한국어 운동 이름, 변형 이름은 금지한다. "
        "summary와 weekly_focus는 각 1문장이다. "
        "weekly_routine은 available_days_per_week 이하 개수로 작성한다. "
        "각 day는 day_index, day_label, focus, exercises만 포함한다. "
        "각 day의 exercises는 1개만 작성한다. "
        "각 exercise item은 exercise, sets, focus, reason, how_to, tips를 포함한다. "
        "반복 운동이면 reps를 넣고, 시간 운동이면 duration_sec를 넣는다. "
        "rest_sec는 가능하면 함께 넣는다. "
        "reason/how_to/tips는 짧게 쓴다. "
        "cautions는 1개만 작성한다. "
        "pc3_payload, user_id, profile_name 같은 추가 key는 넣지 않는다. "
        "JSON은 완전히 닫힌 형태로 끝내고 마지막 문자도 } 이어야 한다. "
        + json.dumps(profile_payload, ensure_ascii=False, separators=(",", ":"), default=str)
    )
    return PROFILE_ROUTINE_SYSTEM_PROMPT, user_prompt


def build_profile_routine_day_prompt(
    profile_payload: dict[str, Any],
    weekly_outline: dict[str, Any],
    day_outline: dict[str, Any],
) -> tuple[str, str]:
    allowed_exercises = ", ".join(EXERCISE_TYPE_VALUES)
    prompt_payload = {
        "profile": profile_payload,
        "weekly_outline": weekly_outline,
        "target_day": day_outline,
    }
    user_prompt = (
        "/no_think\n"
        "아래 정보만 사용해서 정확히 하나의 JSON 객체를 작성한다. "
        f"exercise는 반드시 {allowed_exercises} 중 하나만 사용한다. "
        "반드시 day_index, day_label, focus, exercises만 포함한다. "
        "day_index와 day_label은 target_day와 동일하게 유지한다. "
        "focus는 target_day의 방향을 유지하되 더 구체적으로 작성한다. "
        "exercises는 1개만 작성한다. "
        "각 exercise item은 exercise, sets, focus, reason, how_to, tips를 포함한다. "
        "반복 운동이면 reps를 넣고, 시간 운동이면 duration_sec를 넣는다. "
        "rest_sec는 가능하면 함께 넣는다. "
        "reason/how_to/tips는 짧게 쓴다. "
        "JSON은 완전히 닫힌 형태로 끝내고 마지막 문자도 } 이어야 한다. "
        + json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":"), default=str)
    )
    return PROFILE_ROUTINE_SYSTEM_PROMPT, user_prompt
