# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Manual Project assessment check and evidence mutations."""

from __future__ import annotations

import secrets
from typing import Any, Mapping

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.contracts import (
    ASSESSMENT_MANUAL_CHECK_STATES,
    ASSESSMENT_MAX_EVIDENCE_ID_LEN,
    ASSESSMENT_MAX_REASON_LEN,
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
)
from services.assessments.coverage import enforce_evidence_quotas
from services.assessments.evidence_matching import matching_evidence_rule
from services.assessments.evidence_sources import load_assessment_evidence_source
from services.assessments.profiles import ASSESSMENT_EVIDENCE_TYPES
from services.metrics_lazy import app_metrics
from services.assessments.serialization import row_to_check, row_to_evidence
from services.projects.scope import shared_owner_where
from services.projects.utils import now


_MANUAL_EXCLUSION_STATES = frozenset({"blocked", "skipped", "not_applicable"})
_CHECK_SQL = (
    "SELECT p.status AS project_status, a.status AS assessment_status, "
    "a.profile_snapshot, a.session_id, a.team_id, a.project_id, "
    "c.id, c.assessment_id, c.category, c.check_key, c.target_entity_id, "
    "c.target_type, c.target_value, c.applicability, c.policy_level, "
    "c.state, c.state_source, c.state_reason, c.recommended_action_key, "
    "c.first_evidence_at, c.last_evidence_at, c.created_at, c.updated_at, "
    "c.state_changed_by_member_id, c.state_changed_at "
    "FROM projects p JOIN project_assessments a ON a.project_id = p.id "
    "JOIN project_assessment_checks c ON c.assessment_id = a.id WHERE "
    "{owner_sql} AND p.id = ? AND a.id = ? AND c.id = ?"
)


def _new_evidence_id() -> str:
    return "aev_" + secrets.token_hex(12)


def _check_row(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
) -> dict[str, Any]:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="p",
    )
    row = conn.execute(
        _CHECK_SQL.format(owner_sql=owner_sql),
        (*owner_params, project_id, assessment_id, check_id),
    ).fetchone()
    if not row:
        raise AssessmentNotFound("assessment check was not found in this scope")
    result = dict(row)
    if str(result["project_status"] or "") == "archived":
        raise AssessmentConflict("archived projects are read-only")
    if str(result["assessment_status"] or "") != "active":
        raise AssessmentConflict("completed and archived assessments are read-only")
    return result


def _profile_check(row: Mapping[str, Any]) -> Mapping[str, Any]:
    profile = dialect_for_backend(get_db_backend()).decode_json_dict(
        row.get("profile_snapshot")
    )
    check_key = str(row.get("check_key") or "")
    for check in profile.get("checks", []):
        if isinstance(check, Mapping) and str(check.get("key") or "") == check_key:
            return check
    raise AssessmentConflict("assessment check is missing from its frozen profile")


def _serialized_check(conn: Any, check_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT c.id, c.assessment_id, c.category, c.check_key, "
        "c.target_entity_id, c.target_type, c.target_value, c.applicability, "
        "c.policy_level, c.state, c.state_source, c.state_reason, "
        "c.state_changed_by_member_id, c.state_changed_at, "
        "c.recommended_action_key, c.first_evidence_at, c.last_evidence_at, "
        "c.created_at, c.updated_at, "
        "(SELECT COUNT(*) FROM project_assessment_evidence e "
        "WHERE e.check_id = c.id) AS evidence_count, "
        "(SELECT COUNT(*) FROM project_assessment_evidence e "
        "WHERE e.check_id = c.id AND e.source_state = 'available') "
        "AS available_evidence_count, "
        "(SELECT COUNT(*) FROM project_assessment_evidence e "
        "WHERE e.check_id = c.id AND e.source_state = 'unavailable') "
        "AS unavailable_evidence_count FROM project_assessment_checks c "
        "WHERE c.id = ?",
        (check_id,),
    ).fetchone()
    serialized = row_to_check(row)
    if serialized is None:
        raise AssessmentNotFound("assessment check was not found")
    return serialized


