# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Guarded command plans for finding verification from frozen assessment checks."""

from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import dataclass
from typing import Any, Mapping

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.contracts import AssessmentNotFound
from services.assessments.evidence_sources import load_assessment_evidence_source
from services.projects.contracts import ProjectWorkspaceNotFound
from services.projects.scope import shared_owner_where


PLAN_SCHEMA_VERSION = 1
_SUPPORTED_POLICIES = frozenset({"safe", "standard"})
_COMMAND_TARGET_TYPES = {
    "ping": frozenset({"domain", "ip"}),
    "nmap": frozenset({"domain", "ip"}),
    "dnsrecon": frozenset({"domain"}),
    "httpx": frozenset({"domain", "ip", "url"}),
    "katana": frozenset({"domain", "url"}),
    "nuclei": frozenset({"domain", "ip", "url"}),
}


@dataclass(frozen=True)
class _CommandPlan:
    command: str
    boundary: str
    request_limit: int | None
    time_limit_seconds: int | None
    credential_use: str = "none"


class VerificationActionError(ValueError):
    """A stable verification-action route error."""

    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _command_plan(action_id: str, target_type: str, target_value: str) -> _CommandPlan | None:
    if target_type not in _COMMAND_TARGET_TYPES.get(action_id, frozenset()):
        return None
    quoted = shlex.quote(target_value)
    web_target = target_value
    if target_type == "domain" and action_id in {"httpx", "katana", "nuclei"}:
        web_target = f"https://{target_value}"
    quoted_web = shlex.quote(web_target)
    plans = {
        "ping": _CommandPlan(
            f"ping -c 4 -W 2 {quoted}",
            "Four probes against one approved host.",
            4,
            10,
        ),
        "nmap": _CommandPlan(
            f"nmap -sT -sV -Pn --top-ports 100 --max-retries 2 --host-timeout 10m {quoted}",
            "One approved host, the top 100 TCP ports, and a 10-minute host timeout.",
            100,
            600,
        ),
        "dnsrecon": _CommandPlan(
            f"dnsrecon -d {quoted} -t std",
            "Standard DNS record checks for one approved domain; no brute force or zone walk.",
            None,
            None,
        ),
        "httpx": _CommandPlan(
            f"httpx -u {quoted_web} -status-code -title -tech-detect -silent",
            "One approved host or URL with response metadata only.",
            None,
            None,
        ),
        "katana": _CommandPlan(
            f"katana -u {quoted_web} -d 1 -ct 5 -timeout 10 -silent",
            "One approved web target, crawl depth 1, concurrency 5, and 10-second request timeouts.",
            None,
            None,
        ),
        "nuclei": _CommandPlan(
            f"nuclei -u {quoted_web} -severity high,critical -rl 10 -c 5 -timeout 10 -retries 1 -silent",
            "One approved target, high/critical templates, 10 requests per second, concurrency 5, and one retry.",
            None,
            None,
        ),
    }
    return plans.get(action_id)


def _load_action_row(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    finding_id: str,
    check_id: str,
) -> Any:
    try:
        load_assessment_evidence_source(
            conn, session_id, team_id, project_id, "finding", finding_id
        )
    except AssessmentNotFound as exc:
        raise ProjectWorkspaceNotFound(
            "finding was not found in this project scope"
        ) from exc
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p"
    )
    # The owner clause is supplied by the Project scope service. Every request
    # identifier remains a bound parameter.
    sql = "".join((
        "SELECT c.id AS check_id, c.assessment_id, c.check_key, ",
        "c.target_entity_id, c.target_type, c.target_value, c.policy_level, ",
        "c.recommended_action_key, a.profile_key, a.profile_version, ",
        "a.profile_snapshot, a.status AS assessment_status, p.status AS project_status ",
        "FROM finding_evidence_links link ",
        "JOIN project_assessment_checks c ON c.id = link.evidence_id ",
        "JOIN project_assessments a ON a.id = c.assessment_id ",
        "AND a.project_id = link.project_id ",
        "JOIN projects p ON p.id = link.project_id WHERE ",
        owner_sql,
        " AND link.project_id = ? AND link.finding_id = ? ",
        "AND link.evidence_type = 'assessment_check' AND link.evidence_id = ?",
    ))
    row = conn.execute(
        sql, (*owner_params, project_id, finding_id, check_id)
    ).fetchone()
    if not row:
        raise ProjectWorkspaceNotFound(
            "originating assessment check was not found for this finding"
        )
    return row


def _current_target(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    row: Any,
) -> dict[str, str] | None:
    target_entity_id = str(row["target_entity_id"] or "")
    if not target_entity_id:
        return None
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    sql = "".join((
        "SELECT e.id, e.type, e.canonical_value FROM project_links pl ",
        "JOIN entities e ON e.id = pl.entity_id WHERE pl.project_id = ? ",
        "AND pl.entity_type = 'atlas_entity' AND pl.review_state = 'confirmed' ",
        "AND e.id = ? AND ",
        owner_sql,
        " LIMIT 1",
    ))
    target = conn.execute(
        sql,
        (project_id, target_entity_id, *owner_params),
    ).fetchone()
    if not target:
        return None
    if (
        str(target["type"] or "") != str(row["target_type"] or "")
        or str(target["canonical_value"] or "") != str(row["target_value"] or "")
    ):
        return None
    return {
        "entity_id": str(target["id"] or ""),
        "type": str(target["type"] or ""),
        "value": str(target["canonical_value"] or ""),
    }


