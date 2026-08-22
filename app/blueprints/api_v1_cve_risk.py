# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 reads for configured CVE risk feed status."""

from __future__ import annotations

from flask import jsonify

from blueprints import api_v1 as api_routes
from services.cve_risk.store import get_configured_feed_status


@api_routes.api_v1_bp.route("/risk/feeds")
@api_routes.require_api_auth
def api_cve_risk_feeds():
    feeds = get_configured_feed_status()
    return jsonify({"feeds": feeds, "total": len(feeds)})


__all__ = ["api_cve_risk_feeds"]
