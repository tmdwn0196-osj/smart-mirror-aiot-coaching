from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EXERCISE_TYPE_VALUES = ("squat", "jumping_jack", "knee_raise", "lunge", "pushup")
EXERCISE_TYPE_ALIASES = {
    "squat": "squat",
    "jumping_jack": "jumping_jack",
    "jumping jack": "jumping_jack",
    "jumping-jack": "jumping_jack",
    "knee_raise": "knee_raise",
    "knee raise": "knee_raise",
    "knee-raise": "knee_raise",
    "lunge": "lunge",
    "pushup": "pushup",
    "push-up": "pushup",
    "push up": "pushup",
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
                raise ValueError("exercise mode에서는 features.exercise가 필요합니다.")
            if not self.features.exercise.type:
                raise ValueError("exercise mode에서는 features.exercise.type이 필요합니다.")
        return self


class DetectedSignal(BaseModel):
    category: str
    label: str
    value: str | float | int | bool | list[str] | None = None
    severity: int = Field(default=2, ge=1, le=3)


class ExerciseBaselineProfile(ContractModel):
    exercise_type: ExerciseType
    sample_count: int
    rep_count_avg: float | None = None
    duration_sec_avg: float | None = None
    stability_score_avg: float | None = None
    knee_angle_avg: float | None = None
    squat_depth_avg: float | None = None
    back_angle_mode: str | None = None
    tempo_mode: str | None = None
    frequent_posture_errors: list[str] = Field(default_factory=list)
    recommended_sets: int | None = None
    recommended_reps: int | None = None
    recommended_duration_sec: int | None = None


class ExerciseBaselineCreateRequest(ContractModel):
    user_id: str
    exercise_type: ExerciseType
    samples: list[ExerciseFeature] = Field(min_length=1)
    purpose: str | None = None

    @model_validator(mode="after")
    def validate_sample_types(self):
        invalid_samples = [
            index + 1
            for index, sample in enumerate(self.samples)
            if sample.type is not None and sample.type != self.exercise_type
        ]
        if invalid_samples:
            positions = ", ".join(str(index) for index in invalid_samples)
            raise ValueError(
                f"samples.type은 exercise_type과 일치해야 합니다. 불일치 sample index: {positions}"
            )
        return self


class ExerciseBaselineRecord(ContractModel):
    baseline_id: str
    user_id: str
    exercise_type: ExerciseType
    purpose: str | None = None
    baseline_profile: ExerciseBaselineProfile
    created_at: str


class ExercisePlanItem(ContractModel):
    exercise: str
    sets: int = Field(ge=1, le=10)
    reps: int | None = Field(default=None, ge=1, le=100)
    duration_sec: int | None = Field(default=None, ge=10, le=7200)
    rest_sec: int | None = Field(default=None, ge=0, le=600)
    focus: str
    reason: str


class PC2Payload(ContractModel):
    message: str
    display_lines: list[str] = Field(default_factory=list)


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


class RoutineProfileRecord(ContractModel):
    routine_id: str
    user_id: str
    profile_name: str | None = None
    weight_kg: float | None = None
    user_goal: str
    exercise_experience: str
    available_days_per_week: int = Field(ge=1, le=7)
    restricted_body_parts: list[str] = Field(default_factory=list)
    purpose: str | None = None
    routine_response: RoutineProfileResponse
    source_model: str
    llm_route: str | None = None
    status: str
    created_at: str
