import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, select

from app.config import DB_PATH


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    future=True,
)
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def _add_col(conn, cols: set[str], name: str, sql_type: str, default: str | None = None) -> None:
    if name in cols:
        return
    sql = f"ALTER TABLE coach_logs ADD COLUMN {name} {sql_type}"
    if default is not None:
        sql += f" NOT NULL DEFAULT '{default}'"
    conn.exec_driver_sql(sql)


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    metadata.create_all(engine)
    _ensure_coach_log_columns()


def _ensure_coach_log_columns() -> None:
    with engine.begin() as conn:
        cols = set()
        for row in conn.exec_driver_sql("PRAGMA table_info(coach_logs)").fetchall():
            cols.add(row[1])

        _add_col(conn, cols, "rag_evidence_json", "TEXT", "[]")
        if "rag_evidence_json" not in cols:
            cols.add("rag_evidence_json")

        if "analysis_context_json" not in cols:
            _add_col(conn, cols, "analysis_context_json", "TEXT", "[]")
            if "rag_evidence_json" in cols:
                conn.exec_driver_sql(
                    "UPDATE coach_logs SET analysis_context_json = COALESCE(rag_evidence_json, '[]')"
                )
            cols.add("analysis_context_json")

        _add_col(conn, cols, "baseline_snapshot_json", "TEXT", "{}")
        _add_col(conn, cols, "pc2_output_json", "TEXT", "{}")
        _add_col(conn, cols, "llm_route", "TEXT")
        _add_col(conn, cols, "fallback_used", "INTEGER")
        _add_col(conn, cols, "primary_error", "TEXT")
        _add_col(conn, cols, "is_duplicate_session", "INTEGER")
        _add_col(conn, cols, "duplicate_of_request_id", "TEXT")


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
