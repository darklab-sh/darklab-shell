# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Owner-scoped reads for bounded informational Nmap service evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.projects.scope import shared_owner_where
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload


NMAP_SERVICE_EVIDENCE_PAGE_MAX = 100
NMAP_SERVICE_EVIDENCE_PER_CHECK = 20


def _structured_fields(value: object) -> list[dict[str, Any]]:
    decoded = dialect_for_backend(get_db_backend()).decode_json_list(value)
    return [
        {
            "path": [str(segment) for segment in field.get("path", [])],
            "value": str(field.get("value") or ""),
        }
        for field in decoded
        if isinstance(field, Mapping) and isinstance(field.get("path"), list)
    ]


def _observation(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"] or ""),
        "run_id": str(row["run_id"] or ""),
        "target": str(row["target"] or ""),
        "service": str(row["service"] or ""),
        "script_id": str(row["script_id"] or ""),
        "evidence_kind": str(row["evidence_kind"] or ""),
        "classification": str(row["classification"] or ""),
        "tool_version": str(row["tool_version"] or ""),
        "parser_version": str(row["parser_version"] or ""),
        "fields": _structured_fields(row["fields_json"]),
        "fields_truncated": bool(row["fields_truncated"]),
        "collection_truncated": bool(row["collection_truncated"]),
        "observed_at": row["observed_at"],
        "created_at": row["created_at"],
    }


def nmap_service_evidence_for_run_on_conn(
    conn: Any,
    session_id: str,
    run_id: str,
    *,
    team_id: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    """Return one owner's paginated service observations for a saved run."""
    safe_limit = normalize_page_limit(limit, 50, NMAP_SERVICE_EVIDENCE_PAGE_MAX)
    safe_offset = normalize_page_offset(offset)
    run_owner_sql, run_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="r",
    )
    observation_owner_sql, observation_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="o",
    )
    base = (
        " FROM nmap_service_observations o JOIN runs r ON r.id = o.run_id "
        "WHERE o.run_id = ? AND " + run_owner_sql + " AND " + observation_owner_sql
    )
    params = (str(run_id or "").strip(), *run_owner_params, *observation_owner_params)
    run = conn.execute(
        "SELECT r.id FROM runs r WHERE r.id = ? AND " + run_owner_sql,  # nosec
        (str(run_id or "").strip(), *run_owner_params),
    ).fetchone()
    if not run:
        return None
    total_row = conn.execute("SELECT COUNT(*) AS count" + base, params).fetchone()
    total = int(total_row["count"] or 0) if total_row else 0
    rows = conn.execute(
        "SELECT o.*" + base
        + " ORDER BY o.observed_at DESC, o.id DESC LIMIT ? OFFSET ?",  # nosec
        (*params, safe_limit, safe_offset),
    ).fetchall()
    return page_payload(
        "observations",
        [_observation(row) for row in rows],
        total,
        safe_limit,
        safe_offset,
    )


def list_nmap_service_evidence(
    session_id: str,
    run_id: str,
    *,
    team_id: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        return nmap_service_evidence_for_run_on_conn(
            conn, session_id, run_id, team_id=team_id, limit=limit, offset=offset,
        )


def attach_nmap_service_evidence(
    conn: Any,
    checks: list[dict[str, Any]],
    *,
    session_id: str,
    team_id: str = "",
) -> None:
    """Attach newest-first service facts from available run evidence links."""
    check_ids = [str(check.get("id") or "") for check in checks if check.get("id")]
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="o",
    )
    grouped: dict[str, list[dict[str, Any]]] = {check_id: [] for check_id in check_ids}
    totals: dict[str, int] = {check_id: 0 for check_id in check_ids}
    if check_ids:
        placeholders = ",".join("?" for _ in check_ids)
        rows = conn.execute(
            "SELECT * FROM (SELECT e.check_id, o.*, "
            "ROW_NUMBER() OVER (PARTITION BY e.check_id ORDER BY o.observed_at DESC, o.id DESC) AS item_rank, "
            "COUNT(*) OVER (PARTITION BY e.check_id) AS item_total "
            "FROM project_assessment_evidence e JOIN nmap_service_observations o "
            "ON o.run_id = e.evidence_id WHERE e.evidence_type = 'run' "
            "AND e.source_state = 'available' AND e.check_id IN (" + placeholders + ") AND "  # nosec
            + owner_sql + ") ranked WHERE item_rank <= ? "
            "ORDER BY check_id ASC, observed_at DESC, id DESC",
            (*check_ids, *owner_params, NMAP_SERVICE_EVIDENCE_PER_CHECK),
        ).fetchall()
        for row in rows:
            check_id = str(row["check_id"] or "")
            grouped.setdefault(check_id, []).append(_observation(row))
            totals[check_id] = int(row["item_total"] or 0)
    for check in checks:
        check_id = str(check.get("id") or "")
        check["nmap_service_evidence"] = page_payload(
            "observations",
            grouped.get(check_id, []),
            totals.get(check_id, 0),
            NMAP_SERVICE_EVIDENCE_PER_CHECK,
            0,
        )


__all__ = [
    "attach_nmap_service_evidence",
    "list_nmap_service_evidence",
    "nmap_service_evidence_for_run_on_conn",
]
