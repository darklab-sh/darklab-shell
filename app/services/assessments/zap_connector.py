# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed Project-assessment handoff to the external ZAP worker."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
import hashlib
import json
from typing import Any

import config as app_config
from core.database_access import get_db_connect
from services.assessments.http_profiles import get_http_profile
from services.assessments.recommended_action_queries import load_action_row
from services.connectors.zap_config import zap_connector_settings
from services.connectors.zap_job_artifacts import (
    ZapJobArtifactError,
    zap_report_workspace_path,
)
from services.connectors.zap_job_lifecycle import request_zap_job_cancel
from services.connectors.zap_jobs import (
    ZapJobError,
    zap_job_for_owner,
    zap_jobs_for_owner_check,
)
from services.connectors.zap_plan import build_zap_automation_plan
from services.connectors.zap_plan_contracts import (
    ReviewedZapAutomationPlan,
    ZapPlanError,
)
from services.connectors.zap_scope import (
    ReviewedZapTarget,
    ZapTargetScopeError,
    review_zap_target,
)
from services.connectors.zap_worker import queue_zap_job
from services.projects.scope import shared_owner_where


_PLAN_SCHEMA_VERSION = 1
_ACTIVE_JOB_STATUSES = frozenset(
    {
        "queued",
        "submitting",
        "running",
        "cancel_requested",
        "downloading",
    }
)
_SELECTION_FIELDS = frozenset(
    {
        "http_profile_id",
        "policy_level",
        "scope_exclusions",
        "target_entity_ids",
    }
)


class AssessmentZapError(ValueError):
    """A stable error returned by Assessment ZAP routes."""

    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _downstream_error(exc: Exception) -> AssessmentZapError:
    code = str(getattr(exc, "code", "zap_request_failed") or "zap_request_failed")
    if code == "zap_job_not_found":
        status = 404
    elif code in {
        "zap_connector_disabled",
        "zap_intrusive_disabled",
        "zap_job_scope_changed",
        "zap_job_transition_conflict",
        "zap_job_transition_invalid",
    }:
        status = 409
    elif isinstance(exc, ZapJobArtifactError):
        status = 500
    else:
        status = 400
    return AssessmentZapError(code, str(exc), status_code=status)


def _body(data: object, *, submit: bool) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise AssessmentZapError("invalid_body", "Request body must be a JSON object.")
    allowed = _SELECTION_FIELDS | ({"confirmed", "plan_digest"} if submit else set())
    if set(data) - allowed:
        raise AssessmentZapError(
            "unsupported_fields",
            "ZAP assessment request contains unsupported fields.",
        )
    return data


def _string_list(value: object, *, field: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise AssessmentZapError(
            "zap_selection_invalid",
            f"{field} must be a JSON array.",
        )
    values = tuple(str(item or "").strip() for item in value)
    if any(not item for item in values) or not 1 <= len(values) <= maximum:
        raise AssessmentZapError(
            "zap_selection_invalid",
            f"{field} must contain between one and {maximum} values.",
        )
    if len(set(values)) != len(values):
        raise AssessmentZapError(
            "zap_selection_invalid",
            f"{field} must not contain duplicate values.",
        )
    return values


def _selection(data: Mapping[str, Any]) -> dict[str, Any]:
    profile_id = str(data.get("http_profile_id") or "").strip()
    if not profile_id:
        raise AssessmentZapError(
            "zap_http_profile_required",
            "Select an HTTP profile before reviewing a ZAP plan.",
        )
    policy = str(data.get("policy_level") or "safe").strip().lower()
    if policy not in {"safe", "intrusive"}:
        raise AssessmentZapError(
            "zap_policy_invalid",
            "ZAP policy must be safe or intrusive.",
        )
    raw_exclusions = data.get("scope_exclusions", [])
    if not isinstance(raw_exclusions, (list, tuple)):
        raise AssessmentZapError(
            "zap_selection_invalid",
            "scope_exclusions must be a JSON array.",
        )
    exclusions = tuple(str(item or "").strip() for item in raw_exclusions)
    return {
        "http_profile_id": profile_id,
        "policy_level": policy,
        "scope_exclusions": exclusions,
        "target_entity_ids": _string_list(
            data.get("target_entity_ids"),
            field="target_entity_ids",
            maximum=8,
        ),
    }


def _project_urls(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    entity_ids: Sequence[str],
) -> tuple[str, ...]:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="e",
    )
    placeholders = ", ".join("?" for _ in entity_ids)
    rows = conn.execute(
        "SELECT e.id, e.type, e.canonical_value FROM project_links pl "  # nosec B608
        "JOIN entities e ON e.id = pl.entity_id WHERE pl.project_id = ? "
        "AND pl.entity_type = 'atlas_entity' AND pl.review_state = 'confirmed' "
        "AND COALESCE(e.suppressed, FALSE) = FALSE AND "
        + owner_sql
        + f" AND e.id IN ({placeholders})",
        (project_id, *owner_params, *entity_ids),
    ).fetchall()
    by_id = {
        str(row["id"] or ""): (
            str(row["type"] or ""),
            str(row["canonical_value"] or ""),
        )
        for row in rows
    }
    if any(entity_id not in by_id for entity_id in entity_ids):
        raise AssessmentZapError(
            "zap_target_not_found",
            "A selected ZAP target is no longer confirmed in this Project.",
            status_code=409,
        )
    if any(by_id[entity_id][0] != "url" for entity_id in entity_ids):
        raise AssessmentZapError(
            "zap_target_invalid",
            "ZAP plans require confirmed Project URL targets.",
        )
    return tuple(by_id[entity_id][1] for entity_id in entity_ids)


