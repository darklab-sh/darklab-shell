# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atlas entity profile read route."""

from flask import jsonify, request

from blueprints import atlas as atlas_routes
from services.atlas.lookup import entity_detail
from services.projects.contracts import ProjectWorkspaceError


@atlas_routes.atlas_bp.route("/atlas/entities/<entity_id>")
def atlas_entity_detail(entity_id):
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    offset = lambda name: atlas_routes._parse_int(  # noqa: E731
        request.args.get(name), 0, minimum=0, maximum=100000
    )
    try:
        detail = atlas_routes.run_atlas_read(lambda conn: entity_detail(
            conn,
            session_id,
            entity_id,
            team_id=owner_scope.team_id,
            project_id=request.args.get("project_id") or "",
            runs_offset=offset("runs_offset"),
            findings_offset=offset("findings_offset"),
            finding_bucket=request.args.get("finding_bucket") or "direct",
            related_urls_offset=offset("related_urls_offset"),
            related_ports_offset=offset("related_ports_offset"),
        ))
    except (ProjectWorkspaceError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    if detail is None:
        return jsonify({"error": "entity not found"}), 404
    return jsonify(detail)