def _serialized_evidence(conn: Any, evidence_link_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, assessment_id, check_id, evidence_type, evidence_id, "
        "source_state, observed_at, unavailable_at, unavailable_reason, "
        "match_rule_key, match_rule_version, linked_by, created_at, updated_at "
        "FROM project_assessment_evidence WHERE id = ?",
        (evidence_link_id,),
    ).fetchone()
    serialized = row_to_evidence(row)
    if serialized is None:
        raise AssessmentNotFound("assessment evidence link was not found")
    return serialized


def _profile_rule(check_definition: Mapping[str, Any], rule_key: str) -> Mapping[str, Any] | None:
    for rule in check_definition.get("evidence_rules", []):
        if isinstance(rule, Mapping) and str(rule.get("key") or "") == rule_key:
            return rule
    return None


def _derived_state_from_links(
    conn: Any,
    check_id: str,
    check_definition: Mapping[str, Any],
) -> tuple[str, str]:
    rows = conn.execute(
        "SELECT match_rule_key FROM project_assessment_evidence "
        "WHERE check_id = ? AND source_state = 'available'",
        (check_id,),
    ).fetchall()
    if not rows:
        return "not_started", ""
    for row in rows:
        rule = _profile_rule(check_definition, str(row["match_rule_key"] or ""))
        if rule and "findings" in rule.get("structured_output_kinds", []):
            return "needs_review", "Compatible saved evidence includes app-captured findings."
    return "covered", "Covered by compatible saved evidence."


def _evidence_times(conn: Any, check_id: str) -> tuple[str | None, str | None]:
    row = conn.execute(
        "SELECT MIN(observed_at) AS first_at, MAX(observed_at) AS last_at "
        "FROM project_assessment_evidence WHERE check_id = ?",
        (check_id,),
    ).fetchone()
    if not row:
        return None, None
    return row["first_at"], row["last_at"]


def _touch_assessment(
    conn: Any,
    assessment_id: str,
    session_id: str,
    actor_member_id: str,
    timestamp: str,
) -> None:
    conn.execute(
        "UPDATE project_assessments SET updated_by_session_id = ?, "
        "updated_by_member_id = ?, updated_at = ? WHERE id = ?",
        (session_id, actor_member_id, timestamp, assessment_id),
    )


def update_manual_check_state_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    state: str,
    *,
    reason: str = "",
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    """Set or clear one explicit manual check decision in the active cycle."""
    normalized_state = str(state or "").strip().lower()
    normalized_reason = str(reason or "").strip()
    if normalized_state not in ASSESSMENT_MANUAL_CHECK_STATES:
        raise AssessmentError("assessment manual state is unsupported")
    if len(normalized_reason) > ASSESSMENT_MAX_REASON_LEN:
        raise AssessmentError(
            f"assessment state reason exceeds {ASSESSMENT_MAX_REASON_LEN} characters"
        )
    if normalized_state in _MANUAL_EXCLUSION_STATES and not normalized_reason:
        raise AssessmentError("assessment state reason is required")
    if normalized_state == "not_started" and normalized_reason:
        raise AssessmentError("clearing a manual state does not accept a reason")
    row = _check_row(
        conn,
        str(session_id or "").strip(),
        str(team_id or "").strip(),
        str(project_id or "").strip(),
        str(assessment_id or "").strip(),
        str(check_id or "").strip(),
    )
    from_state = str(row["state"] or "")
    from_source = str(row["state_source"] or "")
    if normalized_state == "not_started":
        if str(row["state_source"] or "") != "manual":
            raise AssessmentConflict("assessment check has no manual state to clear")
        to_state, state_reason = _derived_state_from_links(
            conn,
            str(row["id"]),
            _profile_check(row),
        )
        state_source = "derived"
        state_session_id = ""
        state_member_id = ""
        state_changed_at = None
        applicability = "applicable"
    else:
        to_state = normalized_state
        state_reason = normalized_reason
        state_source = "manual"
        state_session_id = str(session_id or "").strip()
        state_member_id = str(actor_member_id or "").strip()
        state_changed_at = now()
        applicability = (
            "not_applicable"
            if normalized_state == "not_applicable"
            else "applicable"
        )
    timestamp = now()
    conn.execute(
        "UPDATE project_assessment_checks SET applicability = ?, state = ?, "
        "state_source = ?, state_reason = ?, state_changed_by_session_id = ?, "
        "state_changed_by_member_id = ?, state_changed_at = ?, updated_at = ? "
        "WHERE id = ? AND assessment_id = ?",
        (
            applicability,
            to_state,
            state_source,
            state_reason,
            state_session_id,
            state_member_id,
            state_changed_at,
            timestamp,
            str(row["id"]),
            str(row["assessment_id"]),
        ),
    )
    _touch_assessment(
        conn,
        str(row["assessment_id"]),
        str(session_id or "").strip(),
        str(actor_member_id or "").strip(),
        timestamp,
    )
    if from_state != to_state or from_source != state_source:
        app_metrics.record_assessment_check_transition(
            from_state, to_state, state_source
        )
    return {
        "check": _serialized_check(conn, str(row["id"])),
        "from_state": from_state,
        "to_state": to_state,
        "manual_override_cleared": normalized_state == "not_started",
    }


