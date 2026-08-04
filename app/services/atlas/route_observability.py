# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Privacy-safe observability wrapper for exact Atlas lookup routes."""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable

from flask import make_response, request

from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.api_v1.auth import ApiAuthError, current_api_session
from services.atlas.lookup_resolve import (
    AtlasLookupError,
    resolve_entity_lookup,
    resolve_entity_lookup_for_owner,
)
from services.projects.contracts import ProjectWorkspaceError
from services.teams.request_scope import requested_team_id


__all__ = (
    "AtlasLookupError",
    "ProjectWorkspaceError",
    "resolve_entity_lookup",
    "resolve_entity_lookup_for_owner",
    "route",
)

log = logging.getLogger("shell")


def _lookup_session_id(surface: str) -> str:
    if surface == "api_v1":
        return current_api_session().token
    return get_session_id()


def _request_id() -> str:
    return str(request.environ.get("darklab_request_id") or "")[:128]


def _response_error_code(response: Any) -> str:
    payload = response.get_json(silent=True)
    if not isinstance(payload, dict):
        return "lookup_rejected"
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("code") or "lookup_rejected")[:120]
    return str(error or "lookup_rejected")[:120]


def _log_rejected_lookup(
    *,
    reason: str,
    surface: str,
    started: float,
    http_status: int,
    project_rejected: bool = False,
) -> None:
    try:
        session_id = _lookup_session_id(surface)
    except RuntimeError:
        session_id = ""
    team_id = requested_team_id(request)
    payload = request.get_json(silent=True)
    project_id = str(payload.get("project_id") or "")[:160] if isinstance(payload, dict) else ""
    extra: dict[str, object] = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "request_id": _request_id(),
        "team_id": team_id,
        "surface": surface,
        "reason": str(reason or "lookup_rejected")[:120],
        "scope_kind": "team" if team_id else "personal",
        "project_scoped": bool(project_id),
        "http_status": int(http_status),
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
    if project_rejected and project_id:
        extra["project_id"] = project_id
    if project_rejected:
        log.warning("ATLAS_LOOKUP_REJECTED", extra=extra)
    else:
        log.debug("ATLAS_LOOKUP_REJECTED", extra=extra)


def _log_completed_lookup(response: Any, *, event: str, surface: str, started: float) -> None:
    if getattr(response, "status_code", 0) != 200:
        return
    result = response.get_json(silent=True)
    if not isinstance(result, dict) or not result.get("match_state"):
        return
    session_id = _lookup_session_id(surface)
    team_id = requested_team_id(request)
    log.info(event, extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "request_id": _request_id(),
        "team_id": team_id,
        "surface": surface,
        "requested_type": str(result.get("requested_type") or ""),
        "detected_type": str(result.get("detected_type") or ""),
        "match_state": str(result.get("match_state") or ""),
        "scope_kind": "team" if team_id else "personal",
        "project_scoped": bool(result.get("project_id")),
        "candidate_count": len(result.get("candidates") or []),
        "candidates_truncated": bool(result.get("candidates_truncated")),
        "parent_candidate": bool(result.get("parent_host_candidate")),
        "detail_loaded": isinstance(result.get("detail"), dict),
        "duration_ms": int((time.perf_counter() - started) * 1000),
    })


def route(blueprint, *, event: str, surface: str) -> Callable:
    """Register and observe a read-only JSON-body Atlas lookup route."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def observed(*args: Any, **kwargs: Any):
            started = time.perf_counter()
            try:
                response = func(*args, **kwargs)
            except ApiAuthError as exc:
                if exc.status_code == 400 and exc.code == "invalid_body":
                    _log_rejected_lookup(
                        reason=exc.code,
                        surface=surface,
                        started=started,
                        http_status=exc.status_code,
                    )
                raise
            response = make_response(response)
            if response.status_code == 400:
                reason = _response_error_code(response)
                _log_rejected_lookup(
                    reason=reason,
                    surface=surface,
                    started=started,
                    http_status=response.status_code,
                    project_rejected=reason == "invalid_project",
                )
            _log_completed_lookup(response, event=event, surface=surface, started=started)
            return response

        return blueprint.route("/atlas/lookup", methods=["POST"])(observed)

    return decorator
