# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed authorization outcomes shared by background archive workers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.database_access import get_db_connect
from services.teams.capabilities import Capability

from .background_authorization import BackgroundAuthorization, resolve_background_authorization
from .observability import _request_value


class ExportAuthorizationError(RuntimeError):
    """An archive cannot be delivered under the current authorization state."""


class ExportAuthorizationRejected(ExportAuthorizationError):
    def __init__(self, authorization: BackgroundAuthorization) -> None:
        super().__init__(authorization.message or "The export is no longer authorized.")
        self.reason = authorization.state.value


class ExportAuthorizationUnavailable(ExportAuthorizationError):
    def __init__(self, error_type: str) -> None:
        super().__init__("The export's access check is temporarily unavailable.")
        self.reason = "authorization_check_failed"
        self.error_type = _request_value(error_type, 80)


def require_export_authorization(job: Mapping[str, Any]) -> None:
    try:
        with get_db_connect()() as conn:
            authorization = resolve_background_authorization(
                conn,
                principal_id=str(job.get("principal_id") or ""),
                personal_workspace_id=str(job.get("personal_workspace_id") or ""),
                team_id=str(job.get("team_id") or ""),
                originating_credential_id=str(job.get("originating_credential_id") or ""),
                required_capability=Capability.MUTATE_PROJECTS,
            )
    except Exception as exc:
        raise ExportAuthorizationUnavailable(type(exc).__name__) from None
    if not authorization.allowed:
        raise ExportAuthorizationRejected(authorization)
