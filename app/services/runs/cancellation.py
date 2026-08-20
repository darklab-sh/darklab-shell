# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Surface-neutral cancellation request for one active ordinary run."""

from __future__ import annotations

import shutil

from config import SCANNER_PREFIX
from core.process import active_run_pid_start_matches, pid_for_session, pid_for_team
from services.runs.broker import publish_run_event
from services.runs.process_control import (
    ensure_scanner_process_group_current,
    signal_process_group,
)


_SUDO_BIN = shutil.which("sudo") or "/usr/bin/sudo"
_KILL_BIN = shutil.which("kill") or "/bin/kill"
_GONE_DELAYS = (0.0, 0.05, 0.15, 0.3, 0.5)


def request_active_run_cancellation(
    run_id: str,
    session_id: str,
    *,
    team_id: str = "",
) -> bool:
    """Signal a scoped active run and return whether a process was found."""
    normalized_team_id = str(team_id or "")
    pid = (
        pid_for_team(run_id, normalized_team_id)
        if normalized_team_id
        else pid_for_session(run_id, session_id)
    )
    if not pid:
        return False
    ensure_scanner_process_group_current(
        run_id,
        pid,
        session_id,
        team_id=normalized_team_id,
        scanner_prefix=SCANNER_PREFIX,
        active_run_pid_start_matches_fn=active_run_pid_start_matches,
    )
    signal_process_group(
        pid,
        scanner_prefix=SCANNER_PREFIX,
        sudo_bin=_SUDO_BIN,
        kill_bin=_KILL_BIN,
        gone_delays=_GONE_DELAYS,
    )
    publish_run_event(run_id, "killed", {"coordinator": "assessment_batch"})
    return True


__all__ = ["request_active_run_cancellation"]
