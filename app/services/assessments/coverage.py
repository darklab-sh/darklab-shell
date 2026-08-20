# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Incremental assessment-evidence linking and check-state derivation."""

from __future__ import annotations

import secrets
from typing import Any, Callable, Mapping

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.coverage_candidates import candidate_checks_for_run
from services.assessments.evidence_matching import (
    load_run_evidence_facts,
    matching_run_rule,
)
from services.metrics_lazy import app_metrics
from services.projects.utils import cfg_int, now, raise_quota


DEFAULT_MAX_ASSESSMENT_EVIDENCE_PER_OWNER = 1_000_000
DEFAULT_MAX_ASSESSMENT_EVIDENCE_PER_PROJECT = 250_000
_MANUAL_PROTECTED_STATES = frozenset({"blocked", "skipped", "not_applicable"})


def _new_evidence_id() -> str:
    return "aev_" + secrets.token_hex(12)


def _profile_checks(snapshot: object) -> dict[str, Mapping[str, Any]]:
    dialect = dialect_for_backend(get_db_backend())
    profile = snapshot if isinstance(snapshot, Mapping) else dialect.decode_json_dict(snapshot)
    checks = profile.get("checks", []) if isinstance(profile, Mapping) else []
    return {
        str(check.get("key") or ""): check
        for check in checks
        if isinstance(check, Mapping) and str(check.get("key") or "")
    }


def _count(conn: Any, sql: str, params: tuple[object, ...]) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row["count"] or 0) if row else 0


def enforce_evidence_quotas(conn: Any, candidates: list[dict[str, Any]]) -> None:
    missing = [item for item in candidates if not item["already_linked"]]
    if not missing:
        return
    owner_additions: dict[tuple[str, str], int] = {}
    project_additions: dict[str, int] = {}
    project_owner_kinds: dict[str, str] = {}
    for item in missing:
        owner_key = (str(item["session_id"] or ""), str(item["team_id"] or ""))
        owner_additions[owner_key] = owner_additions.get(owner_key, 0) + 1
        project_id = str(item["project_id"] or "")
        project_additions[project_id] = project_additions.get(project_id, 0) + 1
        project_owner_kinds.setdefault(
            project_id,
            "team" if item["team_id"] else "personal",
        )
    owner_limit = cfg_int(
        "max_project_assessment_evidence_per_owner",
        DEFAULT_MAX_ASSESSMENT_EVIDENCE_PER_OWNER,
    )
    project_limit = cfg_int(
        "max_project_assessment_evidence_per_project",
        DEFAULT_MAX_ASSESSMENT_EVIDENCE_PER_PROJECT,
    )
    for (session_id, team_id), added in owner_additions.items():
        if team_id:
            current = _count(
                conn,
                "SELECT COUNT(*) AS count FROM project_assessment_evidence e "
                "JOIN project_assessments a ON a.id = e.assessment_id WHERE a.team_id = ?",
                (team_id,),
            )
        else:
            current = _count(
                conn,
                "SELECT COUNT(*) AS count FROM project_assessment_evidence e "
                "JOIN project_assessments a ON a.id = e.assessment_id "
                "WHERE a.session_id = ? AND a.team_id = ''",
                (session_id,),
            )
        if owner_limit > 0 and current + added > owner_limit:
            raise_quota(
                "assessment evidence quota exceeded for this owner",
                quota_kind="assessment_evidence_owner",
                owner_kind="team" if team_id else "personal",
                limit=owner_limit,
                current_count=current,
                requested_count=added,
            )
    for project_id, added in project_additions.items():
        current = _count(
            conn,
            "SELECT COUNT(*) AS count FROM project_assessment_evidence e "
            "JOIN project_assessments a ON a.id = e.assessment_id WHERE a.project_id = ?",
            (project_id,),
        )
        if project_limit > 0 and current + added > project_limit:
            raise_quota(
                "assessment evidence quota exceeded for this project",
                quota_kind="assessment_evidence_project",
                owner_kind=project_owner_kinds.get(project_id, "unknown"),
                project_id=project_id,
                limit=project_limit,
                current_count=current,
                requested_count=added,
            )


def _derived_state(check: Mapping[str, Any], finding_count: int, rule: Mapping[str, Any]) -> tuple[str, str, bool]:
    current_state = str(check.get("state") or "not_started")
    protected = (
        str(check.get("state_source") or "") == "manual"
        and current_state in _MANUAL_PROTECTED_STATES
    )
    if protected:
        return current_state, str(check.get("state_reason") or ""), True
    finding_evidence = "findings" in rule.get("structured_output_kinds", []) and finding_count > 0
    if finding_evidence or current_state == "needs_review":
        return "needs_review", "Compatible saved evidence includes app-captured findings.", False
    return "covered", "Covered with no app-captured findings in the compatible saved run.", False


