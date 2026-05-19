import json
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


KOREAN_OUTPUT_RULES = (
    "- Keep JSON keys and exercise enum values in English exactly as the schema requires.\n"
    "- Every user-visible natural-language value must be Korean.\n"
    "- Do not answer with English sentences in summary, focus, reason, how_to, tips, cautions, warnings, mirror_message, message, or display_lines.\n"
)


def build_coach_prompt(payload: dict[str, Any], evidence_block: str = "") -> tuple[str, str]:
    system_prompt = (
        "You are PC2, a coaching JSON generator for a Korean smart mirror exercise system. "
        "Return one strict JSON object only. Do not use markdown. Do not invent API fields. "
        "Use the provided evidence as grounded exercise knowledge. "
        "All user-facing text values must be written in Korean."
    )
    user_prompt = (
        "Create a short Korean coaching response for PC3 from this completed exercise session.\n"
        f"{evidence_block}\n"
        "Allowed response shape:\n"
        "{"
        '"summary":"string",'
        '"priority":"string",'
        '"exercise_plan":[{"exercise":"squat|jumping_jack|knee_raise|lunge|pushup","sets":1,"reps":10,"duration_sec":null,"rest_sec":60,"focus":"string","reason":"string","how_to":"string","tips":"string"}],'
        '"mirror_message":"string",'
        '"warnings":["string"],'
        '"pc2_payload":{"message":"string","display_lines":["string"]}'
        "}\n"
        "Rules:\n"
        f"{KOREAN_OUTPUT_RULES}"
        "- pc2_payload.display_lines must contain at least 4 short Korean lines.\n"
        "- Keep each display line concise enough for an on-screen smart mirror.\n"
        "- Include: completed work summary, key posture/rhythm cue, evidence-based reason, next action.\n"
        "- Use only exercises from the allowed list.\n"
        "- If the input suggests pain or instability, reduce intensity and add a warning.\n"
        "- Do not make medical diagnoses. Use stop/seek-professional-help language for sharp pain, dizziness, or breathing distress.\n"
        "- Do not cite evidence that is not present in the evidence block.\n"
        f"Input JSON: {_json(payload)}"
    )
    return system_prompt, user_prompt


def build_profile_routine_prompt(
    profile_payload: dict[str, Any],
    evidence_block: str = "",
    history_block: str = "",
    weekly_adjustment_block: str = "",
) -> tuple[str, str]:
    days = int(profile_payload.get("available_days_per_week") or 3)
    days = max(1, min(7, days))
    system_prompt = (
        "You are PC2, a routine JSON generator for a Korean smart mirror exercise system. "
        "Return one strict JSON object only. Do not use markdown. Do not add fields outside the schema. "
        "Use the provided evidence as grounded exercise knowledge. "
        "All user-facing text values must be written in Korean."
    )
    user_prompt = (
        "Create a Korean weekly exercise routine from this profile.\n"
        f"{evidence_block}\n"
        f"{history_block}\n"
        f"{weekly_adjustment_block}\n"
        "Allowed exercises: squat, jumping_jack, knee_raise, lunge, pushup.\n"
        "Allowed response shape:\n"
        "{"
        '"summary":"string",'
        '"weekly_focus":"string",'
        '"weekly_routine":[{"day_index":1,"day_label":"Day 1","focus":"string","exercises":[{"exercise":"squat|jumping_jack|knee_raise|lunge|pushup","sets":1,"reps":10,"duration_sec":null,"rest_sec":60,"focus":"string","reason":"string","how_to":"string","tips":"string"}]}],'
        '"cautions":["string"]'
        "}\n"
        "Rules:\n"
        f"{KOREAN_OUTPUT_RULES}"
        f"- weekly_routine must contain exactly {days} day objects.\n"
        "- day_index starts at 1 and increases by 1.\n"
        "- day_label can be short Korean text such as '1일차'.\n"
        "- Respect restricted_body_parts conservatively.\n"
        "- Follow WEEKLY_ADJUSTMENT exactly for volume direction and do not increase volume when it says hold_or_decrease.\n"
        "- Adjust volume using USER_HISTORY when it exists: progress cautiously after good completion, reduce load after repeated errors or low completion.\n"
        "- Prefer beginner-safe volume unless the profile clearly says otherwise.\n"
        "- Use evidence to explain exercise choices in summary, reason, how_to, tips, and cautions.\n"
        "- Do not make medical diagnoses. If pain or red flags are mentioned, reduce intensity and add a caution.\n"
        f"Profile JSON: {_json(profile_payload)}"
    )
    return system_prompt, user_prompt
