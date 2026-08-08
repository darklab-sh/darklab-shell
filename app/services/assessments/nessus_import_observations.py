# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Trusted exact-version observations from applied Nessus import evidence."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from services.assessments.cpe_applicability import normalize_observed_cpe
from services.assessments.versioned_cpe import normalize_versioned_cpe
from services.atlas.nessus_versions import NESSUS_XML_CPE_PARSER_VERSION
from services.intel.canonical import entity_signature


NESSUS_IMPORT_OBSERVATION_LIMIT = 256


def load_nessus_import_version_observations(
    conn: Any,
    session_id: str,
    batch_id: str,
    *,
    team_id: str = "",
    observation_id: str = "",
) -> dict[str, Any]:
    """Load bounded owner-scoped observations from one immutable applied batch."""
    owner_session = _text(session_id, 128)
    owner_team = _text(team_id, 128)
    source_id = _text(batch_id, 128)
    evidence_id = _text(observation_id, 128)
    if not source_id or not (owner_session or owner_team) or (observation_id and not evidence_id):
        return _empty(source_id)
    rows = conn.execute(
        "SELECT e.id, e.batch_id, e.subject_key, e.external_id, e.observed_at, "
        "e.source_detail_json FROM atlas_import_evidence e "
        "JOIN atlas_import_batches b ON b.id = e.batch_id "
        "WHERE ((? != '' AND b.team_id = ?) OR "
        "(? = '' AND b.session_id = ? AND b.team_id = '')) "
        "AND b.id = ? AND b.status = 'applied' AND b.format_id = 'nessus_xml' "
        "AND e.evidence_type = 'nessus_service_version' AND (? = '' OR e.id = ?) "
        "ORDER BY e.row_number, e.id LIMIT ?",
        (
            owner_team, owner_team, owner_team, owner_session, source_id,
            evidence_id, evidence_id, NESSUS_IMPORT_OBSERVATION_LIMIT + 1,
        ),
    ).fetchall()
    observations = [item for row in rows if (item := _observation(row)) is not None]
    return {
        "source": "nessus_xml",
        "source_batch_id": source_id,
        "observations": observations[:NESSUS_IMPORT_OBSERVATION_LIMIT],
        "truncated": len(rows) > NESSUS_IMPORT_OBSERVATION_LIMIT,
    }


def nessus_import_observation_matches(record: dict[str, str], observation: dict[str, str]) -> bool:
    """Confirm candidate provenance matches the stored typed observation exactly."""
    return all((
        record["source_id"] == observation["source_batch_id"],
        record["observation_id"] == observation["observation_id"],
        record["target"] == observation["target"],
        record["observed_identifier"] == observation["cpe"],
        record["observed_version"] == observation["version"],
        record["tool_version"] == observation["tool_version"],
        record["parser_version"] == observation["parser_version"],
        record["observed_at"] == observation["observed_at"],
    ))


def persisted_nessus_import_observation_matches(
    conn: Any,
    session_id: str,
    team_id: str,
    record: dict[str, str],
) -> bool:
    """Reload candidate provenance from its applied batch and compare it exactly."""
    parsed = load_nessus_import_version_observations(
        conn,
        session_id,
        record["source_id"],
        team_id=team_id,
        observation_id=record["observation_id"],
    )
    observations = parsed["observations"]
    return len(observations) == 1 and nessus_import_observation_matches(record, observations[0])


def _observation(row: Any) -> dict[str, str] | None:
    detail = _json_object(row["source_detail_json"])
    target_kind = _text(detail.get("target_kind"), 32)
    target = _text(detail.get("target_value"), 512)
    cpe = normalize_versioned_cpe(detail.get("cpe"))
    normalized = normalize_observed_cpe(cpe, explicit_version=detail.get("version")) if cpe else None
    observed_at = _timestamp(row["observed_at"])
    tool_version = _text(detail.get("tool_version"), 128)
    parser_version = _text(detail.get("parser_version"), 128)
    expected_subject = f"{entity_signature(target_kind, target)}\x1f{cpe}" if target_kind and target and cpe else ""
    if not all((
        detail.get("adapter") == "nessus",
        target_kind in {"domain", "ip"},
        normalized,
        str(normalized["version"]) == _text(detail.get("version"), 128) if normalized else False,
        expected_subject == str(row["subject_key"] or ""),
        observed_at,
        tool_version,
        parser_version == NESSUS_XML_CPE_PARSER_VERSION,
    )):
        return None
    return {
        "observation_id": str(row["id"]),
        "target": target,
        "cpe": cpe,
        "version": str(normalized["version"]),
        "source_batch_id": str(row["batch_id"]),
        "observed_at": observed_at,
        "tool_version": tool_version,
        "parser_version": parser_version,
        "plugin_id": _text(row["external_id"], 128),
    }


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _timestamp(value: Any) -> str:
    text = _text(value, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return text if parsed.tzinfo is not None else ""


def _text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if text and len(text) <= limit and not any(ord(char) < 32 for char in text) else ""


def _empty(batch_id: str) -> dict[str, Any]:
    return {"source": "nessus_xml", "source_batch_id": batch_id, "observations": [], "truncated": False}


__all__ = [
    "NESSUS_IMPORT_OBSERVATION_LIMIT",
    "load_nessus_import_version_observations",
    "nessus_import_observation_matches",
    "persisted_nessus_import_observation_matches",
]
