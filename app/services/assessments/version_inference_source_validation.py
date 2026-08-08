# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Owner, source, and entity validation for persisted version inference."""

from __future__ import annotations

from typing import Any

from core.output_targets import command_root
from services.assessments.nessus_import_observations import persisted_nessus_import_observation_matches


_RUN_PARSER_PREFIXES = {"httpx": "httpx-", "nmap": "nmap-"}


def resolve_version_inference_source(
    conn: Any,
    session_id: str,
    team_id: str,
    record: dict[str, str],
) -> tuple[Any, str] | None:
    """Return an owned compatible source and its trusted tool root."""
    query = "SELECT s.* FROM runs s " if record["source_kind"] == "run" else (
        "SELECT s.* FROM atlas_import_batches s "
    )
    row = conn.execute(
        query + "WHERE ((? != '' AND s.team_id = ?) OR "
        "(? = '' AND s.session_id = ? AND s.team_id = '')) AND s.id = ?",
        (team_id, team_id, team_id, session_id, record["source_id"]),
    ).fetchone()
    if not row:
        return None
    if record["source_kind"] == "run":
        source_root = command_root(row["command"])
        parser_prefix = _RUN_PARSER_PREFIXES.get(source_root, "")
        if (
            row["finished"] is None
            or row["exit_code"] != 0
            or not parser_prefix
            or not record["parser_version"].startswith(parser_prefix)
        ):
            return None
        return row, source_root
    if str(row["status"] or "") != "applied":
        return None
    return (row, "import") if persisted_nessus_import_observation_matches(
        conn, session_id, team_id, record
    ) else None


def resolve_version_inference_entity(
    conn: Any,
    session_id: str,
    team_id: str,
    record: dict[str, str],
) -> Any:
    """Resolve exactly one owned entity linked to the validated source."""
    query = (
        "SELECT e.id, e.type, e.canonical_value FROM entities e "
        "WHERE ((? != '' AND e.team_id = ?) OR "
        "(? = '' AND e.session_id = ? AND e.team_id = '')) "
        "AND e.canonical_value = ? AND "
    )
    source_query = (
        "EXISTS (SELECT 1 FROM entity_run_links l WHERE l.entity_id = e.id AND l.run_id = ?) "
        if record["source_kind"] == "run" else
        "EXISTS (SELECT 1 FROM atlas_entity_import_links l WHERE l.entity_id = e.id AND l.batch_id = ?) "
    )
    rows = conn.execute(
        query + source_query + "ORDER BY e.id LIMIT 2",
        (team_id, team_id, team_id, session_id, record["target"], record["source_id"]),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


__all__ = ["resolve_version_inference_entity", "resolve_version_inference_source"]
