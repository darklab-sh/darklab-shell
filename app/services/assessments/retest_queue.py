# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Finding-centered retest groups and bounded shared launch plans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.database_access import get_db_connect
from services.assessments.action_plan_payload import digest_plan
from services.assessments.action_plans import AssessmentActionError
from services.projects.finding_verification import finding_verification_context_on_conn
from services.projects.scope import shared_owner_where
from services.projects.verification_actions import verification_action_plan_on_conn


RETEST_BATCH_MAX_FINDINGS = 10
RETEST_QUEUE_MAX_FINDINGS = 50


def _queue_rows(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
) -> list[Any]:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="link",
    )
    sql = "".join((
        "SELECT DISTINCT f.id AS finding_id, f.title, f.severity, f.first_run_id, ",
        "f.run_id, f.last_run_id, triage.verification_status, c.id AS check_id ",
        "FROM finding_evidence_links link ",
        "JOIN findings f ON f.id = link.finding_id ",
        "JOIN finding_triage_details triage ON triage.finding_id = f.id ",
        "AND COALESCE(triage.team_id, '') = COALESCE(link.team_id, '') ",
        "AND (COALESCE(link.team_id, '') != '' OR triage.session_id = link.session_id) ",
        "JOIN project_assessment_checks c ON c.id = link.evidence_id ",
        "WHERE ",
        owner_sql,
        " AND link.project_id = ? AND link.evidence_type = 'assessment_check' ",
        "AND c.assessment_id = ? AND COALESCE(f.suppressed, FALSE) = FALSE ",
        "AND triage.verification_status IN ('ready_to_verify', 'needs_retest') ",
        "ORDER BY triage.verification_status, f.id, c.id LIMIT ?",
    ))
    return conn.execute(
        sql,
        (*owner_params, project_id, assessment_id, RETEST_QUEUE_MAX_FINDINGS + 1),
    ).fetchall()


def _comparison_summary(context: dict[str, Any]) -> dict[str, Any]:
    retests = [
        item
        for item in context.get("retest_runs", [])
        if isinstance(item, dict)
    ]
    retests.sort(
        key=lambda item: (str(item.get("finished") or ""), str(item.get("id") or "")),
        reverse=True,
    )
    if not retests:
        return {
            "available": False,
            "state": "not_started",
            "reason": "No completed retest evidence is linked to this finding yet.",
            "left_run_id": str(context.get("baseline_run_id") or ""),
            "right_run_id": "",
        }
    newest = retests[0]
    raw_comparison = newest.get("comparison")
    comparison = raw_comparison if isinstance(raw_comparison, dict) else {}
    raw_compatibility = newest.get("compatibility")
    compatibility = raw_compatibility if isinstance(raw_compatibility, dict) else {}
    return {
        "available": bool(comparison.get("available")),
        "state": str(compatibility.get("state") or "unavailable"),
        "reason": str(compatibility.get("reason") or "Retest comparability is unavailable."),
        "left_run_id": str(comparison.get("left_run_id") or ""),
        "right_run_id": str(comparison.get("right_run_id") or ""),
    }


def _group_key(plan: dict[str, Any]) -> tuple[str, ...]:
    raw_target = plan.get("target")
    target = raw_target if isinstance(raw_target, dict) else {}
    raw_action = plan.get("action")
    action = raw_action if isinstance(raw_action, dict) else {}
    raw_profile = plan.get("http_profile")
    profile = raw_profile if isinstance(raw_profile, dict) else {}
    return (
        str(target.get("entity_id") or ""),
        str(target.get("type") or ""),
        str(target.get("value") or ""),
        str(plan.get("check_id") or ""),
        str(action.get("key") or ""),
        str(profile.get("role") or ""),
        str(profile.get("id") or ""),
    )


