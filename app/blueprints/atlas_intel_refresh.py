# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atlas entity intelligence refresh route."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import atlas as atlas_routes
from services.atlas.intel_bridge import refresh_entity_intel
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.teams.capabilities import Capability


@atlas_routes.atlas_bp.route("/atlas/entities/<entity_id>/refresh_intel", methods=["POST"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_entity_intel_refresh(entity_id):
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(
        session_id,
        Capability.TRIAGE_FINDINGS,
    )
    if scope_response:
        return scope_response
    assert owner_scope is not None
    try:
        result = refresh_entity_intel(session_id, entity_id, team_id=owner_scope.team_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if result is None:
        return jsonify({"error": "entity not found"}), 404
    shared_advisory = result.get("shared_advisory")
    if isinstance(shared_advisory, dict) and shared_advisory.get("outcome") != "disabled":
        record_event(
            AuditEventType.CVE_ADVISORY_REFRESH,
            target_id="nvd",
            details={
                "source": "nvd",
                "outcome": str(shared_advisory.get("outcome") or "unknown"),
                "record_count": int(shared_advisory.get("record_count") or 0),
                "origin": "external",
            },
            **route_audit_fields(session_id, request, owner_scope),
        )
    atlas_routes.log.info("ATLAS_INTEL_REFRESH", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "entity_id": entity_id,
        "success_count": result["success_count"],
    })
    return jsonify({"ok": True, "refresh": result})
