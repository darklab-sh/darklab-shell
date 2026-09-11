# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Request-independent authorization for durable and background work."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from services.auth.contracts import InvalidIdentityValue, validate_anonymous_uuid
from services.teams.capabilities import Capability, role_can
from services.teams.scope import OwnerContext, anonymous_owner_context, team_owner_context
from services.teams.storage import get_team_membership


class BackgroundAuthorizationState(str, Enum):
    AUTHORIZED = "authorized"
    PRINCIPAL_MISSING = "principal_missing"
    PRINCIPAL_DISABLED = "principal_disabled"
    WORKSPACE_MISMATCH = "workspace_mismatch"
    TEAM_UNAVAILABLE = "team_unavailable"
    MEMBERSHIP_REVOKED = "membership_revoked"
    CAPABILITY_REVOKED = "capability_revoked"


@dataclass(frozen=True)
class BackgroundAuthorization:
    state: BackgroundAuthorizationState
    principal_id: str = ""
    personal_workspace_id: str = ""
    team_id: str = ""
    member_id: str = ""
    role: str = ""
    originating_credential_id: str = ""
    owner_context: OwnerContext | None = None
    message: str = ""

    @property
    def allowed(self) -> bool:
        return self.state == BackgroundAuthorizationState.AUTHORIZED


@dataclass(frozen=True)
class DurableWorkItem:
    kind: str
    id: str
    label: str
    state: str
    attribution: str
    pausable: bool

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "label": self.label,
            "state": self.state,
            "attribution": self.attribution,
            "pausable": self.pausable,
        }


@dataclass(frozen=True)
class DurableWorkDisposition:
    affected: tuple[DurableWorkItem, ...]
    paused: tuple[DurableWorkItem, ...] = ()

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "affected": [item.to_safe_dict() for item in self.affected],
            "paused": [item.to_safe_dict() for item in self.paused],
            "affected_count": len(self.affected),
            "paused_count": len(self.paused),
        }


def _denied(
    state: BackgroundAuthorizationState,
    *,
    principal_id: str,
    personal_workspace_id: str,
    team_id: str,
    originating_credential_id: str,
    message: str,
    member_id: str = "",
    role: str = "",
) -> BackgroundAuthorization:
    return BackgroundAuthorization(
        state=state,
        principal_id=principal_id,
        personal_workspace_id=personal_workspace_id,
        team_id=team_id,
        member_id=member_id,
        role=role,
        originating_credential_id=originating_credential_id,
        message=message,
    )


def principal_id_for_workspace(conn: Any, personal_workspace_id: str) -> str:
    """Resolve a persisted workspace owner without using request state."""
    workspace_id = str(personal_workspace_id or "").strip()
    if not workspace_id:
        return ""
    row = conn.execute(
        "SELECT principal_id FROM personal_workspaces WHERE id = ?",
        (workspace_id,),
    ).fetchone()
    return str(row["principal_id"] or "") if row else ""


def _anonymous_authorization(
    conn: Any,
    *,
    anonymous_id: str,
    team_id: str,
) -> BackgroundAuthorization:
    if team_id:
        team = conn.execute(
            "SELECT status FROM teams WHERE id = ? AND deleted_at = ''",
            (team_id,),
        ).fetchone()
        if team is None or str(team["status"] or "") != "active":
            return _denied(
                BackgroundAuthorizationState.TEAM_UNAVAILABLE,
                principal_id="",
                personal_workspace_id=anonymous_id,
                team_id=team_id,
                originating_credential_id="",
                message="The durable work team is no longer active.",
            )
        return _denied(
            BackgroundAuthorizationState.MEMBERSHIP_REVOKED,
            principal_id="",
            personal_workspace_id=anonymous_id,
            team_id=team_id,
            originating_credential_id="",
            message="Anonymous work cannot use team scope.",
        )
    return BackgroundAuthorization(
        state=BackgroundAuthorizationState.AUTHORIZED,
        personal_workspace_id=anonymous_id,
        owner_context=anonymous_owner_context(anonymous_id),
    )