def link_manual_evidence_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    evidence_type: str,
    evidence_id: str,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    """Validate and link one saved evidence source to an active check."""
    normalized_type = str(evidence_type or "").strip().lower()
    normalized_id = str(evidence_id or "").strip()
    if normalized_type not in ASSESSMENT_EVIDENCE_TYPES:
        raise AssessmentError("assessment evidence type is unsupported")
    if not normalized_id:
        raise AssessmentError("assessment evidence id is required")
    if len(normalized_id) > ASSESSMENT_MAX_EVIDENCE_ID_LEN:
        raise AssessmentError("assessment evidence id is too long")
    normalized_session_id = str(session_id or "").strip()
    normalized_team_id = str(team_id or "").strip()
    row = _check_row(
        conn,
        normalized_session_id,
        normalized_team_id,
        str(project_id or "").strip(),
        str(assessment_id or "").strip(),
        str(check_id or "").strip(),
    )
    source = load_assessment_evidence_source(
        conn,
        normalized_session_id,
        normalized_team_id,
        str(row["project_id"]),
        normalized_type,
        normalized_id,
    )
    definition = _profile_check(row)
    rule = matching_evidence_rule(
        definition,
        source.facts,
        evidence_type=normalized_type,
        target_type=str(row["target_type"] or ""),
        target_value=str(row["target_value"] or ""),
    )
    if rule is None:
        raise AssessmentConflict(
            "saved evidence does not satisfy this check's frozen compatibility rules"
        )
    existing = conn.execute(
        "SELECT 1 FROM project_assessment_evidence "
        "WHERE check_id = ? AND evidence_type = ? AND evidence_id = ?",
        (str(row["id"]), normalized_type, normalized_id),
    ).fetchone()
    if existing:
        raise AssessmentConflict("assessment evidence is already linked")
    enforce_evidence_quotas(conn, [{
        "already_linked": False,
        "session_id": str(row["session_id"] or ""),
        "team_id": str(row["team_id"] or ""),
        "project_id": str(row["project_id"] or ""),
    }])
    timestamp = now()
    observed_at = source.observed_at or timestamp
    evidence_link_id = _new_evidence_id()
    conn.execute(
        "INSERT INTO project_assessment_evidence "
        "(id, assessment_id, check_id, evidence_type, evidence_id, source_state, "
        "observed_at, unavailable_at, unavailable_reason, match_rule_key, "
        "match_rule_version, linked_by, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'available', ?, NULL, '', ?, ?, 'manual', ?, ?)",
        (
            evidence_link_id,
            str(row["assessment_id"]),
            str(row["id"]),
            normalized_type,
            normalized_id,
            observed_at,
            str(rule.get("key") or ""),
            str(rule.get("version") or ""),
            timestamp,
            timestamp,
        ),
    )
    protected = (
        str(row["state_source"] or "") == "manual"
        and str(row["state"] or "") in _MANUAL_EXCLUSION_STATES
    )
    from_state = str(row["state"] or "")
    from_source = str(row["state_source"] or "")
    to_state = from_state
    first_at, last_at = _evidence_times(conn, str(row["id"]))
    if not protected:
        to_state, state_reason = _derived_state_from_links(conn, str(row["id"]), definition)
        conn.execute(
            "UPDATE project_assessment_checks SET state = ?, state_source = 'derived', "
            "state_reason = ?, state_changed_by_session_id = '', "
            "state_changed_by_member_id = '', state_changed_at = NULL, "
            "first_evidence_at = ?, "
            "last_evidence_at = ?, updated_at = ? WHERE id = ?",
            (to_state, state_reason, first_at, last_at, timestamp, str(row["id"])),
        )
    else:
        conn.execute(
            "UPDATE project_assessment_checks SET first_evidence_at = ?, "
            "last_evidence_at = ?, updated_at = ? WHERE id = ?",
            (first_at, last_at, timestamp, str(row["id"])),
        )
    _touch_assessment(
        conn,
        str(row["assessment_id"]),
        normalized_session_id,
        str(actor_member_id or "").strip(),
        timestamp,
    )
    if not protected and (from_state != to_state or from_source != "derived"):
        app_metrics.record_assessment_check_transition(
            from_state, to_state, "derived"
        )
    return {
        "evidence": _serialized_evidence(conn, evidence_link_id),
        "check": _serialized_check(conn, str(row["id"])),
        "from_state": from_state,
        "to_state": to_state,
        "manual_state_preserved": protected,
    }


