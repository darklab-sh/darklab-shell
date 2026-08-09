# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Personal and team-scoped user-created workflows.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.teams.scope import personal_owner_context, shared_owner_predicate
from services.workflows.captures import MAX_CAPTURES_PER_STEP
from services.workflows.catalog import (
    WORKFLOW_CAPTURE_SOURCES,
    WORKFLOW_INPUT_ID_RE,
    WORKFLOW_INPUT_TYPES,
)
from services.workflows.compiler import WorkflowDefinitionError, compile_workflow_definition


MAX_WORKFLOW_TITLE_LEN = 120
MAX_WORKFLOW_DESCRIPTION_LEN = 1000
MAX_WORKFLOW_STEPS = 40
MAX_WORKFLOW_INPUTS = 24
MAX_WORKFLOW_STEP_CMD_LEN = 1200
MAX_WORKFLOW_STEP_NOTE_LEN = 1000


class UserWorkflowError(ValueError):
    """Raised when a user workflow payload is invalid."""

    def __init__(self, message: str, *, field: str = "") -> None:
        super().__init__(message)
        self.errors = [{"field": field, "message": message}]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _row_to_workflow(row):
    item = {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"] or "",
        "version": int(row["definition_version"] or 1),
        "inputs": dialect_for_backend(get_db_backend()).decode_json_list(row["inputs"]),
        "steps": dialect_for_backend(get_db_backend()).decode_json_list(row["steps"]),
        "source": "user",
        "created": row["created"],
        "updated": row["updated"],
    }
    try:
        normalized = compile_workflow_definition(item)
    except WorkflowDefinitionError:
        return None
    normalized.update({
        "id": item["id"],
        "source": "user",
        "created": item["created"],
        "updated": item["updated"],
    })
    if "team_id" in row.keys():
        normalized["team_id"] = row["team_id"] or ""
    return normalized


def _trim_text(value, limit):
    return str(value or "").strip()[:limit]


