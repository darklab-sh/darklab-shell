# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project Web Surface routes."""

from flask import request

from blueprints import projects as project_routes
from services.projects.web_surface import list_project_web_surface


@project_routes.projects_bp.route("/projects/<project_id>/web-surface")
def projects_web_surface_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    return project_routes._project_json_or_404(list_project_web_surface(
        session_id,
        project_id,
        request.args,
        limit=project_routes._parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
        offset=project_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
        team_id=team_id,
    ))
