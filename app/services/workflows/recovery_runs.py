# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Surface-neutral active-run lookup used by durable recovery owners."""

from __future__ import annotations

from collections.abc import Mapping


def run_is_still_active(execution: Mapping[str, object], run_id: str) -> bool:
    """Return whether the execution owner still has live process metadata."""
    from core.process import pid_for_session, pid_for_team  # noqa: PLC0415

    team_id = str(execution.get("team_id") or "")
    if team_id:
        return pid_for_team(run_id, team_id) is not None
    return pid_for_session(
        run_id,
        str(execution.get("session_id") or ""),
    ) is not None


__all__ = ["run_is_still_active"]
