# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable workflow execution and step state."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import (
    DatabaseBackend,
    dialect_for_backend,
    postgres_advisory_lock_id,
    sqlite_table_exists,
)
from services.runs.private_data import redact_private_values
from services.teams.scope import personal_owner_context, shared_owner_predicate
from services.workflows.captures import MAX_CAPTURE_TOTAL_BYTES
from services.workflows.compiler import workflow_private_values
from services.workflows.contracts import WorkflowActiveExecutionLimitExceeded


ACTIVE_EXECUTION_STATUSES = ("queued", "running", "canceling")
TERMINAL_EXECUTION_STATUSES = ("completed", "failed", "canceled")
MAX_EXECUTION_FAILURE_DETAIL = 500
PUBLIC_EXECUTION_FIELDS = (
    "id",
    "workflow_id",
    "workflow_source",
    "title",
    "status",
    "current_step_id",
    "project_id",
    "created",
    "updated",
    "finished",
    "failure_code",
    "failure_detail",
)
PUBLIC_EXECUTION_STEP_FIELDS = (
    "step_id",
    "step_index",
    "status",
    "run_id",
    "exit_code",
    "capture_names",
    "selected_transition",
    "transition_reason",
    "error_code",
    "error_detail",
    "started",
    "finished",
    "created",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _elapsed_ms(started: object, finished: object) -> int:
    try:
        start = datetime.fromisoformat(str(started or ""))
        end = datetime.fromisoformat(str(finished or ""))
    except ValueError:
        return 0
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, int((end - start).total_seconds() * 1000))


def _capture_failure_metadata(error: str) -> tuple[str, str]:
    normalized = str(error or "").lower()
    if "required captures were not found" in normalized:
        return "required_capture_missing", "required_missing"
    if "execution limit" in normalized:
        return "capture_total_limit", "total_limit"
    if "value limit" in normalized:
        return "capture_value_limit", "value_limit"
    if "control characters" in normalized:
        return "capture_invalid_value", "invalid_value"
    return "capture_failed", "other"


def _new_id(prefix: str) -> str:
    return prefix + secrets.token_hex(8)


def _dialect():
    return dialect_for_backend(get_db_backend())


def _row_keys(row: Any) -> set[str]:
    try:
        return set(row.keys())
    except (AttributeError, TypeError):
        return set()


