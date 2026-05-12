import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from app.config import PRIMARY_LLM_MODEL_NAME, SERVICE_NAME
from app.db import get_latest_baseline, get_logs_by_user, init_db
from app.llm_client import check_fallback_llm_health, check_primary_llm_health
from app.schemas import (
    CoachingResponse,
    ExerciseBaselineCreateRequest,
    ExerciseBaselineRecord,
    FeaturePayload,
    RoutineProfileRequest,
    RoutineProfileResponse,
)
from app.services import create_baseline_record, generate_coaching_response, generate_profile_routine_response


logger = logging.getLogger("pc2_coach")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("pc2_startup service=%s primary_model=%s", SERVICE_NAME, PRIMARY_LLM_MODEL_NAME)
    yield


app = FastAPI(title="PC2 Coach API", version="0.3.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    pri_llm = check_primary_llm_health()
    fb_llm = check_fallback_llm_health()
    llm_ready = pri_llm["status"] == "ok" or fb_llm["status"] == "ok"
    status = "ok" if llm_ready else "degraded"
    return {
        "status": status,
        "service": SERVICE_NAME,
        "primary_llm": pri_llm,
        "fallback_llm": fb_llm,
        "local_fallback": {"status": "ok"},
    }


@app.post("/api/exercise/baseline", response_model=ExerciseBaselineRecord)
def create_exercise_baseline(payload: ExerciseBaselineCreateRequest) -> dict:
    return create_baseline_record(payload)


@app.get("/api/exercise/baseline/{user_id}")
def exercise_baseline(user_id: str, exercise_type: str | None = Query(default=None)) -> dict:
    ex_type = exercise_type.lower() if exercise_type else None
    baseline = get_latest_baseline(user_id, ex_type)
    if baseline is None:
        raise HTTPException(status_code=404, detail="baseline을 찾지 못했습니다.")
    return baseline


@app.post("/api/coach/generate", response_model=CoachingResponse)
def generate_coaching(payload: FeaturePayload) -> dict:
    return generate_coaching_response(payload, logger)


@app.post("/api/routine/profile", response_model=RoutineProfileResponse)
def generate_profile_routine(payload: RoutineProfileRequest) -> dict:
    return generate_profile_routine_response(payload, logger)


@app.get("/api/coach/logs/{user_id}")
def coach_logs(user_id: str, limit: int = Query(default=10, ge=1, le=100)) -> dict:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit는 1 이상 100 이하여야 합니다.")
    return {"user_id": user_id, "logs": get_logs_by_user(user_id, limit=limit)}
