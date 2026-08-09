# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Idempotent persistence for bounded informational Nmap service evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from core.output_targets import command_root
from services.assessments.nmap_service_observations import (
    parse_nmap_xml_service_observations,
)
from services.projects.scope import shared_owner_where


def persist_nmap_xml_service_observations(
    conn: Any,
    session_id: str,
    payload: bytes | str,
    *,
    source_run_id: str,
    team_id: str = "",
    observed_at: str = "",
) -> dict[str, Any]:
    """Store exact structured facts only for a successful owner-scoped Nmap run."""
    run_id = str(source_run_id or "").strip()
    if not _valid_source_run(conn, session_id, team_id, run_id):
        return _summary()
    parsed = parse_nmap_xml_service_observations(
        payload,
        source_run_id=run_id,
        observed_at=observed_at,
    )
    observations = parsed.get("observations")
    if not isinstance(observations, list):
        return _summary()
    created_count = 0
    skipped_count = 0
    for observation in observations:
        if not isinstance(observation, Mapping):
            skipped_count += 1
            continue
        created_count += _persist_observation(
            conn,
            session_id,
            team_id,
            run_id,
            parsed,
            observation,
        )
    return _summary(
        observation_count=len(observations),
        created_count=created_count,
        skipped_count=skipped_count,
        truncated=bool(parsed.get("truncated")),
    )


def _valid_source_run(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
) -> bool:
    if not run_id:
        return False
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="r",
    )
    row = conn.execute(
        "SELECT r.command, r.run_kind, r.finished, r.exit_code FROM runs r WHERE r.id = ? AND "
        + owner_sql,  # nosec B608
        (run_id, *owner_params),
    ).fetchall()
    if len(row) != 1:
        return False
    source = row[0]
    return bool(
        str(source["run_kind"] or "") == "external"
        and str(source["finished"] or "")
        and int(source["exit_code"] if source["exit_code"] is not None else -1) == 0
        and command_root(str(source["command"] or "")) == "nmap"
    )


def _persist_observation(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    parsed: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> int:
    dialect = dialect_for_backend(get_db_backend())
    fields = observation.get("fields")
    normalized_fields = list(fields) if isinstance(fields, list) else []
    values = (
        str(observation.get("observation_id") or ""),
        session_id,
        team_id,
        run_id,
        str(observation.get("target") or ""),
        str(observation.get("service") or ""),
        str(observation.get("script_id") or ""),
        str(observation.get("evidence_kind") or ""),
        str(observation.get("classification") or ""),
        str(parsed.get("tool_version") or ""),
        str(parsed.get("parser_version") or ""),
        dialect.json_param(normalized_fields),
        bool(observation.get("fields_truncated")),
        bool(parsed.get("truncated")),
        str(parsed.get("observed_at") or ""),
        str(parsed.get("observed_at") or ""),
    )
    result = conn.execute(
        "INSERT INTO nmap_service_observations "
        "(id, session_id, team_id, run_id, target, service, script_id, evidence_kind, "
        "classification, tool_version, parser_version, fields_json, fields_truncated, "
        "collection_truncated, observed_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        values,
    )
    created = max(0, int(getattr(result, "rowcount", 0) or 0)) > 0
    row = conn.execute(
        "SELECT * FROM nmap_service_observations WHERE id = ?",
        (values[0],),
    ).fetchone()
    if not row or not _matches(row, values, normalized_fields, dialect):
        raise RuntimeError("Nmap service observation identity conflict")
    return int(created)


def _matches(row: Any, values: tuple[Any, ...], fields: list[Any], dialect: Any) -> bool:
    keys = (
        "id", "session_id", "team_id", "run_id", "target", "service", "script_id",
        "evidence_kind", "classification", "tool_version", "parser_version",
    )
    return bool(
        all(str(row[key] or "") == str(values[index] or "") for index, key in enumerate(keys))
        and dialect.decode_json_list(row["fields_json"]) == fields
        and bool(row["fields_truncated"]) == bool(values[12])
        and bool(row["collection_truncated"]) == bool(values[13])
        and str(row["observed_at"] or "").replace(" ", "T") == str(values[14])
    )


def _summary(
    *,
    observation_count: int = 0,
    created_count: int = 0,
    skipped_count: int = 0,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "observation_count": observation_count,
        "created_count": created_count,
        "skipped_count": skipped_count,
        "truncated": truncated,
    }


__all__ = ["persist_nmap_xml_service_observations"]
