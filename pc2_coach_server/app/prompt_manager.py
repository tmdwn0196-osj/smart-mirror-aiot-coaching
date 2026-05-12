import json
from typing import Any


SYSTEM_PROMPT = (
    "너는 스마트미러 운동 계획 API다.\n"
    "너는 이미지를 직접 보지 않는다.\n"
    "API 입력은 PC3가 만든 운동 feature, 저장된 baseline, 검색된 운동 지식뿐이다.\n"
    "운동 계획은 현재 자세 상태와 baseline 차이를 바탕으로 안전한 범위에서 작성한다.\n"
    "출력은 CoachingResponse JSON만 허용된다.\n"
    "의학적 진단, 질환 추정, 입력에 없는 사실 추측은 금지한다.\n"
    "운동 계획에는 어떤 운동을 할지, 몇 세트인지, 반복 수 또는 시간을 반드시 포함한다.\n"
    "JSON 밖에 Markdown, 설명문, 자연어 문장을 붙이지 않는다."
)

COMPACT_SYSTEM_PROMPT = (
    "입력을 보고 PC3에 보낼 짧은 한국어 한 문장만 출력한다.\n"
    "JSON, 코드블록, key 이름, 설명문은 금지한다.\n"
    "문장은 30자 안팎으로 짧고 바로 실행할 수 있게 쓴다."
)

PROFILE_ROUTINE_SYSTEM_PROMPT = (
    "너는 스마트미러 개인화 루틴 추천 API다.\n"
    "입력은 사용자 프로필 정보뿐이다.\n"
    "user_goal, exercise_experience, available_days_per_week, restricted_body_parts를 기준으로 "
    "안전하고 현실적인 주간 운동 루틴을 작성한다.\n"
    "restricted_body_parts가 비어 있지 않으면 해당 부위에 부담이 큰 동작은 피하거나 강도를 낮춘다.\n"
    "운동 경험이 낮을수록 볼륨과 난이도를 보수적으로 잡는다.\n"
    "출력은 RoutineProfileResponse 형태의 JSON만 허용된다.\n"
    "JSON 밖의 설명문, Markdown, 코드블록은 금지한다."
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
            "짧은 한국어 한 문장만 출력. "
            "JSON 금지. 코드블록 금지. "
            "한 줄 조언만 작성. "
            + json.dumps(slim_data, ensure_ascii=False, separators=(",", ":"))
        )

    return (
        "/no_think\n"
        "아래 운동 feature와 baseline_profile, analysis_context만 사용한다. "
        "현재 상태를 우선하고, baseline보다 낮은 지표가 있으면 볼륨을 보수적으로 잡는다. "
        "운동 계획은 2~4개 item으로 작성하고, item마다 exercise, sets, focus, reason은 필수다. "
        "반복 운동이면 reps를, 정적 운동이면 duration_sec를 넣는다. 둘 다 필요 없으면 하나만 채운다. "
        "priority는 가장 먼저 교정할 포인트 한 줄이다. "
        "summary는 현재 상태와 계획 방향을 1문장으로 요약한다. "
        "mirror_message는 한국어 짧은 문장이고 반드시 !로 끝낸다. "
        "pc2_payload.message는 PC2 화면에 보낼 한 줄 메시지, display_lines는 2~3개 핵심 지시다. "
        "warnings는 필요한 불확실성만 넣는다. "
        + json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":"))
    )


def build_coach_prompt(prompt_payload: dict[str, Any], *, compact: bool = False) -> tuple[str, str]:
    if compact:
        return COMPACT_SYSTEM_PROMPT, _build_user_prompt(prompt_payload, compact=True)
    return SYSTEM_PROMPT, _build_user_prompt(prompt_payload, compact=False)


def build_profile_routine_prompt(profile_payload: dict[str, Any]) -> tuple[str, str]:
    user_prompt = (
        "/no_think\n"
        "아래 프로필만 사용해서 주간 루틴 JSON을 작성한다. "
        "weekly_focus는 이번 주 핵심 방향 1문장이다. "
        "weekly_routine은 available_days_per_week 수와 같거나 더 적은 개수의 day로 작성한다. "
        "각 day는 day_index, day_label, focus, exercises를 포함한다. "
        "exercises의 각 item에는 exercise, sets, focus, reason이 필수다. "
        "반복 운동이면 reps를 넣고, 시간 기반 운동이면 duration_sec를 넣는다. "
        "rest_sec는 가능하면 함께 넣는다. "
        "cautions에는 제한 부위와 관련된 주의점만 1~3개 넣는다. "
        "pc3_payload에는 summary, weekly_focus, available_days_per_week, restricted_body_parts, weekly_routine를 다시 담는다. "
        + json.dumps(profile_payload, ensure_ascii=False, separators=(",", ":"))
    )
    return PROFILE_ROUTINE_SYSTEM_PROMPT, user_prompt
