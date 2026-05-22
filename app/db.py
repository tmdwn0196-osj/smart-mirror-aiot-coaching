import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Column, Date, DateTime, Float, Integer, MetaData, String, Table, Text, create_engine, select, text

from app.config import DATABASE_URL


def _prepare_sqlite_path(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    raw_path = database_url.removeprefix("sqlite:///")
    if raw_path in (":memory:", ""):
        return
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = Path(os.getcwd()) / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)


_prepare_sqlite_path(DATABASE_URL)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
metadata = MetaData()

coach_logs = Table(
    "coach_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("request_id", String(128), nullable=False, index=True),
    Column("session_id", String(128), nullable=True, index=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("mode", String(32), nullable=False),
    Column("purpose", Text, nullable=True),
    Column("request_json", Text, nullable=False),
    Column("pc2_output_json", Text, nullable=False),
    Column("llm_prompt", Text, nullable=False),
    Column("raw_llm_response", Text, nullable=False),
    Column("final_response_json", Text, nullable=False),
    Column("model_name", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

profile_routines = Table(
    "profile_routines",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("routine_id", String(128), nullable=False, index=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("profile_name", String(255), nullable=True),
    Column("weight_kg", Text, nullable=True),
    Column("user_goal", Text, nullable=False),
    Column("exercise_experience", Text, nullable=False),
    Column("available_days_per_week", Integer, nullable=False),
    Column("restricted_body_parts_json", Text, nullable=False, default="[]"),
    Column("purpose", Text, nullable=True),
    Column("start_date", Date, nullable=True),
    Column("routine_response_json", Text, nullable=False),
    Column("source_model", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

profile_routine_days = Table(
    "profile_routine_days",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("routine_id", String(128), nullable=False, index=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("scheduled_date", Date, nullable=False, index=True),
    Column("day_index", Integer, nullable=False),
    Column("day_label", String(64), nullable=False),
    Column("focus", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("weekly_focus", Text, nullable=False),
    Column("day_routine_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

user_profiles = Table(
    "user_profiles",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(128), nullable=False, unique=True, index=True),
    Column("profile_json", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

body_metrics = Table(
    "body_metrics",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("measured_date", Date, nullable=False, index=True),
    Column("weight_kg", Float, nullable=False),
    Column("memo", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

workout_results = Table(
    "workout_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(128), nullable=False, index=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("routine_id", String(128), nullable=True, index=True),
    Column("routine_day_id", String(128), nullable=True, index=True),
    Column("exercise_type", String(64), nullable=False),
    Column("completed_reps", Integer, nullable=True),
    Column("duration_sec", Float, nullable=True),
    Column("stability_score", Float, nullable=True),
    Column("posture_errors_json", Text, nullable=False, default="[]"),
    Column("measurement_quality", String(64), nullable=True),
    Column("measurement_confidence", Float, nullable=True),
    Column("result_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def _iso_datetime(value: Any) -> str | None:
    return value.isoformat() if value else None


def _iso_date(value: Any) -> str | None:
    return value.isoformat() if value else None


def _to_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_postgres() -> bool:
    return engine.dialect.name == "postgresql"


def init_db() -> None:
    metadata.create_all(engine)
    if is_postgres():
        try:
            init_rag_db()
        except Exception:
            # Keep the service importable and let health/RAG endpoints report
            # the concrete PostgreSQL or pgvector failure.
            pass


def init_rag_db() -> None:
    if not is_postgres():
        raise RuntimeError("RAG requires PostgreSQL with pgvector")

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_url TEXT,
                    source_type TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id TEXT PRIMARY KEY,
                    source_id TEXT REFERENCES knowledge_sources(id),
                    exercise TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    applies_when_json TEXT NOT NULL,
                    contraindications_json TEXT NOT NULL,
                    source_title TEXT NOT NULL,
                    source_url TEXT,
                    source_type TEXT NOT NULL,
                    evidence_level TEXT NOT NULL,
                    embedding vector(512) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_exercise
                ON knowledge_chunks (exercise)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_category
                ON knowledge_chunks (category)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding
                ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
                """
            )
        )


def get_knowledge_chunk_count() -> int:
    if not is_postgres():
        return 0
    with engine.begin() as conn:
        result = conn.execute(text("SELECT count(*) FROM knowledge_chunks")).scalar()
    return int(result or 0)


def database_health() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": engine.dialect.name,
        "url_configured": bool(DATABASE_URL),
        "rag_ready": False,
        "pgvector": "not_applicable",
        "knowledge_chunks": 0,
    }
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
            payload["status"] = "ok"
            if is_postgres():
                vector = conn.execute(
                    text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
                ).scalar()
                payload["pgvector"] = "ok" if int(vector or 0) else "missing"
                if payload["pgvector"] == "ok":
                    payload["knowledge_chunks"] = get_knowledge_chunk_count()
                    payload["rag_ready"] = True
    except Exception as exc:
        payload["status"] = "error"
        payload["error"] = str(exc)
    return payload


def save_coach_log(
    *,
    request_id: str,
    session_id: str | None,
    user_id: str,
    mode: str,
    purpose: str | None,
    request_json: dict[str, Any],
    pc2_output_json: dict[str, Any] | None,
    llm_prompt: str,
    raw_llm_response: str,
    final_response_json: dict[str, Any],
    model_name: str,
) -> int:
    init_db()
    with engine.begin() as conn:
        result = conn.execute(
            coach_logs.insert().values(
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                mode=mode,
                purpose=purpose,
                request_json=_dumps(request_json),
                pc2_output_json=_dumps(pc2_output_json or {}),
                llm_prompt=llm_prompt,
                raw_llm_response=raw_llm_response,
                final_response_json=_dumps(final_response_json),
                model_name=model_name,
                created_at=_now(),
            )
        )
    return int(result.inserted_primary_key[0])


def get_logs_by_user(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    stmt = (
        select(coach_logs)
        .where(coach_logs.c.user_id == user_id)
        .order_by(coach_logs.c.created_at.desc())
        .limit(limit)
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt).fetchall()

    logs: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row._mapping)
        logs.append(
            {
                "id": data["id"],
                "request_id": data["request_id"],
                "session_id": data["session_id"],
                "user_id": data["user_id"],
                "mode": data["mode"],
                "purpose": data["purpose"],
                "request": _loads(data["request_json"], default={}),
                "pc2_output": _loads(data["pc2_output_json"], default={}),
                "final_response": _loads(data["final_response_json"], default={}),
                "model_name": data["model_name"],
                "created_at": data["created_at"].isoformat() if data.get("created_at") else None,
            }
        )
    return logs


def upsert_user_profile(user_id: str, profile_json: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = _now()
    with engine.begin() as conn:
        existing = conn.execute(
            select(user_profiles).where(user_profiles.c.user_id == user_id).limit(1)
        ).fetchone()
        if existing:
            conn.execute(
                user_profiles.update()
                .where(user_profiles.c.user_id == user_id)
                .values(profile_json=_dumps(profile_json), updated_at=now)
            )
        else:
            conn.execute(
                user_profiles.insert().values(
                    user_id=user_id,
                    profile_json=_dumps(profile_json),
                    updated_at=now,
                )
            )

    return {"user_id": user_id, "profile": profile_json, "updated_at": now.isoformat()}


def save_body_metric(
    *,
    user_id: str,
    measured_date: date,
    weight_kg: float,
    memo: str | None,
) -> dict[str, Any]:
    init_db()
    with engine.begin() as conn:
        result = conn.execute(
            body_metrics.insert().values(
                user_id=user_id,
                measured_date=measured_date,
                weight_kg=weight_kg,
                memo=memo,
                created_at=_now(),
            )
        )
        row = conn.execute(
            select(body_metrics)
            .where(body_metrics.c.id == result.inserted_primary_key[0])
            .limit(1)
        ).fetchone()

    data = dict(row._mapping)
    return {
        "id": data["id"],
        "user_id": data["user_id"],
        "measured_date": _iso_date(data["measured_date"]),
        "weight_kg": data["weight_kg"],
        "memo": data["memo"],
        "created_at": _iso_datetime(data["created_at"]),
    }


def get_recent_body_metrics(user_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
    init_db()
    stmt = (
        select(body_metrics)
        .where(body_metrics.c.user_id == user_id)
        .order_by(body_metrics.c.measured_date.desc(), body_metrics.c.created_at.desc())
        .limit(limit)
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt).fetchall()

    return [
        {
            "id": row._mapping["id"],
            "user_id": row._mapping["user_id"],
            "measured_date": _iso_date(row._mapping["measured_date"]),
            "weight_kg": row._mapping["weight_kg"],
            "memo": row._mapping["memo"],
            "created_at": _iso_datetime(row._mapping["created_at"]),
        }
        for row in rows
    ]


def save_workout_result(
    *,
    session_id: str,
    user_id: str,
    routine_id: str | None,
    routine_day_id: str | None,
    exercise_type: str,
    completed_reps: int | None,
    duration_sec: float | None,
    stability_score: float | None,
    posture_errors: list[str],
    measurement_quality: str | None,
    measurement_confidence: float | None,
    result_json: dict[str, Any],
) -> int:
    init_db()
    with engine.begin() as conn:
        result = conn.execute(
            workout_results.insert().values(
                session_id=session_id,
                user_id=user_id,
                routine_id=routine_id,
                routine_day_id=routine_day_id,
                exercise_type=exercise_type,
                completed_reps=completed_reps,
                duration_sec=duration_sec,
                stability_score=stability_score,
                posture_errors_json=_dumps(posture_errors),
                measurement_quality=measurement_quality,
                measurement_confidence=measurement_confidence,
                result_json=_dumps(result_json),
                created_at=_now(),
            )
        )
    return int(result.inserted_primary_key[0])


def _workout_record(row: Any) -> dict[str, Any]:
    data = dict(row._mapping)
    result = _loads(data["result_json"], default={})
    status = result.get("status") if isinstance(result, dict) else None
    return {
        "id": data["id"],
        "session_id": data["session_id"],
        "user_id": data["user_id"],
        "routine_id": data["routine_id"],
        "routine_day_id": _to_int_or_none(data["routine_day_id"]),
        "exercise_type": data["exercise_type"],
        "completed_reps": data["completed_reps"],
        "duration_sec": data["duration_sec"],
        "stability_score": data["stability_score"],
        "posture_errors": _loads(data["posture_errors_json"], default=[]),
        "measurement_quality": data["measurement_quality"],
        "measurement_confidence": data["measurement_confidence"],
        "status": status or "completed",
        "result": result,
        "created_at": _iso_datetime(data["created_at"]),
    }


def get_recent_workout_results(user_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    stmt = (
        select(workout_results)
        .where(workout_results.c.user_id == user_id)
        .order_by(workout_results.c.created_at.desc())
        .limit(limit)
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt).fetchall()
    return [_workout_record(row) for row in rows]


def get_latest_routine(user_id: str) -> dict[str, Any] | None:
    init_db()
    stmt = (
        select(profile_routines)
        .where(profile_routines.c.user_id == user_id)
        .order_by(profile_routines.c.created_at.desc())
        .limit(1)
    )
    with engine.begin() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None

    data = dict(row._mapping)
    return {
        "id": data["id"],
        "routine_id": data["routine_id"],
        "user_id": data["user_id"],
        "profile_name": data["profile_name"],
        "user_goal": data["user_goal"],
        "exercise_experience": data["exercise_experience"],
        "available_days_per_week": data["available_days_per_week"],
        "restricted_body_parts": _loads(data["restricted_body_parts_json"], default=[]),
        "start_date": _iso_date(data["start_date"]),
        "routine_response": _loads(data["routine_response_json"], default={}),
        "source_model": data["source_model"],
        "created_at": _iso_datetime(data["created_at"]),
    }


def get_user_history_snapshot(user_id: str) -> dict[str, Any]:
    return {
        "body_metrics": get_recent_body_metrics(user_id, limit=5),
        "workout_results": get_recent_workout_results(user_id, limit=10),
        "coach_logs": get_logs_by_user(user_id, limit=5),
        "latest_routine": get_latest_routine(user_id),
    }


def save_profile_routine(
    *,
    routine_id: str,
    user_id: str,
    profile_name: str | None,
    weight_kg: float | None,
    user_goal: str,
    exercise_experience: str,
    available_days_per_week: int,
    restricted_body_parts: list[str],
    purpose: str | None,
    start_date: date | None,
    routine_response_json: dict[str, Any],
    source_model: str,
) -> None:
    init_db()
    with engine.begin() as conn:
        conn.execute(
            profile_routines.insert().values(
                routine_id=routine_id,
                user_id=user_id,
                profile_name=profile_name,
                weight_kg=str(weight_kg) if weight_kg is not None else None,
                user_goal=user_goal,
                exercise_experience=exercise_experience,
                available_days_per_week=available_days_per_week,
                restricted_body_parts_json=_dumps(restricted_body_parts),
                purpose=purpose,
                start_date=start_date,
                routine_response_json=_dumps(routine_response_json),
                source_model=source_model,
                created_at=_now(),
            )
        )


def save_profile_routine_days(
    *,
    routine_id: str,
    user_id: str,
    summary: str,
    weekly_focus: str,
    weekly_routine: list[dict[str, Any]],
    start_date: date,
) -> list[str]:
    init_db()
    scheduled_dates: list[str] = []
    with engine.begin() as conn:
        for index, day in enumerate(weekly_routine):
            scheduled_date = date.fromordinal(start_date.toordinal() + index)
            scheduled_dates.append(scheduled_date.isoformat())
            conn.execute(
                profile_routine_days.insert().values(
                    routine_id=routine_id,
                    user_id=user_id,
                    scheduled_date=scheduled_date,
                    day_index=day["day_index"],
                    day_label=day["day_label"],
                    focus=day["focus"],
                    summary=summary,
                    weekly_focus=weekly_focus,
                    day_routine_json=_dumps(day),
                    created_at=_now(),
                )
            )
    return scheduled_dates


def get_profile_routine_day_by_date(user_id: str, target_date: date) -> dict[str, Any] | None:
    init_db()
    stmt = (
        select(profile_routine_days)
        .where(profile_routine_days.c.user_id == user_id)
        .where(profile_routine_days.c.scheduled_date == target_date)
        .order_by(profile_routine_days.c.created_at.desc())
        .limit(1)
    )
    with engine.begin() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None

    data = dict(row._mapping)
    day_routine = _loads(data["day_routine_json"], default={})
    return {
        "routine_day_id": data["id"],
        "routine_id": data["routine_id"],
        "user_id": data["user_id"],
        "scheduled_date": data["scheduled_date"].isoformat() if data.get("scheduled_date") else None,
        "day_index": data["day_index"],
        "day_label": data["day_label"],
        "focus": data["focus"],
        "exercises": day_routine.get("exercises") or [],
        "summary": data["summary"],
        "weekly_focus": data["weekly_focus"],
        "created_at": data["created_at"].isoformat() if data.get("created_at") else None,
    }


def get_routine_calendar(user_id: str, from_date: date, to_date: date) -> dict[str, Any]:
    init_db()
    if to_date < from_date:
        from_date, to_date = to_date, from_date

    start_dt = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with engine.begin() as conn:
        routine_rows = conn.execute(
            select(profile_routine_days)
            .where(profile_routine_days.c.user_id == user_id)
            .where(profile_routine_days.c.scheduled_date >= from_date)
            .where(profile_routine_days.c.scheduled_date <= to_date)
            .order_by(profile_routine_days.c.scheduled_date.asc(), profile_routine_days.c.created_at.desc())
        ).fetchall()
        workout_rows = conn.execute(
            select(workout_results)
            .where(workout_results.c.user_id == user_id)
            .where(workout_results.c.created_at >= start_dt)
            .where(workout_results.c.created_at < end_dt)
            .order_by(workout_results.c.created_at.desc())
        ).fetchall()
        log_rows = conn.execute(
            select(coach_logs)
            .where(coach_logs.c.user_id == user_id)
            .where(coach_logs.c.created_at >= start_dt)
            .where(coach_logs.c.created_at < end_dt)
            .order_by(coach_logs.c.created_at.desc())
        ).fetchall()

    workouts = [_workout_record(row) for row in workout_rows]
    logs = [dict(row._mapping) for row in log_rows]
    logs_by_session: dict[str, list[int]] = {}
    for log in logs:
        session_id = str(log.get("session_id") or "")
        if session_id:
            logs_by_session.setdefault(session_id, []).append(int(log["id"]))

    routines_by_date: dict[str, dict[str, Any]] = {}
    for row in routine_rows:
        data = dict(row._mapping)
        key = data["scheduled_date"].isoformat()
        if key in routines_by_date:
            continue
        day_routine = _loads(data["day_routine_json"], default={})
        routines_by_date[key] = {
            "routine_id": data["routine_id"],
            "routine_day_id": data["id"],
            "day_index": data["day_index"],
            "focus": data["focus"],
            "exercises": day_routine.get("exercises") or [],
        }

    days: list[dict[str, Any]] = []
    current = from_date
    while current <= to_date:
        key = current.isoformat()
        routine = routines_by_date.get(key, {})
        routine_day_id = routine.get("routine_day_id")
        day_workouts = [
            item
            for item in workouts
            if item.get("routine_day_id") == routine_day_id
            or (item.get("created_at") or "").startswith(key)
        ]
        coach_ids: list[int] = []
        for workout in day_workouts:
            coach_ids.extend(logs_by_session.get(workout.get("session_id") or "", []))
        if not coach_ids:
            coach_ids = [
                int(log["id"])
                for log in logs
                if _iso_datetime(log.get("created_at") or "").startswith(key)
            ]
        completed_workouts = [item for item in day_workouts if item.get("status") != "skipped"]
        skipped_workouts = [item for item in day_workouts if item.get("status") == "skipped"]
        days.append(
            {
                "date": key,
                "routine_id": routine.get("routine_id"),
                "routine_day_id": routine_day_id,
                "day_index": routine.get("day_index"),
                "focus": routine.get("focus"),
                "exercises": routine.get("exercises") or [],
                "completed": bool(completed_workouts),
                "skipped": bool(skipped_workouts) and not completed_workouts,
                "skipped_count": len(skipped_workouts),
                "workout_results": day_workouts,
                "coach_log_ids": sorted(set(coach_ids)),
            }
        )
        current = current + timedelta(days=1)

    return {
        "user_id": user_id,
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "days": days,
    }


def get_user_progress(user_id: str, *, days: int = 30) -> dict[str, Any]:
    init_db()
    days = max(1, min(days, 365))
    since_dt = _now() - timedelta(days=days)
    since_date = since_dt.date()
    with engine.begin() as conn:
        metric_rows = conn.execute(
            select(body_metrics)
            .where(body_metrics.c.user_id == user_id)
            .where(body_metrics.c.measured_date >= since_date)
            .order_by(body_metrics.c.measured_date.asc(), body_metrics.c.created_at.asc())
        ).fetchall()
        workout_rows = conn.execute(
            select(workout_results)
            .where(workout_results.c.user_id == user_id)
            .where(workout_results.c.created_at >= since_dt)
            .order_by(workout_results.c.created_at.desc())
        ).fetchall()

    metrics = [
        {
            "id": row._mapping["id"],
            "user_id": row._mapping["user_id"],
            "measured_date": _iso_date(row._mapping["measured_date"]),
            "weight_kg": row._mapping["weight_kg"],
            "memo": row._mapping["memo"],
            "created_at": _iso_datetime(row._mapping["created_at"]),
        }
        for row in metric_rows
    ]
    workouts = [_workout_record(row) for row in workout_rows]

    completed_workouts = [item for item in workouts if item.get("status") != "skipped"]
    skipped_workouts = [item for item in workouts if item.get("status") == "skipped"]
    total_reps = sum(int(item.get("completed_reps") or 0) for item in completed_workouts)
    total_duration_sec = sum(float(item.get("duration_sec") or 0) for item in completed_workouts)
    stability_values = [
        float(item["stability_score"])
        for item in completed_workouts
        if item.get("stability_score") is not None
    ]
    by_exercise: dict[str, int] = {}
    for item in completed_workouts:
        name = str(item.get("exercise_type") or "unknown")
        by_exercise[name] = by_exercise.get(name, 0) + 1

    weight_delta = None
    if len(metrics) >= 2:
        weight_delta = round(float(metrics[-1]["weight_kg"]) - float(metrics[0]["weight_kg"]), 2)

    return {
        "user_id": user_id,
        "days": days,
        "body_metrics": metrics,
        "weight_delta_kg": weight_delta,
        "workout_summary": {
            "session_count": len({item.get("session_id") for item in completed_workouts if item.get("session_id")}),
            "workout_count": len(completed_workouts),
            "skipped_count": len(skipped_workouts),
            "total_reps": total_reps,
            "total_duration_sec": total_duration_sec,
            "avg_stability_score": round(sum(stability_values) / len(stability_values), 3)
            if stability_values
            else None,
            "by_exercise": by_exercise,
        },
        "recent_workouts": workouts[:10],
        "recent_coaching": get_logs_by_user(user_id, limit=5),
        "latest_routine": get_latest_routine(user_id),
    }
