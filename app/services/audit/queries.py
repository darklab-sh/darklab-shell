"""Audit event read helpers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from core import database
from core.database_backend import dialect_for_backend
from services.teams.storage import token_hash


@dataclass(frozen=True)
class AuditEventFilters:
    event_type: str = ""
    actor: str = ""
    actor_member_id: str = ""
    actor_session_hash: str = ""
    owner_session_hash: str = ""
    session_id: str = ""
    team_id: str = ""
    project_id: str = ""
    target_type: str = ""
    target_id: str = ""
    correlation_id: str = ""
    date_from: str = ""
    date_to: str = ""


@contextmanager
def _managed_connection(conn=None):
    if conn is not None:
        yield conn, False
        return
    with database.db_connect() as opened:
        yield opened, True


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key]


def _contains_like_filter(value: str) -> str:
    escaped = value.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escaped}%"


def _normalize_date_filter(value: str, *, end_of_day: bool) -> str:
    stripped = str(value or "").strip()
    parts = stripped.split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return stripped
    year, month, day = parts
    if len(year) != 4 or len(month) != 2 or len(day) != 2:
        return stripped
    suffix = "23:59:59.999999+00:00" if end_of_day else "00:00:00+00:00"
    return f"{stripped}T{suffix}"


def event_from_row(row: Any) -> dict[str, Any]:
    dialect = dialect_for_backend(database.DB_BACKEND)
    details = dialect.decode_json_dict(_row_value(row, "details"))
    return {
        "id": _row_value(row, "id"),
        "owner_session_hash": _row_value(row, "owner_session_hash"),
        "team_id": _row_value(row, "team_id"),
        "actor_session_hash": _row_value(row, "actor_session_hash"),
        "actor_session_label": _row_value(row, "actor_session_label"),
        "actor_member_id": _row_value(row, "actor_member_id"),
        "actor_role": _row_value(row, "actor_role"),
        "actor_display_name": _row_value(row, "actor_display_name"),
        "event_type": _row_value(row, "event_type"),
        "target_type": _row_value(row, "target_type"),
        "target_id": _row_value(row, "target_id"),
        "project_id": _row_value(row, "project_id"),
        "request_id": _row_value(row, "request_id"),
        "correlation_id": _row_value(row, "correlation_id"),
        "job_id": _row_value(row, "job_id"),
        "details_version": int(_row_value(row, "details_version") or 0),
        "created": _row_value(row, "created"),
        "client_ip": _row_value(row, "client_ip"),
        "user_agent": _row_value(row, "user_agent"),
        "details": details,
    }


def list_events(
    filters: AuditEventFilters | None = None,
    *,
    conn=None,
    limit: int = 100,
    offset: int = 0,
    max_limit: int = 500,
) -> dict[str, Any]:
    active_filters = filters or AuditEventFilters()
    actor_session_hash = active_filters.actor_session_hash
    if not actor_session_hash and active_filters.session_id:
        actor_session_hash = token_hash(active_filters.session_id)
    owner_session_hash = active_filters.owner_session_hash
    if not owner_session_hash and active_filters.session_id:
        owner_session_hash = token_hash(active_filters.session_id)
    actor_filter = str(active_filters.actor or "").strip()
    actor_like_filter = _contains_like_filter(actor_filter) if actor_filter else ""
    filter_values = [
        str(active_filters.event_type or "").strip(),
        actor_filter,
        str(active_filters.actor_member_id or "").strip(),
        str(actor_session_hash or "").strip(),
        str(owner_session_hash or "").strip(),
        str(active_filters.team_id or "").strip(),
        str(active_filters.project_id or "").strip(),
        str(active_filters.target_type or "").strip(),
        str(active_filters.target_id or "").strip(),
        str(active_filters.correlation_id or "").strip(),
        _normalize_date_filter(active_filters.date_from, end_of_day=False),
        _normalize_date_filter(active_filters.date_to, end_of_day=True),
    ]
    params: list[Any] = [
        filter_values[0], filter_values[0],
        filter_values[1], filter_values[1], actor_like_filter, actor_like_filter, actor_like_filter, filter_values[1],
        filter_values[2], filter_values[2],
        filter_values[3], filter_values[3],
        filter_values[4], filter_values[4],
        filter_values[5], filter_values[5],
        filter_values[6], filter_values[6],
        filter_values[7], filter_values[7],
        filter_values[8], filter_values[8],
        filter_values[9], filter_values[9],
        filter_values[10], filter_values[10],
        filter_values[11], filter_values[11],
    ]
    normalized_max_limit = max(1, int(max_limit or 500))
    page_limit = max(1, min(int(limit or 100), normalized_max_limit))
    page_offset = max(0, int(offset or 0))
    with _managed_connection(conn) as (active_conn, _owns_conn):
        rows = active_conn.execute(
            """
            SELECT * FROM audit_events
            WHERE (? = '' OR event_type = ?)
              AND (
                  ? = ''
                  OR actor_member_id = ?
                  OR LOWER(COALESCE(actor_member_id, '')) LIKE ? ESCAPE '!'
                  OR LOWER(COALESCE(actor_display_name, '')) LIKE ? ESCAPE '!'
                  OR LOWER(COALESCE(actor_session_label, '')) LIKE ? ESCAPE '!'
                  OR actor_session_hash = ?
              )
              AND (? = '' OR actor_member_id = ?)
              AND (? = '' OR actor_session_hash = ?)
              AND (? = '' OR owner_session_hash = ?)
              AND (? = '' OR team_id = ?)
              AND (? = '' OR project_id = ?)
              AND (? = '' OR target_type = ?)
              AND (? = '' OR target_id = ?)
              AND (? = '' OR correlation_id = ?)
              AND (? = '' OR created >= ?)
              AND (? = '' OR created <= ?)
            ORDER BY created DESC, id DESC LIMIT ? OFFSET ?
            """,
            [*params, page_limit + 1, page_offset],
        ).fetchall()
    events = [event_from_row(row) for row in rows[:page_limit]]
    return {
        "events": events,
        "limit": page_limit,
        "offset": page_offset,
        "has_more": len(rows) > page_limit,
    }


def iter_event_pages(
    filters: AuditEventFilters | None = None,
    *,
    conn=None,
    max_rows: int = 10000,
    page_size: int = 500,
):
    export_limit = max(1, int(max_rows or 10000))
    normalized_page_size = max(1, min(int(page_size or 500), export_limit, 1000))
    yielded = 0
    offset = 0
    with _managed_connection(conn) as (active_conn, _owns_conn):
        while yielded < export_limit:
            limit = min(normalized_page_size, export_limit - yielded)
            payload = list_events(
                filters,
                conn=active_conn,
                limit=limit,
                offset=offset,
                max_limit=limit,
            )
            events = payload["events"]
            if not events:
                break
            yielded += len(events)
            offset += len(events)
            truncated = yielded >= export_limit and bool(payload.get("has_more"))
            yield {
                "events": events,
                "limit": export_limit,
                "offset": payload["offset"],
                "truncated": truncated,
            }
            if truncated or not payload.get("has_more"):
                break
