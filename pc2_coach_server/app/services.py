import re
from datetime import date
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException

from app.config import FALLBACK_LLM_ENABLED
from app.db import (
    find_existing_session_log,
    get_latest_baseline,
    get_profile_routine_day_by_date,
    get_latest_profile_routine,
    save_coach_log,
    save_exercise_baseline,
    save_profile_routine,
    save_profile_routine_days,
)
from app.exercise_planning import build_baseline_diff, build_baseline_profile, retrieve_analysis_context
from app.llm_client import (
    call_fallback_llm,
    call_llm_with_fallback,
    call_primary_llm,
    call_primary_profile_routine_llm,
    is_fallback_llm_configured,
    is_primary_llm_configured,
)
from app.output_validator import parse_coaching_json, parse_profile_routine_day_json, parse_profile_routine_json
from app.prompt_manager import build_coach_prompt, build_profile_routine_day_prompt, build_profile_routine_prompt
from app.schemas import (
    BaselineDiff,
    ExerciseBaselineCreateRequest,
    ExerciseBaselineProfile,
    FeaturePayload,
    RoutineProfileDayRecord,
    RoutineProfileRequest,
    RoutineProfileRecord,
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
    categories = set()
    for signal in signal_dicts:
        categories.add(signal["category"])
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


def _resolve_routine_start_date(payload: RoutineProfileRequest) -> date:
    return payload.start_date or date.today()


def _build_routine_day_message(day: dict) -> str:
    exercise_names = [str(item.get("exercise") or "").strip() for item in day.get("exercises") or [] if item.get("exercise")]
    if not exercise_names:
        return f"오늘은 {day.get('focus') or '운동'} 루틴을 진행할 예정입니다."
    exercise_line = ", ".join(exercise_names[:2])
    return f"오늘은 {day.get('focus') or '운동'} 루틴으로 {exercise_line}를 진행할 예정입니다."


def _expand_profile_routine_days(
    payload: RoutineProfileRequest,
    routine_response: dict,
    logger,
    request_id: str,
) -> list[dict]:
    profile_payload = dump_model(payload)
    weekly_outline = {
        "summary": routine_response.get("summary"),
        "weekly_focus": routine_response.get("weekly_focus"),
        "cautions": routine_response.get("cautions") or [],
        "available_days_per_week": payload.available_days_per_week,
        "restricted_body_parts": payload.restricted_body_parts,
    }

    expanded_days: list[dict] = []
    for day in routine_response.get("weekly_routine") or []:
        system_prompt, user_prompt = build_profile_routine_day_prompt(
            profile_payload,
            weekly_outline,
            day,
        )
        try:
            llm_result = call_primary_profile_routine_llm(system_prompt, user_prompt)
            expanded_day = parse_profile_routine_day_json(llm_result["content"], day["day_index"], day)
            expanded_days.append(expanded_day)
        except Exception as exc:
            logger.warning(
                "profile_routine_day_detail_failed request_id=%s user_id=%s day_index=%s error=%s",
                request_id,
                payload.user_id,
                day.get("day_index"),
                exc,
            )
            expanded_days.append(day)
    return expanded_days


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

    categories = set()
    for item in signal_dicts:
        categories.add(item["category"])
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

    main_item = {
        "exercise": select_plan_name(exercise_type),
        "sets": max(2, min(4, baseline_sets)),
        "reps": None if use_duration else reps,
        "duration_sec": 40 if use_duration else None,
        "rest_sec": 60 if use_duration else 75,
        "focus": ", ".join(focus_parts[:2]),
        "reason": "현재 세션 신호와 baseline 차이를 기준으로 보수적으로 볼륨을 잡았습니다.",
    }

    plan = [main_item]
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
        if candidate["exercise"] != main_item["exercise"]:
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


def _restriction_cautions(restricted_body_parts: list[str]) -> list[str]:
    cautions: list[str] = []
    for part in restricted_body_parts:
        name = str(part or "").strip()
        if not name:
            continue
        cautions.append(f"{name} 부위에 통증이 있으면 즉시 강도를 낮추세요.")
        if len(cautions) >= 3:
            break
    return cautions


def validate_trigger(payload: FeaturePayload) -> None:
    if payload.event != EXPECTED_EVENT:
        raise HTTPException(
            status_code=422,
            detail=f"exercise 모드는 {EXPECTED_EVENT} 이벤트에서만 운동 계획을 생성합니다.",
        )


def load_baseline_profile(payload: FeaturePayload) -> ExerciseBaselineProfile | None:
    exercise = payload.features.exercise
    exercise_type = str((exercise.type if exercise else "") or "").lower()
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
    if hasattr(payload, "model_copy"):
        merged_payload = payload.model_copy(deep=True)
    else:
        merged_payload = payload.copy(deep=True)

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
        latency_ms = int((perf_counter() - started_at) * 1000)
        logger.warning(
            "coach_request_failed request_id=%s user_id=%s mode=%s event=%s reason=invalid_event latency_ms=%s",
            request_id,
            payload.user_id,
            payload.mode,
            payload.event,
            latency_ms,
        )
        raise

    baseline_profile = load_baseline_profile(payload)
    latest_profile_routine = get_latest_profile_routine(payload.user_id)
    enriched_payload = merge_baseline_diff(payload, baseline_profile)
    query_text = build_query_text(enriched_payload, baseline=baseline_profile)
    signals = detect_signals(enriched_payload)
    signal_data = dump_signals(signals)
    context_data = retrieve_analysis_context(enriched_payload, signal_data, baseline_profile)
    warnings = warnings_from_signals(signal_data, baseline_profile is not None)
    prompt_data = compact_for_prompt(
        enriched_payload,
        signals,
        query_text=query_text,
        baseline=baseline_profile,
        analysis_context=context_data,
        latest_profile_routine=latest_profile_routine,
    )
    system_prompt, user_prompt = build_coach_prompt(prompt_data)
    fallback_system_prompt, fallback_user_prompt = build_coach_prompt(prompt_data, compact=True)
    llm_prompt = f"{system_prompt}\n\n{user_prompt}"
    base_response = {
        "summary": "",
        "priority": "",
        "exercise_plan": [],
        "mirror_message": "",
        "warnings": warnings,
        "pc2_payload": {"message": "", "display_lines": []},
    }

    llm_ready = is_primary_llm_configured() or is_fallback_llm_configured()
    if llm_ready:
        try:
            llm_started_at = perf_counter()
            llm_result = call_llm_with_fallback(
                system_prompt,
                user_prompt,
                fallback_system_prompt=fallback_system_prompt,
                fallback_user_prompt=fallback_user_prompt,
            )
            llm_ms = int((perf_counter() - llm_started_at) * 1000)
            raw_llm = llm_result["content"]
        except Exception as exc:
            logger.warning(
                "coach_request_local_fallback request_id=%s user_id=%s mode=%s reason=llm_call_failed error=%s",
                request_id,
                payload.user_id,
                payload.mode,
                exc,
            )
            llm_ms = 0
            raw_llm = ""
            llm_result = local_llm_result(f"llm_call_failed: {exc}")
            final_response = build_local_plan_response(
                enriched_payload, baseline_profile, signal_data, context_data, warnings, "llm call failed"
            )
        else:
            if llm_result["served_by"] == "fallback":
                final_response = build_fallback_message_response(raw_llm, warnings)
            else:
                try:
                    final_response = parse_coaching_json(raw_llm, base_response)
                except Exception as exc:
                    if llm_result["served_by"] == "primary" and FALLBACK_LLM_ENABLED:
                        fallback_started_at = perf_counter()
                        try:
                            llm_result = call_fallback_llm(
                                fallback_system_prompt,
                                fallback_user_prompt,
                                primary_error=f"parse_failed: {exc}",
                            )
                            raw_llm = llm_result["content"]
                            llm_ms = int((perf_counter() - fallback_started_at) * 1000)
                            final_response = build_fallback_message_response(raw_llm, warnings)
                        except Exception as fallback_exc:
                            logger.warning(
                                "coach_request_local_fallback request_id=%s user_id=%s mode=%s reason=fallback_parse_failed error=%s",
                                request_id,
                                payload.user_id,
                                payload.mode,
                                fallback_exc,
                            )
                            llm_ms = 0
                            raw_llm = ""
                            llm_result = local_llm_result(f"fallback_parse_failed: {fallback_exc}")
                            final_response = build_local_plan_response(
                                enriched_payload,
                                baseline_profile,
                                signal_data,
                                context_data,
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
                        llm_ms = 0
                        raw_llm = ""
                        llm_result = local_llm_result(f"llm_parse_failed: {exc}")
                        final_response = build_local_plan_response(
                            enriched_payload, baseline_profile, signal_data, context_data, warnings, "llm parse failed"
                        )
    else:
        llm_ms = 0
        raw_llm = ""
        llm_result = local_llm_result("no llm env configured")
        final_response = build_local_plan_response(
            enriched_payload, baseline_profile, signal_data, context_data, warnings, "no llm configured"
        )

    db_pc2_output = final_response.get("pc2_payload")
    db_final_response = final_response
    if llm_result["served_by"] == "fallback":
        db_pc2_output, db_final_response = build_fallback_log_payload(final_response)
    existing_session_log = find_existing_session_log(payload.user_id, payload.session_id)
    is_duplicate_session = existing_session_log is not None
    duplicate_of_request_id = existing_session_log["request_id"] if existing_session_log else None

    save_coach_log(
        request_id=request_id,
        session_id=payload.session_id,
        user_id=payload.user_id,
        mode=payload.mode,
        purpose=payload.purpose,
        feature_payload_json=dump_model(enriched_payload),
        detected_signals_json=signal_data,
        analysis_context_json=context_data,
        baseline_snapshot_json=dump_model(baseline_profile),
        routine_snapshot_json=latest_profile_routine,
        pc2_output_json=db_pc2_output,
        llm_prompt=llm_prompt,
        raw_llm_response=raw_llm,
        final_response_json=db_final_response,
        model_name=llm_result["model_name"],
        llm_route=llm_result["served_by"],
        fallback_used=llm_result["fallback_used"],
        primary_error=llm_result["primary_error"],
        is_duplicate_session=is_duplicate_session,
        duplicate_of_request_id=duplicate_of_request_id,
    )
    latency_ms = int((perf_counter() - started_at) * 1000)
    logger.info(
        "coach_request_success request_id=%s user_id=%s mode=%s route=%s fallback_used=%s duplicate_session=%s signals=%s analysis_context=%s llm_latency_ms=%s latency_ms=%s",
        request_id,
        payload.user_id,
        payload.mode,
        llm_result["served_by"],
        llm_result["fallback_used"],
        is_duplicate_session,
        len(signal_data),
        len(context_data),
        llm_ms,
        latency_ms,
    )
    return final_response


def generate_profile_routine_response(payload: RoutineProfileRequest, logger) -> dict:
    request_id = f"profile_{uuid4().hex[:12]}"
    logger.info(
        "profile_routine_request_start request_id=%s user_id=%s days=%s",
        request_id,
        payload.user_id,
        payload.available_days_per_week,
    )

    prompt_payload = dump_model(payload)
    base_response = {
        "summary": "",
        "weekly_focus": "",
        "weekly_routine": [],
        "cautions": _restriction_cautions(payload.restricted_body_parts),
        "available_days_per_week": payload.available_days_per_week,
        "restricted_body_parts": payload.restricted_body_parts,
        "pc3_payload": {},
    }
    system_prompt, user_prompt = build_profile_routine_prompt(prompt_payload)

    if not is_primary_llm_configured():
        logger.warning(
            "profile_routine_request_failed request_id=%s user_id=%s reason=primary_llm_unconfigured",
            request_id,
            payload.user_id,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "message": "루틴 생성에 실패했습니다.",
                "reason": "primary_llm_unconfigured",
            },
        )

    try:
        llm_result = call_primary_profile_routine_llm(system_prompt, user_prompt)
        raw_llm = llm_result["content"]
    except Exception as exc:
        logger.warning(
            "profile_routine_request_failed request_id=%s user_id=%s reason=primary_llm_call_failed error=%s",
            request_id,
            payload.user_id,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "message": "루틴 생성에 실패했습니다.",
                "reason": "primary_llm_call_failed",
            },
        ) from exc

    try:
        final_response = parse_profile_routine_json(raw_llm, base_response)
    except Exception as exc:
        logger.warning(
            "profile_routine_request_failed request_id=%s user_id=%s reason=primary_llm_parse_failed error=%s",
            request_id,
            payload.user_id,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "message": "루틴 생성에 실패했습니다.",
                "reason": "primary_llm_parse_failed",
            },
        ) from exc

    detailed_days = _expand_profile_routine_days(payload, final_response, logger, request_id)
    final_response["weekly_routine"] = detailed_days
    final_response["pc3_payload"] = {
        **(final_response.get("pc3_payload") or {}),
        "weekly_routine": detailed_days,
    }

    routine_id = f"routine_{uuid4().hex[:12]}"
    start_date = _resolve_routine_start_date(payload)
    save_profile_routine(
        routine_id=routine_id,
        user_id=payload.user_id,
        profile_name=payload.profile_name,
        weight_kg=payload.weight_kg,
        user_goal=payload.user_goal,
        exercise_experience=payload.exercise_experience,
        available_days_per_week=payload.available_days_per_week,
        restricted_body_parts=payload.restricted_body_parts,
        purpose=payload.purpose,
        start_date=start_date,
        routine_response_json=final_response,
        source_model=llm_result["model_name"],
        llm_route=llm_result["served_by"],
    )
    scheduled_dates = save_profile_routine_days(
        routine_id=routine_id,
        user_id=payload.user_id,
        summary=final_response["summary"],
        weekly_focus=final_response["weekly_focus"],
        weekly_routine=detailed_days,
        start_date=start_date,
    )
    final_response["pc3_payload"] = {
        **(final_response.get("pc3_payload") or {}),
        "routine_id": routine_id,
        "start_date": start_date.isoformat(),
        "scheduled_dates": scheduled_dates,
    }

    logger.info(
        "profile_routine_request_success request_id=%s routine_id=%s user_id=%s route=%s days=%s",
        request_id,
        routine_id,
        payload.user_id,
        llm_result["served_by"],
        len(final_response.get("weekly_routine") or []),
    )
    return final_response


def get_profile_routine_record(user_id: str) -> dict:
    routine = get_latest_profile_routine(user_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="저장된 프로필 루틴을 찾지 못했습니다.")
    if hasattr(RoutineProfileRecord, "model_validate"):
        return RoutineProfileRecord.model_validate(routine).model_dump()
    return RoutineProfileRecord.parse_obj(routine).dict()


def get_profile_routine_day_record(user_id: str, target_date: date) -> dict:
    routine_day = get_profile_routine_day_by_date(user_id, target_date)
    if routine_day is None:
        raise HTTPException(status_code=404, detail="해당 날짜의 루틴을 찾지 못했습니다.")

    routine_day["message"] = _build_routine_day_message(routine_day)
    if hasattr(RoutineProfileDayRecord, "model_validate"):
        return RoutineProfileDayRecord.model_validate(routine_day).model_dump()
    return RoutineProfileDayRecord.parse_obj(routine_day).dict()
