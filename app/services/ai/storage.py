"""Small storage helpers for the AI assist queue foundation."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import logging
import time
from typing import Any
import uuid

from core.database import db_connect
from services import metrics as app_metrics
from services.ai import ai_cfg

TERMINAL_STATUSES = frozenset({"completed", "failed"})
ACTIVE_STATUSES = frozenset({"queued", "in_progress"})
log = logging.getLogger("shell")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connection_scope(conn=None):
    if conn is not None:
        yield conn
        return
    with db_connect() as owned:
        yield owned


@contextmanager
def _timed_db_operation(operation: str):
    started = time.perf_counter()
    try:
        yield
    finally:
        app_metrics.record_db_query(operation, time.perf_counter() - started)


def queued_depth(conn=None) -> int:
    with _timed_db_operation("ai_queue_depth"):
        with _connection_scope(conn) as active_conn:
            row = active_conn.execute(
                "SELECT COUNT(*) AS count FROM ai_run_assists WHERE status IN ('queued', 'in_progress')"
            ).fetchone()
            return int(row["count"] if hasattr(row, "keys") else row[0])


def cached_completed_assist(
    session_id: str,
    run_id: str,
    variant: str,
    *,
    model: str,
    prompt_version: str,
    context_hash: str,
    conn=None,
) -> dict[str, Any] | None:
    with _timed_db_operation("ai_cache_lookup"):
        with _connection_scope(conn) as active_conn:
            row = active_conn.execute(
                "SELECT * FROM ai_run_assists WHERE session_id = ? AND run_id = ? "
                "AND variant = ? AND model = ? AND prompt_version = ? AND context_hash = ? "
                "AND status = 'completed' ORDER BY created_at DESC LIMIT 1",
                (session_id, run_id, variant, model, prompt_version, context_hash),
            ).fetchone()
            return _decode_assist_row(row) if row else None


def active_assist(
    session_id: str,
    run_id: str,
    variant: str,
    *,
    model: str,
    prompt_version: str,
    conn=None,
) -> dict[str, Any] | None:
    with _timed_db_operation("ai_active_lookup"):
        with _connection_scope(conn) as active_conn:
            row = active_conn.execute(
                "SELECT * FROM ai_run_assists WHERE session_id = ? AND run_id = ? "
                "AND variant = ? AND model = ? AND prompt_version = ? "
                "AND status IN ('queued', 'in_progress') ORDER BY created_at DESC LIMIT 1",
                (session_id, run_id, variant, model, prompt_version),
            ).fetchone()
            return _decode_assist_row(row) if row else None


def enqueue_assist(
    session_id: str,
    run_id: str,
    variant: str,
    context_result,
    *,
    cfg: dict | None = None,
    model: str | None = None,
    prompt_version: str,
    prompt_version_source: str = "canonical",
    payload_schema_version: str = "v1",
    active_project_id: str = "",
    project_target_snapshot: list[dict[str, Any]] | None = None,
    force: bool = False,
    conn=None,
) -> tuple[dict[str, Any], bool]:
    """Return an existing cached/active assist or insert a queued row."""
    with _timed_db_operation("ai_enqueue_assist"):
        settings = ai_cfg(cfg)
        resolved_model = model or settings["model"]
        owns_conn = conn is None
        with _connection_scope(conn) as active_conn:
            if not force:
                cached = cached_completed_assist(
                    session_id,
                    run_id,
                    variant,
                    model=resolved_model,
                    prompt_version=prompt_version,
                    context_hash=context_result.context_hash,
                    conn=active_conn,
                )
                if cached:
                    app_metrics.record_ai_cache_hit(variant)
                    return cached, False
            active = active_assist(
                session_id,
                run_id,
                variant,
                model=resolved_model,
                prompt_version=prompt_version,
                conn=active_conn,
            )
            if active:
                return active, False
            if queued_depth(active_conn) >= int(settings["max_queue_depth"]):
                raise RuntimeError("ai queue depth limit reached")
            now = utc_now()
            assist_id = f"ai_{uuid.uuid4().hex}"
            active_conn.execute(
                "INSERT INTO ai_run_assists "
                "(id, run_id, session_id, variant, prompt_version, prompt_version_source, "
                "payload_schema_version, model, context_hash, status, active_project_id, "
                "project_target_snapshot, payload, input_chars, estimated_input_tokens, "
                "redacted_bytes, pre_redaction_bytes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    assist_id,
                    run_id,
                    session_id,
                    variant,
                    prompt_version,
                    prompt_version_source,
                    payload_schema_version,
                    resolved_model,
                    context_result.context_hash,
                    active_project_id,
                    _json(project_target_snapshot or []),
                    _json({}),
                    int(context_result.input_chars),
                    int(context_result.estimated_input_tokens),
                    int(context_result.redacted_bytes),
                    int(context_result.pre_redaction_bytes),
                    now,
                    now,
                ),
            )
            if owns_conn:
                active_conn.commit()
            return _decode_assist_row(
                active_conn.execute("SELECT * FROM ai_run_assists WHERE id = ?", (assist_id,)).fetchone()
            ), True


def complete_assist(
    assist_id: str,
    *,
    payload: dict[str, Any],
    raw_model_payload: str = "",
    output_chars: int = 0,
    duration_ms: int = 0,
    conn=None,
) -> dict[str, Any] | None:
    with _timed_db_operation("ai_complete_assist"):
        owns_conn = conn is None
        with _connection_scope(conn) as active_conn:
            active_conn.execute(
                "UPDATE ai_run_assists SET status = 'completed', payload = ?, progress = ?, raw_model_payload = ?, "
                "output_chars = ?, duration_ms = ?, error_code = '', error_message = '', updated_at = ? "
                "WHERE id = ?",
                (
                    _json(payload),
                    _json({}),
                    _cap_raw_payload(raw_model_payload),
                    int(output_chars),
                    int(duration_ms),
                    utc_now(),
                    assist_id,
                ),
            )
            if owns_conn:
                active_conn.commit()
            row = active_conn.execute("SELECT * FROM ai_run_assists WHERE id = ?", (assist_id,)).fetchone()
            return _decode_assist_row(row) if row else None


def replace_suggestion_validations(
    assist_id: str,
    rows: list[dict[str, Any]],
    *,
    conn=None,
) -> None:
    with _timed_db_operation("ai_replace_suggestion_validations"):
        owns_conn = conn is None
        with _connection_scope(conn) as active_conn:
            active_conn.execute("DELETE FROM ai_suggestion_validations WHERE assist_id = ?", (assist_id,))
            now = utc_now()
            for row in rows:
                active_conn.execute(
                    "INSERT INTO ai_suggestion_validations "
                    "(id, assist_id, command, normalized_command, risk_label, validation_result, "
                    "rejection_reason, target, target_allowed, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"aiv_{uuid.uuid4().hex}",
                        assist_id,
                        str(row.get("command") or "")[:2000],
                        str(row.get("normalized_command") or "")[:2000],
                        str(row.get("risk_label") or "unknown")[:20],
                        str(row.get("validation_result") or "pending")[:20],
                        str(row.get("rejection_reason") or "")[:120],
                        str(row.get("target") or "")[:500] or None,
                        bool(row.get("target_allowed")),
                        now,
                    ),
                )
            if owns_conn:
                active_conn.commit()


def fail_assist(assist_id: str, *, error_code: str, error_message: str, conn=None) -> dict[str, Any] | None:
    with _timed_db_operation("ai_fail_assist"):
        owns_conn = conn is None
        with _connection_scope(conn) as active_conn:
            active_conn.execute(
                "UPDATE ai_run_assists SET status = 'failed', progress = ?, error_code = ?, error_message = ?, updated_at = ? "
                "WHERE id = ?",
                (
                    _json({}),
                    str(error_code or "ai_unavailable")[:80],
                    str(error_message or "")[:1000],
                    utc_now(),
                    assist_id,
                ),
            )
            if owns_conn:
                active_conn.commit()
            row = active_conn.execute("SELECT * FROM ai_run_assists WHERE id = ?", (assist_id,)).fetchone()
            return _decode_assist_row(row) if row else None


def claim_next_assist(*, conn=None) -> dict[str, Any] | None:
    with _timed_db_operation("ai_claim_next_assist"):
        owns_conn = conn is None
        with _connection_scope(conn) as active_conn:
            # Keep the queue claim portable across SQLite and Postgres. The rowcount
            # guard below handles worker collisions without a Postgres-only
            # SELECT ... FOR UPDATE SKIP LOCKED branch at the current worker scale.
            row = active_conn.execute(
                "SELECT * FROM ai_run_assists WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            assist_id = row["id"]
            now = utc_now()
            cur = active_conn.execute(
                "UPDATE ai_run_assists SET status = 'in_progress', claimed_at = ?, heartbeat_at = ?, updated_at = ? "
                "WHERE id = ? AND status = 'queued'",
                (now, now, now, assist_id),
            )
            if int(getattr(cur, "rowcount", 0) or 0) != 1:
                if owns_conn:
                    active_conn.rollback()
                return None
            if owns_conn:
                active_conn.commit()
            claimed = active_conn.execute("SELECT * FROM ai_run_assists WHERE id = ?", (assist_id,)).fetchone()
            return _decode_assist_row(claimed) if claimed else None


def heartbeat_assist(assist_id: str, *, conn=None) -> None:
    with _timed_db_operation("ai_heartbeat_assist"):
        owns_conn = conn is None
        with _connection_scope(conn) as active_conn:
            active_conn.execute(
                "UPDATE ai_run_assists SET heartbeat_at = ?, updated_at = ? WHERE id = ? AND status = 'in_progress'",
                (utc_now(), utc_now(), assist_id),
            )
            if owns_conn:
                active_conn.commit()


def update_assist_progress(assist_id: str, progress: dict[str, Any], *, conn=None) -> None:
    with _timed_db_operation("ai_update_assist_progress"):
        owns_conn = conn is None
        with _connection_scope(conn) as active_conn:
            active_conn.execute(
                "UPDATE ai_run_assists SET progress = ?, heartbeat_at = ?, updated_at = ? "
                "WHERE id = ? AND status = 'in_progress'",
                (_json(progress), utc_now(), utc_now(), assist_id),
            )
            if owns_conn:
                active_conn.commit()


def reclaim_stale_assists(*, stale_after_seconds: int = 300) -> int:
    with _timed_db_operation("ai_reclaim_stale_assists"):
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(1, stale_after_seconds))).isoformat()
        with db_connect() as conn:
            cur = conn.execute(
                "UPDATE ai_run_assists SET status = 'failed', progress = ?, error_code = 'ai_unavailable', "
                "error_message = 'AI worker heartbeat expired', updated_at = ? "
                "WHERE status = 'in_progress' AND COALESCE(heartbeat_at, claimed_at, created_at) < ?",
                (_json({}), utc_now(), cutoff),
            )
            conn.commit()
            return int(cur.rowcount or 0)


def list_recent_assists_for_run(session_id: str, run_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    with _timed_db_operation("ai_list_recent_assists"):
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ai_run_assists WHERE session_id = ? AND run_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (session_id, run_id, max(1, min(100, int(limit)))),
            ).fetchall()
        return [_decode_assist_row(row) for row in rows]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _loads_json(value: Any, default: Any, *, assist_id: str = "", column: str = "") -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None or value == "":
        return default
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        log.warning(
            "AI_ASSIST_JSON_DECODE_FAILED",
            extra={"assist_id": assist_id, "column": column},
        )
        return default


def _decode_assist_row(row) -> dict[str, Any]:
    payload = dict(row)
    assist_id = str(payload.get("id") or "")
    payload["payload"] = _loads_json(payload.get("payload"), {}, assist_id=assist_id, column="payload")
    payload["project_target_snapshot"] = _loads_json(
        payload.get("project_target_snapshot"),
        [],
        assist_id=assist_id,
        column="project_target_snapshot",
    )
    payload["progress"] = _loads_json(payload.get("progress"), {}, assist_id=assist_id, column="progress")
    return payload


def _cap_raw_payload(value: str, *, limit: int = 64 * 1024) -> str:
    text = str(value or "")
    if len(text.encode("utf-8", errors="replace")) <= limit:
        return text
    encoded = text.encode("utf-8", errors="replace")[:limit]
    return encoded.decode("utf-8", errors="ignore") + "\n[raw model payload truncated]"
