# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared, secret-free plans for frozen assessment recommendations."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Mapping

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.command_plans import command_plan
from services.assessments.dalfox_xss_actions import DalfoxXssActionContext
from services.assessments.nuclei_profiles import nuclei_profile, public_nuclei_profile
from services.assessments.nuclei_takeover_contracts import NUCLEI_TAKEOVER_CHECK_KEY
from services.assessments.nuclei_takeover_command import reviewed_takeover_command_plan
from services.assessments.schemathesis_actions import SchemathesisActionContext
from services.nuclei.template_cache import (
    managed_nuclei_template_snapshot,
    nuclei_template_cache_unavailable_reason,
)
from services.projects.scope import shared_owner_where


PLAN_SCHEMA_VERSION = 1
_SUPPORTED_POLICIES = frozenset({"safe", "standard"})
class AssessmentActionError(ValueError):
    """A stable assessment-action route error."""

    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def current_assessment_target(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    row: Any,
) -> dict[str, str] | None:
    """Resolve the frozen check target only while it remains confirmed and exact."""
    target_entity_id = str(row["target_entity_id"] or "")
    if not target_entity_id:
        return None
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="e",
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
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_assessment_action_plan(
    row: Any,
    target: dict[str, str] | None,
    project_id: str,
    *,
    finding_id: str = "",
    http_profile: Mapping[str, Any] | None = None,
    http_profile_web_target: str = "",
    http_profile_unavailable_reason: str = "",
    dalfox_xss: DalfoxXssActionContext | None = None,
    schemathesis: SchemathesisActionContext | None = None,
) -> dict[str, Any]:
    """Build one bounded plan from a persisted check and its frozen profile."""
    frozen = _frozen_check(row)
    check_key = str(row["check_key"] or "")
    action_key = str(row["recommended_action_key"] or "")
    action_kind, separator, action_id = action_key.partition(":")
    policy_level = str(row["policy_level"] or "")
    launchable = True
    unavailable_reason = ""
    selected_command = None
    selected_nuclei_profile = (
        nuclei_profile(policy_level)
        if action_id == "nuclei" and check_key != NUCLEI_TAKEOVER_CHECK_KEY
        else None
    )
    selected_nuclei_snapshot = (
        managed_nuclei_template_snapshot() if selected_nuclei_profile else None
    )
    if str(row["project_status"] or "") == "archived":
        launchable = False
        unavailable_reason = "Assessment runs cannot start from an archived Project."
    elif str(row["assessment_status"] or "") == "archived":
        launchable = False
        unavailable_reason = "The assessment cycle is archived."
    elif not target:
        launchable = False
        unavailable_reason = (
            "The frozen target is no longer confirmed in this active Project scope."
        )
    elif not frozen:
        launchable = False
        unavailable_reason = "The frozen check definition is unavailable."
    elif str(frozen.get("recommended_action") or "") != action_key:
        launchable = False
        unavailable_reason = "The frozen action no longer matches the saved check."
    elif str(frozen.get("policy_level") or "") != policy_level:
        launchable = False
        unavailable_reason = "The frozen policy no longer matches the saved check."
    elif selected_nuclei_snapshot and selected_nuclei_snapshot.state != "ready":
        launchable = False
        unavailable_reason = nuclei_template_cache_unavailable_reason(selected_nuclei_snapshot)
    elif not separator or action_kind not in {"command", "workflow"} or not action_id:
        launchable = False
        unavailable_reason = "This check does not have a launchable recommended action."
    elif action_kind == "workflow":
        launchable = False
        unavailable_reason = (
            "Workflow actions need an explicit frozen target-input mapping before they "
            "can launch here."
        )
    elif policy_level == "destructive":
        launchable = False
        unavailable_reason = "Destructive assessment actions cannot launch from Projects."
    elif policy_level == "intrusive" and dalfox_xss is None:
        launchable = False
        unavailable_reason = (
            "Intrusive assessment actions require a separate operator opt-in that is "
            "not enabled here."
        )
    elif policy_level not in _SUPPORTED_POLICIES and policy_level != "intrusive":
        launchable = False
        unavailable_reason = "The saved action has an unsupported execution policy."
    elif dalfox_xss and (action_id != "dalfox" or not target or target["type"] != "url"):
        launchable = False
        unavailable_reason = "The reviewed XSS action no longer matches its saved URL contract."
    elif schemathesis and (action_id != "schemathesis" or not target or target["type"] != "url"):
        launchable = False
        unavailable_reason = "The reviewed API action no longer matches its saved URL contract."
    elif http_profile_unavailable_reason:
        launchable = False
        unavailable_reason = http_profile_unavailable_reason
    elif dalfox_xss and dalfox_xss.unavailable_reason():
        launchable = False
        unavailable_reason = dalfox_xss.unavailable_reason()
    elif schemathesis and schemathesis.unavailable_reason():
        launchable = False
        unavailable_reason = schemathesis.unavailable_reason()
    elif check_key == NUCLEI_TAKEOVER_CHECK_KEY and http_profile:
        launchable = False
        unavailable_reason = "The reviewed takeover check does not send saved credentials."
    elif target:
        selected_command = (
            dalfox_xss.command_plan(http_profile)
            if dalfox_xss
            else schemathesis.command_plan()
            if schemathesis
            else reviewed_takeover_command_plan(target["type"], target["value"])
            if check_key == NUCLEI_TAKEOVER_CHECK_KEY
            else command_plan(
                action_id,
                target["type"],
                target["value"],
                web_target=http_profile_web_target,
                http_profile=http_profile,
                nuclei_profile=(
                    selected_nuclei_profile.key if selected_nuclei_profile else "safe"
                ),
            )
        )
        if selected_command is None:
            launchable = False
            unavailable_reason = (
                "No bounded command template is available for this saved action."
            )

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
        "check_key": check_key,
        "profile_key": str(row["profile_key"] or ""),
        "profile_version": str(row["profile_version"] or ""),
        "action": {
            "key": action_key,
            "kind": action_kind if separator else "",
            "id": action_id if separator else "",
        },
        "target": public_target,
        "policy_level": policy_level,
        "http_profile": dict(http_profile) if http_profile else {
            "name": "",
            "credential_use": "none",
        },
        "scope": {
            "kind": "project_target",
            "project_id": project_id,
            "target_count": 1,
            "fan_out": 1,
        },
        "bounds": {
            "target_count": 1,
            "fan_out": 1,
            "request_limit": selected_command.request_limit if selected_command else None,
            "time_limit_seconds": (
                selected_command.time_limit_seconds if selected_command else None
            ),
            "credential_use": selected_command.credential_use if selected_command else "none",
            "summary": selected_command.boundary if selected_command else "",
        },
        "display_command": selected_command.command if selected_command else "",
        "launchable": launchable,
        "unavailable_reason": unavailable_reason,
        "requires_confirmation": True,
    }
    if dalfox_xss:
        payload["evidence_selection"] = dalfox_xss.public_selection()
    if schemathesis:
        payload["artifact_selection"] = schemathesis.public_selection()
    if selected_nuclei_profile:
        payload["nuclei_profile"] = public_nuclei_profile(
            selected_nuclei_profile.key,
            template_snapshot=selected_nuclei_snapshot.public(),
        )
    payload["plan_digest"] = _digest(payload)
    return payload


