from collections import Counter
from typing import Any

from app.schemas import (
    ExerciseBaselineDiff,
    ExerciseBaselineProfile,
    ExerciseFeature,
    FeaturePayload,
)


KNOWLEDGE_BASE: list[dict[str, Any]] = [
    {
        "id": "squat-stability-reset",
        "exercise_types": ["squat"],
        "signal_categories": ["stability", "knee", "back_posture"],
        "title": "스쿼트 안정성 회복 루틴",
        "content": "무릎 정렬과 몸통 고정을 우선하면 반복 수를 조금 줄여도 자세 품질을 안정화하기 쉽다.",
        "prescription": {"sets": 3, "reps": 8, "rest_sec": 75, "focus": "무릎과 발끝 정렬 유지"},
    },
    {
        "id": "squat-depth-drill",
        "exercise_types": ["squat"],
        "signal_categories": ["depth", "squat_depth"],
        "title": "스쿼트 깊이 보정 드릴",
        "content": "박스 스쿼트나 템포 스쿼트로 하강 구간을 천천히 가져가면 깊이와 균형을 같이 교정하기 좋다.",
        "prescription": {"sets": 3, "reps": 6, "rest_sec": 90, "focus": "하강 3초 유지"},
    },
    {
        "id": "tempo-control",
        "exercise_types": ["squat", "lunge", "pushup", "jumping_jack", "knee_raise"],
        "signal_categories": ["tempo"],
        "title": "속도 제어 세트",
        "content": "빠른 템포는 반동 보상을 만들기 쉬워서 의도적으로 속도를 늦춘 보정 세트를 포함하는 편이 안전하다.",
        "prescription": {"sets": 2, "reps": 5, "rest_sec": 60, "focus": "반동 없이 천천히 수행"},
    },
    {
        "id": "core-bracing",
        "exercise_types": ["squat", "lunge", "pushup", "knee_raise"],
        "signal_categories": ["back_posture"],
        "title": "코어 브레이싱 보조 루틴",
        "content": "상체 기울어짐이 커질 때는 본운동 볼륨을 약간 줄이고 코어 고정 과제를 먼저 넣는 편이 효율적이다.",
        "prescription": {"sets": 3, "duration_sec": 30, "rest_sec": 45, "focus": "복압 유지"},
    },
    {
        "id": "jumping-jack-rhythm",
        "exercise_types": ["jumping_jack"],
        "signal_categories": ["tempo", "exercise_duration", "exercise_record"],
        "title": "점핑잭 리듬 회복 루틴",
        "content": "점핑잭은 일정한 리듬과 착지 안정성이 중요하므로, 볼륨을 급히 늘리기보다 시간과 호흡 리듬을 먼저 맞추는 편이 좋다.",
        "prescription": {"sets": 3, "duration_sec": 40, "rest_sec": 30, "focus": "착지 리듬과 호흡 유지"},
    },
    {
        "id": "knee-raise-balance",
        "exercise_types": ["knee_raise"],
        "signal_categories": ["stability", "back_posture", "exercise_record"],
        "title": "니레이즈 균형 루틴",
        "content": "니레이즈는 상체 흔들림을 줄이고 무릎을 일정 높이까지 드는 반복 품질이 중요해서, 코어 고정과 균형 유지 중심으로 계획을 잡는 편이 효과적이다.",
        "prescription": {"sets": 3, "reps": 10, "rest_sec": 45, "focus": "상체 고정과 무릎 높이 일치"},
    },
    {
        "id": "pushup-volume-control",
        "exercise_types": ["pushup"],
        "signal_categories": ["stability", "exercise_record", "exercise_count"],
        "title": "푸쉬업 볼륨 조절 루틴",
        "content": "푸쉬업 반복 수가 baseline보다 내려갔으면 세트를 잘게 나눠 품질을 유지하면서 전체 볼륨을 회복하는 편이 낫다.",
        "prescription": {"sets": 4, "reps": 6, "rest_sec": 60, "focus": "몸통 일직선 유지"},
    },
    {
        "id": "lunge-balance-reset",
        "exercise_types": ["lunge"],
        "signal_categories": ["stability", "knee", "back_posture"],
        "title": "런지 균형 회복 루틴",
        "content": "런지는 좌우 밸런스와 무릎 정렬이 무너지기 쉬워서, 반복 수를 약간 낮추고 정렬 유지에 집중하는 것이 안전하다.",
        "prescription": {"sets": 3, "reps": 8, "rest_sec": 75, "focus": "좌우 균형과 무릎 정렬 유지"},
    },
    {
        "id": "general-volume-progress",
        "exercise_types": ["squat", "jumping_jack", "knee_raise", "lunge", "pushup"],
        "signal_categories": ["exercise_record", "exercise_count", "exercise_duration", "maintain"],
        "title": "기본 볼륨 진행 규칙",
        "content": "최근 기록이 baseline보다 낮으면 무리한 증량보다 baseline 수준 회복을 먼저 목표로 두는 편이 지속성이 높다.",
        "prescription": {"sets": 3, "reps": 8, "rest_sec": 60, "focus": "baseline 수준 회복"},
    },
]


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _average(values: list[float | None]) -> float | None:
    vals = []
    for value in values:
        if value is not None:
            vals.append(value)
    if not vals:
        return None
    return sum(vals) / len(vals)


