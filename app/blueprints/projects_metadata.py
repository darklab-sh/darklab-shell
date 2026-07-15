# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Entity label and note metadata routes.
"""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.projects.contracts import ProjectWorkspaceError
from services.projects.metadata import (
    add_entity_label,
    delete_entity_label,
    delete_entity_note,
    entity_metadata_target_exists,
    get_entity_note,
    list_entity_labels,
    upsert_entity_note,
)


@project_routes.projects_bp.route("/entities/<entity_type>/<path:entity_id>/labels")
def entity_labels_list(entity_type, entity_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        labels = list_entity_labels(session_id, entity_type, entity_id, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_json_error(str(exc), 400)
    if labels is None:
        return project_routes._project_not_found("entity not found")
    return jsonify({"labels": labels})


@project_routes.projects_bp.route("/entities/<entity_type>/<path:entity_id>/labels", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def entity_labels_create(entity_type, entity_id):
    session_id, team_id, error_response = project_routes._project_owner(
        project_routes._entity_metadata_write_capability(entity_type)
    )
    if error_response:
        return error_response
    try:
        label = add_entity_label(
            session_id,
            entity_type,
            entity_id,
            request.get_json(silent=True) or {},
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if label is None:
        return project_routes._project_not_found("entity not found")
    project_routes.log.info("ENTITY_LABEL_ADDED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "entity_type": label["entity_type"],
    })
    return jsonify({"ok": True, "label": label}), 201


@project_routes.projects_bp.route("/entities/<entity_type>/<path:entity_id>/labels", methods=["DELETE"])
@limiter.limit(project_routes._project_write_limit)
def entity_labels_delete(entity_type, entity_id):
    session_id, team_id, error_response = project_routes._project_owner(
        project_routes._entity_metadata_write_capability(entity_type)
    )
    if error_response:
        return error_response
    try:
        deleted = delete_entity_label(
            session_id,
            entity_type,
            entity_id,
            request.get_json(silent=True) or {},
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if deleted is None:
        return project_routes._project_not_found("entity not found")
    if not deleted:
        return project_routes._project_not_found("label not found")
    project_routes.log.info("ENTITY_LABEL_REMOVED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "entity_type": entity_type,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True})


@project_routes.projects_bp.route("/entities/<entity_type>/<path:entity_id>/note")
def entity_note_get(entity_type, entity_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        if not entity_metadata_target_exists(session_id, entity_type, entity_id, team_id=team_id):
            return project_routes._project_not_found("entity not found")
        note = get_entity_note(session_id, entity_type, entity_id, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_json_error(str(exc), 400)
    return jsonify({"note": note})


@project_routes.projects_bp.route("/entities/<entity_type>/<path:entity_id>/note", methods=["PUT"])
@limiter.limit(project_routes._project_write_limit)
def entity_note_update(entity_type, entity_id):
    session_id, team_id, error_response = project_routes._project_owner(
        project_routes._entity_metadata_write_capability(entity_type)
    )
    if error_response:
        return error_response
    try:
        note = upsert_entity_note(
            session_id,
            entity_type,
            entity_id,
            request.get_json(silent=True) or {},
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if note is None:
        return project_routes._project_not_found("entity not found")
    project_routes.log.info("ENTITY_NOTE_SAVED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "entity_type": note["entity_type"],
    })
    return jsonify({"ok": True, "note": note})


@project_routes.projects_bp.route("/entities/<entity_type>/<path:entity_id>/note", methods=["DELETE"])
@limiter.limit(project_routes._project_write_limit)
def entity_note_delete(entity_type, entity_id):
    session_id, team_id, error_response = project_routes._project_owner(
        project_routes._entity_metadata_write_capability(entity_type)
    )
    if error_response:
        return error_response
    try:
        deleted = delete_entity_note(session_id, entity_type, entity_id, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if deleted is None:
        return project_routes._project_not_found("entity not found")
    if not deleted:
        return project_routes._project_not_found("note not found")
    project_routes.log.info("ENTITY_NOTE_REMOVED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "entity_type": entity_type,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True})