def _clean_payload(data):
    if not isinstance(data, dict):
        raise UserWorkflowError("workflow payload must be an object", field="workflow")
    title = _trim_text(data.get("title"), MAX_WORKFLOW_TITLE_LEN)
    description = _trim_text(data.get("description"), MAX_WORKFLOW_DESCRIPTION_LEN)
    if not title:
        raise UserWorkflowError("workflow title is required", field="title")

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise UserWorkflowError("workflow needs at least one command step", field="steps")
    if len(raw_steps) > MAX_WORKFLOW_STEPS:
        raise UserWorkflowError(
            f"workflow can have at most {MAX_WORKFLOW_STEPS} steps",
            field="steps",
        )

    raw_version = str(data.get("version") or "").strip()
    if "version" in data and raw_version not in {"1", "2", "3"}:
        raise UserWorkflowError("unsupported workflow version", field="version")

    steps = []
    step_ids = set()
    capture_names: dict[str, str] = {}
    version = int(raw_version) if raw_version in {"1", "2", "3"} else 1
    for index, item in enumerate(raw_steps):
        if not isinstance(item, dict):
            raise UserWorkflowError("workflow step must be an object", field=f"steps.{index}")
        cmd = _trim_text(item.get("cmd"), MAX_WORKFLOW_STEP_CMD_LEN)
        note = _trim_text(item.get("note"), MAX_WORKFLOW_STEP_NOTE_LEN)
        if not cmd:
            raise UserWorkflowError("workflow step command is required", field=f"steps.{index}.cmd")
        if version >= 2:
            step_id = str(item.get("id") or "").strip().lower()
            if not WORKFLOW_INPUT_ID_RE.fullmatch(step_id):
                raise UserWorkflowError(
                    "step ID must use lowercase letters, numbers, and underscores",
                    field=f"steps.{index}.id",
                )
            if step_id in step_ids:
                raise UserWorkflowError("step ID must be unique", field=f"steps.{index}.id")
            step_ids.add(step_id)
        raw_captures = item.get("captures") or []
        if not isinstance(raw_captures, list):
            raise UserWorkflowError(
                "workflow captures must be a list",
                field=f"steps.{index}.captures",
            )
        if len(raw_captures) > MAX_CAPTURES_PER_STEP:
            raise UserWorkflowError(
                f"workflow step can define at most {MAX_CAPTURES_PER_STEP} captures",
                field=f"steps.{index}.captures",
            )
        for capture_index, capture in enumerate(raw_captures):
            capture_path = f"steps.{index}.captures.{capture_index}"
            if not isinstance(capture, dict):
                raise UserWorkflowError("workflow capture must be an object", field=capture_path)
            name = str(capture.get("name") or "").strip().lower()
            if not WORKFLOW_INPUT_ID_RE.fullmatch(name):
                raise UserWorkflowError(
                    "capture name must use lowercase letters, numbers, and underscores",
                    field=f"{capture_path}.name",
                )
            if name in capture_names:
                raise UserWorkflowError(
                    "capture name must be unique",
                    field=f"{capture_path}.name",
                )
            capture_names[name] = f"{capture_path}.name"
            source = str(capture.get("source") or "").strip().lower()
            if source not in WORKFLOW_CAPTURE_SOURCES:
                raise UserWorkflowError(
                    f"unsupported workflow capture source {source!r}",
                    field=f"{capture_path}.source",
                )
            option_field = {
                "first_line_containing": "contains",
                "entity": "entity_type",
                "json_pointer": "pointer",
            }.get(source)
            option_value = str(capture.get(option_field) or "").strip() if option_field else ""
            if option_field and not option_value:
                raise UserWorkflowError(
                    f"workflow capture requires {option_field.replace('_', ' ')}",
                    field=f"{capture_path}.{option_field}",
                )
            if source == "json_pointer" and not option_value.startswith("/"):
                raise UserWorkflowError(
                    "workflow capture JSON Pointer must start with /",
                    field=f"{capture_path}.pointer",
                )
            capture_kind = str(capture.get("kind") or capture.get("mode") or "").strip().lower()
            if capture_kind == "collection" and version < 3:
                raise UserWorkflowError(
                    "collection captures require workflow version 3",
                    field=f"{capture_path}.kind",
                )
            if capture_kind == "collection":
                try:
                    item_limit = int(capture.get("item_limit") or 32)
                except (TypeError, ValueError) as exc:
                    raise UserWorkflowError(
                        "collection item limit must be an integer",
                        field=f"{capture_path}.item_limit",
                    ) from exc
                if not 1 <= item_limit <= 32:
                    raise UserWorkflowError("collection item limit must be between 1 and 32", field=f"{capture_path}.item_limit")
        step = dict(item)
        step["cmd"] = cmd
        step["note"] = note
        steps.append(step)

    raw_inputs = data.get("inputs")
    if raw_inputs is None:
        raw_inputs = []
    if not isinstance(raw_inputs, list):
        raise UserWorkflowError("workflow inputs must be a list", field="inputs")
    if len(raw_inputs) > MAX_WORKFLOW_INPUTS:
        raise UserWorkflowError(
            f"workflow can have at most {MAX_WORKFLOW_INPUTS} inputs",
            field="inputs",
        )
    input_ids = set()
    for index, item in enumerate(raw_inputs):
        if not isinstance(item, dict):
            raise UserWorkflowError("workflow input must be an object", field=f"inputs.{index}")
        input_id = str(item.get("id") or "").strip().lower()
        if not WORKFLOW_INPUT_ID_RE.fullmatch(input_id):
            raise UserWorkflowError(
                "parameter ID must start with a letter and use lowercase letters, numbers, and underscores",
                field=f"inputs.{index}.id",
            )
        if input_id in input_ids:
            raise UserWorkflowError("parameter ID must be unique", field=f"inputs.{index}.id")
        input_ids.add(input_id)
        if input_id in capture_names:
            raise UserWorkflowError(
                "parameter ID cannot match a capture name",
                field=f"inputs.{index}.id",
            )
        input_type = str(item.get("type") or "text").strip().lower()
        if input_type not in WORKFLOW_INPUT_TYPES:
            raise UserWorkflowError(
                f"unsupported workflow input type {input_type!r}",
                field=f"inputs.{index}.type",
            )
        if "sensitive" in item and not isinstance(item.get("sensitive"), bool):
            raise UserWorkflowError(
                "parameter sensitive state must be true or false",
                field=f"inputs.{index}.sensitive",
            )

    entry = {
        "version": version,
        "title": title,
        "description": description,
        "inputs": raw_inputs,
        "steps": steps,
    }
    try:
        normalized = compile_workflow_definition(entry)
    except WorkflowDefinitionError as exc:
        raise UserWorkflowError(str(exc), field=exc.field or "workflow") from exc
    return normalized


