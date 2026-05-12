from typing import Any

from app.schemas import DetectedSignal, ExerciseBaselineProfile, FeaturePayload


KNEE_ERRS = {"knees_caving_in", "knee_valgus", "knees_in"}
BAD_BACK = {"forward", "rounded", "bent"}
FAST_TEMPO = {"fast", "too_fast"}
LEG_EXS = {"squat", "lunge"}


def _dump_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _append_part(parts: list[str], label: str, value: Any, suffix: str = "") -> None:
    if value is None or value == "" or value == []:
        return
    if isinstance(value, list):
        items = []
        for item in value:
            if item is not None:
                items.append(str(item))
        value = " ".join(items)
    parts.append(f"{label} {value}{suffix}".strip())


def build_query_text(payload: FeaturePayload, baseline: ExerciseBaselineProfile | None = None) -> str:
    exercise = payload.features.exercise
    baseline_diff = payload.baseline_diff.exercise
    environment = payload.environment
    parts = ["mode exercise"]

    if exercise is not None:
        rep_count = exercise.rep_count if exercise.rep_count is not None else exercise.count
        duration = exercise.duration_sec if exercise.duration_sec is not None else exercise.duration_seconds
        _append_part(parts, "exercise", exercise.type)
        _append_part(parts, "knee angle", exercise.knee_angle)
        _append_part(parts, "back angle", exercise.back_angle)
        _append_part(parts, "rep count", rep_count)
        _append_part(parts, "duration", duration, " sec")
        _append_part(parts, "stability score", exercise.stability_score)
        _append_part(parts, "squat depth", exercise.squat_depth)
        _append_part(parts, "tempo", exercise.tempo)
        _append_part(parts, "posture errors", exercise.posture_errors)

    if baseline_diff is not None:
        _append_part(parts, "count baseline change", baseline_diff.count_change)
        _append_part(parts, "stability baseline change", baseline_diff.stability_change)
        _append_part(parts, "knee angle baseline change", baseline_diff.knee_angle_change)
        _append_part(parts, "depth baseline change", baseline_diff.squat_depth_change)

    if baseline is not None:
        _append_part(parts, "baseline reps", baseline.rep_count_avg)
        _append_part(parts, "baseline duration", baseline.duration_sec_avg, " sec")
        _append_part(parts, "baseline stability", baseline.stability_score_avg)

    if environment is not None:
        _append_part(parts, "temperature", environment.temperature)
        _append_part(parts, "humidity", environment.humidity)
        _append_part(parts, "illuminance", environment.illuminance)
    _append_part(parts, "purpose", payload.purpose)
    return ", ".join(parts)


def detect_signals(payload: FeaturePayload) -> list[DetectedSignal]:
    exercise = payload.features.exercise
    baseline_diff = payload.baseline_diff.exercise
    environment = payload.environment
    signals: list[DetectedSignal] = []

    if exercise is not None:
        exercise_type = str(exercise.type or "")
        posture_errors = set()
        for item in exercise.posture_errors:
            posture_errors.add(str(item))
        knee_hits = sorted(posture_errors & KNEE_ERRS)
        if exercise_type in LEG_EXS and knee_hits:
            signals.append(
                DetectedSignal(
                    category="knee",
                    label="무릎 정렬 오류",
                    value=knee_hits,
                    severity=3,
                )
            )
        stability = _num(exercise.stability_score)
        if stability is not None and stability < 0.70:
            signals.append(
                DetectedSignal(category="stability", label="안정성 점수 낮음", value=stability, severity=2)
            )
        depth = _num(exercise.squat_depth)
        if exercise_type == "squat" and depth is not None and depth < 0.55:
            signals.append(DetectedSignal(category="depth", label="스쿼트 깊이가 얕음", value=depth, severity=2))
        knee_angle = _num(exercise.knee_angle)
        if exercise_type in LEG_EXS and knee_angle is not None and not 80 <= knee_angle <= 110:
            signals.append(
                DetectedSignal(category="squat_depth", label="무릎 각도 기준 범위 이탈", value=knee_angle, severity=2)
            )
        back_angle = str(exercise.back_angle or "").lower()
        if back_angle in BAD_BACK:
            signals.append(
                DetectedSignal(
                    category="back_posture",
                    label="상체가 앞으로 기울어짐",
                    value=exercise.back_angle,
                    severity=2,
                )
            )
        tempo = str(exercise.tempo or "").lower()
        if tempo in FAST_TEMPO:
            signals.append(DetectedSignal(category="tempo", label="동작 속도가 빠름", value=exercise.tempo, severity=2))
        rep_count = exercise.rep_count if exercise.rep_count is not None else exercise.count
        rep_count = _num(rep_count)
        if rep_count is not None:
            signals.append(
                DetectedSignal(category="exercise_count", label="운동 반복 횟수 감지", value=int(rep_count), severity=1)
            )
        duration = exercise.duration_sec if exercise.duration_sec is not None else exercise.duration_seconds
        duration = _num(duration)
        if duration is not None:
            signals.append(
                DetectedSignal(category="exercise_duration", label="운동 지속시간 감지", value=duration, severity=1)
            )

    if baseline_diff is not None:
        if baseline_diff.count_change is not None and baseline_diff.count_change < 0:
            signals.append(
                DetectedSignal(
                    category="exercise_record",
                    label="baseline 대비 운동 횟수 감소",
                    value=baseline_diff.count_change,
                    severity=1,
                )
            )
        if baseline_diff.stability_change is not None and baseline_diff.stability_change < -0.03:
            signals.append(
                DetectedSignal(
                    category="stability",
                    label="baseline 대비 안정성 하락",
                    value=baseline_diff.stability_change,
                    severity=2,
                )
            )

    if environment is not None:
        illuminance = _num(environment.illuminance)
        if illuminance is not None and illuminance < 150:
            signals.append(DetectedSignal(category="illuminance", label="조도 낮음", value=illuminance, severity=1))
        humidity = _num(environment.humidity)
        if humidity is not None and humidity >= 75:
            signals.append(DetectedSignal(category="humidity", label="습도 높음", value=humidity, severity=1))

    if not signals:
        signals.append(DetectedSignal(category="maintain", label="큰 이상 신호 없음", value=None, severity=1))
    return signals


def compact_for_prompt(
    payload: FeaturePayload,
    signals: list[DetectedSignal],
    *,
    query_text: str | None = None,
    baseline: ExerciseBaselineProfile | None = None,
    analysis_context: list[dict[str, Any]] | None = None,
    latest_profile_routine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feature_json = {
        "features": _dump_model(payload.features),
        "baseline_diff": _dump_model(payload.baseline_diff),
    }
    if payload.environment is not None:
        feature_json["environment"] = _dump_model(payload.environment)

    signal_data = []
    for signal in signals[:8]:
        signal_data.append(
            {
                "category": signal.category,
                "label": signal.label,
                "value": signal.value,
                "severity": signal.severity,
            }
        )

    return {
        "mode": payload.mode,
        "event": payload.event,
        "purpose": payload.purpose,
        "feature_summary": query_text or build_query_text(payload, baseline=baseline),
        "feature_json": feature_json,
        "baseline_profile": _dump_model(baseline) if baseline is not None else None,
        "latest_profile_routine": latest_profile_routine,
        "analysis_context": analysis_context or [],
        "detected_signals": signal_data,
    }


def dump_signals(signals: list[DetectedSignal]) -> list[dict[str, Any]]:
    data = []
    for sig in signals:
        data.append(_dump_model(sig))
    return data
