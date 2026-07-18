# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project monitoring and digest settings routes.
"""

from flask import jsonify, request
from werkzeug.exceptions import BadRequest

from blueprints import projects as project_routes
from extensions import limiter
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects import digests as project_digests
from services.projects.contracts import ProjectWorkspaceError
from services.projects.monitoring import (
    get_project_monitoring,
    get_project_monitoring_summary,
    update_project_monitoring_fire_ack,
)
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability
from services.watchers.serialization import watcher_fire_payload


@project_routes.projects_bp.route("/projects/<project_id>/monitoring")
def projects_monitoring(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    fire_limit = project_routes._parse_int(request.args.get("fire_limit"), 8, minimum=1, maximum=25)
    payload = get_project_monitoring(
        session_id,
        project_id,
        team_id=team_id,
        fire_limit=fire_limit,
    )
    if payload is None:
        project_routes.log.debug("PROJECT_MONITORING_MISS", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "route": "project_monitoring",
        })
        return project_routes._project_not_found()
    digest_settings = project_digests.get_digest_settings(session_id, project_id, team_id=team_id)
    payload["digest_settings"] = digest_settings or {}
    payload["notification_channels"] = project_routes._project_notification_channels(session_id, team_id)
    payload["can_manage_digest_settings"] = project_routes._can_manage_project_digest_settings(session_id, team_id)
    counts = payload.get("counts") or {}
    summary = payload.get("summary") or {}
    project_routes.log.info("PROJECT_MONITORING_VIEWED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "fire_limit": fire_limit,
        "monitor_count": len(payload.get("monitors") or []),
        "timeline_count": len(payload.get("timeline") or []),
        "changed_count": int(counts.get("changed") or 0),
        "failed_count": int(counts.get("failed") or 0),
        "highest_severity": str(summary.get("highest_severity") or ""),
    })
    return project_routes._project_json_or_404(payload)


@project_routes.projects_bp.route("/projects/<project_id>/digest-settings", methods=["GET"])
def projects_digest_settings_get(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    settings = project_digests.get_digest_settings(session_id, project_id, team_id=team_id)
    if settings is None:
        return project_routes._project_not_found()
    return jsonify({
        "digest_settings": settings,
        "notification_channels": project_routes._project_notification_channels(session_id, team_id),
        "can_manage_digest_settings": project_routes._can_manage_project_digest_settings(session_id, team_id),
    })


@project_routes.projects_bp.route("/projects/<project_id>/digest-settings", methods=["PATCH"])
@limiter.limit(project_routes._project_write_limit)
def projects_digest_settings_update(project_id):
    capabilities = (Capability.MANAGE_AUTOMATION, Capability.MANAGE_NOTIFICATIONS)
    session_id, team_id, error_response = project_routes._project_owner_any_capability(capabilities)
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise BadRequest("digest settings payload must be a JSON object")
    try:
        settings = project_digests.save_digest_settings(session_id, project_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        project_routes.log.warning("PROJECT_DIGEST_SETTINGS_REJECTED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "status": project_routes._project_error_status(exc),
            "reason": str(exc),
        })
        return project_routes._project_json_error(str(exc), project_routes._project_error_status(exc))
    project_routes.log.info("PROJECT_DIGEST_SETTINGS_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "enabled": bool(settings.get("enabled")),
        "cadence_preset": str(settings.get("cadence_preset") or ""),
        "channel_count": len(settings.get("channel_ids") or []),
        "quiet_no_change": bool(settings.get("quiet_no_change")),
    })
    return jsonify({
        "digest_settings": settings,
        "notification_channels": project_routes._project_notification_channels(session_id, team_id),
        "can_manage_digest_settings": project_routes._can_manage_project_digest_settings(session_id, team_id),
    })


@project_routes.projects_bp.route("/projects/<project_id>/monitoring/summary")
def projects_monitoring_summary(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    fire_limit = project_routes._parse_int(request.args.get("fire_limit"), 8, minimum=1, maximum=25)
    window_start = project_routes._parse_optional_iso_datetime(request.args.get("window_start"), name="window_start")
    window_end = project_routes._parse_optional_iso_datetime(request.args.get("window_end"), name="window_end")
    payload = get_project_monitoring_summary(
        session_id,
        project_id,
        team_id=team_id,
        fire_limit=fire_limit,
        window_start=window_start,
        window_end=window_end,
    )
    if payload is None:
        project_routes.log.debug("PROJECT_MONITORING_MISS", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "route": "project_monitoring_summary",
        })
        return project_routes._project_not_found()
    summary = payload.get("summary") or {}
    window_summary = payload.get("window_summary") or {}
    windowed = bool(window_start or window_end)
    project_routes.log.info("PROJECT_MONITORING_SUMMARY_VIEWED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "fire_limit": fire_limit,
        "changed_count": int(summary.get("changed_monitor_count") or 0),
        "failed_count": int(summary.get("failed_monitor_count") or 0),
        "highest_severity": str(summary.get("highest_severity") or ""),
        "top_change_count": len(summary.get("top_changes") or []),
        "windowed": windowed,
        "window_changed_count": int(window_summary.get("changed_monitor_count") or 0) if windowed else 0,
        "window_recovered_count": int(window_summary.get("recovered_monitor_count") or 0) if windowed else 0,
        "window_failed_count": int(window_summary.get("failed_monitor_count") or 0) if windowed else 0,
        "window_highest_severity": str(window_summary.get("highest_severity") or "") if windowed else "",
        "window_top_change_count": len(window_summary.get("top_changes") or []) if windowed else 0,
        "window_fire_count": int((payload.get("digest_window") or {}).get("fire_count") or 0) if windowed else 0,
    })
    return project_routes._project_json_or_404(payload)


@project_routes.projects_bp.route("/projects/<project_id>/monitoring/fires/<fire_id>", methods=["PATCH"])
@limiter.limit(project_routes._project_write_limit)
def projects_monitoring_fire_update(project_id, fire_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.TRIAGE_FINDINGS)
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise BadRequest("monitoring fire payload must be a JSON object")
    ack_note = str(data.get("ack_note") or "").strip()
    try:
        updated = update_project_monitoring_fire_ack(
            session_id,
            project_id,
            fire_id,
            ack_state=str(data.get("ack_state") or "").strip(),
            ack_note=ack_note,
            ack_by=session_id,
            team_id=team_id,
        )
    except ValueError as exc:
        project_routes.log.warning("PROJECT_MONITORING_FIRE_ACK_REJECTED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "fire_id": fire_id,
            "status": 400,
            "reason": str(exc),
        })
        return jsonify({"error": "invalid_monitoring_fire_update", "message": str(exc)}), 400
    if updated is None:
        project_routes.log.debug("PROJECT_MONITORING_FIRE_ACK_MISS", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "fire_id": fire_id,
        })
        return project_routes._project_not_found()
    watcher, fire = updated

    def _record_ack(conn):
        record_event(
            AuditEventType.WATCHER_ACK,
            target_id=watcher.id,
            project_id=project_id,
            details={
                "watcher_id": watcher.id,
                "project_id": project_id,
                "fire_id": fire.id,
                "ack_state": fire.ack_state,
                "note_chars": len(ack_note),
            },
            conn=conn,
            **project_routes._project_audit_fields(session_id, team_id),
        )

    run_project_transaction(_record_ack)
    project_routes.log.info("PROJECT_MONITORING_FIRE_ACK_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "watcher_id": watcher.id,
        "fire_id": fire.id,
        "ack_state": fire.ack_state,
        "note_chars": len(ack_note),
    })
    return jsonify({"ok": True, "fire": watcher_fire_payload(fire)})
