# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded compatibility and freshness checks for managed Nuclei templates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
import os
import re
import subprocess
from typing import Any

from services.commands.registry_validation import resolve_runtime_command
from services.nuclei.provenance import MANAGED_TEMPLATE_DIR
from services.nuclei.template_cache import (
    NucleiTemplateCacheSnapshot,
    managed_nuclei_template_snapshot,
)


DEFAULT_STALE_AFTER_SECONDS = 7 * 24 * 60 * 60
MAX_STALE_AFTER_SECONDS = 365 * 24 * 60 * 60
VERSION_TIMEOUT_SECONDS = 5
VALIDATION_TIMEOUT_SECONDS = 90
_VERSION_RE = re.compile(r"\bv?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\b")
_RunCommand = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class NucleiTemplateHealth:
    """One target-free health result for the shared managed template cache."""

    state: str
    snapshot: NucleiTemplateCacheSnapshot
    validation_state: str = "not_run"
    nuclei_version: str = ""
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS
    reason_code: str = ""

    @property
    def launchable(self) -> bool:
        return self.state in {"ready", "stale"} and self.validation_state == "passed"

    def public(self) -> dict[str, Any]:
        return {
            **self.snapshot.public(),
            "state": self.state,
            "validation_state": self.validation_state,
            "nuclei_version": self.nuclei_version,
            "stale_after_seconds": self.stale_after_seconds,
            "reason_code": self.reason_code,
            "launchable": self.launchable,
        }


def managed_nuclei_template_health(
    template_dir: str = MANAGED_TEMPLATE_DIR,
    *,
    snapshot: NucleiTemplateCacheSnapshot | None = None,
    binary_path: str | None = None,
    current_time: datetime | None = None,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    run_command: _RunCommand | None = None,
) -> NucleiTemplateHealth:
    """Validate one immutable cache snapshot without contacting a scan target."""
    selected = snapshot or managed_nuclei_template_snapshot(template_dir)
    threshold = max(1, min(int(stale_after_seconds), MAX_STALE_AFTER_SECONDS))
    if selected.state != "ready":
        return NucleiTemplateHealth(
            selected.state,
            selected,
            stale_after_seconds=threshold,
            reason_code=f"template_cache_{selected.state}",
        )
    resolved_binary = binary_path or resolve_runtime_command("nuclei")
    if not resolved_binary:
        return NucleiTemplateHealth(
            "unavailable",
            selected,
            validation_state="unavailable",
            stale_after_seconds=threshold,
            reason_code="nuclei_not_installed",
        )
    if run_command is None:
        binary_key = _binary_key(resolved_binary)
        version = _cached_binary_version(resolved_binary, binary_key)
        validation = _cached_validation(
            resolved_binary,
            binary_key,
            version,
            selected.content_digest,
            os.path.abspath(template_dir),
        )
    else:
        version = _binary_version(resolved_binary, run_command)
        validation = _validate_templates(resolved_binary, template_dir, run_command)
    if validation == "failed":
        return NucleiTemplateHealth(
            "incompatible", selected, validation, version, threshold,
            "template_validation_failed",
        )
    if validation != "passed":
        return NucleiTemplateHealth(
            "unavailable", selected, validation, version, threshold,
            "template_validation_unavailable",
        )
    stale = _snapshot_is_stale(selected, current_time=current_time, threshold=threshold)
    return NucleiTemplateHealth(
        "stale" if stale else "ready",
        selected,
        validation,
        version,
        threshold,
        "template_cache_stale" if stale else "",
    )


def clear_nuclei_template_health_cache() -> None:
    """Forget process-local validation results after a managed-cache change."""
    _cached_binary_version.cache_clear()
    _cached_validation.cache_clear()


def _binary_key(binary_path: str) -> tuple[int, ...]:
    try:
        info = os.stat(binary_path)
    except OSError:
        return ()
    return (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@lru_cache(maxsize=8)
def _cached_binary_version(binary_path: str, binary_key: tuple[int, ...]) -> str:
    del binary_key
    return _binary_version(binary_path, subprocess.run)


@lru_cache(maxsize=32)
def _cached_validation(
    binary_path: str,
    binary_key: tuple[int, ...],
    binary_version: str,
    content_digest: str,
    template_dir: str,
) -> str:
    del binary_key, binary_version, content_digest
    return _validate_templates(binary_path, template_dir, subprocess.run)


def _binary_version(binary_path: str, run_command: _RunCommand) -> str:
    try:
        completed = run_command(
            [binary_path, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    output = f"{completed.stdout or ''}\n{completed.stderr or ''}"[:4096]
    match = _VERSION_RE.search(output)
    return match.group(0) if match else ""


def _validate_templates(
    binary_path: str,
    template_dir: str,
    run_command: _RunCommand,
) -> str:
    command = [
        binary_path,
        "-validate",
        "-t", os.path.abspath(template_dir),
        "-ud", os.path.abspath(template_dir),
        "-disable-update-check",
        "-no-color",
        "-silent",
    ]
    try:
        completed = run_command(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=VALIDATION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return "passed" if completed.returncode == 0 else "failed"


def _snapshot_is_stale(
    snapshot: NucleiTemplateCacheSnapshot,
    *,
    current_time: datetime | None,
    threshold: int,
) -> bool:
    try:
        refreshed = datetime.fromisoformat(snapshot.refreshed_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return True
    if refreshed.tzinfo is None:
        refreshed = refreshed.replace(tzinfo=UTC)
    now = current_time or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (now.astimezone(UTC) - refreshed.astimezone(UTC)).total_seconds() > threshold


__all__ = [
    "DEFAULT_STALE_AFTER_SECONDS",
    "NucleiTemplateHealth",
    "clear_nuclei_template_health_cache",
    "managed_nuclei_template_health",
]
