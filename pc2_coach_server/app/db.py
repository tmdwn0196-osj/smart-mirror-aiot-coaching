import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Column, Date, DateTime, Integer, MetaData, String, Table, Text, create_engine, inspect, select

from app.config import DATABASE_URL


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
    Column("goal", Text, nullable=True),
    Column("feature_payload_json", Text, nullable=False),
    Column("detected_signals_json", Text, nullable=False),
    Column("rag_evidence_json", Text, nullable=False, default="[]"),
    Column("analysis_context_json", Text, nullable=False, default="[]"),
    Column("baseline_snapshot_json", Text, nullable=False, default="{}"),
    Column("routine_snapshot_json", Text, nullable=False, default="{}"),
    Column("pc2_output_json", Text, nullable=False, default="{}"),
    Column("llm_prompt", Text, nullable=False),
    Column("raw_llm_response", Text, nullable=False),
    Column("final_response_json", Text, nullable=False),
    Column("model_name", String(255), nullable=False),
    Column("llm_route", String(32), nullable=True),
    Column("fallback_used", Integer, nullable=True),
    Column("primary_error", Text, nullable=True),
    Column("is_duplicate_session", Integer, nullable=True),
    Column("duplicate_of_request_id", String(128), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

exercise_baselines = Table(
    "exercise_baselines",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("baseline_id", String(128), nullable=False, index=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("exercise_type", String(64), nullable=False, index=True),
    Column("purpose", Text, nullable=True),
    Column("baseline_profile_json", Text, nullable=False),
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
    Column("llm_route", String(32), nullable=True),
    Column("status", String(32), nullable=False, default="generated"),
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def init_db() -> None:
    metadata.create_all(engine)
    _ensure_coach_log_columns()
    _ensure_profile_routine_columns()


def _ensure_coach_log_columns() -> None:
    cols = {column["name"] for column in inspect(engine).get_columns("coach_logs")}
    with engine.begin() as conn:
        if "rag_evidence_json" not in cols:
            conn.exec_driver_sql("ALTER TABLE coach_logs ADD COLUMN IF NOT EXISTS rag_evidence_json TEXT NOT NULL DEFAULT '[]'")
        if "analysis_context_json" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE coach_logs ADD COLUMN IF NOT EXISTS analysis_context_json TEXT NOT NULL DEFAULT '[]'"
            )
            if "rag_evidence_json" in cols:
                conn.exec_driver_sql(
                    "UPDATE coach_logs SET analysis_context_json = COALESCE(rag_evidence_json, '[]') "
                    "WHERE analysis_context_json IS NULL OR analysis_context_json = '[]'"
                )
        if "baseline_snapshot_json" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE coach_logs ADD COLUMN IF NOT EXISTS baseline_snapshot_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "routine_snapshot_json" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE coach_logs ADD COLUMN IF NOT EXISTS routine_snapshot_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "pc2_output_json" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE coach_logs ADD COLUMN IF NOT EXISTS pc2_output_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "llm_route" not in cols:
            conn.exec_driver_sql("ALTER TABLE coach_logs ADD COLUMN IF NOT EXISTS llm_route TEXT")
        if "fallback_used" not in cols:
            conn.exec_driver_sql("ALTER TABLE coach_logs ADD COLUMN IF NOT EXISTS fallback_used INTEGER")
        if "primary_error" not in cols:
            conn.exec_driver_sql("ALTER TABLE coach_logs ADD COLUMN IF NOT EXISTS primary_error TEXT")
        if "is_duplicate_session" not in cols:
            conn.exec_driver_sql("ALTER TABLE coach_logs ADD COLUMN IF NOT EXISTS is_duplicate_session INTEGER")
        if "duplicate_of_request_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE coach_logs ADD COLUMN IF NOT EXISTS duplicate_of_request_id TEXT")


def _ensure_profile_routine_columns() -> None:
    cols = {column["name"] for column in inspect(engine).get_columns("profile_routines")}
    with engine.begin() as conn:
        if "start_date" not in cols:
            conn.exec_driver_sql("ALTER TABLE profile_routines ADD COLUMN IF NOT EXISTS start_date DATE")


def find_existing_session_log(user_id: str, session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None

    init_db()
    stmt = (
        select(coach_logs)
        .where(coach_logs.c.user_id == user_id)
        .where(coach_logs.c.session_id == session_id)
        .order_by(coach_logs.c.created_at.asc())
        .limit(1)
    )
    with engine.begin() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None

    data = dict(row._mapping)
    return {
        "request_id": data["request_id"],
        "created_at": data["created_at"].isoformat() if data.get("created_at") else None,
    }


def save_exercise_baseline(
    *,
    baseline_id: str,
    user_id: str,
    exercise_type: str,
    purpose: str | None,
    baseline_profile_json: dict[str, Any],
) -> None:
    init_db()
    with engine.begin() as conn:
        conn.execute(
            exercise_baselines.insert().values(
                baseline_id=baseline_id,
                user_id=user_id,
                exercise_type=exercise_type,
                purpose=purpose,
                baseline_profile_json=_dumps(baseline_profile_json),
                created_at=_now(),
            )
        )


def get_latest_baseline(user_id: str, exercise_type: str | None = None) -> dict[str, Any] | None:
    init_db()
    stmt = select(exercise_baselines).where(exercise_baselines.c.user_id == user_id)
    if exercise_type:
        stmt = stmt.where(exercise_baselines.c.exercise_type == exercise_type)
    stmt = stmt.order_by(exercise_baselines.c.created_at.desc()).limit(1)

    with engine.begin() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None

    data = dict(row._mapping)
    return {
        "baseline_id": data["baseline_id"],
        "user_id": data["user_id"],
        "exercise_type": data["exercise_type"],
        "purpose": data["purpose"],
        "baseline_profile": _loads(data["baseline_profile_json"], default={}),
        "created_at": data["created_at"].isoformat() if data.get("created_at") else None,
    }


def save_coach_log(
    *,
    request_id: str,
    session_id: str | None,
    user_id: str,
    mode: str,
    purpose: str | None,
    feature_payload_json: dict[str, Any],
    detected_signals_json: list[dict[str, Any]],
    analysis_context_json: list[dict[str, Any]],
    baseline_snapshot_json: dict[str, Any] | None,
    routine_snapshot_json: dict[str, Any] | None,
    pc2_output_json: dict[str, Any] | None,
    llm_prompt: str,
    raw_llm_response: str,
    final_response_json: dict[str, Any],
    model_name: str,
    llm_route: str | None = None,
    fallback_used: bool | None = None,
    primary_error: str | None = None,
    is_duplicate_session: bool | None = None,
    duplicate_of_request_id: str | None = None,
) -> None:
    init_db()
    with engine.begin() as conn:
        conn.execute(
            coach_logs.insert().values(
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                mode=mode,
                goal=purpose,
                feature_payload_json=_dumps(feature_payload_json),
                detected_signals_json=_dumps(detected_signals_json),
                rag_evidence_json=_dumps(analysis_context_json),
                analysis_context_json=_dumps(analysis_context_json),
                baseline_snapshot_json=_dumps(baseline_snapshot_json or {}),
                routine_snapshot_json=_dumps(routine_snapshot_json or {}),
                pc2_output_json=_dumps(pc2_output_json or {}),
                llm_prompt=llm_prompt,
                raw_llm_response=raw_llm_response,
                final_response_json=_dumps(final_response_json),
                model_name=model_name,
                llm_route=llm_route,
                fallback_used=int(fallback_used) if fallback_used is not None else None,
                primary_error=primary_error,
                is_duplicate_session=int(is_duplicate_session) if is_duplicate_session is not None else None,
                duplicate_of_request_id=duplicate_of_request_id,
                created_at=_now(),
            )
        )


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
        context_raw = data.get("analysis_context_json") or data.get("rag_evidence_json")
        fallback_used = data.get("fallback_used")
        is_duplicate_session = data.get("is_duplicate_session")
        logs.append(
            {
                "id": data["id"],
                "request_id": data["request_id"],
                "session_id": data["session_id"],
                "user_id": data["user_id"],
                "mode": data["mode"],
                "purpose": data["goal"],
                "detected_signals": _loads(data["detected_signals_json"], default=[]),
                "analysis_context": _loads(context_raw, default=[]),
                "baseline_snapshot": _loads(data.get("baseline_snapshot_json"), default={}),
                "routine_snapshot": _loads(data.get("routine_snapshot_json"), default={}),
                "pc2_output": _loads(data.get("pc2_output_json"), default={}),
                "final_response": _loads(data["final_response_json"], default={}),
                "model_name": data["model_name"],
                "llm_route": data.get("llm_route"),
                "fallback_used": bool(fallback_used) if fallback_used is not None else None,
                "primary_error": data.get("primary_error"),
                "is_duplicate_session": bool(is_duplicate_session) if is_duplicate_session is not None else False,
                "duplicate_of_request_id": data.get("duplicate_of_request_id"),
                "created_at": data["created_at"].isoformat() if data.get("created_at") else None,
            }
        )
    return logs


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
    llm_route: str | None,
    status: str = "generated",
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
                llm_route=llm_route,
                status=status,
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


def _get_scheduled_dates_by_routine_id(routine_id: str) -> list[str]:
    stmt = (
        select(profile_routine_days.c.scheduled_date)
        .where(profile_routine_days.c.routine_id == routine_id)
        .order_by(profile_routine_days.c.scheduled_date.asc())
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt).fetchall()
    return [row[0].isoformat() for row in rows if row and row[0] is not None]


def get_latest_profile_routine(user_id: str) -> dict[str, Any] | None:
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
    weight_kg_raw = data.get("weight_kg")
    weight_kg = float(weight_kg_raw) if weight_kg_raw not in (None, "") else None
    return {
        "routine_id": data["routine_id"],
        "user_id": data["user_id"],
        "profile_name": data.get("profile_name"),
        "weight_kg": weight_kg,
        "user_goal": data["user_goal"],
        "exercise_experience": data["exercise_experience"],
        "available_days_per_week": data["available_days_per_week"],
        "restricted_body_parts": _loads(data.get("restricted_body_parts_json"), default=[]),
        "purpose": data.get("purpose"),
        "start_date": data["start_date"].isoformat() if data.get("start_date") else None,
        "scheduled_dates": _get_scheduled_dates_by_routine_id(data["routine_id"]),
        "routine_response": _loads(data.get("routine_response_json"), default={}),
        "source_model": data["source_model"],
        "llm_route": data.get("llm_route"),
        "status": data.get("status") or "generated",
        "created_at": data["created_at"].isoformat() if data.get("created_at") else None,
    }


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
