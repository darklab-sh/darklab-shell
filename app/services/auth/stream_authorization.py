# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Revalidate already-authenticated streams without retaining bearer secrets."""

from __future__ import annotations

import json
import logging
from time import monotonic
from collections.abc import Generator, Iterator
from datetime import datetime, timezone
from typing import Any

from flask import current_app

from core.database_access import get_db_connect
from core.helpers import get_authentication_result
from services.teams.capabilities import Capability

from .background_authorization import resolve_background_authorization
from .browser_sessions import revalidate_browser_session
from .contracts import STREAM_AUTH_CHECK_SECONDS
from .resolver import AnonymousContext, AuthenticatedContext

log = logging.getLogger("shell")

def _credential_rejection(conn: Any, context: AuthenticatedContext, now: datetime) -> str:
    row = conn.execute(
        "SELECT principal_id, credential_type, expires_at, revoked_at FROM credentials WHERE id = ?",
        (context.credential_id,),
    ).fetchone()
    if (
        row is None
        or row["principal_id"] != context.principal_id
        or row["credential_type"] != context.credential_type
    ):
        return "unknown_credential"
    if row["revoked_at"] is not None:
        return "revoked_credential"
    if row["expires_at"] is not None:
        expiry = datetime.fromisoformat(str(row["expires_at"]))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= now:
            return "expired_credential"
    if context.credential_type == "pat":
        scopes = {row["scope"] for row in conn.execute(
            "SELECT scope FROM credential_scopes WHERE credential_id = ?", (context.credential_id,),
        ).fetchall()}
        if not context.capabilities.issubset(scopes):
            return "insufficient_scope"
    return ""


def stream_rejection(
    conn: Any,
    context: AuthenticatedContext,
    *,
    team_id: str,
    idle_seconds: int,
    require_control: bool,
    now: datetime,
) -> str:
    """Check current session, credential, principal and Team state using only IDs."""
    if context.authentication_method == "browser_cookie":
        rejected = revalidate_browser_session(
            context.browser_session_id,
            principal_id=context.principal_id,
            credential_id=context.credential_id,
            oidc_identity_id=context.oidc_identity_id,
            idle_seconds=idle_seconds,
            now=now,
            conn=conn,
        )
    else:
        rejected = _credential_rejection(conn, context, now)
    if rejected:
        return rejected
    authority = resolve_background_authorization(
        conn,
        principal_id=context.principal_id,
        personal_workspace_id=context.personal_workspace_id,
        team_id=team_id,
        originating_credential_id=context.credential_id,
        required_capability=Capability.RUN_COMMANDS if require_control else None,
    )
    return "" if authority.allowed else authority.state.value


def authorized_stream(
    events: Iterator[str],
    *,
    run_id: str,
    team_id: str = "",
    terminate_pty: bool = False,
) -> Generator[str, None, None]:
    """Capture safe request identity now and check it throughout response iteration."""
    context = get_authentication_result().context
    connect = get_db_connect()
    idle_seconds = int(current_app.config.get("DARKLAB_CONFIG", {}).get("browser_session_idle_minutes", 30)) * 60

    def generate() -> Generator[str, None, None]:
        next_check = 0.0
        try:
            for item in events:
                rejected = ""
                now_monotonic = monotonic()
                if not isinstance(context, AnonymousContext) and now_monotonic >= next_check:
                    try:
                        if not isinstance(context, AuthenticatedContext):
                            rejected = "credential_required"
                        else:
                            with connect() as conn:
                                rejected = stream_rejection(
                                    conn, context, team_id=team_id, idle_seconds=idle_seconds,
                                    require_control=terminate_pty, now=datetime.now(timezone.utc),
                                )
                    except Exception:
                        log.error("AUTH_STREAM_CHECK_FAILED", exc_info=True, extra={"run_id": run_id})
                        rejected = "authorization_unavailable"
                    next_check = now_monotonic + STREAM_AUTH_CHECK_SECONDS
                if rejected:
                    log.info("AUTH_STREAM_CLOSED", extra={
                        "run_id": run_id, "team_id": team_id, "reason": rejected,
                        "principal_id": getattr(context, "principal_id", ""),
                        "credential_id": getattr(context, "credential_id", ""),
                        "interactive": terminate_pty,
                    })
                    if terminate_pty and isinstance(context, AuthenticatedContext):
                        from services.runs.cancellation import request_active_run_cancellation  # noqa: PLC0415

                        try:
                            request_active_run_cancellation(run_id, context.personal_workspace_id, team_id=team_id)
                        except Exception:
                            log.error("AUTH_STREAM_PTY_STOP_FAILED", exc_info=True, extra={"run_id": run_id})
                    yield "data: " + json.dumps({
                        "type": "error", "code": 1, "error_code": rejected,
                        "text": "Access to this stream ended. Sign in again to continue.",
                    }) + "\n\n"
                    return
                yield item
        finally:
            close = getattr(events, "close", None)
            if close is not None:
                close()

    return generate()
