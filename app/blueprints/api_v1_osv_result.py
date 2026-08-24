# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Public response mapping for explicit external OSV lookups."""

from __future__ import annotations

from core.helpers import get_client_ip, get_log_session_id
from flask import jsonify

from blueprints import api_v1 as api_routes


def osv_lookup_response(result: dict, *, session_id: str, owner_scope):
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
        return api_routes._api_json_error(
            "osv_lookup_disabled",
            "External OSV package lookups are disabled.",
            409,
        )
    if outcome == "failed":
        api_routes.log.error("API_OSV_ADVISORY_LOOKUP_FAILED", extra=fields)
        return api_routes._api_json_error(
            "osv_lookup_failed",
            "The external OSV package lookup failed.",
            503,
        )
    if outcome == "busy":
        api_routes.log.warning(
            "API_OSV_ADVISORY_LOOKUP_REJECTED",
            extra={
                **fields,
                "reason": str(result.get("reason") or "provider_busy"),
            },
        )
        return api_routes._api_json_error(
            "osv_lookup_busy",
            "External OSV lookups are temporarily busy. Try again shortly.",
            429,
        )
    if outcome not in {"stored", "positive_cached", "negative_cached"}:
        api_routes.log.error("API_OSV_ADVISORY_LOOKUP_FAILED", extra=fields)
        return api_routes._api_json_error(
            "osv_lookup_failed",
            "The external OSV package lookup returned an invalid result.",
            503,
        )
    api_routes.log.info("API_OSV_ADVISORY_LOOKUP_COMPLETED", extra=fields)
    return jsonify(
        {
            "ok": True,
            "source": "osv",
            "outcome": outcome,
            "record_count": fields["record_count"],
        }
    )


__all__ = ["osv_lookup_response"]
