# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Final cleanup for brokered external-command workers."""

import logging
from collections.abc import Callable
from typing import Any

from core.helpers import get_log_session_id


log = logging.getLogger("shell")


def cleanup_broker_worker(
    proc: Any,
    run_id: str,
    session_id: str,
    team_id: str,
    client_ip: str,
    cleanup_proc_stream: Callable[..., Any],
    pid_pop: Callable[[str], Any],
    active_run_remove: Callable[[str], Any],
    private_material_cleanup: Callable[[], None] | None,
) -> None:
    cleanup_proc_stream(proc)
    pid_pop(run_id)
    active_run_remove(run_id)
    if not private_material_cleanup:
        return
    try:
        private_material_cleanup()
    except Exception:
        log.error("RUN_PRIVATE_MATERIAL_CLEANUP_FAILED", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "ip": client_ip,
        })
