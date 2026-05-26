"""
Session-scoped user-created workflows.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from core.database import DB_BACKEND, db_connect
from core.database_backend import dialect_for_backend
from services.workflows.catalog import normalize_workflow_entry


MAX_WORKFLOW_TITLE_LEN = 120
MAX_WORKFLOW_DESCRIPTION_LEN = 1000
MAX_WORKFLOW_STEPS = 40
MAX_WORKFLOW_INPUTS = 24
MAX_WORKFLOW_STEP_CMD_LEN = 1200
MAX_WORKFLOW_STEP_NOTE_LEN = 1000


class UserWorkflowError(ValueError):
    """Raised when a user workflow payload is invalid."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _row_to_workflow(row):
    item = {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"] or "",
        "inputs": dialect_for_backend(DB_BACKEND).decode_json_list(row["inputs"]),
        "steps": dialect_for_backend(DB_BACKEND).decode_json_list(row["steps"]),
        "source": "user",
        "created": row["created"],
        "updated": row["updated"],
    }
    normalized = normalize_workflow_entry(item)
    if not normalized:
        return None
    normalized.update({
        "id": item["id"],
        "source": "user",
        "created": item["created"],
        "updated": item["updated"],
    })
    return normalized


def _trim_text(value, limit):
    return str(value or "").strip()[:limit]


def _clean_payload(data):
    if not isinstance(data, dict):
        raise UserWorkflowError("workflow payload must be an object")
    title = _trim_text(data.get("title"), MAX_WORKFLOW_TITLE_LEN)
    description = _trim_text(data.get("description"), MAX_WORKFLOW_DESCRIPTION_LEN)
    if not title:
        raise UserWorkflowError("workflow title is required")

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise UserWorkflowError("workflow needs at least one command step")
    if len(raw_steps) > MAX_WORKFLOW_STEPS:
        raise UserWorkflowError(f"workflow can have at most {MAX_WORKFLOW_STEPS} steps")

    steps = []
    for item in raw_steps:
        if not isinstance(item, dict):
            continue
        cmd = _trim_text(item.get("cmd"), MAX_WORKFLOW_STEP_CMD_LEN)
        note = _trim_text(item.get("note"), MAX_WORKFLOW_STEP_NOTE_LEN)
        if cmd:
            steps.append({"cmd": cmd, "note": note})
    if not steps:
        raise UserWorkflowError("workflow needs at least one command step")

    raw_inputs = data.get("inputs")
    if raw_inputs is None:
        raw_inputs = []
    if not isinstance(raw_inputs, list):
        raise UserWorkflowError("workflow inputs must be a list")
    if len(raw_inputs) > MAX_WORKFLOW_INPUTS:
        raise UserWorkflowError(f"workflow can have at most {MAX_WORKFLOW_INPUTS} inputs")

    entry = {
        "title": title,
        "description": description,
        "inputs": raw_inputs,
        "steps": steps,
    }
    normalized = normalize_workflow_entry(entry)
    if not normalized:
        raise UserWorkflowError("workflow variables must be declared with valid input metadata")
    if len(normalized["steps"]) != len(steps):
        raise UserWorkflowError("all {{variables}} used by steps must be declared as workflow inputs")
    return normalized


def list_user_workflows(session_id):
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT id, title, description, inputs, steps, created, updated "
            "FROM user_workflows WHERE session_id = ? ORDER BY updated DESC, created DESC",
            (session_id,),
        ).fetchall()
    return [item for item in (_row_to_workflow(row) for row in rows) if item]


def get_user_workflow(session_id, workflow_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, title, description, inputs, steps, created, updated "
            "FROM user_workflows WHERE session_id = ? AND id = ?",
            (session_id, workflow_id),
        ).fetchone()
    return _row_to_workflow(row) if row else None


def _new_workflow_id():
    return "usr_" + secrets.token_hex(8)


def create_user_workflow(session_id, data):
    workflow = _clean_payload(data)
    created = _now()
    with db_connect() as conn:
        dialect = dialect_for_backend(DB_BACKEND)
        for _ in range(10):
            workflow_id = _new_workflow_id()
            result = conn.execute(
                "INSERT INTO user_workflows "  # nosec B608
                "(id, session_id, title, description, inputs, steps, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                + dialect.insert_or_ignore_clause(("id",)),
                (
                    workflow_id,
                    session_id,
                    workflow["title"],
                    workflow["description"],
                    dialect.json_param(workflow["inputs"]),
                    dialect.json_param(workflow["steps"]),
                    created,
                    created,
                ),
            )
            if result.rowcount:
                conn.commit()
                return get_user_workflow(session_id, workflow_id)
        raise UserWorkflowError("could not allocate a workflow id")


def update_user_workflow(session_id, workflow_id, data):
    workflow = _clean_payload(data)
    updated = _now()
    with db_connect() as conn:
        dialect = dialect_for_backend(DB_BACKEND)
        result = conn.execute(
            "UPDATE user_workflows "
            "SET title = ?, description = ?, inputs = ?, steps = ?, updated = ? "
            "WHERE session_id = ? AND id = ?",
            (
                workflow["title"],
                workflow["description"],
                dialect.json_param(workflow["inputs"]),
                dialect.json_param(workflow["steps"]),
                updated,
                session_id,
                workflow_id,
            ),
        )
        conn.commit()
    if result.rowcount == 0:
        return None
    return get_user_workflow(session_id, workflow_id)


def delete_user_workflow(session_id, workflow_id):
    with db_connect() as conn:
        result = conn.execute(
            "DELETE FROM user_workflows WHERE session_id = ? AND id = ?",
            (session_id, workflow_id),
        )
        conn.commit()
    return result.rowcount > 0
