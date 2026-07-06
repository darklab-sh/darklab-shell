"""Process-group signaling helpers for run termination."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from collections.abc import Callable
from typing import Any

from config import SCANNER_PREFIX

log = logging.getLogger("shell")


def process_group_is_gone(pgid: int, *, delays: tuple[float, ...]) -> bool:
    for delay in delays:
        if delay:
            time.sleep(delay)
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        except OSError:
            return False
    return False


def signal_process_group(
    pgid: int,
    *,
    scanner_prefix: list[str] | tuple[str, ...] | str | None = None,
    sudo_bin: str,
    kill_bin: str,
    gone_delays: tuple[float, ...],
    subprocess_run_fn: Callable[..., Any] = subprocess.run,
) -> None:
    configured_prefix = SCANNER_PREFIX if scanner_prefix is None else scanner_prefix
    log.debug(
        "RUN_PROCESS_GROUP_SIGNAL_ATTEMPT",
        extra={
            "pgid": pgid,
            "scanner_prefix_enabled": bool(configured_prefix),
            "sudo_bin": sudo_bin,
            "kill_bin": kill_bin,
        },
    )
    if configured_prefix:
        result = subprocess_run_fn(
            [sudo_bin, "-u", "scanner", kill_bin, "-TERM", "--", f"-{pgid}"],
            timeout=5,
        )
        if result.returncode != 0:
            gone = process_group_is_gone(pgid, delays=gone_delays)
            log.warning(
                "RUN_PROCESS_GROUP_SIGNAL_NONZERO",
                extra={"pgid": pgid, "returncode": result.returncode, "process_gone": gone},
            )
            if gone:
                return
            raise OSError(f"sudo kill exited with status {result.returncode}")
        return

    os.killpg(pgid, signal.SIGTERM)


def ensure_scanner_process_group_current(
    run_id: str,
    pid: int,
    session_id: str,
    team_id: str = "",
    *,
    scanner_prefix: list[str] | tuple[str, ...] | str | None = None,
    active_run_pid_start_matches_fn: Callable[..., bool],
) -> None:
    configured_prefix = SCANNER_PREFIX if scanner_prefix is None else scanner_prefix
    if not configured_prefix:
        return
    if active_run_pid_start_matches_fn(run_id, pid, session_id=session_id, team_id=team_id):
        return
    raise ProcessLookupError("active run PID start time no longer matches")
