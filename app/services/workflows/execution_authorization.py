# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared authorization and runtime checks for durable execution owners."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from config import resolve_effective_cfg
from services.auth.background_authorization import BackgroundAuthorizationState
from services.workflows.execution_owner import resolve_execution_owner


def max_execution_runtime_seconds() -> int:
    return max(
        1,
        int(
            resolve_effective_cfg().get("workflow_execution_max_runtime_seconds")
            or 14_400
        ),
    )


def execution_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or ""))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def execution_expired(
    execution: Mapping[str, object], *, now: datetime | None = None, max_runtime_seconds: int | None = None
) -> bool:
    created = execution_timestamp(execution.get("created"))
    if created is None:
        return True
    current = now or datetime.now(timezone.utc)
    runtime_limit = max_execution_runtime_seconds() if max_runtime_seconds is None else max(1, int(max_runtime_seconds))
    return (current - created).total_seconds() >= runtime_limit


def execution_elapsed_seconds(
    execution: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> float:
    created = execution_timestamp(execution.get("created"))
    if created is None:
        return 0.0
    finished = (
        execution_timestamp(execution.get("finished"))
        or now
        or datetime.now(timezone.utc)
    )
    return max(0.0, (finished - created).total_seconds())


def current_execution_role(
    execution: Mapping[str, object],
) -> tuple[str, str, str]:
    """Return one stable failure or the initiator's current command role."""
    authorization = resolve_execution_owner(execution)
    if authorization.state is BackgroundAuthorizationState.PRINCIPAL_DISABLED:
        return "principal_disabled", authorization.message, ""
    if authorization.state is BackgroundAuthorizationState.TEAM_UNAVAILABLE:
        return "team_unavailable", "The execution team is no longer active.", ""
    if authorization.state is BackgroundAuthorizationState.MEMBERSHIP_REVOKED:
        return "member_revoked", "The execution initiator is no longer active.", ""
    if authorization.state is BackgroundAuthorizationState.CAPABILITY_REVOKED:
        return "permission_revoked", "The initiator can no longer run commands.", authorization.role
    if not authorization.allowed:
        return "owner_unavailable", authorization.message, ""
    return "", "", authorization.role


__all__ = [
    "current_execution_role",
    "execution_elapsed_seconds",
    "execution_expired",
    "execution_timestamp",
    "max_execution_runtime_seconds",
]
