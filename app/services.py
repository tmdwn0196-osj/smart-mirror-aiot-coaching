from datetime import date, timedelta
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException

from app.config import (
    PRIMARY_LLM_TIMEOUT_SECONDS,
    REQUEST_DEADLINE_SECONDS,
    ROUTINE_PROFILE_MAX_TOKENS,
    ROUTINE_PROFILE_TIMEOUT_SECONDS,
)
from app.db import (
    get_profile_routine_day_by_date,
    get_routine_calendar,
    get_user_history_snapshot,
    save_coach_log,
    save_profile_routine,
    save_profile_routine_days,
    save_workout_result,
    upsert_user_profile,
)
from app.llm_client import call_primary_llm, is_primary_llm_configured
from app.output_validator import parse_coaching_json, parse_profile_routine_json
from app.prompt_manager import build_coach_prompt, build_profile_routine_prompt
from app.rag import retrieve_coach_evidence, retrieve_routine_evidence
from app.schemas import FeaturePayload, RoutineProfileDayRecord, RoutineProfileRequest, WorkoutSkipRequest


EXPECTED_EVENT = "session_completed"


def dump_model(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


def _resolve_routine_start_date(payload: RoutineProfileRequest) -> date:
    return payload.start_date or date.today()


def _build_scheduled_dates(start_date: date, available_days_per_week: int, weekly_routine: list[dict]) -> list[str]:
    routine_days = weekly_routine or []
    if available_days_per_week <= 4:
        day_offsets = [index * 2 for index, _ in enumerate(routine_days)]
    else:
        day_offsets = list(range(len(routine_days)))
    return [(start_date + timedelta(days=offset)).isoformat() for offset in day_offsets]


def _remaining_seconds(started_at: float, limit_seconds: float, reserve_seconds: float = 0.5) -> float:
    elapsed = perf_counter() - started_at
    return max(0.0, limit_seconds - elapsed - reserve_seconds)


def _build_routine_day_message(day: dict) -> str:
    exercise_names = [
        str(item.get("exercise") or "").strip()
        for item in day.get("exercises") or []
        if item.get("exercise")
    ]
    if not exercise_names:
        return f"오늘은 {day.get('focus') or '운동'} 루틴을 진행할 예정입니다."
    exercise_line = ", ".join(exercise_names[:2])
    return f"오늘은 {day.get('focus') or '운동'} 루틴입니다. {exercise_line}부터 진행하세요."


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


def _history_summary(history: dict) -> dict:
    metrics = history.get("body_metrics") or []
    workouts = history.get("workout_results") or []
    coaching = history.get("coach_logs") or []
    latest_routine = history.get("latest_routine") or {}
    latest_metric = metrics[0] if metrics else {}
    return {
        "body_metric_count": len(metrics),
        "recent_workout_count": len(workouts),
        "recent_coaching_count": len(coaching),
        "latest_weight_kg": latest_metric.get("weight_kg"),
        "latest_weight_date": latest_metric.get("measured_date"),
        "latest_routine_id": latest_routine.get("routine_id"),
    }


def _build_user_history_block(history: dict) -> str:
    metrics = history.get("body_metrics") or []
    workouts = history.get("workout_results") or []
    coaching = history.get("coach_logs") or []
    latest_routine = history.get("latest_routine") or {}
    if not (metrics or workouts or coaching or latest_routine):
        return "[USER_HISTORY]\nNo prior user history was found."

    lines = ["[USER_HISTORY]"]
    if metrics:
        metric_line = "; ".join(
            f"{item.get('measured_date')} weight={item.get('weight_kg')}kg"
            for item in metrics[:5]
        )
        lines.append(f"body_metrics: {metric_line}")
    if workouts:
        workout_parts = []
        for item in workouts[:10]:
            workout_parts.append(
                f"{item.get('exercise_type')} reps={item.get('completed_reps')} "
                f"duration={item.get('duration_sec')} stability={item.get('stability_score')} "
                f"errors={item.get('posture_errors')}"
            )
        lines.append("recent_workouts: " + "; ".join(workout_parts))
    if coaching:
        coaching_parts = []
        for item in coaching[:5]:
            final_response = item.get("final_response") or {}
            coaching_parts.append(
                f"summary={final_response.get('summary')} priority={final_response.get('priority')}"
            )
        lines.append("recent_coaching: " + "; ".join(coaching_parts))
    if latest_routine:
        lines.append(
            f"latest_routine: id={latest_routine.get('routine_id')} "
            f"goal={latest_routine.get('user_goal')} start={latest_routine.get('start_date')}"
        )
    return "\n".join(lines)


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _restricted_tokens(parts: list[str]) -> set[str]:
    token_map = {
        "knee": {"knee", "무릎", "valgus"},
        "무릎": {"knee", "무릎", "valgus"},
        "back": {"back", "허리", "trunk", "spine"},
        "허리": {"back", "허리", "trunk", "spine"},
        "shoulder": {"shoulder", "어깨"},
        "어깨": {"shoulder", "어깨"},
        "ankle": {"ankle", "발목", "landing"},
        "발목": {"ankle", "발목", "landing"},
    }
    tokens: set[str] = set()
    for part in parts:
        key = str(part or "").strip().lower()
        tokens.update(token_map.get(key, {key}))
    return {token for token in tokens if token}


def _build_weekly_adjustment(payload: RoutineProfileRequest, history: dict) -> dict:
    anchor = min(_resolve_routine_start_date(payload), date.today())
    from_date = anchor - timedelta(days=13)
    days = history.get("calendar_days") or []
    if not days:
        calendar = get_routine_calendar(payload.user_id, from_date, anchor)
        days = calendar.get("days") or []
    planned_days = [day for day in days if day.get("routine_id")]
    completed_days = [day for day in planned_days if day.get("completed")]
    completion_rate = (len(completed_days) / len(planned_days)) if planned_days else 0.0

    workouts = [
        workout
        for day in days
        for workout in (day.get("workout_results") or [])
        if isinstance(workout, dict)
    ]
    if not workouts:
        workouts = history.get("workout_results") or []

    stability_values = [
        value
        for value in (_safe_float(item.get("stability_score")) for item in workouts)
        if value is not None
    ]
    avg_stability = sum(stability_values) / len(stability_values) if stability_values else None

    error_counts: dict[str, int] = {}
    for workout in workouts:
        for error in workout.get("posture_errors") or []:
            key = str(error or "").strip().lower()
            if key:
                error_counts[key] = error_counts.get(key, 0) + 1
    repeated_errors = [key for key, count in error_counts.items() if count >= 2]

    warning_texts: list[str] = []
    for log in history.get("coach_logs") or []:
        final_response = log.get("final_response") or {}
        warning_texts.extend(str(item).lower() for item in final_response.get("warnings") or [])
        warning_texts.append(str(final_response.get("summary") or "").lower())
        warning_texts.append(str(final_response.get("mirror_message") or "").lower())

    restricted = _restricted_tokens(payload.restricted_body_parts)
    pain_tokens = {"pain", "통증", "sharp", "dizziness", "어지러", "breathing", "호흡"}
    joined_errors = " ".join(error_counts)
    joined_warnings = " ".join(warning_texts)
    pain_tokens = {"pain", "sharp", "dizziness", "unstable", "instability"}
    restricted_hits = bool(restricted and any(token in joined_errors for token in restricted))
    restricted_warning_hits = bool(
        restricted
        and any(token in joined_warnings for token in restricted)
        and any(token in joined_warnings for token in pain_tokens)
    )
    pain_hits = any(token in joined_errors for token in pain_tokens) or restricted_warning_hits

    metrics = history.get("body_metrics") or []
    weight_delta = None
    if len(metrics) >= 2:
        latest = _safe_float(metrics[0].get("weight_kg"))
        oldest = _safe_float(metrics[-1].get("weight_kg"))
        if latest is not None and oldest is not None:
            weight_delta = round(latest - oldest, 2)

    direction = "hold"
    volume_change_percent = 0
    reasons: list[str] = []
    focus_cues: list[str] = []

    if not planned_days and not workouts:
        reasons.append("최근 14일 운동 기록이 부족해 강도를 보수적으로 유지합니다.")
        focus_cues.append("새 주간 루틴은 낮은 강도에서 자세 안정성을 먼저 확인합니다.")
    elif restricted_hits or pain_hits:
        direction = "hold_or_decrease"
        volume_change_percent = -10
        reasons.append("제한 부위나 통증 관련 신호가 반복되어 강도를 낮춥니다.")
        focus_cues.append("통증이 있으면 즉시 중단하고 대체 동작 또는 짧은 범위로 진행합니다.")
    elif repeated_errors:
        direction = "hold_or_decrease"
        volume_change_percent = 0
        reasons.append("자세 오류가 반복되어 이번 주에는 강도 증가를 막습니다.")
        focus_cues.append("반복 오류: " + ", ".join(repeated_errors[:3]))
    elif planned_days and completion_rate < 0.5:
        direction = "decrease"
        volume_change_percent = -20 if completion_rate < 0.25 else -10
        reasons.append("최근 계획 대비 완료율이 낮아 운동량을 줄입니다.")
        focus_cues.append("완료 가능한 세트 수를 우선하고 휴식 시간을 충분히 둡니다.")
    elif planned_days and completion_rate >= 0.8 and avg_stability is not None and avg_stability >= 0.8:
        direction = "increase"
        volume_change_percent = 10 if completion_rate >= 1.0 and avg_stability >= 0.88 else 5
        reasons.append("최근 완료율과 자세 안정성이 좋아 소폭 증량합니다.")
        focus_cues.append("자세가 흔들리면 즉시 이전 강도로 되돌립니다.")
    else:
        reasons.append("최근 기록이 중간 수준이라 현재 강도를 유지합니다.")
        focus_cues.append("완료율과 자세 안정성을 먼저 쌓습니다.")

    if payload.user_goal == "weight_management" and weight_delta is not None and abs(weight_delta) < 0.3:
        reasons.append("몸무게 변화가 작아 유산소성 운동 비중을 조금 늘립니다.")
        focus_cues.append("점핑잭이나 니레이즈는 호흡이 무너지지 않는 범위로 배치합니다.")

    return {
        "direction": direction,
        "volume_change_percent": volume_change_percent,
        "reasons": reasons[:4],
        "focus_cues": focus_cues[:4],
    }


def _build_weekly_adjustment_block(adjustment: dict) -> str:
    return (
        "[WEEKLY_ADJUSTMENT]\n"
        f"direction={adjustment.get('direction')} "
        f"volume_change_percent={adjustment.get('volume_change_percent')}\n"
        "reasons: " + "; ".join(str(item) for item in adjustment.get("reasons") or []) + "\n"
        "focus_cues: " + "; ".join(str(item) for item in adjustment.get("focus_cues") or [])
    )


def _korean_routine_day_message(day: dict) -> str:
    exercise_names = [
        str(item.get("exercise") or "").strip()
        for item in day.get("exercises") or []
        if item.get("exercise")
    ]
    if not exercise_names:
        return f"오늘은 {day.get('focus') or '운동'} 루틴을 진행할 예정입니다."
    exercise_line = ", ".join(exercise_names[:2])
    return f"오늘은 {day.get('focus') or '운동'} 루틴입니다. {exercise_line}부터 진행하세요."


def _korean_restriction_cautions(restricted_body_parts: list[str]) -> list[str]:
    label_map = {
        "knee": "무릎",
        "back": "허리/등",
        "shoulder": "어깨",
        "ankle": "발목",
    }
    cautions: list[str] = []
    for part in restricted_body_parts:
        name = label_map.get(str(part or "").strip(), str(part or "").strip())
        if not name:
            continue
        cautions.append(f"{name} 부위에 통증이 있으면 즉시 강도를 낮추세요.")
        if len(cautions) >= 3:
            break
    return cautions


def _localize_weekly_adjustment(adjustment: dict, payload: RoutineProfileRequest) -> dict:
    direction = adjustment.get("direction") or "hold"
    percent = int(adjustment.get("volume_change_percent") or 0)
    if direction == "increase":
        reasons = ["최근 완료율과 자세 안정성이 좋아 다음 주 운동량을 조금 올립니다."]
        focus_cues = ["자세가 흔들리면 즉시 이전 강도로 되돌립니다."]
    elif direction == "decrease":
        reasons = ["최근 완료율이 낮아 다음 주 운동량을 줄입니다."]
        focus_cues = ["완료 가능한 세트 수를 우선하고 휴식 시간을 충분히 둡니다."]
    elif direction == "hold_or_decrease":
        reasons = ["자세 오류나 제한 부위 신호가 있어 강도 증가는 보류합니다."]
        focus_cues = ["통증이 있으면 즉시 중단하고 대체 동작 또는 짧은 범위로 진행합니다."]
    else:
        reasons = ["최근 기록을 기준으로 현재 강도를 유지합니다."]
        focus_cues = ["완료율과 자세 안정성을 먼저 쌓습니다."]
    if payload.user_goal == "weight_management":
        reasons.append("체중 관리 목표가 있어 유산소성 동작 비중을 함께 고려합니다.")
        focus_cues.append("점핑잭과 니 레이즈는 호흡이 무너지지 않는 범위로 배치합니다.")
    return {
        **adjustment,
        "direction": direction,
        "volume_change_percent": percent,
        "reasons": reasons[:4],
        "focus_cues": focus_cues[:4],
    }


def _save_completed_workout(payload: FeaturePayload, request_payload: dict, final_response: dict) -> int:
    exercise = ((request_payload.get("features") or {}).get("exercise") or {})
    exercise_type = exercise.get("type") or "unknown"
    completed_reps = exercise.get("count")
    if completed_reps is None:
        completed_reps = exercise.get("rep_count")
    duration_sec = exercise.get("duration_sec")
    if duration_sec is None:
        duration_sec = exercise.get("duration_seconds")
    result_json = {
        "summary": final_response.get("summary"),
        "priority": final_response.get("priority"),
        "warnings": final_response.get("warnings") or [],
        "pc2_payload": final_response.get("pc2_payload") or {},
        "baseline_diff": request_payload.get("baseline_diff") or {},
    }
    return save_workout_result(
        session_id=payload.session_id or f"session_{uuid4().hex[:12]}",
        user_id=payload.user_id,
        routine_id=payload.routine_id,
        routine_day_id=str(payload.routine_day_id) if payload.routine_day_id is not None else None,
        exercise_type=exercise_type,
        completed_reps=int(completed_reps) if completed_reps is not None else None,
        duration_sec=float(duration_sec) if duration_sec is not None else None,
        stability_score=exercise.get("stability_score"),
        posture_errors=exercise.get("posture_errors") or [],
        measurement_quality=exercise.get("measurement_quality"),
        measurement_confidence=exercise.get("measurement_confidence"),
        result_json=result_json,
    )


def save_skipped_workout(payload: WorkoutSkipRequest) -> dict:
    data = dump_model(payload)
    result_json = {
        "status": "skipped",
        "skip_reason": payload.skip_reason or "사용자가 운동을 넘김",
    }
    record_id = save_workout_result(
        session_id=payload.session_id,
        user_id=payload.user_id,
        routine_id=payload.routine_id,
        routine_day_id=str(payload.routine_day_id) if payload.routine_day_id is not None else None,
        exercise_type=payload.exercise_type,
        completed_reps=payload.completed_reps,
        duration_sec=payload.duration_sec,
        stability_score=payload.stability_score,
        posture_errors=payload.posture_errors,
        measurement_quality=payload.measurement_quality,
        measurement_confidence=payload.measurement_confidence,
        result_json=result_json,
    )
    return {
        "id": record_id,
        "status": "skipped",
        "skip_reason": result_json["skip_reason"],
        **data,
    }


def validate_trigger(payload: FeaturePayload) -> None:
    if payload.event != EXPECTED_EVENT:
        raise HTTPException(
            status_code=422,
            detail=f"exercise mode only supports the {EXPECTED_EVENT} event.",
        )


def _primary_unavailable(reason: str, error: str | None = None) -> HTTPException:
    detail = {"reason": reason}
    if error:
        detail["error"] = error
    return HTTPException(status_code=503, detail=detail)


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
    validate_trigger(payload)

    request_payload = dump_model(payload)
    base_response = {
        "summary": "",
        "priority": "",
        "exercise_plan": [],
        "mirror_message": "",
        "warnings": [],
        "pc2_payload": {"message": "", "display_lines": []},
        "evidence": [],
    }

    try:
        evidence_block, evidence = retrieve_coach_evidence(request_payload)
        base_response["evidence"] = evidence
    except Exception as exc:
        logger.warning(
            "coach_request_failed request_id=%s user_id=%s reason=rag_unavailable error=%s",
            request_id,
            payload.user_id,
            exc,
        )
        raise _primary_unavailable("rag_unavailable", str(exc)) from exc

    system_prompt, user_prompt = build_coach_prompt(request_payload, evidence_block)
    llm_prompt = f"{system_prompt}\n\n{user_prompt}"

    if not is_primary_llm_configured():
        logger.warning(
            "coach_request_failed request_id=%s user_id=%s reason=primary_llm_unconfigured",
            request_id,
            payload.user_id,
        )
        raise _primary_unavailable("primary_llm_unconfigured")

    try:
        llm_started_at = perf_counter()
        llm_result = call_primary_llm(system_prompt, user_prompt)
        llm_ms = int((perf_counter() - llm_started_at) * 1000)
        raw_llm = llm_result["content"]
    except Exception as exc:
        logger.warning(
            "coach_request_failed request_id=%s user_id=%s reason=primary_llm_call_failed error=%s",
            request_id,
            payload.user_id,
            exc,
        )
        raise _primary_unavailable("primary_llm_call_failed", str(exc)) from exc

    try:
        final_response = parse_coaching_json(raw_llm, base_response)
    except Exception as exc:
        retry_remaining = _remaining_seconds(started_at, REQUEST_DEADLINE_SECONDS)
        if retry_remaining <= 0.75:
            logger.warning(
                "coach_request_failed request_id=%s user_id=%s reason=primary_llm_parse_failed error=%s",
                request_id,
                payload.user_id,
                exc,
            )
            raise _primary_unavailable("primary_llm_parse_failed", str(exc)) from exc
        try:
            retry_started_at = perf_counter()
            retry_prompt = (
                user_prompt
                + "\n\nPrevious response was invalid. Return the same JSON keys, but rewrite every user-visible natural-language value in Korean."
            )
            retry_result = call_primary_llm(
                system_prompt,
                retry_prompt,
                timeout_seconds=min(PRIMARY_LLM_TIMEOUT_SECONDS, retry_remaining),
            )
            raw_llm = retry_result["content"]
            llm_ms += int((perf_counter() - retry_started_at) * 1000)
            llm_result = retry_result
            final_response = parse_coaching_json(raw_llm, base_response)
        except Exception as retry_exc:
            logger.warning(
                "coach_request_failed request_id=%s user_id=%s reason=primary_llm_parse_failed error=%s",
                request_id,
                payload.user_id,
                retry_exc,
            )
            raise _primary_unavailable("primary_llm_parse_failed", str(retry_exc)) from retry_exc

    latency_ms = int((perf_counter() - started_at) * 1000)
    logger.info(
        "coach_request_success request_id=%s user_id=%s model=%s llm_latency_ms=%s latency_ms=%s",
        request_id,
        payload.user_id,
        llm_result["model_name"],
        llm_ms,
        latency_ms,
    )
    return final_response


def generate_profile_routine_response(payload: RoutineProfileRequest, logger) -> dict:
    started_at = perf_counter()
    request_id = f"profile_{uuid4().hex[:12]}"
    logger.info(
        "profile_routine_request_start request_id=%s user_id=%s days=%s",
        request_id,
        payload.user_id,
        payload.available_days_per_week,
    )

    request_payload = dump_model(payload)
    history = payload.user_history if isinstance(payload.user_history, dict) else get_user_history_snapshot(payload.user_id)
    raw_adjustment = payload.weekly_adjustment if isinstance(payload.weekly_adjustment, dict) else _build_weekly_adjustment(payload, history)
    weekly_adjustment = _localize_weekly_adjustment(raw_adjustment, payload)
    base_response = {
        "summary": "",
        "weekly_focus": "",
        "weekly_routine": [],
        "cautions": _korean_restriction_cautions(payload.restricted_body_parts),
        "available_days_per_week": payload.available_days_per_week,
        "restricted_body_parts": payload.restricted_body_parts,
        "pc3_payload": {},
        "evidence": [],
        "history_summary": _history_summary(history),
        "weekly_adjustment": weekly_adjustment,
    }
    try:
        evidence_block, evidence = retrieve_routine_evidence(request_payload)
        base_response["evidence"] = evidence
    except Exception as exc:
        logger.warning(
            "profile_routine_request_failed request_id=%s user_id=%s reason=rag_unavailable error=%s",
            request_id,
            payload.user_id,
            exc,
        )
        raise _primary_unavailable("rag_unavailable", str(exc)) from exc

    history_block = _build_user_history_block(history)
    weekly_adjustment_block = _build_weekly_adjustment_block(weekly_adjustment)
    system_prompt, user_prompt = build_profile_routine_prompt(
        request_payload,
        evidence_block,
        history_block,
        weekly_adjustment_block,
    )

    if not is_primary_llm_configured():
        logger.warning(
            "profile_routine_request_failed request_id=%s user_id=%s reason=primary_llm_unconfigured",
            request_id,
            payload.user_id,
        )
        raise _primary_unavailable("primary_llm_unconfigured")

    try:
        llm_result = call_primary_llm(
            system_prompt,
            user_prompt,
            max_tokens=ROUTINE_PROFILE_MAX_TOKENS,
            timeout_seconds=min(ROUTINE_PROFILE_TIMEOUT_SECONDS, REQUEST_DEADLINE_SECONDS - 1.0),
        )
        raw_llm = llm_result["content"]
        try:
            final_response = parse_profile_routine_json(raw_llm, base_response)
        except Exception as exc:
            retry_remaining = _remaining_seconds(started_at, REQUEST_DEADLINE_SECONDS)
            if retry_remaining <= 0.75:
                raise exc
            retry_result = call_primary_llm(
                system_prompt,
                user_prompt
                + "\n\nPrevious response was invalid. Return the same JSON keys, but rewrite every user-visible natural-language value in Korean.",
                max_tokens=ROUTINE_PROFILE_MAX_TOKENS,
                timeout_seconds=min(ROUTINE_PROFILE_TIMEOUT_SECONDS, retry_remaining),
            )
            llm_result = retry_result
            raw_llm = retry_result["content"]
            final_response = parse_profile_routine_json(raw_llm, base_response)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "profile_routine_request_failed request_id=%s user_id=%s reason=primary_llm_failed error=%s",
            request_id,
            payload.user_id,
            exc,
        )
        raise _primary_unavailable("primary_llm_failed", str(exc)) from exc

    routine_id = f"routine_{uuid4().hex[:12]}"
    start_date = _resolve_routine_start_date(payload)
    scheduled_dates = _build_scheduled_dates(
        start_date,
        payload.available_days_per_week,
        final_response.get("weekly_routine") or [],
    )
    final_response["pc3_payload"] = {
        **(final_response.get("pc3_payload") or {}),
        "routine_id": routine_id,
        "start_date": start_date.isoformat(),
        "scheduled_dates": scheduled_dates,
        "weekly_adjustment": weekly_adjustment,
    }

    logger.info(
        "profile_routine_request_success request_id=%s routine_id=%s user_id=%s model=%s days=%s",
        request_id,
        routine_id,
        payload.user_id,
        llm_result["model_name"],
        len(final_response.get("weekly_routine") or []),
    )
    return final_response


def get_profile_routine_day_record(user_id: str, target_date: date) -> dict:
    routine_day = get_profile_routine_day_by_date(user_id, target_date)
    if routine_day is None:
        raise HTTPException(status_code=404, detail="해당 날짜의 루틴을 찾지 못했습니다.")

    routine_day["message"] = _korean_routine_day_message(routine_day)
    if hasattr(RoutineProfileDayRecord, "model_validate"):
        return RoutineProfileDayRecord.model_validate(routine_day).model_dump()
    return RoutineProfileDayRecord.parse_obj(routine_day).dict()