def resolve_background_authorization(
    conn: Any,
    *,
    principal_id: str,
    personal_workspace_id: str,
    team_id: str = "",
    required_capability: Capability | str | None = None,
    originating_credential_id: str = "",
    actor_member_id: str = "",
) -> BackgroundAuthorization:
    """Resolve current authority from durable ids, never from a credential secret."""
    principal = str(principal_id or "").strip()
    workspace_id = str(personal_workspace_id or "").strip()
    selected_team = str(team_id or "").strip()
    credential_id = str(originating_credential_id or "").strip()
    # The historical member id is attribution only. Current authorization is
    # always resolved from the principal, so removing and later re-adding a
    # member doesn't revive stale authority.
    del actor_member_id

    if not principal:
        try:
            anonymous_id = validate_anonymous_uuid(workspace_id)
        except InvalidIdentityValue:
            anonymous_id = ""
        if anonymous_id:
            return _anonymous_authorization(
                conn,
                anonymous_id=anonymous_id,
                team_id=selected_team,
            )
        principal = principal_id_for_workspace(conn, workspace_id)

    if not principal:
        return _denied(
            BackgroundAuthorizationState.PRINCIPAL_MISSING,
            principal_id="",
            personal_workspace_id=workspace_id,
            team_id=selected_team,
            originating_credential_id=credential_id,
            message="The durable work owner has no principal.",
        )

    row = conn.execute(
        "SELECT p.status, w.id AS personal_workspace_id, w.storage_key "
        "FROM principals p JOIN personal_workspaces w ON w.principal_id = p.id "
        "WHERE p.id = ?",
        (principal,),
    ).fetchone()
    if row is None:
        return _denied(
            BackgroundAuthorizationState.PRINCIPAL_MISSING,
            principal_id=principal,
            personal_workspace_id=workspace_id,
            team_id=selected_team,
            originating_credential_id=credential_id,
            message="The durable work principal no longer exists.",
        )
    if str(row["status"] or "") != "active":
        return _denied(
            BackgroundAuthorizationState.PRINCIPAL_DISABLED,
            principal_id=principal,
            personal_workspace_id=workspace_id,
            team_id=selected_team,
            originating_credential_id=credential_id,
            message="The durable work principal is disabled.",
        )
    authoritative_workspace = str(row["personal_workspace_id"] or "")
    if workspace_id != authoritative_workspace:
        return _denied(
            BackgroundAuthorizationState.WORKSPACE_MISMATCH,
            principal_id=principal,
            personal_workspace_id=workspace_id,
            team_id=selected_team,
            originating_credential_id=credential_id,
            message="The durable work workspace does not belong to its principal.",
        )

    if not selected_team:
        return BackgroundAuthorization(
            state=BackgroundAuthorizationState.AUTHORIZED,
            principal_id=principal,
            personal_workspace_id=workspace_id,
            originating_credential_id=credential_id,
            owner_context=OwnerContext(
                scope="personal",
                owner_id=workspace_id,
                workspace_storage_key=str(row["storage_key"] or ""),
                actor_principal_id=principal,
                actor_credential_id=credential_id,
            ),
        )

    membership = get_team_membership(conn, selected_team, principal)
    if not membership:
        team = conn.execute(
            "SELECT status FROM teams WHERE id = ? AND deleted_at = ''",
            (selected_team,),
        ).fetchone()
        state = (
            BackgroundAuthorizationState.MEMBERSHIP_REVOKED
            if team is not None and str(team["status"] or "") == "active"
            else BackgroundAuthorizationState.TEAM_UNAVAILABLE
        )
        return _denied(
            state,
            principal_id=principal,
            personal_workspace_id=workspace_id,
            team_id=selected_team,
            originating_credential_id=credential_id,
            message=(
                "The durable work principal is no longer an active team member."
                if state == BackgroundAuthorizationState.MEMBERSHIP_REVOKED
                else "The durable work team is no longer active."
            ),
        )
    if str(membership.get("team_status") or "") != "active":
        return _denied(
            BackgroundAuthorizationState.TEAM_UNAVAILABLE,
            principal_id=principal,
            personal_workspace_id=workspace_id,
            team_id=selected_team,
            originating_credential_id=credential_id,
            message="The durable work team is no longer active.",
            member_id=str(membership.get("id") or ""),
            role=str(membership.get("role") or ""),
        )
    role = str(membership.get("role") or "")
    if required_capability is not None and not role_can(role, required_capability):
        return _denied(
            BackgroundAuthorizationState.CAPABILITY_REVOKED,
            principal_id=principal,
            personal_workspace_id=workspace_id,
            team_id=selected_team,
            originating_credential_id=credential_id,
            message="The current team role no longer permits this work.",
            member_id=str(membership.get("id") or ""),
            role=role,
        )
    member_id = str(membership.get("id") or "")
    return BackgroundAuthorization(
        state=BackgroundAuthorizationState.AUTHORIZED,
        principal_id=principal,
        personal_workspace_id=workspace_id,
        team_id=selected_team,
        member_id=member_id,
        role=role,
        originating_credential_id=credential_id,
        owner_context=team_owner_context(
            selected_team,
            actor_member_id=member_id,
            actor_principal_id=principal,
            actor_credential_id=credential_id,
        ),
    )


_DURABLE_WORK_QUERIES = (
    ("schedule", "schedules", "id", "label", "CASE WHEN enabled THEN 'enabled' ELSE 'paused' END", True),
    ("watcher", "watchers", "id", "label", "state", True),
    ("workflow", "user_workflows", "id", "title", "'saved'", False),
    (
        "notification_channel",
        "notification_channels",
        "id",
        "label",
        "CASE WHEN muted THEN 'muted' ELSE 'active' END",
        True,
    ),
    (
        "project_digest",
        "project_digest_settings",
        "project_id",
        "project_id",
        "CASE WHEN enabled THEN 'enabled' ELSE 'paused' END",
        True,
    ),
)