def _batch_reason(items: list[dict[str, Any]]) -> str:
    if len(items) < 2:
        return "A shared batch needs at least two findings; use the finding's individual action."
    if len(items) > RETEST_BATCH_MAX_FINDINGS:
        return f"This group exceeds the {RETEST_BATCH_MAX_FINDINGS}-finding batch limit."
    unavailable = next(
        (
            str(item["action_plan"].get("unavailable_reason") or "The action is unavailable.")
            for item in items
            if not item["action_plan"].get("launchable")
        ),
        "",
    )
    if unavailable:
        return unavailable
    if any(str(item["action_plan"].get("policy_level") or "") != "safe" for item in items):
        return "Shared batches are limited to safe assessment actions."
    if any(
        str(item["action_plan"].get("bounds", {}).get("credential_use") or "none")
        != "none"
        for item in items
    ):
        return "Credentialed HTTP roles stay individual so every use is reviewed separately."
    commands = {str(item["action_plan"].get("display_command") or "") for item in items}
    if len(commands) != 1 or not next(iter(commands), ""):
        return "The findings don't share one exact bounded command."
    return ""


def _public_item(row: Any, plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": str(row["finding_id"] or ""),
        "title": str(row["title"] or "Saved finding"),
        "severity": str(row["severity"] or "info"),
        "verification_status": str(row["verification_status"] or "not_started"),
        "check_id": str(row["check_id"] or ""),
        "action_plan": plan,
        "comparison": _comparison_summary(context),
        "suggestion": context.get("suggestion") or {},
        "human_disposition_required": True,
    }


def _public_group(key: tuple[str, ...], items: list[dict[str, Any]]) -> dict[str, Any]:
    first = items[0]["action_plan"]
    target = first.get("target") if isinstance(first.get("target"), dict) else {}
    action = first.get("action") if isinstance(first.get("action"), dict) else {}
    profile = first.get("http_profile") if isinstance(first.get("http_profile"), dict) else {}
    credential_use = profile.get("credential_use") or "none"
    if isinstance(credential_use, list):
        credential_use = [str(value) for value in credential_use if str(value)]
    elif credential_use != "none":
        credential_use = str(credential_use)
    reason = _batch_reason(items)
    group_id = "rtg_" + digest_plan({"group": key})[:20]
    digest = digest_plan({
        "group_id": group_id,
        "finding_ids": [item["finding_id"] for item in items],
        "plan_digests": [item["action_plan"].get("plan_digest") for item in items],
        "verification_statuses": [item["verification_status"] for item in items],
    })
    return {
        "id": group_id,
        "project_id": str(first.get("project_id") or ""),
        "assessment_id": str(first.get("assessment_id") or ""),
        "grouping": {
            "project_target": {
                "entity_id": str(target.get("entity_id") or ""),
                "type": str(target.get("type") or ""),
                "value": str(target.get("value") or ""),
            },
            "assessment_check": {
                "id": str(first.get("check_id") or ""),
                "key": str(first.get("check_key") or ""),
            },
            "action": dict(action),
            "http_profile": {
                "id": str(profile.get("id") or ""),
                "name": str(profile.get("name") or "No saved HTTP profile"),
                "role": str(profile.get("role") or "none"),
                "credential_use": credential_use,
            },
        },
        "items": items,
        "finding_count": len(items),
        "batch": {
            "launchable": not reason,
            "unavailable_reason": reason,
            "max_findings": RETEST_BATCH_MAX_FINDINGS,
            "plan_digest": digest,
            "display_command": str(first.get("display_command") or ""),
            "requires_confirmation": True,
        },
    }


