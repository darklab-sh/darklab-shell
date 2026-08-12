# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project Monitoring CVE risk acknowledgement route."""

from flask import jsonify, request
from werkzeug.exceptions import BadRequest

from blueprints import projects as project_routes
from extensions import limiter
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability


@project_routes.projects_bp.route(
    "/projects/<project_id>/monitoring/risk-events/<escalation_id>",
    methods=["PATCH"],
)
@limiter.limit(project_routes._project_write_limit)
def projects_monitoring_risk_event_update(project_id, escalation_id):
    from services.cve_risk.escalation import acknowledge_escalation  # noqa: PLC0415

    session_id, team_id, error_response = project_routes._project_owner(Capability.TRIAGE_FINDINGS)
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise BadRequest("risk escalation payload must be a JSON object")
    ack_note = str(data.get("ack_note") or "").strip()
    audit_fields = project_routes._project_audit_fields(session_id, team_id)

    def _update(conn):
        return acknowledge_escalation(
            conn,
            escalation_id,
            session_id=session_id,
            team_id=team_id,
            project_id=project_id,
            ack_state=str(data.get("ack_state") or "").strip(),
            ack_note=ack_note,
            actor_session_id=str(audit_fields.get("actor_session_id") or session_id),
            actor_member_id=str(audit_fields.get("actor_member_id") or ""),
        )

    try:
        updated = run_project_transaction(_update)
    except ValueError as exc:
        project_routes.log.warning("PROJECT_RISK_ESCALATION_ACK_REJECTED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id, "project_id": project_id,
            "escalation_id": escalation_id, "http_status": 400,
            "reason": str(exc),
        })
        return jsonify({"error": "invalid_risk_escalation_update", "message": str(exc)}), 400
    if updated is None:
        return project_routes._project_not_found()
    project_routes.log.info("PROJECT_RISK_ESCALATION_ACK_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id, "project_id": project_id,
        "escalation_id": escalation_id, "ack_state": str(updated.get("ack_state") or ""),
        "note_chars": len(ack_note[:1000]),
    })
    return jsonify({"ok": True, "risk_event": updated})
