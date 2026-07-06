"""Project auto-promote rule route group."""

from __future__ import annotations

from blueprints import projects as project_routes
from services.projects.contracts import ProjectWorkspaceError
from services.teams.capabilities import Capability


@project_routes.projects_bp.route("/projects/<project_id>/auto-promote-rules")
def projects_auto_promote_rules_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    rules = project_routes.list_auto_promote_rules(session_id, project_id, team_id=team_id)
    return project_routes._project_json_or_404(rules, key="rules")


@project_routes.projects_bp.route("/projects/<project_id>/auto-promote-rules/preview", methods=["POST"])
@project_routes.limiter.limit(project_routes._project_auto_promote_preview_limit, key_func=project_routes.get_session_id)
def projects_auto_promote_rules_preview(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    data = project_routes.request.get_json(silent=True) or {}
    try:
        preview = project_routes.preview_auto_promote_rule(
            session_id,
            project_id,
            data,
            team_id=team_id,
            limit=project_routes._project_auto_promote_match_limit(
                project_routes.request.args.get("limit"),
                "max_project_auto_promote_preview_matches",
                200,
                hard_max=1000,
            ),
        )
    except ProjectWorkspaceError as exc:
        project_routes._log_project_auto_promote_rejected(
            "PROJECT_AUTO_PROMOTE_RULE_PREVIEW_REJECTED",
            session_id,
            team_id,
            project_id,
            exc,
            data=data,
        )
        return project_routes._project_error_response(exc)
    project_routes.log.debug("PROJECT_AUTO_PROMOTE_RULE_PREVIEWED", extra={
        **project_routes._project_auto_promote_log_context(session_id, team_id, project_id),
        **project_routes._project_auto_promote_safe_rule(preview.get("rule") if isinstance(preview, dict) else {}),
        **project_routes._project_auto_promote_result_fields(preview),
    })
    return project_routes.jsonify({"ok": True, "preview": preview})


@project_routes.projects_bp.route("/projects/<project_id>/auto-promote-rules", methods=["POST"])
@project_routes.limiter.limit(project_routes._project_write_limit)
def projects_auto_promote_rules_create(project_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    data = project_routes.request.get_json(silent=True) or {}
    team_context = project_routes._project_team_log_context(session_id, team_id)
    try:
        rule = project_routes.create_auto_promote_rule(
            session_id,
            project_id,
            data,
            team_id=team_id,
            member_id=team_context.get("actor_member_id", ""),
        )
    except ProjectWorkspaceError as exc:
        project_routes._log_project_auto_promote_rejected(
            "PROJECT_AUTO_PROMOTE_RULE_CREATE_REJECTED",
            session_id,
            team_id,
            project_id,
            exc,
            data=data,
        )
        return project_routes._project_error_response(exc)
    project_routes.log.info("PROJECT_AUTO_PROMOTE_RULE_CREATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "rule_id": rule["id"],
        **project_routes._project_auto_promote_safe_rule(rule),
        **team_context,
    })
    return project_routes.jsonify({"ok": True, "rule": rule}), 201


@project_routes.projects_bp.route("/projects/<project_id>/auto-promote-rules/<rule_id>", methods=["PUT"])
@project_routes.limiter.limit(project_routes._project_write_limit)
def projects_auto_promote_rules_update(project_id, rule_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    data = project_routes.request.get_json(silent=True) or {}
    team_context = project_routes._project_team_log_context(session_id, team_id)
    try:
        rule = project_routes.update_auto_promote_rule(session_id, project_id, rule_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        project_routes._log_project_auto_promote_rejected(
            "PROJECT_AUTO_PROMOTE_RULE_UPDATE_REJECTED",
            session_id,
            team_id,
            project_id,
            exc,
            rule_id=rule_id,
            data=data,
        )
        return project_routes._project_error_response(exc)
    if rule is None:
        project_routes.log.warning("PROJECT_AUTO_PROMOTE_RULE_UPDATE_MISS", extra={
            **project_routes._project_auto_promote_log_context(session_id, team_id, project_id, rule_id=rule_id),
            "status": 404,
            "reason": "auto-promote rule not found",
        })
        return project_routes._project_not_found("auto-promote rule not found")
    project_routes.log.info("PROJECT_AUTO_PROMOTE_RULE_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "rule_id": rule_id,
        **project_routes._project_auto_promote_safe_rule(rule),
        **team_context,
    })
    return project_routes.jsonify({"ok": True, "rule": rule})


@project_routes.projects_bp.route("/projects/<project_id>/auto-promote-rules/<rule_id>", methods=["DELETE"])
@project_routes.limiter.limit(project_routes._project_write_limit)
def projects_auto_promote_rules_delete(project_id, rule_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    rule_for_log = project_routes.get_auto_promote_rule(session_id, project_id, rule_id, team_id=team_id)
    deleted = project_routes.delete_auto_promote_rule(session_id, project_id, rule_id, team_id=team_id)
    if deleted is None:
        project_routes.log.warning("PROJECT_AUTO_PROMOTE_RULE_DELETE_MISS", extra={
            **project_routes._project_auto_promote_log_context(session_id, team_id, project_id, rule_id=rule_id),
            "status": 404,
            "reason": "auto-promote rule not found",
        })
        return project_routes._project_not_found("auto-promote rule not found")
    project_routes.log.info("PROJECT_AUTO_PROMOTE_RULE_DELETED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "rule_id": rule_id,
        **project_routes._project_auto_promote_safe_rule(rule_for_log),
        **project_routes._project_team_log_context(session_id, team_id),
    })
    return project_routes.jsonify({"ok": True})


@project_routes.projects_bp.route("/projects/<project_id>/auto-promote-rules/<rule_id>/apply", methods=["POST"])
@project_routes.limiter.limit(project_routes._project_write_limit)
def projects_auto_promote_rules_apply(project_id, rule_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        result = project_routes.apply_auto_promote_rule(
            session_id,
            project_id,
            rule_id,
            team_id=team_id,
            limit=project_routes._project_auto_promote_match_limit(
                project_routes.request.args.get("limit"),
                "max_project_auto_promote_apply_matches",
                1000,
                hard_max=5000,
            ),
        )
    except ProjectWorkspaceError as exc:
        project_routes._log_project_auto_promote_rejected(
            "PROJECT_AUTO_PROMOTE_RULE_APPLY_REJECTED",
            session_id,
            team_id,
            project_id,
            exc,
            rule_id=rule_id,
        )
        return project_routes._project_error_response(exc)
    if result is None:
        project_routes.log.warning("PROJECT_AUTO_PROMOTE_RULE_APPLY_MISS", extra={
            **project_routes._project_auto_promote_log_context(session_id, team_id, project_id, rule_id=rule_id),
            "status": 404,
            "reason": "auto-promote rule not found",
        })
        return project_routes._project_not_found("auto-promote rule not found")
    project_routes.log.info("PROJECT_AUTO_PROMOTE_RULE_APPLIED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "rule_id": rule_id,
        **project_routes._project_auto_promote_safe_rule(result.get("rule") if isinstance(result, dict) else {}),
        **project_routes._project_auto_promote_result_fields(result),
        **project_routes._project_team_log_context(session_id, team_id),
    })
    return project_routes.jsonify({"ok": True, "result": result})