def unlink_manual_evidence_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    evidence_link_id: str,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    """Remove one manual evidence link and recalculate the affected check."""
    row = _check_row(
        conn,
        str(session_id or "").strip(),
        str(team_id or "").strip(),
        str(project_id or "").strip(),
        str(assessment_id or "").strip(),
        str(check_id or "").strip(),
    )
    evidence = conn.execute(
        "SELECT id, evidence_type, evidence_id, linked_by FROM "
        "project_assessment_evidence WHERE id = ? AND assessment_id = ? AND check_id = ?",
        (
            str(evidence_link_id or "").strip(),
            str(row["assessment_id"]),
            str(row["id"]),
        ),
    ).fetchone()
    if not evidence:
        raise AssessmentNotFound("assessment evidence link was not found in this scope")
    if str(evidence["linked_by"] or "") != "manual":
        raise AssessmentConflict("derived assessment evidence cannot be manually unlinked")
    deleted = {
        "id": str(evidence["id"]),
        "evidence_type": str(evidence["evidence_type"] or ""),
        "evidence_id": str(evidence["evidence_id"] or ""),
    }
    conn.execute(
        "DELETE FROM project_assessment_evidence WHERE id = ? AND linked_by = 'manual'",
        (str(evidence["id"]),),
    )
    timestamp = now()
    protected = (
        str(row["state_source"] or "") == "manual"
        and str(row["state"] or "") in _MANUAL_EXCLUSION_STATES
    )
    from_state = str(row["state"] or "")
    from_source = str(row["state_source"] or "")
    to_state = from_state
    first_at, last_at = _evidence_times(conn, str(row["id"]))
    if not protected:
        to_state, state_reason = _derived_state_from_links(
            conn,
            str(row["id"]),
            _profile_check(row),
        )
        conn.execute(
            "UPDATE project_assessment_checks SET state = ?, state_source = 'derived', "
            "state_reason = ?, state_changed_by_session_id = '', "
            "state_changed_by_member_id = '', state_changed_at = NULL, "
            "first_evidence_at = ?, last_evidence_at = ?, updated_at = ? WHERE id = ?",
            (to_state, state_reason, first_at, last_at, timestamp, str(row["id"])),
        )
    else:
        conn.execute(
            "UPDATE project_assessment_checks SET first_evidence_at = ?, "
            "last_evidence_at = ?, updated_at = ? WHERE id = ?",
            (first_at, last_at, timestamp, str(row["id"])),
        )
    _touch_assessment(
        conn,
        str(row["assessment_id"]),
        str(session_id or "").strip(),
        str(actor_member_id or "").strip(),
        timestamp,
    )
    if not protected and (from_state != to_state or from_source != "derived"):
        app_metrics.record_assessment_check_transition(
            from_state, to_state, "derived"
        )
    return {
        "deleted": deleted,
        "check": _serialized_check(conn, str(row["id"])),
        "from_state": from_state,
        "to_state": to_state,
        "manual_state_preserved": protected,
    }
