# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Resolve the persisted initiator for a workflow or fan-out process launch."""

from collections.abc import Mapping

from core.database_access import get_db_connect
from services.auth.background_authorization import BackgroundAuthorization, resolve_background_authorization
from services.runs.contracts import RunStartRejected
from services.teams.capabilities import Capability
from services.teams.scope import OwnerContext


def resolve_execution_owner(execution: Mapping[str, object]) -> BackgroundAuthorization:
    with get_db_connect()() as conn:
        return resolve_background_authorization(
            conn,
            principal_id=str(execution.get("principal_id") or ""),
            personal_workspace_id=str(execution.get("personal_workspace_id") or ""),
            team_id=str(execution.get("team_id") or ""),
            actor_member_id=str(execution.get("actor_member_id") or ""),
            originating_credential_id=str(execution.get("originating_credential_id") or ""),
            required_capability=Capability.RUN_COMMANDS,
        )


def execution_owner_context(execution: Mapping[str, object]) -> OwnerContext:
    authorization = resolve_execution_owner(execution)
    if not authorization.allowed or authorization.owner_context is None:
        raise RunStartRejected(authorization.state.value, authorization.message, status_code=403)
    return authorization.owner_context
