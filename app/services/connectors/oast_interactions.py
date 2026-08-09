# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded persistence and Project evidence links for private OAST callbacks."""

from __future__ import annotations

from datetime import datetime
import re
import secrets
from typing import Any

from core.database_backend import DatabaseBackend, dialect_for_backend, parse_database_backend
from services.assessments.coverage import enforce_evidence_quotas
from services.connectors.oast_interaction_review import (
    OastInteractionReviewError,
    ReviewedOastInteraction,
    review_oast_interaction,
)
from services.connectors.oast_correlations import (
    OastCorrelationError,
    _connection_scope,
    _owner_predicate,
    _utc_now,
)
from services.projects.contracts import ProjectWorkspaceQuotaExceeded


_INTERACTION_ID_RE = re.compile(r"oin_[0-9a-f]{32}")
_MAX_INTERACTIONS_PER_CORRELATION = 64
_MANUAL_PROTECTED_STATES = frozenset({"blocked", "skipped", "not_applicable"})
_CHECK_REASON = "Private OAST interaction captured; review the saved interaction evidence."


def _conn_dialect(conn):
    backend = getattr(conn, "database_backend", DatabaseBackend.SQLITE)
    return dialect_for_backend(parse_database_backend(backend))


def _decode_json(conn, value: object) -> dict[str, Any]:
    return _conn_dialect(conn).decode_json_dict(value)


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    return _utc_now(parsed)


def _interaction_row(conn, row: Any) -> dict[str, Any]:
    data = dict(row)
    data["finding_id"] = str(data.get("finding_id") or "")
    data["summary"] = _decode_json(conn, data.pop("summary_json", {}))
    data["callback_domain"] = (
        f"{data['callback_label']}.{data['allowed_domain']}"
    )
    return data


def _select_sql(owner_sql: str) -> str:
    return (
        "SELECT i.*, c.session_id, c.team_id, c.project_id, c.assessment_id, "
        "c.check_id, c.run_id, c.target_entity_id, c.callback_label, "
        "c.allowed_domain, c.status AS correlation_status, c.activated_at, "
        "c.active_until FROM oast_interactions i JOIN oast_correlations c "
        "ON c.id = i.correlation_id WHERE " + owner_sql  # nosec B608
    )


def _owned_correlation(conn, session_id: str, team_id: str, correlation_id: str):
    owner_sql, owner_params = _owner_predicate(session_id, team_id, table_prefix="c")
    return conn.execute(
        "SELECT c.*, pc.state AS check_state, pc.state_source AS check_state_source, "
        "pc.state_reason AS check_state_reason, pc.first_evidence_at, pc.last_evidence_at "
        "FROM oast_correlations c JOIN project_assessment_checks pc "
        "ON pc.assessment_id = c.assessment_id AND pc.id = c.check_id "
        "WHERE c.id = ? AND " + owner_sql,  # nosec B608
        (correlation_id, *owner_params),
    ).fetchone()


def _increment_count(conn, correlation_id: str, column: str, instant: str) -> None:
    if column not in {"duplicate_count", "rejected_count"}:
        raise ValueError("unsupported OAST counter")
    conn.execute(
        f"UPDATE oast_correlations SET {column} = {column} + 1, updated_at = ? "  # nosec B608
        f"WHERE id = ? AND {column} < 10000",
        (instant, correlation_id),
    )


def _validate_active_window(
    correlation: Any,
    reviewed: ReviewedOastInteraction,
    received: datetime,
) -> None:
    activated = _timestamp(correlation["activated_at"])
    active_until = _timestamp(correlation["active_until"])
    observed = _timestamp(reviewed.observed_at)
    callback_matches = reviewed.callback_label == str(correlation["callback_label"] or "")
    if reviewed.protocol == "dns" and reviewed.summary.get("query_name"):
        callback_domain = (
            f"{correlation['callback_label']}.{correlation['allowed_domain']}"
        ).lower()
        query_name = reviewed.summary["query_name"]
        callback_matches = callback_matches and (
            query_name == callback_domain or query_name.endswith("." + callback_domain)
        )
    if (
        str(correlation["status"] or "") != "active"
        or not str(correlation["run_id"] or "")
        or not callback_matches
        or not activated <= observed < active_until
        or not activated <= received < active_until
    ):
        raise OastCorrelationError(
            "oast_interaction_window_closed",
            "The OAST interaction is outside its active correlation window",
        )


