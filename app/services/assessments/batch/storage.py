# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic parent, chunk, and child initialization for assessment batches."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import (
    DatabaseBackend,
    dialect_for_backend,
    postgres_advisory_lock_id,
)
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_HARD_MAX_ACTIVE_PER_OWNER,
    BATCH_TERMINAL_STATUSES,
    BatchConcurrency,
)
from services.assessments.batch.events import append_batch_event_on_conn
from services.assessments.batch.policy import batch_chunk_sizes, normalize_batch_concurrency
from services.assessments.batch.retry_events import append_retry_created_on_conn
from services.assessments.batch.settings import assessment_batch_settings
from services.assessments.batch.storage_read import active_batch_count, get_batch_parent
from services.projects.scope import shared_owner_where
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_checkpoint import create_fanout_checkpoint


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _dialect():
    return dialect_for_backend(get_db_backend())


def _new_id(prefix: str) -> str:
    return prefix + secrets.token_hex(12)


def _active_limit(value: object) -> int:
    if isinstance(value, bool):
        raise AssessmentBatchError(
            "invalid_batch_policy", "Active batch limit must be an integer."
        )
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise AssessmentBatchError(
            "invalid_batch_policy",
            "Active batch limit must be an integer.",
        ) from exc
    if not 1 <= limit <= BATCH_HARD_MAX_ACTIVE_PER_OWNER:
        raise AssessmentBatchError(
            "invalid_batch_policy",
            f"Active batch limit must be between 1 and {BATCH_HARD_MAX_ACTIVE_PER_OWNER}.",
        )
    return limit


def _lock_owner(conn: Any, session_id: str, team_id: str) -> None:
    if get_db_backend() != DatabaseBackend.POSTGRES:
        return
    owner_key = f"team:{team_id}" if team_id else f"personal:{session_id}"
    conn.execute(
        "SELECT pg_advisory_xact_lock(?)",
        (
            postgres_advisory_lock_id(
                f"darklab_shell_assessment_batch_owner:{owner_key}"
            ),
        ),
    )


def _require_active_assessment(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    team_id: str,
) -> None:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="a"
    )
    row = conn.execute(
        "SELECT a.id FROM project_assessments a WHERE "
        + owner_sql  # nosec: fixed owner clause
        + " AND a.project_id = ? AND a.id = ? AND a.status = 'active'",
        (*owner_params, project_id, assessment_id),
    ).fetchone()
    if not row:
        raise AssessmentBatchError(
            "assessment_not_active",
            "The active assessment wasn't found in this Project scope.",
            status_code=409,
        )


def _require_retry_source(
    conn: Any,
    session_id: str,
    source_batch_id: str,
    project_id: str,
    assessment_id: str,
    *,
    team_id: str,
) -> None:
    if not source_batch_id:
        return
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    row = conn.execute(
        "SELECT e.status FROM assessment_batches b "
        "JOIN workflow_executions e ON e.id = b.execution_id "
        "WHERE e.execution_kind = ? AND "
        + owner_sql  # nosec: fixed owner clause
        + " AND b.execution_id = ? AND b.assessment_id = ? AND e.project_id = ?",
        (
            ASSESSMENT_BATCH_EXECUTION_KIND,
            *owner_params,
            source_batch_id,
            assessment_id,
            project_id,
        ),
    ).fetchone()
    if not row or str(row["status"] or "") not in BATCH_TERMINAL_STATUSES:
        raise AssessmentBatchError(
            "invalid_retry_source",
            "A retry requires a terminal assessment batch from the same cycle.",
            status_code=409,
        )


def _insert_chunks(
    conn: Any, batch_id: str, sizes: tuple[int, ...], created: str
) -> None:
    for chunk_index, child_count in enumerate(sizes):
        step_id = f"chunk_{chunk_index + 1:04d}"
        checkpoint = create_fanout_checkpoint(child_count)
        conn.execute(
            "INSERT INTO workflow_execution_steps "
            "(id, execution_id, step_id, step_index, status, capture_names, fanout_checkpoint, created) "
            "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)",
            (
                _new_id("wst_"),
                batch_id,
                step_id,
                chunk_index,
                _dialect().json_param([]),
                _dialect().json_param(checkpoint.to_payload()),
                created,
            ),
        )
        for ordinal in checkpoint.pending:
            conn.execute(
                "INSERT INTO workflow_execution_children "
                "(id, execution_id, step_id, ordinal, attempt, run_id, status, error_code, created) "
                "VALUES (?, ?, ?, ?, 1, '', 'pending', '', ?)",
                (_new_id("wfc_"), batch_id, step_id, ordinal, created),
            )
        append_batch_event_on_conn(
            conn,
            batch_id,
            "chunk_initialized",
            chunk_index=chunk_index,
            status="pending",
            details={"item_count": child_count},
            created=created,
        )


