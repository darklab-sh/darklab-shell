# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project deletion route and assessment-batch lifecycle guard."""

from __future__ import annotations

from flask import jsonify

from blueprints import projects as project_routes
from blueprints.assessment_batch_lifecycle import batch_lifecycle_pending_response
from extensions import limiter
from services.assessments.batch.lifecycle_guard import BatchLifecycleCancellation
from services.audit.models import AuditEventType
from services.projects.crud import delete_project
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability


@project_routes.projects_bp.route("/projects/<project_id>", methods=["DELETE"])
@limiter.limit(project_routes._project_write_limit)
def projects_delete(project_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MUTATE_PROJECTS
    )
    if error_response:
        return error_response

    def _delete_project(conn):
        deleted = delete_project(session_id, project_id, team_id=team_id, conn=conn)
        if deleted is not True:
            return project_routes._project_not_found() if deleted is False else deleted
        project_routes.record_event(
            AuditEventType.PROJECT_DELETE,
            target_id=project_id,
            project_id=project_id,
            details={"project_id": project_id, "deleted_count": 1},
            conn=conn,
            **project_routes._project_audit_fields(session_id, team_id),
        )
        return None

    delete_response = run_project_transaction(_delete_project)
    if isinstance(delete_response, BatchLifecycleCancellation):
        return batch_lifecycle_pending_response(
            delete_response,
            session_id,
            team_id=team_id,
        )
    if delete_response is not None:
        return delete_response
    project_routes.log.info("PROJECT_DELETED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
    })
    return jsonify({"ok": True})


__all__ = ["projects_delete"]
