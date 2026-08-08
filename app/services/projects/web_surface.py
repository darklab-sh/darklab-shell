# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-scoped Web Surface capture queries."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.web_gallery import web_surface_rows_from_events
from services.intel.canonical import (
    CanonicalizationError,
    canonical_domain,
    canonical_ip,
    canonical_url,
)
from services.projects.artifacts import (
    artifact_availability,
    artifact_owner_context,
    row_to_run_file_artifact,
)
from services.projects.scope import shared_owner_where
from services.projects.utils import normalize_page_window, page_payload
from services.runs.kinds import RUN_KIND_EXTERNAL


_IMAGE_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")


def list_project_web_surface(session_id, project_id, *, limit=50, offset=0, team_id=""):
    """Return a bounded capture page backed by verified project image artifacts."""
    safe_limit, safe_offset = normalize_page_window(limit, offset)
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(
            session_id, team_id=team_id, table_alias="p",
        )
        run_owner_sql, run_owner_params = shared_owner_where(
            session_id, team_id=team_id, table_alias="r",
        )
        where_sql = (
            "p.id = ? AND " + project_owner_sql + " AND " + run_owner_sql
            + " AND r.run_kind = ? AND a.kind = 'screenshot' "
            "AND a.detected_by = 'httpx_screenshot' AND a.preview_type = 'image' "
            "AND a.content_type IN ('image/jpeg', 'image/png', 'image/webp')"
        )
        params = (project_id, *project_owner_params, *run_owner_params, RUN_KIND_EXTERNAL)
        total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM run_file_artifacts a "
            "JOIN runs r ON r.id = a.run_id "
            "JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = r.id "
            "JOIN projects p ON p.id = l.project_id WHERE " + where_sql,  # nosec B608
            params,
        ).fetchone()
        if total_row is None:
            return None
        project_row = conn.execute(
            "SELECT 1 FROM projects p WHERE p.id = ? AND " + project_owner_sql,  # nosec B608
            (project_id, *project_owner_params),
        ).fetchone()
        if not project_row:
            return None
        total = int(total_row["count"] or 0)
        capture_filter_sql = where_sql + " ORDER BY a.created DESC, a.id DESC LIMIT ? OFFSET ?"
        rows = conn.execute(
            "SELECT a.id, a.session_id, a.run_id, a.workspace_path, a.display_name, "  # nosec B608
            "a.kind, a.byte_size, a.detected_by, a.content_type, a.preview_type, "
            "a.content_sha256, a.created, r.team_id AS run_team_id, r.command, "
            "r.started, r.finished, r.output_preview "
            "FROM run_file_artifacts a JOIN runs r ON r.id = a.run_id "
            "JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = r.id "
            "JOIN projects p ON p.id = l.project_id WHERE "
            + capture_filter_sql,
            (*params, safe_limit, safe_offset),
        ).fetchall()
        captures = _capture_items(session_id, rows)
        _attach_capture_entity_ids(conn, session_id, captures, team_id=team_id)
    return page_payload("captures", captures, total, safe_limit, safe_offset)


def _capture_items(session_id: str, rows: list[object]) -> list[dict[str, object]]:
    dialect = dialect_for_backend(get_db_backend())
    event_rows_by_run: dict[str, dict[str, dict[str, object] | None]] = {}
    captures = []
    for row in rows:
        artifact = row_to_run_file_artifact(row)
        if not artifact:
            continue
        run_id = str(artifact["run_id"] or "")
        if run_id not in event_rows_by_run:
            events = dialect.decode_json_list(row["output_preview"])
            event_rows_by_run[run_id] = _capture_metadata_by_path(events, run_id)
        metadata_by_path = event_rows_by_run[run_id]
        workspace_path = str(artifact["workspace_path"] or "")
        metadata = metadata_by_path.get(workspace_path)
        metadata_state = "available" if isinstance(metadata, dict) else (
            "conflict" if workspace_path in metadata_by_path else "missing"
        )
        availability = artifact_availability(
            str(artifact.get("session_id") or session_id),
            artifact,
            owner_context=artifact_owner_context(str(artifact.get("session_id") or session_id), artifact),
        )
        capture = {
            **(metadata or {}),
            "metadata_state": metadata_state,
            "capture_state": _capture_state(metadata_state, availability),
            "artifact": _artifact_payload(artifact, availability),
            "source_run": {
                "id": run_id,
                "command": str(row["command"] or ""),
                "started": str(row["started"] or ""),
                "finished": str(row["finished"] or ""),
            },
            "url_entity_id": "",
            "host_entity_id": "",
        }
        captures.append(capture)
    return captures