def _reviewed_targets(
    urls: Sequence[str],
    settings,
    resolve_addresses: Callable[[str], Iterable[str]] | None,
) -> tuple[ReviewedZapTarget, ...]:
    targets = []
    for url in urls:
        if resolve_addresses is None:
            targets.append(review_zap_target(url, settings))
        else:
            targets.append(
                review_zap_target(url, settings, resolve_addresses=resolve_addresses)
            )
    return tuple(targets)


def _plan_digest(payload: Mapping[str, Any]) -> str:
    stable = {
        key: value
        for key, value in payload.items()
        if key not in {"plan_digest", "plan_yaml"}
    }
    encoded = json.dumps(
        stable,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_assessment_zap_plan(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    data: object,
    *,
    team_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    resolve_addresses: Callable[[str], Iterable[str]] | None = None,
) -> tuple[dict[str, Any], ReviewedZapAutomationPlan]:
    """Re-read scope and return the exact, non-secret ZAP plan for review."""
    selection = _selection(_body(data, submit=False))
    settings = zap_connector_settings(cfg)
    try:
        with get_db_connect()() as conn:
            row = load_action_row(
                conn,
                session_id,
                team_id,
                project_id,
                assessment_id,
                check_id,
            )
            if str(row["project_status"] or "") == "archived":
                raise AssessmentZapError(
                    "zap_project_archived",
                    "ZAP jobs cannot start from an archived Project.",
                    status_code=409,
                )
            if str(row["assessment_status"] or "") != "active":
                raise AssessmentZapError(
                    "zap_assessment_inactive",
                    "ZAP jobs require an active assessment cycle.",
                    status_code=409,
                )
            urls = _project_urls(
                conn,
                session_id,
                team_id,
                project_id,
                selection["target_entity_ids"],
            )
        profile = get_http_profile(
            session_id,
            project_id,
            selection["http_profile_id"],
            team_id=team_id,
        )
        if profile is None:
            raise AssessmentZapError(
                "zap_http_profile_not_found",
                "The selected HTTP profile is no longer available.",
                status_code=409,
            )
        reviewed_targets = _reviewed_targets(urls, settings, resolve_addresses)
        plan = build_zap_automation_plan(
            settings,
            reviewed_targets,
            profile,
            policy_level=selection["policy_level"],
            scope_exclusions=selection["scope_exclusions"],
            intrusive_enabled=bool(
                app_config.CFG.get("assessment_intrusive_actions_enabled", False)
            ),
        )
    except AssessmentZapError:
        raise
    except (ZapPlanError, ZapTargetScopeError) as exc:
        raise _downstream_error(exc) from exc
    preview = {
        "schema_version": _PLAN_SCHEMA_VERSION,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "check_id": check_id,
        "http_profile": {
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or ""),
            "revision": int(profile.get("revision") or 1),
            "role": str(profile.get("role") or "anonymous"),
        },
        "target_entity_ids": list(selection["target_entity_ids"]),
        "scope_exclusions": list(selection["scope_exclusions"]),
        "summary": plan.summary.to_dict(),
        "plan_sha256": hashlib.sha256(plan.yaml_bytes).hexdigest(),
        "plan_yaml": plan.yaml_bytes.decode("utf-8"),
        "requires_confirmation": True,
    }
    preview["plan_digest"] = _plan_digest(preview)
    return preview, plan