def create_batch_parent(
    *,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
    preview_id: str,
    preview_digest: str,
    item_count: int,
    concurrency: BatchConcurrency | None = None,
    source_batch_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    owner_client_id: str = "",
    owner_tab_id: str = "",
    max_active: int | None = None,
    _preflight_on_conn: Callable[[Any, str], str] | None = None,
    _initialize_on_conn: Callable[[Any, str, str], None] | None = None,
) -> dict[str, object]:
    """Create one parent and every value-free chunk/child row atomically."""
    sizes = batch_chunk_sizes(item_count)
    normalized_item_count = sum(sizes)
    policy = concurrency or normalize_batch_concurrency()
    policy = normalize_batch_concurrency(
        batch=policy.batch,
        target=policy.target,
        owner=policy.owner,
        instance=policy.instance,
    )
    active_limit = max_active if max_active is not None else assessment_batch_settings().max_active_per_owner
    owner_limit = _active_limit(active_limit)
    normalized_preview_id = str(preview_id or "").strip()
    normalized_digest = str(preview_digest or "").strip().lower()
    if not normalized_preview_id or len(normalized_preview_id) > 64:
        raise AssessmentBatchError(
            "invalid_preview", "Assessment batch preview id is invalid."
        )
    if len(normalized_digest) != 64 or any(
        char not in "0123456789abcdef" for char in normalized_digest
    ):
        raise AssessmentBatchError(
            "invalid_preview", "Assessment batch preview digest is invalid."
        )
    batch_id = _new_id("abx_")
    created = _now()
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    with get_db_connect()() as conn:
        conn.execute(_dialect().begin_immediate_sql())
        _lock_owner(conn, session_id, team_id)
        if _preflight_on_conn:
            existing_batch_id = _preflight_on_conn(conn, created)
            if existing_batch_id:
                conn.commit()
                return get_batch_parent(
                    session_id, existing_batch_id, team_id=team_id
                ) or {}
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_executions e WHERE e.execution_kind = ? AND "  # nosec B608
            + owner_sql
            + " AND e.status IN ('queued', 'running', 'canceling')",
            (ASSESSMENT_BATCH_EXECUTION_KIND, *owner_params),
        ).fetchone()
        if int(active["n"] if active else 0) >= owner_limit:
            raise AssessmentBatchError(
                "active_batch_limit",
                f"Active assessment batch limit reached ({owner_limit}).",
                status_code=409,
            )
        _require_active_assessment(
            conn,
            session_id,
            project_id,
            assessment_id,
            team_id=team_id,
        )
        _require_retry_source(
            conn,
            session_id,
            str(source_batch_id or "").strip(),
            project_id,
            assessment_id,
            team_id=team_id,
        )
        first_step_id = "chunk_0001"
        conn.execute(
            "INSERT INTO workflow_executions "
            "(id, execution_kind, session_id, team_id, workflow_id, workflow_source, title, "
            "definition_snapshot, input_values, variables, status, current_step_id, project_id, "
            "actor_member_id, actor_role, owner_client_id, owner_tab_id, created, updated) "
            "VALUES (?, ?, ?, ?, ?, 'assessment', 'Assessment batch', ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id,
                ASSESSMENT_BATCH_EXECUTION_KIND,
                session_id,
                str(team_id or ""),
                assessment_id,
                _dialect().json_param({}),
                _dialect().json_param({}),
                _dialect().json_param({}),
                first_step_id,
                project_id,
                str(actor_member_id or ""),
                str(actor_role or ""),
                str(owner_client_id or ""),
                str(owner_tab_id or ""),
                created,
                created,
            ),
        )
        conn.execute(
            "INSERT INTO assessment_batches "
            "(execution_id, assessment_id, preview_id, preview_digest, source_execution_id, "
            "item_count, max_parallel, max_target_parallel, max_owner_parallel, "
            "max_instance_parallel, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id,
                assessment_id,
                normalized_preview_id,
                normalized_digest,
                str(source_batch_id or "").strip() or None,
                normalized_item_count,
                policy.batch,
                policy.target,
                policy.owner,
                policy.instance,
                created,
            ),
        )
        append_batch_event_on_conn(
            conn,
            batch_id,
            "parent_created",
            status="queued",
            source_batch_id=str(source_batch_id or "").strip(),
            details={"item_count": normalized_item_count, "chunk_count": len(sizes)},
            created=created,
        )
        _insert_chunks(conn, batch_id, sizes, created)
        if _initialize_on_conn:
            _initialize_on_conn(conn, batch_id, created)
        append_retry_created_on_conn(conn, source_batch_id, batch_id, normalized_item_count, created)
        conn.commit()
    return get_batch_parent(session_id, batch_id, team_id=team_id) or {}


__all__ = ["active_batch_count", "create_batch_parent", "get_batch_parent"]
