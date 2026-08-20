# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Serializers shared by API v1 routes."""

from __future__ import annotations

from typing import Any


def json_error(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": str(code or "error"), "message": str(message or "Request failed.")}}


def _bool(value: Any) -> bool:
    return bool(value)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _assessment_batch_summary(row: dict[str, Any]) -> dict[str, Any] | None:
    provenance = row.get("assessment_batch")
    if not isinstance(provenance, dict):
        return None
    item = provenance.get("item")
    if not isinstance(item, dict):
        return None
    return {
        "schema_version": 1,
        "batch_id": str(provenance.get("batch_id") or ""),
        "assessment_id": str(provenance.get("assessment_id") or ""),
        "project_id": str(provenance.get("project_id") or ""),
        "status": str(provenance.get("status") or ""),
        "source_batch_id": str(provenance.get("source_batch_id") or ""),
        "created": provenance.get("created"),
        "item": {
            "item_index": _int(item.get("item_index")),
            "step_id": str(item.get("step_id") or ""),
            "attempt": _int(item.get("attempt")),
            "status": str(item.get("status") or ""),
            "run_id": str(item.get("run_id") or ""),
            "exit_code": item.get("exit_code"),
            "check_count": _int(item.get("check_count")),
        },
    }


def run_summary(row: dict[str, Any]) -> dict[str, Any]:
    run_id = str(row.get("id") or row.get("run_id") or "")
    assessment_batch = _assessment_batch_summary(row)
    return {
        "id": run_id,
        "command": str(row.get("command") or ""),
        "started": row.get("started"),
        "finished": row.get("finished"),
        "status": _run_status(row),
        "exit_code": row.get("exit_code"),
        "run_kind": str(row.get("run_kind") or ""),
        "output_line_count": _int(row.get("output_line_count")),
        "preview_truncated": _bool(row.get("preview_truncated")),
        "full_output_available": _bool(row.get("full_output_available")),
        "full_output_truncated": _bool(row.get("full_output_truncated")),
        "artifact_count": _int(row.get("artifact_count")),
        "finding_count": _int(row.get("finding_count")),
        "label_count": _int(row.get("label_count")),
        "note_count": _int(row.get("note_count")),
        "atlas_entity_count": _int(row.get("atlas_entity_count")),
        "atlas_finding_count": _int(row.get("atlas_finding_count")),
        "scheduled": _bool(row.get("scheduled")),
        "schedule_id": str(row.get("schedule_id") or ""),
        "assessment_batch": assessment_batch,
        "assessment_batch_id": str((assessment_batch or {}).get("batch_id") or ""),
        "assessment_batch_item_index": (
            _int(assessment_batch["item"].get("item_index"))
            if assessment_batch
            else None
        ),
    }


def client_run_response(
    run_id: str,
    command: str,
    started: Any,
    finished: Any,
    exit_code: int,
    output_line_count: int,
    preview_truncated: bool,
) -> dict[str, Any]:
    """Return the saved-run envelope used by browser-owned terminal commands."""
    saved_run = run_summary({
        "id": run_id,
        "command": command,
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "exit_code": exit_code,
        "run_kind": "builtin",
        "output_line_count": output_line_count,
        "preview_truncated": preview_truncated,
        "full_output_available": False,
        "full_output_truncated": False,
    })
    return {
        "ok": True,
        "run": saved_run,
        "run_id": run_id,
        "output_line_count": output_line_count,
    }


def _run_status(row: dict[str, Any]) -> str:
    if row.get("status"):
        return str(row["status"])
    if row.get("finished"):
        exit_code = row.get("exit_code")
        if exit_code is None:
            return "complete"
        try:
            return "succeeded" if int(exit_code) == 0 else "failed"
        except (TypeError, ValueError):
            return "complete"
    return "running"


def artifact_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "run_id": str(row.get("run_id") or ""),
        "workspace_path": str(row.get("workspace_path") or ""),
        "display_name": str(row.get("display_name") or ""),
        "kind": str(row.get("kind") or ""),
        "byte_size": _int(row.get("byte_size")),
        "detected_by": str(row.get("detected_by") or ""),
        "content_type": str(row.get("content_type") or ""),
        "preview_type": str(row.get("preview_type") or ""),
        "content_sha256": str(row.get("content_sha256") or ""),
        "created": row.get("created"),
        "file_available": _bool(row.get("file_available", True)),
        "file_status": str(row.get("file_status") or ""),
        "file_status_detail": str(row.get("file_status_detail") or ""),
    }