def confirm_assessment_action_plan(
    data: Any,
    load_plan: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Re-read and validate a previously previewed assessment action plan."""
    if not isinstance(data, Mapping):
        raise AssessmentActionError(
            "invalid_body",
            "Request body must be a JSON object.",
        )
    allowed = {
        "confirmed", "http_profile_id", "parameter_observation_id",
        "plan_digest", "schema_artifact_id", "source_run_id", "workspace_cwd",
    }
    if set(data) - allowed:
        raise AssessmentActionError(
            "unsupported_fields",
            "Assessment launch contains unsupported fields.",
        )
    if data.get("confirmed") is not True:
        raise AssessmentActionError(
            "confirmation_required",
            "Explicit assessment launch confirmation is required.",
            status_code=409,
        )
    supplied_digest = str(data.get("plan_digest") or "").strip()
    if not supplied_digest:
        raise AssessmentActionError(
            "plan_digest_required",
            "The assessment launch plan digest is required.",
        )
    plan = load_plan()
    if supplied_digest != plan["plan_digest"]:
        raise AssessmentActionError(
            "stale_plan",
            "The assessment launch plan changed. Review the current plan and confirm again.",
            status_code=409,
        )
    if not plan["launchable"]:
        raise AssessmentActionError(
            "action_unavailable",
            str(plan["unavailable_reason"] or "Assessment action is unavailable."),
            status_code=409,
        )
    return plan
