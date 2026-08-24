# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 action for one explicit external OSV package lookup."""

from __future__ import annotations

from core.helpers import get_client_ip, get_log_session_id
from flask import request
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.cve_risk.osv_external import query_external_osv
from services.storage.transactions import run_transaction
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied

from blueprints import api_v1 as api_routes
from blueprints.api_v1_osv_result import osv_lookup_response


def _error(code: str, message: str, status: int):
    return api_routes._api_json_error(code, message, status)


def _request_values(data: dict) -> tuple[str, str]:
    if set(data) - {"purl", "version"}:
        raise ValueError("request accepts only purl and version")
    purl = data.get("purl")
    version = data.get("version")
    if not isinstance(purl, str) or not isinstance(version, str):
        raise ValueError("purl and version must be strings")
    if not purl.strip() or not version.strip():
        raise ValueError("purl and version are required")
    return purl.strip(), version.strip()


@api_routes.api_v1_bp.route("/advisories/osv/lookup", methods=["POST"])
@api_routes.limiter.limit(
    api_routes._api_team_write_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_osv_advisory_lookup():
    session_id = ""
    owner_scope = None
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(
            owner_scope,
            Capability.TRIAGE_FINDINGS,
        )
        purl, version = _request_values(api_routes._json_body())

        result = query_external_osv(purl, version)

        def _record_audit(conn):
            record_event(
                AuditEventType.CVE_ADVISORY_REFRESH,
                target_id="osv",
                details={
                    "source": "osv",
                    "outcome": str(result.get("outcome") or "unknown"),
                    "record_count": int(result.get("record_count") or 0),
                    "origin": "external",
                },
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )

        run_transaction(_record_audit)
    except TeamPermissionDenied as exc:
        return _error("team_forbidden", str(exc), 403)
    except ValueError as exc:
        api_routes.log.warning(
            "API_OSV_ADVISORY_LOOKUP_REJECTED",
            extra={
                "ip": get_client_ip(),
                "session": get_log_session_id(session_id),
                "team_id": getattr(owner_scope, "team_id", ""),
                "source": "osv",
                "reason": "invalid_request",
            },
        )
        return _error("invalid_osv_lookup", str(exc), 400)

    return osv_lookup_response(result, session_id=session_id, owner_scope=owner_scope)