def _mode(values: list[str]) -> str | None:
    vals = []
    for value in values:
        if value:
            vals.append(value)
    if not vals:
        return None
    return Counter(vals).most_common(1)[0][0]


def _avg_attr(samples: list[ExerciseFeature], name: str) -> float | None:
    vals = []
    for sample in samples:
        vals.append(_num(getattr(sample, name)))
    return _average(vals)


def _mode_back(samples: list[ExerciseFeature]) -> str | None:
    vals = []
    for sample in samples:
        if sample.back_angle is not None:
            vals.append(str(sample.back_angle).lower())
    return _mode(vals)


def _mode_tempo(samples: list[ExerciseFeature]) -> str | None:
    vals = []
    for sample in samples:
        if sample.tempo:
            vals.append(str(sample.tempo).lower())
    return _mode(vals)


def _top_errs(samples: list[ExerciseFeature]) -> list[str]:
    counts: Counter[str] = Counter()
    for sample in samples:
        for item in sample.posture_errors:
            if item:
                counts.update([str(item)])

    items = []
    for item, _ in counts.most_common(3):
        items.append(item)
    return items


def _diff_val(now: float | None, base: float | None) -> float | None:
    if now is None or base is None:
        return None
    return _round(now - base)


def _exercise_type_from_payload(payload: FeaturePayload) -> str:
    exercise = payload.features.exercise
    exercise_type = str(getattr(exercise, "type", "") or "").strip().lower()
    return exercise_type or ""


def build_baseline_profile(exercise_type: str, samples: list[ExerciseFeature]) -> ExerciseBaselineProfile:
    rep_values = []
    duration_values = []
    back_values = []
    tempo_values = []
    for sample in samples:
        rep_count = sample.rep_count if sample.rep_count is not None else sample.count
        duration = sample.duration_sec if sample.duration_sec is not None else sample.duration_seconds
        rep_values.append(_num(rep_count))
        duration_values.append(_num(duration))
        if sample.back_angle is not None:
            back_values.append(str(sample.back_angle).lower())
        if sample.tempo:
            tempo_values.append(str(sample.tempo).lower())

    rep_avg = _average(rep_values)
    dur_avg = _average(duration_values)
    stab_avg = _avg_attr(samples, "stability_score")
    knee_avg = _avg_attr(samples, "knee_angle")
    depth_avg = _avg_attr(samples, "squat_depth")
    back_mode = _mode(back_values)
    tempo_mode = _mode(tempo_values)
    top_errs = _top_errs(samples)

    rec_sets = 4 if (stab_avg or 0) >= 0.8 else 3
    rec_reps = max(6, min(15, int(round(rep_avg or 8))))
    rec_dur = max(20, min(180, int(round(dur_avg or 45))))

    return ExerciseBaselineProfile(
        exercise_type=exercise_type.lower(),
        sample_count=len(samples),
        rep_count_avg=_round(rep_avg),
        duration_sec_avg=_round(dur_avg),
        stability_score_avg=_round(stab_avg),
        knee_angle_avg=_round(knee_avg),
        squat_depth_avg=_round(depth_avg),
        back_angle_mode=back_mode,
        tempo_mode=tempo_mode,
        frequent_posture_errors=top_errs,
        recommended_sets=rec_sets,
        recommended_reps=rec_reps,
        recommended_duration_sec=rec_dur,
    )


