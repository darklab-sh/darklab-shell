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


def run_summary(row: dict[str, Any]) -> dict[str, Any]:
    run_id = str(row.get("id") or row.get("run_id") or "")
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