def _ensure_assessment_run_evidence(conn, correlation: Any, observed_at: str) -> None:
    existing = conn.execute(
        "SELECT 1 FROM project_assessment_evidence WHERE check_id = ? "
        "AND evidence_type = 'run' AND evidence_id = ?",
        (correlation["check_id"], correlation["run_id"]),
    ).fetchone()
    candidate = {
        "already_linked": existing is not None,
        "session_id": str(correlation["session_id"] or ""),
        "team_id": str(correlation["team_id"] or ""),
        "project_id": str(correlation["project_id"] or ""),
    }
    try:
        enforce_evidence_quotas(conn, [candidate])
    except ProjectWorkspaceQuotaExceeded as exc:
        raise OastCorrelationError(
            "oast_interaction_evidence_limit",
            "The Project assessment evidence limit was reached",
        ) from exc
    if existing is None:
        evidence_id = "aev_" + secrets.token_hex(12)
        conn.execute(
            "INSERT INTO project_assessment_evidence "
            "(id, assessment_id, check_id, evidence_type, evidence_id, source_state, "
            "observed_at, unavailable_at, unavailable_reason, match_rule_key, "
            "match_rule_version, linked_by, created_at, updated_at) "
            "VALUES (?, ?, ?, 'run', ?, 'available', ?, NULL, '', "
            "'private_oast_interaction', '1', 'derived', ?, ?)",
            (
                evidence_id,
                correlation["assessment_id"],
                correlation["check_id"],
                correlation["run_id"],
                observed_at,
                observed_at,
                observed_at,
            ),
        )
    current_state = str(correlation["check_state"] or "")
    protected = (
        str(correlation["check_state_source"] or "") == "manual"
        and current_state in _MANUAL_PROTECTED_STATES
    )
    first_evidence_at = str(correlation["first_evidence_at"] or "") or observed_at
    last_evidence_at = max(str(correlation["last_evidence_at"] or ""), observed_at)
    if protected:
        conn.execute(
            "UPDATE project_assessment_checks SET first_evidence_at = ?, "
            "last_evidence_at = ?, updated_at = ? WHERE id = ?",
            (first_evidence_at, last_evidence_at, observed_at, correlation["check_id"]),
        )
        return
    conn.execute(
        "UPDATE project_assessment_checks SET state = 'needs_review', "
        "state_source = 'derived', state_reason = ?, first_evidence_at = ?, "
        "last_evidence_at = ?, updated_at = ? WHERE id = ?",
        (
            _CHECK_REASON,
            first_evidence_at,
            last_evidence_at,
            observed_at,
            correlation["check_id"],
        ),
    )