def build_baseline_diff(
    feature: ExerciseFeature | None,
    baseline: ExerciseBaselineProfile | None,
) -> ExerciseBaselineDiff:
    if feature is None or baseline is None:
        return ExerciseBaselineDiff()

    rep_count = feature.rep_count if feature.rep_count is not None else feature.count
    duration = feature.duration_sec if feature.duration_sec is not None else feature.duration_seconds
    rep_count = _num(rep_count)
    duration = _num(duration)
    stability = _num(feature.stability_score)
    knee_angle = _num(feature.knee_angle)
    squat_depth = _num(feature.squat_depth)

    return ExerciseBaselineDiff(
        count_change=_diff_val(rep_count, baseline.rep_count_avg),
        stability_change=_diff_val(stability, baseline.stability_score_avg),
        knee_angle_change=_diff_val(knee_angle, baseline.knee_angle_avg),
        squat_depth_change=_diff_val(squat_depth, baseline.squat_depth_avg),
        duration_change=_diff_val(duration, baseline.duration_sec_avg),
    )


def retrieve_analysis_context(
    payload: FeaturePayload,
    signal_dicts: list[dict[str, Any]],
    baseline: ExerciseBaselineProfile | None,
) -> list[dict[str, Any]]:
    exercise_type = _exercise_type_from_payload(payload)
    categories = set()
    for item in signal_dicts:
        categories.add(str(item.get("category")))
    contexts: list[dict[str, Any]] = []

    if baseline is not None:
        contexts.append(
            {
                "source": "baseline_profile",
                "exercise_type": baseline.exercise_type,
                "content": {
                    "sample_count": baseline.sample_count,
                    "rep_count_avg": baseline.rep_count_avg,
                    "duration_sec_avg": baseline.duration_sec_avg,
                    "stability_score_avg": baseline.stability_score_avg,
                    "knee_angle_avg": baseline.knee_angle_avg,
                    "squat_depth_avg": baseline.squat_depth_avg,
                    "recommended_sets": baseline.recommended_sets,
                    "recommended_reps": baseline.recommended_reps,
                },
            }
        )

    scored_items: list[tuple[int, dict[str, Any]]] = []
    for entry in KNOWLEDGE_BASE:
        score = 0
        if exercise_type in entry["exercise_types"]:
            score += 3
        score += len(categories.intersection(entry["signal_categories"])) * 2
        if score > 0:
            scored_items.append((score, entry))

    top_items = sorted(scored_items, key=lambda item: item[0], reverse=True)[:3]
    for _, entry in top_items:
        contexts.append(
            {
                "source": "rag_knowledge",
                "knowledge_id": entry["id"],
                "title": entry["title"],
                "content": entry["content"],
                "prescription": entry["prescription"],
            }
        )

    if not contexts:
        contexts.append(
            {
                "source": "rag_knowledge",
                "knowledge_id": "general-default",
                "title": "기본 유지 루틴",
                "content": "현재 신호가 크지 않으면 baseline을 넘지 않는 범위에서 볼륨을 유지하고 자세 일관성을 우선한다.",
                "prescription": {"sets": 3, "reps": 8, "rest_sec": 60, "focus": "폼 유지"},
            }
        )
    return contexts
