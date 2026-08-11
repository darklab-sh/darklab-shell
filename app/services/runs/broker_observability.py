# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded logging for Assessment launch broker rejections."""

from __future__ import annotations

import logging

from core.helpers import get_log_session_id

_BROKER_DISABLED = "Run broker is disabled by configuration."
_BROKER_REDIS_UNAVAILABLE = "Run broker requires Redis, but Redis is not available."


def _reason_code(reason: object) -> str:
    normalized = str(reason or "").strip()
    if normalized == _BROKER_DISABLED:
        return "configuration_disabled"
    if normalized == _BROKER_REDIS_UNAVAILABLE:
        return "redis_unavailable"
    return "dependency_unavailable"


def log_assessment_broker_unavailable(
    logger: logging.Logger,
    *,
    request_id: object,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str = "",
    check_id: str = "",
    finding_id: str = "",
    action_kind: str,
    source: str,
    reason: object,
    broker_mode: object,
) -> None:
    """Emit one safe INFO/WARNING for an Assessment launch rejection."""
    reason_code = _reason_code(reason)
    extra = {
        "request_id": str(request_id or "")[:128],
        "session": get_log_session_id(session_id),
        "owner_kind": "team" if team_id else "personal",
        "team_id": team_id,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "check_id": check_id,
        "finding_id": finding_id,
        "action_kind": action_kind,
        "source": source,
        "reason": reason_code,
        "broker_mode": str(broker_mode or "unknown")
        if str(broker_mode or "") in {"redis", "in_process"}
        else "unknown",
    }
    log_method = logger.info if reason_code == "configuration_disabled" else logger.warning
    log_method("PROJECT_ASSESSMENT_BROKER_UNAVAILABLE", extra=extra)


__all__ = ["log_assessment_broker_unavailable"]
