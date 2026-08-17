# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Request adapters for bounded Project probe correlation."""

from typing import Any

from services.assessments.probe_log_context import ProbeLogContext


def route_probe_log_context(
    source: str, request: Any, session_id: str, team_id: str = "",
) -> ProbeLogContext:
    return ProbeLogContext(
        source, request.environ.get("darklab_request_id", ""), session_id, team_id,
    )


__all__ = ["route_probe_log_context"]
