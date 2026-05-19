import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.config import RAG_CONTEXT_K, RAG_ENABLED, RAG_VECTOR_TOP_K
from app.db import engine, init_rag_db, is_postgres
from app.llm_client import call_embedding, call_rerank


BASE_DIR = Path(__file__).resolve().parent.parent
SEED_PATH = BASE_DIR / "data" / "exercise_knowledge_seed.json"
EMBEDDING_BATCH_SIZE = 16


def _require_rag_ready() -> None:
    if not RAG_ENABLED:
        raise RuntimeError("RAG is disabled")
    if not is_postgres():
        raise RuntimeError("RAG requires PostgreSQL with pgvector")
    init_rag_db()


def _load_seed() -> list[dict[str, Any]]:
    if not SEED_PATH.exists():
        raise RuntimeError(f"knowledge seed not found: {SEED_PATH}")
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("knowledge seed must be a JSON array")
    return payload


def _source_id(record: dict[str, Any]) -> str:
    raw = str(record.get("source_url") or record.get("source_title") or "unknown").lower()
    safe = "".join(ch if ch.isalnum() else "_" for ch in raw).strip("_")
    return (safe[:96] or "source_unknown")


def _embedding_text(record: dict[str, Any]) -> str:
    applies = ", ".join(record.get("applies_when") or [])
    contraindications = ", ".join(record.get("contraindications") or [])
    return (
        f"exercise: {record.get('exercise')}\n"
        f"category: {record.get('category')}\n"
        f"title: {record.get('title')}\n"
        f"applies_when: {applies}\n"
        f"contraindications: {contraindications}\n"
        f"content: {record.get('content')}"
    )


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def _compact_evidence(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "exercise": record.get("exercise"),
        "category": record.get("category"),
        "title": record.get("title"),
        "source": record.get("source_title"),
        "source_url": record.get("source_url"),
        "evidence_level": record.get("evidence_level"),
    }


def _embed_texts(texts: list[str], *, input_type: str) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        embeddings.extend(
            call_embedding(
                texts[start : start + EMBEDDING_BATCH_SIZE],
                input_type=input_type,
            )
        )
    return embeddings


def _fetch_nearest_safety_chunk(
    embedding_literal: str,
    *,
    exercise: str | None,
) -> dict[str, Any] | None:
    where = "WHERE category = 'safety'"
    params: dict[str, Any] = {"embedding": embedding_literal}
    if exercise:
        where += " AND exercise = :exercise"
        params["exercise"] = exercise

    with engine.begin() as conn:
        row = conn.execute(
            text(
                f"""
                SELECT
                    id,
                    exercise,
                    category,
                    title,
                    content,
                    source_title,
                    source_url,
                    source_type,
                    evidence_level,
                    1 - (embedding <=> CAST(:embedding AS vector)) AS score
                FROM knowledge_chunks
                {where}
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()
    return dict(row) if row else None


def ingest_seed_knowledge() -> dict[str, Any]:
    _require_rag_ready()
    records = _load_seed()
    if len(records) < 75:
        raise RuntimeError("knowledge seed must contain at least 75 chunks")

    texts = [_embedding_text(record) for record in records]
    embeddings = _embed_texts(texts, input_type="passage")
    if len(embeddings) != len(records):
        raise RuntimeError("embedding count did not match seed record count")

    with engine.begin() as conn:
        for record, embedding in zip(records, embeddings):
            source_id = _source_id(record)
            conn.execute(
                text(
                    """
                    INSERT INTO knowledge_sources (id, title, source_url, source_type)
                    VALUES (:id, :title, :source_url, :source_type)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        source_url = EXCLUDED.source_url,
                        source_type = EXCLUDED.source_type
                    """
                ),
                {
                    "id": source_id,
                    "title": record["source_title"],
                    "source_url": record.get("source_url"),
                    "source_type": record.get("source_type") or "reference",
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO knowledge_chunks (
                        id,
                        source_id,
                        exercise,
                        category,
                        title,
                        content,
                        applies_when_json,
                        contraindications_json,
                        source_title,
                        source_url,
                        source_type,
                        evidence_level,
                        embedding,
                        updated_at
                    )
                    VALUES (
                        :id,
                        :source_id,
                        :exercise,
                        :category,
                        :title,
                        :content,
                        :applies_when_json,
                        :contraindications_json,
                        :source_title,
                        :source_url,
                        :source_type,
                        :evidence_level,
                        CAST(:embedding AS vector),
                        now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        source_id = EXCLUDED.source_id,
                        exercise = EXCLUDED.exercise,
                        category = EXCLUDED.category,
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        applies_when_json = EXCLUDED.applies_when_json,
                        contraindications_json = EXCLUDED.contraindications_json,
                        source_title = EXCLUDED.source_title,
                        source_url = EXCLUDED.source_url,
                        source_type = EXCLUDED.source_type,
                        evidence_level = EXCLUDED.evidence_level,
                        embedding = EXCLUDED.embedding,
                        updated_at = now()
                    """
                ),
                {
                    "id": record["id"],
                    "source_id": source_id,
                    "exercise": record["exercise"],
                    "category": record["category"],
                    "title": record["title"],
                    "content": record["content"],
                    "applies_when_json": json.dumps(record.get("applies_when") or []),
                    "contraindications_json": json.dumps(record.get("contraindications") or []),
                    "source_title": record["source_title"],
                    "source_url": record.get("source_url"),
                    "source_type": record.get("source_type") or "reference",
                    "evidence_level": record.get("evidence_level") or "reference",
                    "embedding": _vector_literal(embedding),
                },
            )

    return {"seed_records": len(records), "stored_chunks": len(records)}