def durable_work_for_credential(conn: Any, principal_id: str, credential_id: str) -> tuple[DurableWorkItem, ...]:
    """Enumerate durable definitions attributed to a credential id."""
    items: list[DurableWorkItem] = []
    for kind, table, id_column, label_column, state_sql, pausable in _DURABLE_WORK_QUERIES:
        rows = conn.execute(
            f"SELECT {id_column} AS id, {label_column} AS label, {state_sql} AS state, "  # nosec
            "created_by_credential_id, last_changed_by_credential_id "
            f"FROM {table} WHERE principal_id = ? AND "  # nosec
            "(created_by_credential_id = ? OR last_changed_by_credential_id = ?) "
            "ORDER BY id",
            (principal_id, credential_id, credential_id),
        ).fetchall()
        for row in rows:
            attribution = (
                "last_changed"
                if str(row["last_changed_by_credential_id"] or "") == credential_id
                else "created"
            )
            items.append(DurableWorkItem(
                kind=kind,
                id=str(row["id"]),
                label=str(row["label"] or ""),
                state=str(row["state"] or ""),
                attribution=attribution,
                pausable=pausable,
            ))
    return tuple(items)


def pause_durable_work_for_credential(
    conn: Any,
    principal_id: str,
    credential_id: str,
) -> DurableWorkDisposition:
    """Pause future-capable definitions linked to a revoked credential."""
    affected = durable_work_for_credential(conn, principal_id, credential_id)
    match = "principal_id = ? AND (created_by_credential_id = ? OR last_changed_by_credential_id = ?)"
    params = (principal_id, credential_id, credential_id)
    conn.execute(
        f"UPDATE schedules SET enabled = FALSE, paused_reason = 'credential_revoked' WHERE {match}",  # nosec
        params,
    )
    conn.execute(
        f"UPDATE watchers SET state = 'paused', state_reason = 'credential_revoked' WHERE {match}",  # nosec
        params,
    )
    conn.execute(
        f"UPDATE notification_channels SET muted = TRUE WHERE {match}",  # nosec
        params,
    )
    conn.execute(
        f"UPDATE project_digest_settings SET enabled = FALSE WHERE {match}",  # nosec
        params,
    )
    return DurableWorkDisposition(
        affected=affected,
        paused=tuple(item for item in affected if item.pausable),
    )


def suspend_principal_background_work(conn: Any, principal_id: str, *, now: str) -> None:
    """Apply the persistent half of the principal-disable global stop."""
    conn.execute(
        "UPDATE schedules SET enabled = FALSE, paused_reason = 'principal_disabled', updated = ? "
        "WHERE principal_id = ?",
        (now, principal_id),
    )
    conn.execute(
        "UPDATE watchers SET state = 'paused', state_reason = 'principal_disabled', updated = ? "
        "WHERE principal_id = ?",
        (now, principal_id),
    )
    conn.execute(
        "UPDATE notification_channels SET muted = TRUE, updated = ? WHERE principal_id = ?",
        (now, principal_id),
    )
    conn.execute(
        "UPDATE project_digest_settings SET enabled = FALSE, updated = ? WHERE principal_id = ?",
        (now, principal_id),
    )
    conn.execute(
        "UPDATE workflow_executions SET status = CASE WHEN status = 'queued' THEN 'failed' ELSE 'canceling' END, "
        "failure_code = 'principal_disabled', failure_detail = 'The principal was disabled.', updated = ?, "
        "finished = CASE WHEN status = 'queued' THEN ? ELSE finished END "
        "WHERE principal_id = ? AND status IN ('queued', 'running', 'canceling')",
        (now, now, principal_id),
    )
    conn.execute(
        "UPDATE notification_events SET status = 'dead', next_attempt_at = '', "
        "last_error = 'principal disabled', dead_at = ? "
        "WHERE principal_id = ? AND status IN ('pending', 'retry_wait')",
        (now, principal_id),
    )
    conn.execute(
        "UPDATE ai_run_assists SET status = 'failed', error_code = 'principal_disabled', "
        "error_message = 'The principal was disabled.', updated_at = ? "
        "WHERE principal_id = ? AND status IN ('queued', 'in_progress')",
        (now, principal_id),
    )
    conn.execute(
        "UPDATE zap_connector_jobs SET status = 'failed', error_code = 'principal_disabled', "
        "error_detail = 'The principal was disabled.', updated_at = ?, finished_at = ? "
        "WHERE principal_id = ? AND status IN ('queued', 'submitting', 'running', 'cancel_requested', 'downloading')",
        (now, now, principal_id),
    )
    conn.execute(
        "UPDATE oast_correlations SET status = 'failed', error_code = 'principal_disabled', "
        "error_detail = 'The principal was disabled.', updated_at = ?, closed_at = ? "
        "WHERE principal_id = ? AND status IN ('reserved', 'active')",
        (now, now, principal_id),
    )


__all__ = [
    "BackgroundAuthorization",
    "BackgroundAuthorizationState",
    "DurableWorkDisposition",
    "DurableWorkItem",
    "durable_work_for_credential",
    "pause_durable_work_for_credential",
    "principal_id_for_workspace",
    "resolve_background_authorization",
    "suspend_principal_background_work",
]