def _workflow_owner_where(session_id, *, team_id="", table_alias=""):
    prefix = f"{table_alias}." if table_alias else ""
    if team_id:
        return f"{prefix}team_id = ?", (team_id,)
    return shared_owner_predicate(
        personal_owner_context(session_id),
        team_column=f"{prefix}team_id",
        session_column=f"{prefix}session_id",
    )


def list_user_workflows(session_id, *, team_id=""):
    with get_db_connect()() as conn:
        owner_sql, owner_params = _workflow_owner_where(session_id, team_id=team_id)
        rows = conn.execute(
            "SELECT id, session_id, team_id, definition_version, title, description, inputs, steps, created, updated "
            "FROM user_workflows WHERE " + owner_sql + " ORDER BY updated DESC, created DESC",  # nosec
            owner_params,
        ).fetchall()
    return [item for item in (_row_to_workflow(row) for row in rows) if item]


def get_user_workflow(session_id, workflow_id, *, team_id=""):
    with get_db_connect()() as conn:
        owner_sql, owner_params = _workflow_owner_where(session_id, team_id=team_id)
        row = conn.execute(
            "SELECT id, session_id, team_id, definition_version, title, description, inputs, steps, created, updated "
            "FROM user_workflows WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, workflow_id),
        ).fetchone()
    return _row_to_workflow(row) if row else None


def _new_workflow_id():
    return "usr_" + secrets.token_hex(8)


def _definition_version(workflow) -> int:
    version = workflow.get("version")
    return version if isinstance(version, int) and version in {1, 2, 3} else 1


def create_user_workflow(session_id, data, *, team_id=""):
    workflow = _clean_payload(data)
    created = _now()
    with get_db_connect()() as conn:
        dialect = dialect_for_backend(get_db_backend())
        for _ in range(10):
            workflow_id = _new_workflow_id()
            result = conn.execute(
                "INSERT INTO user_workflows "  # nosec
                "(id, session_id, team_id, definition_version, title, description, inputs, steps, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                + dialect.insert_or_ignore_clause(("id",)),
                (
                    workflow_id,
                    session_id,
                    str(team_id or ""),
                    _definition_version(workflow),
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
                return get_user_workflow(session_id, workflow_id, team_id=team_id)
        raise UserWorkflowError("could not allocate a workflow id")


def update_user_workflow(session_id, workflow_id, data, *, team_id=""):
    workflow = _clean_payload(data)
    updated = _now()
    with get_db_connect()() as conn:
        dialect = dialect_for_backend(get_db_backend())
        owner_sql, owner_params = _workflow_owner_where(session_id, team_id=team_id)
        result = conn.execute(
            "UPDATE user_workflows "
            "SET definition_version = ?, title = ?, description = ?, inputs = ?, steps = ?, updated = ? "
            "WHERE " + owner_sql + " AND id = ?",  # nosec
            (
                _definition_version(workflow),
                workflow["title"],
                workflow["description"],
                dialect.json_param(workflow["inputs"]),
                dialect.json_param(workflow["steps"]),
                updated,
                *owner_params,
                workflow_id,
            ),
        )
        conn.commit()
    if result.rowcount == 0:
        return None
    return get_user_workflow(session_id, workflow_id, team_id=team_id)


def delete_user_workflow(session_id, workflow_id, *, team_id=""):
    with get_db_connect()() as conn:
        owner_sql, owner_params = _workflow_owner_where(session_id, team_id=team_id)
        result = conn.execute(
            "DELETE FROM user_workflows WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, workflow_id),
        )
        conn.commit()
    return result.rowcount > 0
