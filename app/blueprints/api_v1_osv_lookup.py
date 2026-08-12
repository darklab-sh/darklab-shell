# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 action for one explicit external OSV package lookup."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.cve_risk.osv_external import query_external_osv
from services.storage.transactions import run_transaction
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


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

        def _lookup(conn):
            result = query_external_osv(conn, purl, version)
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
            return result

        result = run_transaction(_lookup)
    except TeamPermissionDenied as exc:
        return _error("team_forbidden", str(exc), 403)
    except ValueError as exc:
        api_routes.log.warning("API_OSV_ADVISORY_LOOKUP_REJECTED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": getattr(owner_scope, "team_id", ""),
            "source": "osv",
            "reason": "invalid_request",
        })
        return _error("invalid_osv_lookup", str(exc), 400)

    outcome = str(result.get("outcome") or "unknown")
    fields = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": owner_scope.team_id,
        "source": "osv",
        "outcome": outcome,
        "record_count": int(result.get("record_count") or 0),
    }
    if outcome == "disabled":
        api_routes.log.warning("API_OSV_ADVISORY_LOOKUP_REJECTED", extra=fields)
        return _error(
            "osv_lookup_disabled",
            "External OSV package lookups are disabled.",
            409,
        )
    if outcome == "failed":
        api_routes.log.error("API_OSV_ADVISORY_LOOKUP_FAILED", extra=fields)
        return _error(
            "osv_lookup_failed",
            "The external OSV package lookup failed.",
            503,
        )
    if outcome not in {"stored", "positive_cached", "negative_cached"}:
        api_routes.log.error("API_OSV_ADVISORY_LOOKUP_FAILED", extra=fields)
        return _error(
            "osv_lookup_failed",
            "The external OSV package lookup returned an invalid result.",
            503,
        )
    api_routes.log.info("API_OSV_ADVISORY_LOOKUP_COMPLETED", extra=fields)
    return jsonify({
        "ok": True,
        "source": "osv",
        "outcome": outcome,
        "record_count": fields["record_count"],
    })
