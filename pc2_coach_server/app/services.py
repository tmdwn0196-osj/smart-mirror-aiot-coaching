from time import perf_counter
import re
from uuid import uuid4

from fastapi import HTTPException

from app.config import FALLBACK_LLM_ENABLED
from app.db import get_latest_baseline, save_coach_log, save_exercise_baseline
from app.exercise_planning import build_baseline_diff, build_baseline_profile, retrieve_analysis_context
from app.llm_client import (
    call_fallback_llm,
    call_llm_with_fallback,
    is_fallback_llm_configured,
    is_primary_llm_configured,
)
from app.output_validator import parse_coaching_json
from app.prompt_manager import build_coach_prompt
from app.schemas import (
    BaselineDiff,
    ExerciseBaselineCreateRequest,
    ExerciseBaselineProfile,
    FeaturePayload,
)
from app.signal_service import build_query_text, compact_for_prompt, detect_signals, dump_signals


EXPECTED_EVENT = "session_completed"
LOCAL_FALLBACK_MODEL_NAME = "local-rule-fallback"


def dump_model(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


def warnings_from_signals(signal_dicts: list[dict], baseline_found: bool) -> list[str]:
    warnings: list[str] = []
    categories = {signal["category"] for signal in signal_dicts}
    if "illuminance" in categories:
        warnings.append("조도가 낮아 비전 feature 신뢰도가 낮을 수 있습니다.")
    if not baseline_found:
        warnings.append("저장된 baseline이 없어 현재 입력만으로 계획을 생성했습니다.")
    return warnings


def select_plan_name(exercise_type: str) -> str:
    names = {
        "squat": "tempo squat",
        "jumping_jack": "jumping jack",
        "knee_raise": "knee raise",
        "lunge": "reverse lunge",
        "pushup": "push-up",
    }
    return names.get(exercise_type, exercise_type or "exercise")


def build_local_plan_response(
    payload: FeaturePayload,
    baseline_profile: ExerciseBaselineProfile | None,
    signal_dicts: list[dict],
    analysis_context: list[dict],
    warnings: list[str],
    fallback_reason: str,
) -> dict:
    exercise = payload.features.exercise
    exercise_type = str((exercise.type if exercise else "") or "")
    baseline_reps = baseline_profile.recommended_reps if baseline_profile else 8
    baseline_sets = baseline_profile.recommended_sets if baseline_profile else 3
    focus_parts: list[str] = []
    priority = "현재 자세 안정화"

    categories = {item["category"] for item in signal_dicts}
    if "knee" in categories:
        priority = "무릎 정렬 안정화"
        focus_parts.append("무릎-발끝 정렬")
    if "tempo" in categories:
        focus_parts.append("속도 늦추기")
    if "back_posture" in categories:
        focus_parts.append("상체 고정")
    if "stability" in categories:
        focus_parts.append("반복 품질 유지")
    if not focus_parts:
        focus_parts.append("폼 유지")

    reps = max(4, baseline_reps - 2) if baseline_reps is not None else 6
    use_duration = exercise_type == "jumping_jack"

    primary_item = {
        "exercise": select_plan_name(exercise_type),
        "sets": max(2, min(4, baseline_sets)),
        "reps": None if use_duration else reps,
        "duration_sec": 40 if use_duration else None,
        "rest_sec": 60 if use_duration else 75,
        "focus": ", ".join(focus_parts[:2]),
        "reason": "현재 세션 신호와 baseline 차이를 기준으로 보수적으로 볼륨을 잡았습니다.",
    }

    plan = [primary_item]
    for context in analysis_context:
        prescription = context.get("prescription")
        if not isinstance(prescription, dict):
            continue
        candidate = {
            "exercise": context.get("title") or context.get("knowledge_id") or "support drill",
            "sets": int(prescription.get("sets") or 2),
            "reps": int(prescription["reps"]) if prescription.get("reps") is not None else None,
            "duration_sec": int(prescription["duration_sec"]) if prescription.get("duration_sec") is not None else None,
            "rest_sec": int(prescription["rest_sec"]) if prescription.get("rest_sec") is not None else 45,
            "focus": str(prescription.get("focus") or "폼 유지"),
            "reason": str(context.get("content") or "보조 루틴으로 자세 품질을 보완합니다."),
        }
        if candidate["exercise"] != primary_item["exercise"]:
            plan.append(candidate)
        if len(plan) >= 3:
            break

    message = f"{priority}부터 잡고 {plan[0]['sets']}세트만 정확히 진행하세요."
    return {
        "summary": "환경변수 없이도 동작하도록 로컬 규칙 기반 운동 계획을 생성했습니다.",
        "priority": priority,
        "exercise_plan": plan,
        "mirror_message": f"{priority}에 집중하면서 천천히 진행하세요!",
        "warnings": [*warnings, f"LLM 사용이 불가능해 로컬 규칙 기반 계획으로 대체했습니다. ({fallback_reason})"],
        "pc2_payload": {
            "message": message,
            "display_lines": [focus_parts[0], f"{plan[0]['sets']}세트 진행", "천천히 정확하게"],
        },
    }


def local_llm_result(reason: str) -> dict:
    return {
        "served_by": "local",
        "model_name": LOCAL_FALLBACK_MODEL_NAME,
        "fallback_used": True,
        "primary_error": reason,
    }


def build_fallback_message_response(message: str, warnings: list[str]) -> dict:
    raw = str(message or "").strip()
    summary_match = re.search(r'"summary"\s*:\s*"([^"]+)"', raw)
    if summary_match:
        raw = summary_match.group(1)
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.replace("{", " ").replace("}", " ")
    raw = re.sub(r'"(?:summary|priority|mirror_message|message)"\s*:\s*', " ", raw)
    clean = " ".join(raw.split())
    if not clean:
        clean = "지금은 자세 요약만 전달합니다. 천천히 정확하게 진행하세요."
    if not clean.endswith(("!", ".", "?")):
        clean += "."
    return {
        "summary": clean,
        "priority": clean,
        "exercise_plan": [],
        "mirror_message": clean,
        "warnings": warnings,
        "pc2_payload": {
            "message": clean,
            "display_lines": [clean],
        },
    }


def build_fallback_log_payload(response: dict) -> tuple[dict, dict]:
    message = str((((response.get("pc2_payload") or {}).get("message")) or "")).strip()
    if not message:
        message = str(response.get("mirror_message") or response.get("summary") or "").strip()
    simple = {"message": message}
    return simple, simple


def validate_trigger(payload: FeaturePayload) -> None:
    if payload.event != EXPECTED_EVENT:
        raise HTTPException(
            status_code=422,
            detail=f"exercise 모드는 {EXPECTED_EVENT} 이벤트에서만 운동 계획을 생성합니다.",
        )


def load_baseline_profile(payload: FeaturePayload) -> ExerciseBaselineProfile | None:
    exercise_type = str((payload.features.exercise.type if payload.features.exercise else "") or "").lower()
    baseline_record = get_latest_baseline(payload.user_id, exercise_type or None)
    if baseline_record is None:
        return None
    baseline_profile = baseline_record.get("baseline_profile") or {}
    if hasattr(ExerciseBaselineProfile, "model_validate"):
        return ExerciseBaselineProfile.model_validate(baseline_profile)
    return ExerciseBaselineProfile.parse_obj(baseline_profile)


def merge_baseline_diff(payload: FeaturePayload, baseline_profile: ExerciseBaselineProfile | None) -> FeaturePayload:
    computed = build_baseline_diff(payload.features.exercise, baseline_profile)
    incoming = payload.baseline_diff.exercise
    merged_payload = payload.model_copy(deep=True) if hasattr(payload, "model_copy") else payload.copy(deep=True)

    if incoming is None:
        merged_payload.baseline_diff = BaselineDiff(exercise=computed)
        return merged_payload

    merged_payload.baseline_diff = BaselineDiff(
        exercise=type(incoming)(
            count_change=incoming.count_change if incoming.count_change is not None else computed.count_change,
            stability_change=incoming.stability_change if incoming.stability_change is not None else computed.stability_change,
            knee_angle_change=incoming.knee_angle_change if incoming.knee_angle_change is not None else computed.knee_angle_change,
            squat_depth_change=incoming.squat_depth_change if incoming.squat_depth_change is not None else computed.squat_depth_change,
            duration_change=incoming.duration_change if incoming.duration_change is not None else computed.duration_change,
        )
    )
    return merged_payload


def create_baseline_record(payload: ExerciseBaselineCreateRequest) -> dict:
    baseline_id = f"base_{uuid4().hex[:12]}"
    profile = build_baseline_profile(payload.exercise_type, payload.samples)
    save_exercise_baseline(
        baseline_id=baseline_id,
        user_id=payload.user_id,
        exercise_type=payload.exercise_type.lower(),
        purpose=payload.purpose,
        baseline_profile_json=dump_model(profile),
    )
    baseline = get_latest_baseline(payload.user_id, payload.exercise_type.lower())
    return {
        "baseline_id": baseline_id,
        "user_id": payload.user_id,
        "exercise_type": payload.exercise_type.lower(),
        "purpose": payload.purpose,
        "baseline_profile": dump_model(profile),
        "created_at": baseline["created_at"] if baseline else "",
    }


def generate_coaching_response(payload: FeaturePayload, logger) -> dict:
    started_at = perf_counter()
    request_id = f"coach_{uuid4().hex[:12]}"
    logger.info(
        "coach_request_start request_id=%s user_id=%s mode=%s event=%s",
        request_id,
        payload.user_id,
        payload.mode,
        payload.event,
    )
    try:
        validate_trigger(payload)
    except HTTPException:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.warning(
            "coach_request_failed request_id=%s user_id=%s mode=%s event=%s reason=invalid_event latency_ms=%s",
            request_id,
            payload.user_id,
            payload.mode,
            payload.event,
            elapsed_ms,
        )
        raise

    baseline_profile = load_baseline_profile(payload)
    enriched_payload = merge_baseline_diff(payload, baseline_profile)
    query_text = build_query_text(enriched_payload, baseline=baseline_profile)
    signals = detect_signals(enriched_payload)
    signal_dicts = dump_signals(signals)
    analysis_context = retrieve_analysis_context(enriched_payload, signal_dicts, baseline_profile)
    warnings = warnings_from_signals(signal_dicts, baseline_profile is not None)
    prompt_payload = compact_for_prompt(
        enriched_payload,
        signals,
        query_text=query_text,
        baseline=baseline_profile,
        analysis_context=analysis_context,
    )
    system_prompt, user_prompt = build_coach_prompt(prompt_payload)
    fallback_system_prompt, fallback_user_prompt = build_coach_prompt(prompt_payload, compact=True)
    llm_prompt = f"{system_prompt}\n\n{user_prompt}"
    base_response = {
        "summary": "",
        "priority": "",
        "exercise_plan": [],
        "mirror_message": "",
        "warnings": warnings,
        "pc2_payload": {"message": "", "display_lines": []},
    }

    llm_configured = is_primary_llm_configured() or is_fallback_llm_configured()
    if llm_configured:
        try:
            llm_started_at = perf_counter()
            llm_result = call_llm_with_fallback(
                system_prompt,
                user_prompt,
                fallback_system_prompt=fallback_system_prompt,
                fallback_user_prompt=fallback_user_prompt,
            )
            llm_latency_ms = int((perf_counter() - llm_started_at) * 1000)
            raw_llm_response = llm_result["content"]
        except Exception as exc:
            logger.warning(
                "coach_request_local_fallback request_id=%s user_id=%s mode=%s reason=llm_call_failed error=%s",
                request_id,
                payload.user_id,
                payload.mode,
                exc,
            )
            llm_latency_ms = 0
            raw_llm_response = ""
            llm_result = local_llm_result(f"llm_call_failed: {exc}")
            final_response = build_local_plan_response(
                enriched_payload, baseline_profile, signal_dicts, analysis_context, warnings, "llm call failed"
            )
        else:
            if llm_result["served_by"] == "fallback":
                final_response = build_fallback_message_response(raw_llm_response, warnings)
            else:
                try:
                    final_response = parse_coaching_json(raw_llm_response, base_response)
                except Exception as exc:
                    if llm_result["served_by"] == "primary" and FALLBACK_LLM_ENABLED:
                        fallback_started_at = perf_counter()
                        try:
                            llm_result = call_fallback_llm(
                                fallback_system_prompt,
                                fallback_user_prompt,
                                primary_error=f"parse_failed: {exc}",
                            )
                            raw_llm_response = llm_result["content"]
                            llm_latency_ms = int((perf_counter() - fallback_started_at) * 1000)
                            final_response = build_fallback_message_response(raw_llm_response, warnings)
                        except Exception as fallback_exc:
                            logger.warning(
                                "coach_request_local_fallback request_id=%s user_id=%s mode=%s reason=fallback_parse_failed error=%s",
                                request_id,
                                payload.user_id,
                                payload.mode,
                                fallback_exc,
                            )
                            llm_latency_ms = 0
                            raw_llm_response = ""
                            llm_result = local_llm_result(f"fallback_parse_failed: {fallback_exc}")
                            final_response = build_local_plan_response(
                                enriched_payload,
                                baseline_profile,
                                signal_dicts,
                                analysis_context,
                                warnings,
                                "fallback parse failed",
                            )
                    else:
                        logger.warning(
                            "coach_request_local_fallback request_id=%s user_id=%s mode=%s reason=llm_parse_failed error=%s",
                            request_id,
                            payload.user_id,
                            payload.mode,
                            exc,
                        )
                        llm_latency_ms = 0
                        raw_llm_response = ""
                        llm_result = local_llm_result(f"llm_parse_failed: {exc}")
                        final_response = build_local_plan_response(
                            enriched_payload, baseline_profile, signal_dicts, analysis_context, warnings, "llm parse failed"
                        )
    else:
        llm_latency_ms = 0
        raw_llm_response = ""
        llm_result = local_llm_result("no llm env configured")
        final_response = build_local_plan_response(
            enriched_payload, baseline_profile, signal_dicts, analysis_context, warnings, "no llm configured"
        )

    db_pc2_output = final_response.get("pc2_payload")
    db_final_response = final_response
    if llm_result["served_by"] == "fallback":
        db_pc2_output, db_final_response = build_fallback_log_payload(final_response)

    save_coach_log(
        request_id=request_id,
        session_id=payload.session_id,
        user_id=payload.user_id,
        mode=payload.mode,
        purpose=payload.purpose,
        feature_payload_json=dump_model(enriched_payload),
        detected_signals_json=signal_dicts,
        analysis_context_json=analysis_context,
        baseline_snapshot_json=dump_model(baseline_profile),
        pc2_output_json=db_pc2_output,
        llm_prompt=llm_prompt,
        raw_llm_response=raw_llm_response,
        final_response_json=db_final_response,
        model_name=llm_result["model_name"],
        llm_route=llm_result["served_by"],
        fallback_used=llm_result["fallback_used"],
        primary_error=llm_result["primary_error"],
    )
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    logger.info(
        "coach_request_success request_id=%s user_id=%s mode=%s route=%s fallback_used=%s signals=%s analysis_context=%s llm_latency_ms=%s latency_ms=%s",
        request_id,
        payload.user_id,
        payload.mode,
        llm_result["served_by"],
        llm_result["fallback_used"],
        len(signal_dicts),
        len(analysis_context),
        llm_latency_ms,
        elapsed_ms,
    )
    return final_response
