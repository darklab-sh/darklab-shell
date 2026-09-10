# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Best-effort runtime enforcement for principal state changes."""

from __future__ import annotations

import logging

from core.process import active_runs_for_principal
from services.runs.cancellation import request_active_run_cancellation


log = logging.getLogger("shell")


def stop_principal_active_work(principal_id: str) -> tuple[str, ...]:
    """Terminate tracked command and PTY processes owned by a principal."""
    stopped: list[str] = []
    for active in active_runs_for_principal(principal_id):
        run_id = str(active.get("run_id") or "")
        try:
            if request_active_run_cancellation(
                run_id,
                str(active.get("session_id") or ""),
                team_id=str(active.get("team_id") or ""),
            ):
                stopped.append(run_id)
        except Exception:
            log.error(
                "PRINCIPAL_ACTIVE_WORK_STOP_FAILED",
                exc_info=True,
                extra={"principal_id": principal_id, "run_id": run_id},
            )
    from services.projects.package_jobs import (  # noqa: PLC0415
        stop_evidence_package_archive_jobs_for_principal,
    )
    from services.reports.jobs import stop_report_export_jobs_for_principal  # noqa: PLC0415

    package_jobs = stop_evidence_package_archive_jobs_for_principal(principal_id)
    report_jobs = stop_report_export_jobs_for_principal(principal_id)
    log.info(
        "PRINCIPAL_ACTIVE_WORK_STOPPED",
        extra={
            "principal_id": principal_id,
            "run_count": len(stopped),
            "package_job_count": len(package_jobs),
            "report_job_count": len(report_jobs),
        },
    )
    return tuple(stopped)


__all__ = ["stop_principal_active_work"]