def assessment_retest_queue_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    """Return bounded retest groups for one already-scoped Assessment cycle."""
    rows = _queue_rows(conn, session_id, team_id, project_id, assessment_id)
    truncated = len(rows) > RETEST_QUEUE_MAX_FINDINGS
    rows = rows[:RETEST_QUEUE_MAX_FINDINGS]
    contexts: dict[str, dict[str, Any]] = {}
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    status_counts = {"ready_to_verify": 0, "needs_retest": 0}
    seen_findings: set[str] = set()
    for row in rows:
        finding_id = str(row["finding_id"] or "")
        plan = verification_action_plan_on_conn(
            conn,
            session_id,
            project_id,
            finding_id,
            str(row["check_id"] or ""),
            team_id=team_id,
        )
        context = contexts.get(finding_id)
        if context is None:
            context = finding_verification_context_on_conn(
                conn,
                session_id,
                project_id,
                finding_id,
                team_id=team_id,
            )
            contexts[finding_id] = context
        item = _public_item(row, plan, context)
        groups.setdefault(_group_key(plan), []).append(item)
        if finding_id not in seen_findings:
            status = str(row["verification_status"] or "")
            if status in status_counts:
                status_counts[status] += 1
            seen_findings.add(finding_id)
    public_groups = [_public_group(key, items) for key, items in groups.items()]
    public_groups.sort(key=lambda group: (
        str(group["grouping"]["project_target"]["value"]).casefold(),
        str(group["grouping"]["assessment_check"]["key"]),
        str(group["grouping"]["action"].get("key") or ""),
        str(group["id"]),
    ))
    return {
        "groups": public_groups,
        "rollup": {
            **status_counts,
            "total_findings": len(seen_findings),
            "group_count": len(public_groups),
            "batch_launchable_groups": sum(
                int(group["batch"]["launchable"]) for group in public_groups
            ),
            "individual_only_groups": sum(
                int(not group["batch"]["launchable"]) for group in public_groups
            ),
        },
        "batch_max_findings": RETEST_BATCH_MAX_FINDINGS,
        "truncated": truncated,
        "grouping_contract": (
            "Findings share a group only when Project target, Assessment check, action, "
            "and HTTP role/profile are identical. Different values stay individual."
        ),
        "partial_failure_contract": (
            "One shared run is linked to each finding independently after completion; "
            "one failed evidence link doesn't remove successful links."
        ),
        "disposition_contract": (
            "Retest evidence can suggest verified or needs retest, but a person must save "
            "the final finding disposition."
        ),
    }


def confirmed_retest_batch_plan_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    group_id: str,
    data: Any,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    """Rebuild and confirm one current credential-free shared retest plan."""
    if not isinstance(data, Mapping):
        raise AssessmentActionError("invalid_body", "Request body must be a JSON object.")
    if set(data) - {"confirmed", "plan_digest", "workspace_cwd"}:
        raise AssessmentActionError(
            "unsupported_fields", "Retest batch launch contains unsupported fields."
        )
    if data.get("confirmed") is not True:
        raise AssessmentActionError(
            "confirmation_required",
            "Explicit retest batch confirmation is required.",
            status_code=409,
        )
    queue = assessment_retest_queue_on_conn(
        conn,
        session_id,
        project_id,
        assessment_id,
        team_id=team_id,
    )
    group = next(
        (item for item in queue["groups"] if item["id"] == str(group_id or "")),
        None,
    )
    if not group:
        raise AssessmentActionError(
            "batch_not_found",
            "The saved retest group is no longer available.",
            status_code=404,
        )
    if str(data.get("plan_digest") or "") != group["batch"]["plan_digest"]:
        raise AssessmentActionError(
            "stale_plan",
            "The retest batch changed. Review the current group and confirm again.",
            status_code=409,
        )
    if not group["batch"]["launchable"]:
        raise AssessmentActionError(
            "batch_unavailable",
            str(group["batch"]["unavailable_reason"] or "Retest batch is unavailable."),
            status_code=409,
        )
    return group


def confirm_retest_batch_plan(
    session_id: str,
    project_id: str,
    assessment_id: str,
    group_id: str,
    data: Any,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    with get_db_connect()() as conn:
        return confirmed_retest_batch_plan_on_conn(
            conn,
            session_id,
            project_id,
            assessment_id,
            group_id,
            data,
            team_id=team_id,
        )


__all__ = [
    "RETEST_BATCH_MAX_FINDINGS",
    "RETEST_QUEUE_MAX_FINDINGS",
    "assessment_retest_queue_on_conn",
    "confirm_retest_batch_plan",
    "confirmed_retest_batch_plan_on_conn",
]