def public_zap_job(job: Mapping[str, Any]) -> dict[str, Any]:
    """Return bounded owner-visible state without worker-private identity."""
    status = str(job.get("status") or "")
    job_id = str(job.get("id") or "")
    report_filename = str(job.get("report_filename") or "")
    public = {
        key: job.get(key)
        for key in (
            "id",
            "project_id",
            "assessment_id",
            "check_id",
            "http_profile_id",
            "http_profile_revision",
            "policy_level",
            "status",
            "target_count",
            "plan_summary",
            "progress",
            "remote_plan_id",
            "report_filename",
            "report_bytes",
            "report_sha256",
            "error_code",
            "error_detail",
            "created_at",
            "updated_at",
            "submitted_at",
            "finished_at",
            "expires_at",
        )
    }
    public["cancelable"] = status in _ACTIVE_JOB_STATUSES
    if status in {"ready", "imported"} and report_filename:
        public["files_path"] = zap_report_workspace_path(job_id, report_filename)
        if status == "ready":
            public["atlas_draft_id"] = str(job.get("import_source_id") or "")
        else:
            public["atlas_batch_id"] = str(job.get("import_source_id") or "")
    return public


def confirm_and_queue_assessment_zap_job(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    data: object,
    *,
    team_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    cfg: Mapping[str, Any] | None = None,
    resolve_addresses: Callable[[str], Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Rebuild, digest-check, and durably queue the reviewed plan bytes."""
    body = _body(data, submit=True)
    if body.get("confirmed") is not True:
        raise AssessmentZapError(
            "confirmation_required",
            "Explicit ZAP plan confirmation is required.",
            status_code=409,
        )
    supplied_digest = str(body.get("plan_digest") or "").strip()
    if not supplied_digest:
        raise AssessmentZapError(
            "plan_digest_required",
            "The reviewed ZAP plan digest is required.",
        )
    selection = {key: body.get(key) for key in _SELECTION_FIELDS}
    preview, plan = build_assessment_zap_plan(
        session_id,
        project_id,
        assessment_id,
        check_id,
        selection,
        team_id=team_id,
        cfg=cfg,
        resolve_addresses=resolve_addresses,
    )
    if supplied_digest != preview["plan_digest"]:
        raise AssessmentZapError(
            "stale_plan",
            "The ZAP plan changed. Review the current plan and confirm again.",
            status_code=409,
        )
    profile = preview["http_profile"]
    try:
        job = queue_zap_job(
            session_id,
            project_id,
            assessment_id,
            check_id,
            str(profile["id"]),
            int(profile["revision"]),
            plan,
            team_id=team_id,
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            cfg=cfg,
        )
    except (ZapJobError, ZapJobArtifactError) as exc:
        raise _downstream_error(exc) from exc
    return public_zap_job(job)


def get_assessment_zap_job(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    job_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    job = zap_job_for_owner(session_id, job_id, team_id=team_id)
    if job is None or any(
        (
            str(job.get("project_id") or "") != project_id,
            str(job.get("assessment_id") or "") != assessment_id,
            str(job.get("check_id") or "") != check_id,
        )
    ):
        raise AssessmentZapError(
            "zap_job_not_found", "ZAP job not found.", status_code=404
        )
    return public_zap_job(job)


def list_assessment_zap_jobs(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    *,
    team_id: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return bounded owner-visible history after rechecking the nested check."""
    with get_db_connect()() as conn:
        load_action_row(
            conn,
            session_id,
            team_id,
            project_id,
            assessment_id,
            check_id,
        )
        jobs = zap_jobs_for_owner_check(
            session_id,
            project_id,
            assessment_id,
            check_id,
            team_id=team_id,
            limit=limit,
            conn=conn,
        )
    return [public_zap_job(job) for job in jobs]


def cancel_assessment_zap_job(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    job_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    current = get_assessment_zap_job(
        session_id,
        project_id,
        assessment_id,
        check_id,
        job_id,
        team_id=team_id,
    )
    if not current["cancelable"]:
        raise AssessmentZapError(
            "zap_job_not_cancelable",
            "This ZAP job is no longer active.",
            status_code=409,
        )
    try:
        return public_zap_job(
            request_zap_job_cancel(session_id, job_id, team_id=team_id)
        )
    except ZapJobError as exc:
        raise _downstream_error(exc) from exc


__all__ = [
    "AssessmentZapError",
    "build_assessment_zap_plan",
    "cancel_assessment_zap_job",
    "confirm_and_queue_assessment_zap_job",
    "get_assessment_zap_job",
    "list_assessment_zap_jobs",
    "public_zap_job",
]