def search_knowledge(
    query: str,
    *,
    exercise: str | None = None,
    vector_top_k: int | None = None,
    context_k: int | None = None,
) -> list[dict[str, Any]]:
    _require_rag_ready()
    query = query.strip()
    if not query:
        raise RuntimeError("query is required")

    embedding = _embed_texts([query], input_type="query")[0]
    embedding_literal = _vector_literal(embedding)
    limit = vector_top_k or RAG_VECTOR_TOP_K
    where = "WHERE exercise = :exercise" if exercise else ""
    params: dict[str, Any] = {
        "embedding": embedding_literal,
        "limit": limit,
    }
    if exercise:
        params["exercise"] = exercise

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT
                    id,
                    exercise,
                    category,
                    title,
                    content,
                    source_title,
                    source_url,
                    source_type,
                    evidence_level,
                    1 - (embedding <=> CAST(:embedding AS vector)) AS score
                FROM knowledge_chunks
                {where}
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()

    candidates = [dict(row) for row in rows]
    if not candidates:
        return []

    rankings = call_rerank(query, [item["content"] for item in candidates])
    by_index = {item["index"]: item["logit"] for item in rankings}
    for index, item in enumerate(candidates):
        item["rerank_logit"] = by_index.get(index, float("-inf"))

    candidates.sort(key=lambda item: item["rerank_logit"], reverse=True)
    final_count = context_k or RAG_CONTEXT_K
    selected = candidates[:final_count]

    if selected and not any(item.get("category") == "safety" for item in selected):
        safety_chunk = _fetch_nearest_safety_chunk(embedding_literal, exercise=exercise)
        if safety_chunk and all(item["id"] != safety_chunk["id"] for item in selected):
            if len(selected) >= final_count:
                selected = selected[:-1] + [safety_chunk]
            else:
                selected.append(safety_chunk)

    return selected


def build_evidence_block(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "[EVIDENCE]\nNo evidence was retrieved."
    lines = ["[EVIDENCE]"]
    for index, chunk in enumerate(chunks, start=1):
        lines.append(
            f"E{index} id={chunk['id']} exercise={chunk.get('exercise')} "
            f"category={chunk.get('category')} source={chunk.get('source_title')}"
        )
        lines.append(str(chunk.get("content") or "").strip())
    return "\n".join(lines)


def summarize_evidence(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_compact_evidence(chunk) for chunk in chunks]


def retrieve_routine_evidence(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    query = (
        f"weekly routine goal={payload.get('user_goal')} "
        f"experience={payload.get('exercise_experience')} "
        f"days={payload.get('available_days_per_week')} "
        f"limitations={payload.get('restricted_body_parts')} "
        "safe exercise selection progression regression cautions"
    )
    chunks = search_knowledge(query)
    return build_evidence_block(chunks), summarize_evidence(chunks)


def retrieve_coach_evidence(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    exercise = ((payload.get("features") or {}).get("exercise") or {})
    exercise_type = exercise.get("type")
    query = (
        f"post workout coaching exercise={exercise_type} "
        f"count={exercise.get('count') or exercise.get('rep_count')} "
        f"state={exercise.get('state')} "
        f"stability_score={exercise.get('stability_score')} "
        f"posture_errors={exercise.get('posture_errors')} "
        f"measurement_quality={exercise.get('measurement_quality')} "
        "specific cue safety next action recovery"
    )
    chunks = search_knowledge(query, exercise=exercise_type if exercise_type else None)
    return build_evidence_block(chunks), summarize_evidence(chunks)