def _capture_metadata_by_path(events: object, run_id: str) -> dict[str, dict[str, object] | None]:
    indexed: dict[str, dict[str, object] | None] = {}
    for row in web_surface_rows_from_events(events):
        path = str(row.get("artifact_path") or "")
        source_run_id = str(row.get("source_run_id") or "")
        if not path:
            continue
        normalized = {**row, "source_run_id": run_id}
        if source_run_id and source_run_id != run_id:
            normalized = None
        previous = indexed.get(path)
        if path not in indexed:
            indexed[path] = normalized
        elif previous != normalized:
            indexed[path] = None
    return indexed


def _artifact_payload(artifact: Mapping[str, object], availability: Mapping[str, object]) -> dict[str, object]:
    return {
        "id": artifact.get("id") or "",
        "workspace_path": artifact.get("workspace_path") or "",
        "display_name": artifact.get("display_name") or "",
        "byte_size": max(0, int(artifact.get("byte_size") or 0)),
        "content_type": artifact.get("content_type") if artifact.get("content_type") in _IMAGE_CONTENT_TYPES else "",
        "content_sha256": artifact.get("content_sha256") or "",
        "created": artifact.get("created") or "",
        **availability,
    }


def _capture_state(metadata_state: str, availability: Mapping[str, object]) -> str:
    if metadata_state != "available":
        return f"metadata_{metadata_state}"
    file_status = str(availability.get("file_status") or "missing")
    if file_status == "available":
        return "current"
    if file_status == "changed":
        return "changed"
    return "unavailable"


def _attach_capture_entity_ids(conn, session_id: str, captures: list[dict[str, object]], *, team_id="") -> None:
    run_ids = sorted({str(item["source_run"]["id"]) for item in captures if item.get("url")})
    url_values = sorted({_canonical_capture_url(item.get("url")) for item in captures} - {""})
    host_values = sorted({_capture_host(item.get("url")) for item in captures} - {""})
    if not run_ids or not url_values:
        return
    run_placeholders = ",".join("?" for _ in run_ids)
    value_placeholders = ",".join("?" for _ in (*url_values, *host_values))
    entity_owner_sql, entity_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e",
    )
    entity_filter_sql = (
        f"erl.run_id IN ({run_placeholders}) AND "
        + entity_owner_sql
        + " AND e.type IN ('url', 'domain', 'ip') "
        + f"AND e.canonical_value IN ({value_placeholders})"
    )
    rows = conn.execute(
        "SELECT erl.run_id, e.id, e.type, e.canonical_value, e.host_entity_id "  # nosec B608
        "FROM entity_run_links erl JOIN entities e ON e.id = erl.entity_id "
        "WHERE "
        + entity_filter_sql,
        (*run_ids, *entity_owner_params, *url_values, *host_values),
    ).fetchall()
    linked = {(str(row["run_id"]), str(row["type"]), str(row["canonical_value"])): row for row in rows}
    linked_ids = {(str(row["run_id"]), str(row["id"])) for row in rows}
    for capture in captures:
        run_id = str(capture["source_run"]["id"])
        url_row = linked.get((run_id, "url", _canonical_capture_url(capture.get("url"))))
        host_value = _capture_host(capture.get("url"))
        host_type = _host_type(host_value)
        host_row = linked.get((run_id, host_type, host_value)) if host_type else None
        if url_row:
            capture["url_entity_id"] = str(url_row["id"] or "")
            url_host_id = str(url_row["host_entity_id"] or "")
            if url_host_id and (run_id, url_host_id) in linked_ids:
                capture["host_entity_id"] = url_host_id
        if not capture["host_entity_id"] and host_row:
            capture["host_entity_id"] = str(host_row["id"] or "")


def _canonical_capture_url(value: object) -> str:
    try:
        return canonical_url(str(value or ""))
    except CanonicalizationError:
        return ""


def _capture_host(value: object) -> str:
    host = str(urlsplit(str(value or "")).hostname or "")
    try:
        return canonical_ip(host)
    except CanonicalizationError:
        try:
            return canonical_domain(host)
        except CanonicalizationError:
            return ""


def _host_type(value: str) -> str:
    if not value:
        return ""
    try:
        canonical_ip(value)
    except CanonicalizationError:
        return "domain"
    return "ip"


__all__ = ["list_project_web_surface"]