def _execution_from_row(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    keys = _row_keys(row)
    result = {key: row[key] for key in keys}
    dialect = _dialect()
    for field in ("definition_snapshot", "input_values", "variables"):
        result[field] = dialect.decode_json_dict(result.get(field))
    return result


def _step_from_row(row: Any) -> dict[str, Any]:
    keys = _row_keys(row)
    result = {key: row[key] for key in keys}
    result["capture_names"] = _dialect().decode_json_list(result.get("capture_names"))
    if result.get("run_id"):
        result["stream"] = f"/runs/{result['run_id']}/stream"
    return result


def public_execution(execution: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return the execution state used by browser and terminal surfaces."""
    if not execution:
        return {}
    definition = execution.get("definition_snapshot")
    variables = execution.get("variables")
    private_values = workflow_private_values(
        definition if isinstance(definition, Mapping) else {},
        variables if isinstance(variables, Mapping) else {},
    )
    result = {
        field: execution.get(field)
        for field in PUBLIC_EXECUTION_FIELDS
        if field in execution
    }
    if "failure_detail" in result:
        result["failure_detail"] = redact_private_values(
            result["failure_detail"],
            private_values,
        )
    raw_steps = execution.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    result["steps"] = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        public_step = {
            field: step.get(field)
            for field in PUBLIC_EXECUTION_STEP_FIELDS
            if field in step
        }
        if "error_detail" in public_step:
            public_step["error_detail"] = redact_private_values(
                public_step["error_detail"],
                private_values,
            )
        result["steps"].append(public_step)
    return result


def _owner_where(session_id: str, *, team_id: str = "", table_alias: str = "") -> tuple[str, tuple[Any, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    if team_id:
        return f"{prefix}team_id = ?", (team_id,)
    return shared_owner_predicate(
        personal_owner_context(session_id),
        team_column=f"{prefix}team_id",
        session_column=f"{prefix}session_id",
    )


def _lock_execution_owner(conn, session_id: str, team_id: str) -> None:
    if get_db_backend() != DatabaseBackend.POSTGRES:
        return
    owner_key = f"team:{team_id}" if team_id else f"personal:{session_id}"
    conn.execute(
        "SELECT pg_advisory_xact_lock(?)",
        (postgres_advisory_lock_id(f"darklab_shell_workflow_owner:{owner_key}"),),
    )


def create_execution(
    *,
    session_id: str,
    team_id: str,
    workflow_id: str,
    workflow_source: str,
    definition: Mapping[str, object],
    inputs: Mapping[str, str],
    workspace_cwd: str = "",
    project_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    owner_client_id: str = "",
    owner_tab_id: str = "",
    max_active: int = 3,
) -> dict[str, Any]:
    execution_id = _new_id("wfx_")
    created = _now()
    raw_steps = definition.get("steps")
    steps = [step for step in raw_steps if isinstance(step, Mapping)] if isinstance(raw_steps, list) else []
    dialect = _dialect()
    with get_db_connect()() as conn:
        _lock_execution_owner(conn, session_id, team_id)
        owner_sql, owner_params = _owner_where(session_id, team_id=team_id)
        active_row = conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_executions WHERE " + owner_sql  # nosec
            + " AND status IN ('queued', 'running', 'canceling')",
            owner_params,
        ).fetchone()
        active_count = int(active_row["n"] if active_row else 0)
        if active_count >= max(1, int(max_active)):
            raise WorkflowActiveExecutionLimitExceeded(max(1, int(max_active)))
        conn.execute(
            "INSERT INTO workflow_executions "
            "(id, session_id, team_id, workflow_id, workflow_source, title, definition_snapshot, "
            "input_values, variables, status, current_step_id, workspace_cwd, project_id, actor_member_id, "
            "actor_role, owner_client_id, owner_tab_id, created, updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                execution_id,
                session_id,
                str(team_id or ""),
                workflow_id,
                workflow_source,
                str(definition.get("title") or "Workflow")[:120],
                dialect.json_param(dict(definition)),
                dialect.json_param(dict(inputs)),
                dialect.json_param(dict(inputs)),
                str(steps[0].get("id") or "") if steps else "",
                str(workspace_cwd or ""),
                str(project_id or ""),
                str(actor_member_id or ""),
                str(actor_role or ""),
                str(owner_client_id or ""),
                str(owner_tab_id or ""),
                created,
                created,
            ),
        )
        for index, step in enumerate(steps):
            conn.execute(
                "INSERT INTO workflow_execution_steps "
                "(id, execution_id, step_id, step_index, status, capture_names, created) "
                "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (
                    _new_id("wst_"),
                    execution_id,
                    str(step.get("id") or f"step_{index + 1}"),
                    index,
                    dialect.json_param([]),
                    created,
                ),
            )
        conn.commit()
    return get_execution(session_id, execution_id, team_id=team_id) or {}


def list_executions(
    session_id: str,
    *,
    team_id: str = "",
    workflow_id: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    owner_sql, owner_params = _owner_where(session_id, team_id=team_id)
    workflow_sql = " AND workflow_id = ?" if workflow_id else ""
    workflow_params = (workflow_id,) if workflow_id else ()
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT * FROM workflow_executions WHERE " + owner_sql  # nosec
            + workflow_sql
            + " ORDER BY created DESC LIMIT ?",
            (*owner_params, *workflow_params, max(1, min(int(limit or 50), 100))),
        ).fetchall()
        executions = [item for item in (_execution_from_row(row) for row in rows) if item]
        execution_ids = [str(item.get("id") or "") for item in executions if item.get("id")]
        step_rows = []
        if execution_ids:
            placeholders = ", ".join("?" for _execution_id in execution_ids)
            step_rows = conn.execute(
                "SELECT * FROM workflow_execution_steps WHERE execution_id IN ("  # nosec
                + placeholders
                + ") ORDER BY execution_id ASC, step_index ASC",
                tuple(execution_ids),
            ).fetchall()
    steps_by_execution: dict[str, list[dict[str, Any]]] = {
        execution_id: [] for execution_id in execution_ids
    }
    for row in step_rows:
        steps_by_execution.setdefault(str(row["execution_id"] or ""), []).append(_step_from_row(row))
    for execution in executions:
        execution["steps"] = steps_by_execution.get(str(execution.get("id") or ""), [])
    return executions


def active_execution_count(session_id: str, *, team_id: str = "") -> int:
    owner_sql, owner_params = _owner_where(session_id, team_id=team_id)
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_executions WHERE " + owner_sql  # nosec
            + " AND status IN ('queued', 'running', 'canceling')",
            owner_params,
        ).fetchone()
    return int(row["n"] if row else 0)


def active_execution_count_for_actor(session_id: str) -> int:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_executions WHERE session_id = ? "
            "AND status IN ('queued', 'running', 'canceling')",
            (session_id,),
        ).fetchone()
    return int(row["n"] if row else 0)


def get_execution(session_id: str, execution_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    owner_sql, owner_params = _owner_where(session_id, team_id=team_id, table_alias="e")
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT e.* FROM workflow_executions e WHERE " + owner_sql + " AND e.id = ?",  # nosec
            (*owner_params, execution_id),
        ).fetchone()
        if not row:
            return None
        step_rows = conn.execute(
            "SELECT * FROM workflow_execution_steps WHERE execution_id = ? ORDER BY step_index ASC",
            (execution_id,),
        ).fetchall()
    result = _execution_from_row(row)
    if result is not None:
        result["steps"] = [_step_from_row(step) for step in step_rows]
    return result


def get_execution_by_id(execution_id: str) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        row = conn.execute("SELECT * FROM workflow_executions WHERE id = ?", (execution_id,)).fetchone()
        if not row:
            return None
        step_rows = conn.execute(
            "SELECT * FROM workflow_execution_steps WHERE execution_id = ? ORDER BY step_index ASC",
            (execution_id,),
        ).fetchall()
    result = _execution_from_row(row)
    if result is not None:
        result["steps"] = [_step_from_row(step) for step in step_rows]
    return result


def active_execution_page_for_recovery(
    *,
    limit: int = 100,
    after_created: str = "",
    after_id: str = "",
) -> list[tuple[str, str]]:
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT id, created FROM workflow_executions "
            "WHERE status IN ('queued', 'running', 'canceling') "
            "AND (? = '' OR created > ? OR (created = ? AND id > ?)) "
            "ORDER BY created ASC, id ASC LIMIT ?",
            (
                after_created,
                after_created,
                after_created,
                after_id,
                max(1, min(int(limit or 100), 500)),
            ),
        ).fetchall()
    return [(str(row["id"]), str(row["created"] or "")) for row in rows]


def completed_run_for_recovery(run_id: str) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT r.*, art.rel_path FROM runs r "
            "LEFT JOIN run_output_artifacts art ON art.run_id = r.id WHERE r.id = ? AND r.finished IS NOT NULL",
            (run_id,),
        ).fetchone()
    if not row:
        return None
    return {key: row[key] for key in _row_keys(row)}


def reset_launching_step_for_recovery(execution_id: str, step_id: str) -> bool:
    now = _now()
    with get_db_connect()() as conn:
        reset = conn.execute(
            "UPDATE workflow_execution_steps SET status = 'pending', started = NULL "
            "WHERE execution_id = ? AND step_id = ? AND status = 'launching' AND run_id = ''",
            (execution_id, step_id),
        )
        if reset.rowcount:
            conn.execute(
                "UPDATE workflow_executions SET status = 'queued', updated = ? "
                "WHERE id = ? AND status IN ('queued', 'running')",
                (now, execution_id),
            )
        conn.commit()
    return bool(reset.rowcount)


def fail_execution(execution_id: str, code: str, detail: str, *, step_id: str = "") -> bool:
    now = _now()
    bounded_code = str(code or "execution_failed")[:80]
    bounded_detail = str(detail or "")[:MAX_EXECUTION_FAILURE_DETAIL]
    with get_db_connect()() as conn:
        failed = conn.execute(
            "UPDATE workflow_executions SET status = 'failed', current_step_id = '', failure_code = ?, "
            "failure_detail = ?, updated = ?, finished = ? "
            "WHERE id = ? AND status IN ('queued', 'running', 'canceling')",
            (bounded_code, bounded_detail, now, now, execution_id),
        )
        if not failed.rowcount:
            conn.rollback()
            return False
        if step_id:
            conn.execute(
                "UPDATE workflow_execution_steps SET status = 'failed', error_code = ?, error_detail = ?, finished = ? "
                "WHERE execution_id = ? AND step_id = ? AND status IN ('pending', 'launching', 'running')",
                (bounded_code, bounded_detail, now, execution_id, step_id),
            )
        conn.execute(
            "UPDATE workflow_execution_steps SET status = 'skipped', finished = ? "
            "WHERE execution_id = ? AND status = 'pending'",
            (now, execution_id),
        )
        conn.commit()
    return True


def fail_execution_for_run(run_id: str, code: str, detail: str) -> bool:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT execution_id, step_id FROM workflow_execution_steps WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if not row:
        return False
    return fail_execution(str(row["execution_id"]), code, detail, step_id=str(row["step_id"]))


def execution_for_run(run_id: str) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT e.* FROM workflow_executions e "
            "JOIN workflow_execution_steps s ON s.execution_id = e.id WHERE s.run_id = ?",
            (run_id,),
        ).fetchone()
    return _execution_from_row(row)


def workflow_provenance_by_run(
    conn,
    run_ids: list[str],
    *,
    include_steps: bool = False,
    owner_scope: Any | None = None,
    session_id: str = "",
    team_id: str = "",
) -> dict[str, dict[str, Any]]:
    """Return bounded workflow ancestry for authorized run ids and owners."""
    normalized_ids = [str(run_id) for run_id in run_ids if run_id]
    if not normalized_ids:
        return {}
    if get_db_backend() == DatabaseBackend.SQLITE and not all(
        sqlite_table_exists(conn, table_name)
        for table_name in ("workflow_executions", "workflow_execution_steps")
    ):
        return {}
    placeholders = ", ".join("?" for _run_id in normalized_ids)
    owner_sql = ""
    owner_params: tuple[Any, ...] = ()
    if owner_scope is not None:
        owner_clause, raw_owner_params = owner_scope.predicate(table_alias="e")
        owner_sql = " AND " + owner_clause
        owner_params = tuple(raw_owner_params)
    elif session_id or team_id:
        owner_clause, owner_params = _owner_where(session_id, team_id=team_id, table_alias="e")
        owner_sql = " AND " + owner_clause
    rows = conn.execute(
        "SELECT s.run_id, s.execution_id, s.step_id, s.step_index, s.status AS step_status, "  # nosec
        "s.exit_code, s.selected_transition, s.transition_reason, "
        "e.workflow_id, e.workflow_source, e.title, e.status AS execution_status, e.current_step_id "
        "FROM workflow_execution_steps s "
        "JOIN workflow_executions e ON e.id = s.execution_id "
        f"WHERE s.run_id IN ({placeholders})" + owner_sql,
        (*normalized_ids, *owner_params),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    execution_ids: set[str] = set()
    for row in rows:
        run_id = str(row["run_id"] or "")
        execution_id = str(row["execution_id"] or "")
        execution_ids.add(execution_id)
        result[run_id] = {
            "execution_id": execution_id,
            "workflow_id": str(row["workflow_id"] or ""),
            "workflow_source": str(row["workflow_source"] or ""),
            "title": str(row["title"] or "Workflow"),
            "status": str(row["execution_status"] or ""),
            "current_step_id": str(row["current_step_id"] or ""),
            "step": {
                "step_id": str(row["step_id"] or ""),
                "step_index": int(row["step_index"] or 0),
                "status": str(row["step_status"] or ""),
                "run_id": run_id,
                "exit_code": row["exit_code"],
                "selected_transition": str(row["selected_transition"] or ""),
                "transition_reason": str(row["transition_reason"] or ""),
            },
        }
    if not include_steps or not execution_ids:
        return result
    execution_placeholders = ", ".join("?" for _execution_id in execution_ids)
    step_rows = conn.execute(
        "SELECT execution_id, step_id, step_index, status, run_id, exit_code, "  # nosec
        "selected_transition, transition_reason FROM workflow_execution_steps "
        f"WHERE execution_id IN ({execution_placeholders}) "
        "ORDER BY execution_id ASC, step_index ASC",
        tuple(sorted(execution_ids)),
    ).fetchall()
    steps_by_execution: dict[str, list[dict[str, Any]]] = {}
    for row in step_rows:
        execution_id = str(row["execution_id"] or "")
        steps_by_execution.setdefault(execution_id, []).append({
            "step_id": str(row["step_id"] or ""),
            "step_index": int(row["step_index"] or 0),
            "status": str(row["status"] or ""),
            "run_id": str(row["run_id"] or ""),
            "exit_code": row["exit_code"],
            "selected_transition": str(row["selected_transition"] or ""),
            "transition_reason": str(row["transition_reason"] or ""),
        })
    for provenance in result.values():
        provenance["steps"] = steps_by_execution.get(str(provenance["execution_id"]), [])
    return result


def workflow_provenance_for_run(run_id: str) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        return workflow_provenance_by_run(conn, [run_id], include_steps=True).get(run_id)


def apply_workflow_provenance(run: dict[str, Any], provenance: dict[str, Any] | None) -> None:
    run["workflow_execution"] = provenance
    run["workflow_execution_id"] = str((provenance or {}).get("execution_id") or "")
    step = (provenance or {}).get("step")
    run["workflow_step_id"] = str(step.get("step_id") or "") if isinstance(step, Mapping) else ""


def execution_launch_pointer(execution_id: str) -> tuple[str, str, str] | None:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT session_id, team_id, current_step_id FROM workflow_executions WHERE id = ?",
            (execution_id,),
        ).fetchone()
    if not row:
        return None
    return str(row["session_id"] or ""), str(row["team_id"] or ""), str(row["current_step_id"] or "")


def claim_step_for_launch(execution_id: str, step_id: str) -> dict[str, Any] | None:
    """Claim one pending step. Only one caller can win this transition."""
    now = _now()
    with get_db_connect()() as conn:
        result = conn.execute(
            "UPDATE workflow_execution_steps SET status = 'launching', started = ? "
            "WHERE execution_id = ? AND step_id = ? AND status = 'pending'",
            (now, execution_id, step_id),
        )
        if result.rowcount != 1:
            conn.rollback()
            return None
        row = conn.execute("SELECT * FROM workflow_executions WHERE id = ?", (execution_id,)).fetchone()
        execution = _execution_from_row(row)
        if not execution or execution.get("status") not in {"queued", "running"}:
            conn.rollback()
            return None
        conn.execute(
            "UPDATE workflow_executions SET status = 'running', current_step_id = ?, updated = ? WHERE id = ?",
            (step_id, now, execution_id),
        )
        conn.commit()
    execution["current_step_id"] = step_id
    execution["status"] = "running"
    return execution


def bind_step_run(execution_id: str, step_id: str, run_id: str) -> bool:
    with get_db_connect()() as conn:
        result = conn.execute(
            "UPDATE workflow_execution_steps SET run_id = ?, status = 'running' "
            "WHERE execution_id = ? AND step_id = ? AND status = 'launching' AND run_id = ''",
            (run_id, execution_id, step_id),
        )
        conn.commit()
    return result.rowcount == 1


def _transition_for_step(
    definition: Mapping[str, object],
    step_id: str,
    *,
    exit_code: int,
    capture_failed: bool,
) -> tuple[str, str]:
    raw_steps = definition.get("steps")
    steps = [step for step in raw_steps if isinstance(step, Mapping)] if isinstance(raw_steps, list) else []
    index = next((position for position, step in enumerate(steps) if step.get("id") == step_id), -1)
    if index < 0:
        return "stop", "definition_error"
    step = steps[index]
    raw_next = step.get("next")
    next_value: Mapping[str, object] = raw_next if isinstance(raw_next, Mapping) else {}
    raw_codes = next_value.get("codes")
    codes: Mapping[str, object] = raw_codes if isinstance(raw_codes, Mapping) else {}
    code_destination = None if capture_failed else codes.get(str(exit_code))
    if code_destination:
        return str(code_destination), f"exit_code:{exit_code}"
    success = exit_code == 0 and not capture_failed
    outcome = "success" if success else "failure"
    destination = next_value.get(outcome)
    if destination:
        return str(destination), outcome
    if success:
        if index + 1 < len(steps):
            return str(steps[index + 1].get("id") or "stop"), "implicit_success"
        return "complete", "implicit_success"
    return "stop", "capture_failure" if capture_failed else "implicit_failure"


def finalize_run_step(
    run_id: str,
    exit_code: int,
    *,
    captures: Mapping[str, str] | None = None,
    capture_error: str = "",
) -> dict[str, Any] | None:
    """Finalize a linked step and select its next destination exactly once."""
    finished = _now()
    dialect = _dialect()
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT s.execution_id, s.step_id, s.status AS step_status, s.started AS step_started, "
            "e.definition_snapshot, e.variables "
            "FROM workflow_execution_steps s JOIN workflow_executions e ON e.id = s.execution_id "
            "WHERE s.run_id = ?",
            (run_id,),
        ).fetchone()
        if not row or row["step_status"] not in {"launching", "running"}:
            return None
        definition = dialect.decode_json_dict(row["definition_snapshot"])
        variables = dialect.decode_json_dict(row["variables"])
        pending_captures = {str(key): str(value) for key, value in (captures or {}).items()}
        current_step = next(
            (
                step
                for step in definition.get("steps") or []
                if isinstance(step, Mapping) and step.get("id") == row["step_id"]
            ),
            {},
        )
        required_capture_names = {
            str(item.get("name") or "")
            for item in current_step.get("captures") or []
            if isinstance(item, Mapping) and item.get("required")
        }
        missing_required = sorted(required_capture_names - set(pending_captures))
        if missing_required:
            capture_error = capture_error or (
                "required captures were not found: " + ", ".join(missing_required)
            )
        input_ids = {
            str(item.get("id") or "")
            for item in definition.get("inputs") or []
            if isinstance(item, Mapping)
        }
        capture_values = {
            key: str(value)
            for key, value in variables.items()
            if key not in input_ids
        }
        capture_values.update(pending_captures)
        if sum(len(value.encode("utf-8")) for value in capture_values.values()) > MAX_CAPTURE_TOTAL_BYTES:
            capture_error = capture_error or "workflow captures exceed the execution limit"
            pending_captures = {}
        variables.update(pending_captures)
        destination, reason = _transition_for_step(
            definition,
            str(row["step_id"]),
            exit_code=int(exit_code),
            capture_failed=bool(capture_error),
        )
        step_status = "succeeded" if int(exit_code) == 0 and not capture_error else "failed"
        capture_error_code, capture_failure_reason = _capture_failure_metadata(capture_error)
        claimed = conn.execute(
            "UPDATE workflow_execution_steps SET status = ?, exit_code = ?, capture_names = ?, "
            "selected_transition = ?, transition_reason = ?, error_code = ?, error_detail = ?, finished = ? "
            "WHERE run_id = ? AND status IN ('launching', 'running')",
            (
                step_status,
                int(exit_code),
                dialect.json_param(sorted(pending_captures)),
                destination,
                reason,
                capture_error_code if capture_error else "",
                str(capture_error or "")[:MAX_EXECUTION_FAILURE_DETAIL],
                finished,
                run_id,
            ),
        )
        if claimed.rowcount != 1:
            conn.rollback()
            return None
        execution_id = str(row["execution_id"])
        if destination in {"complete", "stop"}:
            terminal_status = "completed" if destination == "complete" else "failed"
            failure_code = ""
            failure_detail = ""
            if terminal_status == "failed":
                failure_code = capture_error_code if capture_error else "step_failed"
                failure_detail = str(capture_error or f"step exited with {exit_code}")[
                    :MAX_EXECUTION_FAILURE_DETAIL
                ]
            conn.execute(
                "UPDATE workflow_executions SET variables = ?, status = ?, current_step_id = '', "
                "failure_code = ?, failure_detail = ?, updated = ?, finished = ? WHERE id = ?",
                (
                    dialect.json_param(variables),
                    terminal_status,
                    failure_code,
                    failure_detail,
                    finished,
                    finished,
                    execution_id,
                ),
            )
            conn.execute(
                "UPDATE workflow_execution_steps SET status = 'skipped', finished = ? "
                "WHERE execution_id = ? AND status = 'pending'",
                (finished, execution_id),
            )
        else:
            conn.execute(
                "UPDATE workflow_executions SET variables = ?, current_step_id = ?, updated = ? WHERE id = ?",
                (dialect.json_param(variables), destination, finished, execution_id),
            )
        conn.commit()
    return {
        "execution_id": execution_id,
        "step_id": str(row["step_id"]),
        "step_status": step_status,
        "exit_code": int(exit_code),
        "duration_ms": _elapsed_ms(row["step_started"], finished),
        "capture_failed": bool(capture_error),
        "capture_failure_reason": capture_failure_reason if capture_error else "",
        "destination": destination,
        "transition_reason": reason,
        "terminal": destination in {"complete", "stop"},
    }


def fail_step_launch(execution_id: str, step_id: str, code: str, detail: str) -> bool:
    now = _now()
    with get_db_connect()() as conn:
        claimed = conn.execute(
            "UPDATE workflow_execution_steps SET status = 'failed', error_code = ?, error_detail = ?, finished = ? "
            "WHERE execution_id = ? AND step_id = ? AND status = 'launching'",
            (str(code or "launch_failed"), str(detail or "")[:MAX_EXECUTION_FAILURE_DETAIL], now, execution_id, step_id),
        )
        if claimed.rowcount:
            conn.execute(
                "UPDATE workflow_executions SET status = 'failed', current_step_id = '', failure_code = ?, "
                "failure_detail = ?, updated = ?, finished = ? WHERE id = ?",
                (str(code or "launch_failed"), str(detail or "")[:MAX_EXECUTION_FAILURE_DETAIL], now, now, execution_id),
            )
            conn.execute(
                "UPDATE workflow_execution_steps SET status = 'skipped', finished = ? "
                "WHERE execution_id = ? AND status = 'pending'",
                (now, execution_id),
            )
        conn.commit()
    return bool(claimed.rowcount)


def cancel_execution(session_id: str, execution_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    owner_sql, owner_params = _owner_where(session_id, team_id=team_id)
    now = _now()
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT * FROM workflow_executions WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, execution_id),
        ).fetchone()
        execution = _execution_from_row(row)
        if not execution:
            return None
        if execution.get("status") in TERMINAL_EXECUTION_STATUSES:
            return execution
        active_rows = []
        if get_db_backend() == DatabaseBackend.POSTGRES:
            active_rows = conn.execute(
                "SELECT run_id FROM workflow_execution_steps WHERE execution_id = ? "
                "AND status IN ('pending', 'launching', 'running') FOR UPDATE",
                (execution_id,),
            ).fetchall()
        changed = conn.execute(
            "UPDATE workflow_executions SET status = 'canceled', current_step_id = '', failure_code = 'canceled', "
            "updated = ?, finished = ? WHERE id = ? AND status IN ('queued', 'running', 'canceling')",
            (now, now, execution_id),
        )
        if changed.rowcount != 1:
            conn.rollback()
            return get_execution(session_id, execution_id, team_id=team_id)
        if get_db_backend() != DatabaseBackend.POSTGRES:
            active_rows = conn.execute(
                "SELECT run_id FROM workflow_execution_steps WHERE execution_id = ? "
                "AND status IN ('launching', 'running') AND run_id <> ''",
                (execution_id,),
            ).fetchall()
        conn.execute(
            "UPDATE workflow_execution_steps SET status = 'canceled', finished = ? "
            "WHERE execution_id = ? AND status IN ('pending', 'launching', 'running')",
            (now, execution_id),
        )
        conn.commit()
    result = get_execution(session_id, execution_id, team_id=team_id)
    if result is not None:
        result["_canceled_run_ids"] = sorted({
            str(row["run_id"])
            for row in active_rows
            if str(row["run_id"] or "")
        })
    return result