def reconcile_run_evidence_on_conn(
    conn: Any,
    run_id: str,
    *,
    command_target_inputs_fn: Callable[[str], list[dict[str, str]]] | None = None,
) -> dict[str, int]:
    """Incrementally link one finalized run to compatible active checks."""
    facts_kwargs = {}
    if command_target_inputs_fn is not None:
        facts_kwargs["command_target_inputs_fn"] = command_target_inputs_fn
    facts = load_run_evidence_facts(conn, run_id, **facts_kwargs)
    summary = {
        "checks_considered": 0,
        "checks_matched": 0,
        "evidence_linked": 0,
        "evidence_already_linked": 0,
        "states_updated": 0,
        "manual_states_preserved": 0,
    }
    if facts is None:
        app_metrics.record_assessment_evidence_matches("run", "unavailable")
        return summary
    candidates: list[dict[str, Any]] = []
    profile_cache: dict[str, dict[str, Mapping[str, Any]]] = {}
    for check in candidate_checks_for_run(conn, facts.run_id):
        summary["checks_considered"] += 1
        assessment_id = str(check["assessment_id"] or "")
        definitions = profile_cache.get(assessment_id)
        if definitions is None:
            definitions = _profile_checks(check["profile_snapshot"])
            profile_cache[assessment_id] = definitions
        definition = definitions.get(str(check["check_key"] or ""))
        if definition is None:
            continue
        rule = matching_run_rule(
            definition,
            facts,
            target_type=str(check["target_type"] or ""),
            target_value=str(check["target_value"] or ""),
        )
        if rule is None:
            continue
        existing = conn.execute(
            "SELECT 1 FROM project_assessment_evidence "
            "WHERE check_id = ? AND evidence_type = 'run' AND evidence_id = ?",
            (str(check["check_id"]), facts.run_id),
        ).fetchone()
        candidates.append({
            **check,
            "definition": definition,
            "rule": rule,
            "already_linked": existing is not None,
        })
    summary["checks_matched"] = len(candidates)
    app_metrics.record_assessment_evidence_matches(
        "run", "matched", summary["checks_matched"]
    )
    app_metrics.record_assessment_evidence_matches(
        "run",
        "unmatched",
        summary["checks_considered"] - summary["checks_matched"],
    )
    enforce_evidence_quotas(conn, candidates)
    timestamp = facts.finished_at or now()
    for check in candidates:
        if check["already_linked"]:
            summary["evidence_already_linked"] += 1
        else:
            conn.execute(
                "INSERT INTO project_assessment_evidence "
                "(id, assessment_id, check_id, evidence_type, evidence_id, source_state, "
                "observed_at, unavailable_at, unavailable_reason, match_rule_key, "
                "match_rule_version, linked_by, created_at, updated_at) "
                "VALUES (?, ?, ?, 'run', ?, 'available', ?, NULL, '', ?, ?, 'derived', ?, ?)",
                (
                    _new_evidence_id(),
                    str(check["assessment_id"]),
                    str(check["check_id"]),
                    facts.run_id,
                    timestamp,
                    str(check["rule"].get("key") or ""),
                    str(check["rule"].get("version") or ""),
                    timestamp,
                    timestamp,
                ),
            )
            summary["evidence_linked"] += 1
        state, reason, protected = _derived_state(check, facts.finding_count, check["rule"])
        if protected:
            summary["manual_states_preserved"] += 1
        first_evidence_at = str(check.get("first_evidence_at") or "") or timestamp
        last_evidence_at = max(str(check.get("last_evidence_at") or ""), timestamp)
        current_state = str(check.get("state") or "")
        current_source = str(check.get("state_source") or "")
        state_source = current_source if protected else "derived"
        state_reason = str(check.get("state_reason") or "") if protected else reason
        conn.execute(
            "UPDATE project_assessment_checks SET state = ?, state_source = ?, state_reason = ?, "
            "first_evidence_at = ?, last_evidence_at = ?, updated_at = ? WHERE id = ?",
            (
                state,
                state_source,
                state_reason,
                first_evidence_at,
                last_evidence_at,
                timestamp,
                str(check["check_id"]),
            ),
        )
        if state != current_state or state_source != current_source:
            summary["states_updated"] += 1
            app_metrics.record_assessment_check_transition(
                current_state, state, state_source
            )
    return summary