def ingest_oast_interaction(
    session_id: str,
    correlation_id: str,
    payload: object,
    *,
    team_id: str = "",
    interaction_id: str = "",
    now: datetime | None = None,
    conn=None,
) -> dict[str, Any]:
    """Persist one redacted interaction only while its correlation is active."""
    received = _utc_now(now)
    received_at = received.isoformat()
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        correlation = _owned_correlation(
            active_conn,
            str(session_id or "").strip(),
            str(team_id or "").strip(),
            str(correlation_id or "").strip(),
        )
        if correlation is None:
            raise OastCorrelationError(
                "oast_correlation_not_found",
                "OAST correlation not found",
            )
        try:
            reviewed = review_oast_interaction(payload)
        except OastInteractionReviewError as exc:
            _increment_count(
                active_conn,
                str(correlation["id"]),
                "rejected_count",
                received_at,
            )
            if owns_conn:
                active_conn.commit()
            raise OastCorrelationError(exc.code, str(exc)) from exc
        try:
            _validate_active_window(correlation, reviewed, received)
        except OastCorrelationError:
            _increment_count(
                active_conn,
                str(correlation["id"]),
                "rejected_count",
                received_at,
            )
            if owns_conn:
                active_conn.commit()
            raise
        existing = active_conn.execute(
            "SELECT i.*, c.session_id, c.team_id, c.project_id, c.assessment_id, "
            "c.check_id, c.run_id, c.target_entity_id, c.callback_label, "
            "c.allowed_domain, c.status AS correlation_status, c.activated_at, "
            "c.active_until FROM oast_interactions i JOIN oast_correlations c "
            "ON c.id = i.correlation_id WHERE i.correlation_id = ? "
            "AND i.event_fingerprint = ?",
            (correlation["id"], reviewed.event_fingerprint),
        ).fetchone()
        if existing is not None:
            _increment_count(
                active_conn,
                str(correlation["id"]),
                "duplicate_count",
                received_at,
            )
            if owns_conn:
                active_conn.commit()
            return {"created": False, "interaction": _interaction_row(active_conn, existing)}
        if int(correlation["interaction_count"] or 0) >= _MAX_INTERACTIONS_PER_CORRELATION:
            _increment_count(
                active_conn,
                str(correlation["id"]),
                "rejected_count",
                received_at,
            )
            if owns_conn:
                active_conn.commit()
            raise OastCorrelationError(
                "oast_interaction_limit",
                "The OAST correlation interaction limit was reached",
            )
        selected_id = str(interaction_id or "").strip() or "oin_" + secrets.token_hex(16)
        if not _INTERACTION_ID_RE.fullmatch(selected_id):
            raise OastCorrelationError(
                "oast_interaction_id_invalid",
                "The OAST interaction id is invalid",
            )
        _ensure_assessment_run_evidence(active_conn, correlation, reviewed.observed_at)
        active_conn.execute(
            "INSERT INTO oast_interactions ("
            "id, correlation_id, protocol, event_fingerprint, provider_event_sha256, "
            "observed_at, received_at, summary_json, redacted_field_count, "
            "truncated_field_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                selected_id,
                correlation["id"],
                reviewed.protocol,
                reviewed.event_fingerprint,
                reviewed.provider_event_sha256,
                reviewed.observed_at,
                received_at,
                _conn_dialect(active_conn).json_param(reviewed.summary),
                reviewed.redacted_field_count,
                reviewed.truncated_field_count,
            ),
        )
        active_conn.execute(
            "UPDATE oast_correlations SET interaction_count = interaction_count + 1, "
            "updated_at = ? WHERE id = ?",
            (received_at, correlation["id"]),
        )
        if owns_conn:
            active_conn.commit()
        owner_sql, owner_params = _owner_predicate(
            str(session_id or ""), str(team_id or ""), table_prefix="c"
        )
        row = active_conn.execute(
            _select_sql(owner_sql) + " AND i.id = ?",  # nosec B608
            (*owner_params, selected_id),
        ).fetchone()
        return {"created": True, "interaction": _interaction_row(active_conn, row)}


def oast_interactions_for_owner_correlation(
    session_id: str,
    correlation_id: str,
    *,
    team_id: str = "",
    limit: int = 25,
    conn=None,
) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit), 100))
    owner_sql, owner_params = _owner_predicate(
        str(session_id or ""), str(team_id or ""), table_prefix="c"
    )
    with _connection_scope(conn) as active_conn:
        rows = active_conn.execute(
            _select_sql(owner_sql)
            + " AND i.correlation_id = ? ORDER BY i.observed_at DESC, i.id DESC LIMIT ?",  # nosec B608
            (*owner_params, correlation_id, bounded_limit),
        ).fetchall()
        return [_interaction_row(active_conn, row) for row in rows]


__all__ = [
    "ingest_oast_interaction",
    "oast_interactions_for_owner_correlation",
]
