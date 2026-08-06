# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser routes for saved finding remediation and verification decisions."""

from flask import jsonify, request
from werkzeug.exceptions import BadRequest

from blueprints import projects as project_routes
from extensions import limiter
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceError
from services.projects.metadata import (
    default_finding_triage_details,
    finding_triage_target_exists,
    get_finding_triage_details,
)
from services.teams.capabilities import Capability


@project_routes.projects_bp.route("/findings/<finding_id>/triage")
def finding_triage_detail(finding_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        if not finding_triage_target_exists(session_id, finding_id, team_id=team_id):
            return project_routes._project_not_found("finding not found")
        triage = get_finding_triage_details(session_id, finding_id, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    return jsonify({
        "triage": triage or default_finding_triage_details(
            session_id, finding_id, team_id=team_id
        ),
    })


def _triage_payload(session_id, team_id, finding_id):
    if not request.is_json:
        return None
    body_bytes = len(request.get_data(cache=True) or b"")
    try:
        return request.get_json(silent=False)
    except BadRequest:
        project_routes.log.warning("FINDING_TRIAGE_PAYLOAD_DECODE_FAILED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "finding_id": finding_id,
            "content_type": request.content_type or "",
            "body_bytes": body_bytes,
        })
        raise ProjectWorkspaceError("finding triage payload must be JSON") from None


def _verification_changed(previous, response):
    return any(
        str((previous or {}).get(field) or "") != str(response.get(field) or "")
        for field in ("verification_steps", "verification_status", "verification_notes")
    )


@project_routes.projects_bp.route("/findings/<finding_id>/triage", methods=["PUT"])
@limiter.limit(project_routes._project_write_limit)
def finding_triage_update(finding_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.TRIAGE_FINDINGS
    )
    if error_response:
        return error_response
    try:
        if not finding_triage_target_exists(session_id, finding_id, team_id=team_id):
            return project_routes._project_not_found("finding not found")
        data = _triage_payload(session_id, team_id, finding_id)
        if not isinstance(data, dict):
            raise ProjectWorkspaceError("finding triage payload must be a JSON object")
        previous = get_finding_triage_details(session_id, finding_id, team_id=team_id)
        next_status = str(data.get("verification_status") or "not_started").strip() or "not_started"
        will_clear = (
            not str(data.get("remediation") or "").strip()
            and not str(data.get("verification_steps") or "").strip()
            and next_status == "not_started"
            and not str(data.get("verification_notes") or "").strip()
        )
        project_routes.log.debug("FINDING_TRIAGE_UPDATE_REQUESTED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "finding_id": finding_id,
            "previous_verification_status": (
                previous.get("verification_status") if previous else "not_started"
            ),
            "next_verification_status": next_status,
            "will_clear": will_clear,
        })
        triage = project_routes.upsert_finding_triage_details(
            session_id,
            finding_id,
            data,
            team_id=team_id,
            actor_member_id=project_routes._project_actor_member_id(session_id, team_id),
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if triage is None and not will_clear:
        project_routes.log.warning("FINDING_TRIAGE_UPDATE_MISS", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "finding_id": finding_id,
            "reason": "target_missing_after_precheck",
        })
        return project_routes._project_not_found("finding not found")
    response = triage or default_finding_triage_details(
        session_id, finding_id, team_id=team_id
    )
    if _verification_changed(previous, response):
        project_routes.record_event(
            AuditEventType.VERIFICATION_EDIT,
            target_id=finding_id,
            details={
                "finding_id": finding_id,
                "from_state": str((previous or {}).get("verification_status") or "not_started"),
                "to_state": str(response.get("verification_status") or "not_started"),
            },
            **project_routes._project_audit_fields(session_id, team_id),
        )
    action = "cleared" if will_clear else ("updated" if previous else "created")
    project_routes.log.info("FINDING_TRIAGE_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "finding_id": finding_id,
        "action": action,
        "triage_id": response.get("id") or "",
        "verification_status": response.get("verification_status") or "not_started",
        "has_remediation": bool(str(response.get("remediation") or "").strip()),
        "has_verification_steps": bool(str(response.get("verification_steps") or "").strip()),
        "has_verification_notes": bool(str(response.get("verification_notes") or "").strip()),
    })
    return jsonify({"ok": True, "triage": response})
