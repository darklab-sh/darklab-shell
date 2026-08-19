# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Operator-controlled orchestration for managed Nuclei template refreshes."""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
import os
import subprocess
import sys
from typing import Any

from config import SCANNER_PREFIX
from services.nuclei.template_cache import clear_nuclei_template_snapshot_cache
from services.nuclei.template_health import clear_nuclei_template_health_cache
from services.nuclei.template_lock import (
    NucleiTemplateLockBusy,
    NucleiTemplateLockError,
    managed_nuclei_template_lock,
)
from services.nuclei.template_refresh_worker import (
    UPDATE_TIMEOUT_SECONDS,
)


log = logging.getLogger("shell")
REFRESH_PROCESS_TIMEOUT_SECONDS = UPDATE_TIMEOUT_SECONDS + 120
MAX_WORKER_RESPONSE_BYTES = 4096


class NucleiTemplateRefreshError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def managed_nuclei_template_refresh_enabled() -> bool:
    configured = os.environ.get("NUCLEI_TEMPLATE_REFRESH_ENABLED")
    if configured is None:
        configured = os.environ.get("NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED", "true")
    return configured.strip().lower() in {"1", "true", "yes", "on"}


def refresh_operator_action() -> str:
    if managed_nuclei_template_refresh_enabled():
        return "Ask an operator with Run commands access to update the managed templates."
    return (
        "Ask a deployment operator to enable NUCLEI_TEMPLATE_REFRESH_ENABLED or "
        "replace the managed template cache outside the app."
    )


def refresh_managed_nuclei_templates(
    *,
    active_batch_exists: Callable[[], bool],
    run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    if not managed_nuclei_template_refresh_enabled():
        raise NucleiTemplateRefreshError(
            "nuclei_template_refresh_disabled",
            "Managed Nuclei template refresh is disabled for this deployment.",
        )
    prefix = [SCANNER_PREFIX] if isinstance(SCANNER_PREFIX, str) else list(SCANNER_PREFIX)
    command = [*prefix, sys.executable, "-m", "services.nuclei.template_refresh_worker"]
    try:
        with managed_nuclei_template_lock(exclusive=True, blocking=False):
            if active_batch_exists():
                raise NucleiTemplateRefreshError(
                    "nuclei_template_refresh_batch_active",
                    "Managed templates can't be updated while a Nuclei assessment batch is active.",
                )
            completed = run_command(
                command,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=REFRESH_PROCESS_TIMEOUT_SECONDS,
            )
    except NucleiTemplateLockBusy as exc:
        raise NucleiTemplateRefreshError(
            "nuclei_template_refresh_in_progress",
            "Another managed Nuclei template refresh is already in progress.",
        ) from exc
    except NucleiTemplateLockError as exc:
        raise NucleiTemplateRefreshError(
            "nuclei_template_lock_unavailable",
            "The managed Nuclei template lock is unavailable.",
            status_code=503,
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("NUCLEI_TEMPLATE_REFRESH_FAILED", extra={"reason_code": "worker_unavailable"})
        raise NucleiTemplateRefreshError(
            "nuclei_template_refresh_failed",
            "The managed template refresh failed; the previous cache was kept.",
            status_code=503,
        ) from exc
    output = completed.stdout or ""
    if len(output.encode("utf-8", errors="replace")) > MAX_WORKER_RESPONSE_BYTES:
        result: object = None
    else:
        try:
            result = json.loads(output)
        except json.JSONDecodeError:
            result = None
    if completed.returncode != 0 or not isinstance(result, dict) or result.get("status") != "updated":
        reason_code = (
            str(result.get("reason_code") or "template_refresh_failed")
            if isinstance(result, dict)
            else "template_refresh_failed"
        )
        log.warning("NUCLEI_TEMPLATE_REFRESH_FAILED", extra={"reason_code": reason_code})
        raise NucleiTemplateRefreshError(
            "nuclei_template_refresh_failed",
            "The managed template refresh failed; the previous cache was kept. "
            "Check outbound access and try again.",
            status_code=503,
        )
    clear_nuclei_template_snapshot_cache()
    clear_nuclei_template_health_cache()
    log.info("NUCLEI_TEMPLATE_REFRESH_SUCCEEDED", extra={
        "release_version": str(result.get("release_version") or ""),
    })
    return {
        "status": "updated",
        "release_version": str(result.get("release_version") or ""),
        "content_digest": str(result.get("content_digest") or ""),
    }


__all__ = [
    "NucleiTemplateRefreshError",
    "managed_nuclei_template_refresh_enabled",
    "refresh_managed_nuclei_templates",
    "refresh_operator_action",
]
