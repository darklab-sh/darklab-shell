"""
Project link and run-entity relationship routes.
"""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects.contracts import ProjectWorkspaceError
from services.projects.links import (
    link_project_entities,
    link_project_entity,
    link_project_run_entities,
    list_project_links,
    preview_project_run_entity_links,
    preview_project_run_entity_unlinks,
    unlink_project_entities,
    unlink_project_entity,
    unlink_project_run_entities,
)
from services.teams.capabilities import Capability


@project_routes.projects_bp.route("/projects/<project_id>/links")
def projects_links_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    links = list_project_links(session_id, project_id, team_id=team_id)
    return project_routes._project_json_or_404(links, key="links")


@project_routes.projects_bp.route("/projects/<project_id>/links", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def projects_links_create(project_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    if isinstance(data, dict) and "entity_ids" in data:
        try:
            result = link_project_entities(session_id, project_id, data, team_id=team_id)
        except ProjectWorkspaceError as exc:
            if str(exc) == "too_many":
                return project_routes._project_bulk_too_many_response()
            return project_routes._project_error_response(exc)
        if result is None:
            return project_routes._project_not_found()
        counts = result.get("counts", {})
        record_event(
            AuditEventType.PROJECT_LINK,
            target_id=project_id,
            project_id=project_id,
            details={
                "project_id": project_id,
                "entity_type": data.get("entity_type") or "",
                "entity_ids": [str(entity_id or "") for entity_id in data.get("entity_ids") or []],
                "created_count": int(counts.get("added") or 0),
                "source": data.get("source") or "manual",
            },
            **project_routes._project_audit_fields(session_id, team_id),
        )
        project_routes.log.info("PROJECT_LINKS_BULK_ADDED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "project_id": project_id,
            "entity_type": data.get("entity_type") or "",
            "counts": counts,
            "failures": project_routes._project_bulk_failures(result.get("results")),
        })
        if data.get("include_entities") and data.get("entity_type") == "run":
            linked_entities = link_project_run_entities(
                session_id,
                project_id,
                [str(run_id or "") for run_id in data.get("entity_ids") or []],
                data.get("source") or "manual",
                team_id=team_id,
            )
            if linked_entities is not None:
                result["linked_entities"] = linked_entities
        return jsonify(result)
    try:
        link = link_project_entity(session_id, project_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if link is None:
        return project_routes._project_not_found()
    record_event(
        AuditEventType.PROJECT_LINK,
        target_id=project_id,
        project_id=project_id,
        details={
            "project_id": project_id,
            "entity_type": link["entity_type"],
            "entity_id": link.get("entity_id") or "",
            "created_count": 1,
            "source": link["source"],
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("PROJECT_LINK_ADDED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "entity_type": link["entity_type"],
        "source": link["source"],
    })
    body = {"ok": True, "link": link}
    if data.get("include_entities") and data.get("entity_type") == "run":
        linked_entities = link_project_run_entities(
            session_id,
            project_id,
            [str(data.get("entity_id") or "")],
            data.get("source") or "manual",
            team_id=team_id,
        )
        if linked_entities is not None:
            body["linked_entities"] = linked_entities
    return jsonify(body), 201


@project_routes.projects_bp.route("/projects/<project_id>/links/run-entities/preview", methods=["POST"])
def projects_run_entity_link_preview(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    try:
        preview = preview_project_run_entity_links(session_id, project_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        if str(exc) == "too_many":
            return project_routes._project_bulk_too_many_response()
        return project_routes._project_error_response(exc)
    if preview is None:
        return project_routes._project_not_found()
    return jsonify({"ok": True, "preview": preview})


@project_routes.projects_bp.route("/projects/<project_id>/links/run-entities/remove-preview", methods=["POST"])
def projects_run_entity_unlink_preview(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    try:
        preview = preview_project_run_entity_unlinks(session_id, project_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        if str(exc) == "too_many":
            return project_routes._project_bulk_too_many_response()
        return project_routes._project_error_response(exc)
    if preview is None:
        return project_routes._project_not_found()
    return jsonify({"ok": True, "preview": preview})


@project_routes.projects_bp.route("/projects/<project_id>/links", methods=["DELETE"])
@limiter.limit(project_routes._project_write_limit)
def projects_links_delete(project_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    if isinstance(data, dict) and "entity_ids" in data:
        try:
            result = unlink_project_entities(session_id, project_id, data, team_id=team_id)
        except ProjectWorkspaceError as exc:
            if str(exc) == "too_many":
                return project_routes._project_bulk_too_many_response()
            return project_routes._project_error_response(exc)
        if result is None:
            return project_routes._project_not_found()
        counts = result.get("counts", {})
        record_event(
            AuditEventType.PROJECT_UNLINK,
            target_id=project_id,
            project_id=project_id,
            details={
                "project_id": project_id,
                "entity_type": data.get("entity_type") or "",
                "entity_ids": [str(entity_id or "") for entity_id in data.get("entity_ids") or []],
                "deleted_count": int(counts.get("removed") or 0),
                "source": "project_links_bulk",
            },
            **project_routes._project_audit_fields(session_id, team_id),
        )
        project_routes.log.info("PROJECT_LINKS_BULK_REMOVED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "project_id": project_id,
            "entity_type": data.get("entity_type") or "",
            "counts": counts,
            "failures": project_routes._project_bulk_failures(result.get("results")),
        })
        return jsonify(result)
    try:
        deleted = unlink_project_entity(session_id, project_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if deleted is None:
        return project_routes._project_not_found()
    if not deleted:
        return project_routes._project_not_found("project link not found")
    record_event(
        AuditEventType.PROJECT_UNLINK,
        target_id=project_id,
        project_id=project_id,
        details={
            "project_id": project_id,
            "entity_type": data.get("entity_type") or "",
            "entity_id": data.get("entity_id") or "",
            "deleted_count": 1,
            "source": "project_links",
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    body: dict[str, object] = {"ok": True}
    unlinked_entity_count = 0
    if (
        data.get("entity_type") == "run"
        and (data.get("include_entities") or data.get("include_curated_entities"))
    ):
        unlinked_entities = unlink_project_run_entities(
            session_id,
            project_id,
            [str(data.get("entity_id") or "")],
            include_curated=bool(data.get("include_curated_entities")),
            team_id=team_id,
        )
        if unlinked_entities is not None:
            body["unlinked_entities"] = unlinked_entities
            unlinked_entity_count = int(unlinked_entities.get("removed", 0) or 0)
    project_routes.log.info("PROJECT_LINK_REMOVED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "entity_type": data.get("entity_type") or "",
        "entity_id": data.get("entity_id") or "",
        "unlinked_entities": unlinked_entity_count,
    })
    return jsonify(body)
