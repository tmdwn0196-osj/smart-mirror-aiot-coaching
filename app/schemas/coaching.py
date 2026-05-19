from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


EXERCISE_TYPE_VALUES = ("squat", "jumping_jack", "knee_raise", "lunge", "pushup")
EXERCISE_TYPE_ALIASES = {
    "squat": "squat",
    "tempo squat": "squat",
    "box squat": "squat",
    "jumping_jack": "jumping_jack",
    "jumping jack": "jumping_jack",
    "jumping-jack": "jumping_jack",
    "knee_raise": "knee_raise",
    "knee raise": "knee_raise",
    "knee-raise": "knee_raise",
    "knee raises": "knee_raise",
    "lunge": "lunge",
    "reverse lunge": "lunge",
    "pushup": "pushup",
    "push-up": "pushup",
    "push up": "pushup",
    "pushups": "pushup",
}

CoachMode = Literal["exercise"]
CoachEvent = Literal["session_completed"]
ExerciseType = Literal["squat", "jumping_jack", "knee_raise", "lunge", "pushup"]


def normalize_exercise_type_name(name: str) -> str | None:
    return EXERCISE_TYPE_ALIASES.get(str(name or "").strip().lower())


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExerciseFeature(ContractModel):
    type: ExerciseType | None = None
    count: int | None = None
    rep_count: int | None = None
    state: str | None = None
    stability_score: float | None = None
    posture_errors: list[str] = Field(default_factory=list)
    squat_depth: float | None = None
    knee_angle: float | None = None
    back_angle: float | str | None = None
    duration_sec: float | None = None
    duration_seconds: float | None = None
    tempo: str | None = None
    measurement_quality: str | None = None
    measurement_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class FeatureBundle(ContractModel):
    exercise: ExerciseFeature | None = None


class ExerciseBaselineDiff(ContractModel):
    count_change: float | None = None
    stability_change: float | None = None
    knee_angle_change: float | None = None
    squat_depth_change: float | None = None
    duration_change: float | None = None


class BaselineDiff(ContractModel):
    exercise: ExerciseBaselineDiff | None = None


class EnvironmentFeature(ContractModel):
    temperature: float | None = None
    humidity: float | None = None
    illuminance: float | None = None


class FeaturePayload(ContractModel):
    user_id: str
    session_id: str | None = None
    routine_id: str | None = None
    routine_day_id: str | int | None = None
    mode: CoachMode = "exercise"
    event: CoachEvent
    features: FeatureBundle = Field(default_factory=FeatureBundle)
    baseline_diff: BaselineDiff = Field(default_factory=BaselineDiff)
    environment: EnvironmentFeature | None = None
    purpose: str | None = None

    @model_validator(mode="after")
    def validate_exercise_payload(self):
        if self.mode == "exercise":
            if self.features.exercise is None:
                raise ValueError("features.exercise is required for exercise mode.")
            if not self.features.exercise.type:
                raise ValueError("features.exercise.type is required for exercise mode.")
        return self


class ExercisePlanItem(ContractModel):
    exercise: str
    sets: int = Field(ge=1, le=10)
    reps: int | None = Field(default=None, ge=1, le=100)
    duration_sec: int | None = Field(default=None, ge=10, le=7200)
    rest_sec: int | None = Field(default=None, ge=0, le=600)
    focus: str
    reason: str
    how_to: str = ""
    tips: str = ""


class PC2Payload(ContractModel):
    message: str
    display_lines: list[str] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)


class CoachingResponse(ContractModel):
    summary: str
    priority: str
    exercise_plan: list[ExercisePlanItem]
    mirror_message: str
    warnings: list[str] = Field(default_factory=list)
    pc2_payload: PC2Payload


class RoutineProfileRequest(ContractModel):
    user_id: str
    profile_name: str | None = None
    weight_kg: float | None = Field(default=None, ge=1, le=500)
    user_goal: str = Field(min_length=1)
    exercise_experience: str = Field(min_length=1)
    available_days_per_week: int = Field(ge=1, le=7)
    restricted_body_parts: list[str] = Field(default_factory=list)
    purpose: str | None = None
    start_date: date | None = None
    user_history: dict | None = None
    weekly_adjustment: dict | None = None


class WeeklyRoutineDay(ContractModel):
    day_index: int = Field(ge=1, le=7)
    day_label: str
    focus: str
    exercises: list[ExercisePlanItem] = Field(default_factory=list)


class RoutineProfileResponse(ContractModel):
    summary: str
    weekly_focus: str
    weekly_routine: list[WeeklyRoutineDay] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    pc3_payload: dict = Field(default_factory=dict)


class RoutineProfileDayRecord(ContractModel):
    routine_day_id: int | None = None
    routine_id: str
    user_id: str
    scheduled_date: str
    day_index: int = Field(ge=1, le=7)
    day_label: str
    focus: str
    exercises: list[ExercisePlanItem] = Field(default_factory=list)
    summary: str
    weekly_focus: str
    message: str
    created_at: str | None = None


class BodyMetricRequest(ContractModel):
    measured_date: date
    weight_kg: float = Field(ge=1, le=500)
    memo: str | None = None


class BodyMetricRecord(ContractModel):
    id: int
    user_id: str
    measured_date: str
    weight_kg: float
    memo: str | None = None
    created_at: str


class WorkoutSkipRequest(ContractModel):
    session_id: str
    user_id: str
    routine_id: str | None = None
    routine_day_id: str | int | None = None
    exercise_type: str
    completed_reps: int | None = Field(default=None, ge=0, le=1000)
    duration_sec: float | None = Field(default=None, ge=0)
    stability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    posture_errors: list[str] = Field(default_factory=list)
    measurement_quality: str | None = None
    measurement_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    skip_reason: str | None = None


class CalendarDayRecord(ContractModel):
    date: str
    routine_id: str | None = None
    routine_day_id: int | None = None
    day_index: int | None = None
    focus: str | None = None
    exercises: list[ExercisePlanItem] = Field(default_factory=list)
    completed: bool = False
    skipped: bool = False
    skipped_count: int = 0
    workout_results: list[dict] = Field(default_factory=list)
    coach_log_ids: list[int] = Field(default_factory=list)


class CalendarResponse(ContractModel):
    user_id: str
    from_date: str
    to_date: str
    days: list[CalendarDayRecord] = Field(default_factory=list)


class ProgressResponse(ContractModel):
    user_id: str
    days: int
    body_metrics: list[BodyMetricRecord] = Field(default_factory=list)
    weight_delta_kg: float | None = None
    workout_summary: dict = Field(default_factory=dict)
    recent_workouts: list[dict] = Field(default_factory=list)
    recent_coaching: list[dict] = Field(default_factory=list)
    latest_routine: dict | None = None
