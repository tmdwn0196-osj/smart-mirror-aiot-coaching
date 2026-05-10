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


def _build_user_prompt(prompt_payload: dict[str, Any], *, compact: bool) -> str:
    if compact:
        slim_payload = {
            "purpose": prompt_payload.get("purpose"),
            "feature_summary": prompt_payload.get("feature_summary"),
            "baseline_profile": prompt_payload.get("baseline_profile"),
            "detected_signals": [
                {
                    "label": item.get("label"),
                    "value": item.get("value"),
                    "severity": item.get("severity"),
                }
                for item in prompt_payload.get("detected_signals", [])
                if isinstance(item, dict)
            ][:4],
        }
        return (
            "/no_think\n"
            "아래 요약만 사용해 JSON만 출력. "
            "key는 summary,priority,exercise_plan,mirror_message,warnings,pc2_payload. "
            "exercise_plan은 2~3개. 각 item key는 exercise,sets,reps,duration_sec,rest_sec,focus,reason. "
            "pc2_payload key는 message,display_lines. "
            "message는 한 줄, display_lines는 2~3줄. "
            + json.dumps(slim_payload, ensure_ascii=False, separators=(",", ":"))
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
    return SYSTEM_PROMPT, _build_user_prompt(prompt_payload, compact=compact)
