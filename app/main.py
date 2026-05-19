from datetime import date
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from app.config import PRIMARY_LLM_MODEL_NAME, SERVICE_NAME
from app.db import (
    database_health,
    get_logs_by_user,
    get_routine_calendar,
    get_user_progress,
    init_db,
    save_body_metric,
)
from app.llm_client import check_primary_llm_health
from app.rag import ingest_seed_knowledge, search_knowledge
from app.schemas import (
    BodyMetricRecord,
    BodyMetricRequest,
    CalendarResponse,
    CoachingResponse,
    FeaturePayload,
    ProgressResponse,
    RoutineProfileDayRecord,
    RoutineProfileRequest,
    RoutineProfileResponse,
    WorkoutSkipRequest,
)
from app.services import (
    generate_coaching_response,
    generate_profile_routine_response,
    get_profile_routine_day_record,
    save_skipped_workout,
)


logger = logging.getLogger("pc2_coach")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        init_db()
    except Exception as exc:
        logger.warning("pc2_startup_db_unavailable error=%s", exc)
    logger.info("pc2_startup service=%s primary_model=%s", SERVICE_NAME, PRIMARY_LLM_MODEL_NAME)
    yield


app = FastAPI(title="PC2 Coach API", version="0.4.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    primary_llm = check_primary_llm_health()
    storage = database_health()
    status = "ok" if primary_llm["status"] == "ok" and storage.get("status") == "ok" else "degraded"
    return {
        "status": status,
        "service": SERVICE_NAME,
        "primary_llm": primary_llm,
        "storage": storage,
    }


@app.post("/api/routine/profile", response_model=RoutineProfileResponse)
def generate_profile_routine(payload: RoutineProfileRequest) -> dict:
    return generate_profile_routine_response(payload, logger)


@app.get("/api/routine/profile/{user_id}/day", response_model=RoutineProfileDayRecord)
def get_profile_routine_day(user_id: str, target_date: date = Query(...)) -> dict:
    return get_profile_routine_day_record(user_id, target_date)


@app.get("/api/routine/profile/{user_id}/calendar", response_model=CalendarResponse)
def get_profile_routine_calendar(
    user_id: str,
    from_date: date = Query(...),
    to_date: date = Query(...),
) -> dict:
    return get_routine_calendar(user_id, from_date, to_date)


@app.post("/api/coach/generate", response_model=CoachingResponse)
def generate_coaching(payload: FeaturePayload) -> dict:
    return generate_coaching_response(payload, logger)


@app.post("/api/workouts/skip")
def save_workout_skip(payload: WorkoutSkipRequest) -> dict:
    return save_skipped_workout(payload)


@app.get("/api/coach/logs/{user_id}")
def coach_logs(user_id: str, limit: int = Query(default=10, ge=1, le=100)) -> dict:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100.")
    return {"user_id": user_id, "logs": get_logs_by_user(user_id, limit=limit)}


@app.post("/api/users/{user_id}/body-metrics", response_model=BodyMetricRecord)
def create_body_metric(user_id: str, payload: BodyMetricRequest) -> dict:
    return save_body_metric(
        user_id=user_id,
        measured_date=payload.measured_date,
        weight_kg=payload.weight_kg,
        memo=payload.memo,
    )


@app.get("/api/users/{user_id}/progress", response_model=ProgressResponse)
def get_progress(user_id: str, days: int = Query(default=30, ge=1, le=365)) -> dict:
    return get_user_progress(user_id, days=days)


@app.post("/api/knowledge/ingest")
def ingest_knowledge() -> dict:
    try:
        return ingest_seed_knowledge()
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"reason": "knowledge_ingest_failed", "error": str(exc)}) from exc


@app.get("/api/knowledge/search")
def knowledge_search(q: str = Query(..., min_length=1), exercise: str | None = Query(default=None)) -> dict:
    try:
        return {"query": q, "results": search_knowledge(q, exercise=exercise)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"reason": "knowledge_search_failed", "error": str(exc)}) from exc