def _frozen_check(row: Any) -> Mapping[str, Any] | None:
    snapshot = dialect_for_backend(get_db_backend()).decode_json_dict(
        row["profile_snapshot"]
    )
    check_key = str(row["check_key"] or "")
    for item in snapshot.get("checks", []):
        if isinstance(item, Mapping) and str(item.get("key") or "") == check_key:
            return item
    return None


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verification_action_plan_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    finding_id: str,
    check_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    """Return a fresh, secret-free launch preview for one frozen origin check."""
    row = _load_action_row(
        conn, session_id, team_id, project_id, finding_id, check_id
    )
    target = _current_target(conn, session_id, team_id, project_id, row)
    frozen = _frozen_check(row)
    action_key = str(row["recommended_action_key"] or "")
    action_kind, separator, action_id = action_key.partition(":")
    policy_level = str(row["policy_level"] or "")
    launchable = True
    unavailable_reason = ""
    command_plan = None
    if str(row["project_status"] or "") == "archived":
        launchable = False
        unavailable_reason = "Verification runs cannot start from an archived Project."
    elif str(row["assessment_status"] or "") == "archived":
        launchable = False
        unavailable_reason = "The originating assessment cycle is archived."
    elif not target:
        launchable = False
        unavailable_reason = "The frozen target is no longer confirmed in this active Project scope."
    elif not frozen:
        launchable = False
        unavailable_reason = "The frozen check definition is unavailable."
    elif str(frozen.get("recommended_action") or "") != action_key:
        launchable = False
        unavailable_reason = "The frozen action no longer matches the saved check."
    elif str(frozen.get("policy_level") or "") != policy_level:
        launchable = False
        unavailable_reason = "The frozen policy no longer matches the saved check."
    elif not separator or action_kind not in {"command", "workflow"} or not action_id:
        launchable = False
        unavailable_reason = "This check does not have a launchable recommended action."
    elif action_kind == "workflow":
        launchable = False
        unavailable_reason = "Workflow actions need an explicit frozen target-input mapping before they can launch here."
    elif policy_level == "destructive":
        launchable = False
        unavailable_reason = "Destructive assessment actions cannot launch from finding verification."
    elif policy_level == "intrusive":
        launchable = False
        unavailable_reason = "Intrusive assessment actions require a separate operator opt-in that is not enabled here."
    elif policy_level not in _SUPPORTED_POLICIES:
        launchable = False
        unavailable_reason = "The saved action has an unsupported execution policy."
    elif target:
        command_plan = _command_plan(action_id, target["type"], target["value"])
        if command_plan is None:
            launchable = False
            unavailable_reason = "No bounded command template is available for this saved action."

    public_target = target or {
        "entity_id": str(row["target_entity_id"] or ""),
        "type": str(row["target_type"] or ""),
        "value": str(row["target_value"] or ""),
    }
    payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "project_id": project_id,
        "finding_id": finding_id,
        "assessment_id": str(row["assessment_id"] or ""),
        "check_id": str(row["check_id"] or ""),
        "check_key": str(row["check_key"] or ""),
        "profile_key": str(row["profile_key"] or ""),
        "profile_version": str(row["profile_version"] or ""),
        "action": {
            "key": action_key,
            "kind": action_kind if separator else "",
            "id": action_id if separator else "",
        },
        "target": public_target,
        "policy_level": policy_level,
        "http_profile": {"name": "", "credential_use": "none"},
        "scope": {
            "kind": "project_target",
            "project_id": project_id,
            "target_count": 1,
            "fan_out": 1,
        },
        "bounds": {
            "target_count": 1,
            "fan_out": 1,
            "request_limit": command_plan.request_limit if command_plan else None,
            "time_limit_seconds": command_plan.time_limit_seconds if command_plan else None,
            "credential_use": command_plan.credential_use if command_plan else "none",
            "summary": command_plan.boundary if command_plan else "",
        },
        "display_command": command_plan.command if command_plan else "",
        "launchable": launchable,
        "unavailable_reason": unavailable_reason,
        "requires_confirmation": True,
    }
    payload["plan_digest"] = _digest(payload)
    return payload


def get_verification_action_plan(
    session_id: str,
    project_id: str,
    finding_id: str,
    check_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    with get_db_connect()() as conn:
        return verification_action_plan_on_conn(
            conn,
            session_id,
            project_id,
            finding_id,
            check_id,
            team_id=team_id,
        )


def confirm_verification_action_plan(
    session_id: str,
    project_id: str,
    finding_id: str,
    check_id: str,
    data: Any,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise VerificationActionError("invalid_body", "Request body must be a JSON object.")
    allowed = {"confirmed", "plan_digest", "workspace_cwd"}
    if set(data) - allowed:
        raise VerificationActionError(
            "unsupported_fields", "Verification launch contains unsupported fields."
        )
    if data.get("confirmed") is not True:
        raise VerificationActionError(
            "confirmation_required", "Explicit verification launch confirmation is required.",
            status_code=409,
        )
    supplied_digest = str(data.get("plan_digest") or "").strip()
    if not supplied_digest:
        raise VerificationActionError(
            "plan_digest_required", "The verification launch plan digest is required."
        )
    plan = get_verification_action_plan(
        session_id,
        project_id,
        finding_id,
        check_id,
        team_id=team_id,
    )
    if supplied_digest != plan["plan_digest"]:
        raise VerificationActionError(
            "stale_plan",
            "The verification launch plan changed. Review the current plan and confirm again.",
            status_code=409,
        )
    if not plan["launchable"]:
        raise VerificationActionError(
            "action_unavailable",
            str(plan["unavailable_reason"] or "Verification action is unavailable."),
            status_code=409,
        )
    return plan
