# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Isolated, bounded worker for refreshing the managed Nuclei cache."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from services.commands.registry_validation import resolve_runtime_command
from services.nuclei.provenance import MANAGED_TEMPLATE_DIR
from services.nuclei.template_cache import managed_nuclei_template_snapshot
from services.nuclei.template_cache_files import default_nuclei_config_path
from services.nuclei.template_health import VALIDATION_TIMEOUT_SECONDS
from services.nuclei.template_refresh_files import (
    install_staged_template_cache,
    rebase_staged_template_manifest,
    staged_release_config,
)


UPDATE_TIMEOUT_SECONDS = 180


def _failed(
    reason_code: str,
    phase: str,
    *,
    exit_status: int | None = None,
    error: Exception | None = None,
) -> dict[str, str | int]:
    result: dict[str, str | int] = {
        "status": "failed",
        "reason_code": reason_code,
        "phase": phase,
    }
    if exit_status is not None:
        result["exit_status"] = int(exit_status)
    if error is not None:
        if isinstance(error, subprocess.TimeoutExpired):
            result["error_class"] = "TimeoutExpired"
        elif isinstance(error, OSError):
            result["error_class"] = "OSError"
        elif isinstance(error, ValueError):
            result["error_class"] = "ValueError"
    return result


def _run(binary: str, stage_dir: Path, config_root: Path) -> dict[str, str | int]:
    environment = os.environ.copy()
    environment["HOME"] = str(config_root)
    environment["XDG_CONFIG_HOME"] = str(config_root / ".config")
    config_path = Path(environment["XDG_CONFIG_HOME"]) / "nuclei" / ".templates-config.json"
    update = subprocess.run(
        [binary, "-update-templates", "-ud", str(stage_dir)],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        timeout=UPDATE_TIMEOUT_SECONDS,
    )
    if update.returncode != 0:
        return _failed(
            "template_update_failed",
            "update",
            exit_status=update.returncode,
        )
    snapshot = managed_nuclei_template_snapshot(
        stage_dir,
        config_path=config_path,
        acquire_lock=False,
    )
    if snapshot.state != "ready" or not snapshot.release_version:
        return _failed("staged_cache_invalid", "snapshot")
    validation = subprocess.run(
        [
            binary,
            "-validate",
            "-t", str(stage_dir),
            "-ud", str(stage_dir),
            "-disable-update-check",
            "-no-color",
            "-silent",
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        timeout=VALIDATION_TIMEOUT_SECONDS,
    )
    if validation.returncode != 0:
        return _failed(
            "staged_cache_incompatible",
            "validation",
            exit_status=validation.returncode,
        )
    live_dir = Path(MANAGED_TEMPLATE_DIR)
    try:
        rebase_staged_template_manifest(stage_dir, live_dir)
    except (OSError, ValueError) as exc:
        return _failed("staged_manifest_rebase_failed", "manifest", error=exc)
    try:
        config_payload = staged_release_config(config_path, live_dir)
    except ValueError as exc:
        return _failed("staged_release_metadata_invalid", "metadata", error=exc)
    try:
        install_staged_template_cache(
            stage_dir,
            live_dir,
            default_nuclei_config_path(),
            config_payload,
        )
    except (OSError, ValueError) as exc:
        return _failed("template_install_failed", "install", error=exc)
    return {
        "status": "updated",
        "release_version": snapshot.release_version,
        "content_digest": snapshot.content_digest,
    }


def refresh_worker() -> dict[str, str | int]:
    binary = resolve_runtime_command("nuclei")
    if not binary:
        return _failed("nuclei_not_installed", "resolve")
    live_parent = Path(MANAGED_TEMPLATE_DIR).parent
    stage_dir = Path(tempfile.mkdtemp(prefix=".darklab-nuclei-stage-", dir=live_parent))
    config_root = Path(tempfile.mkdtemp(prefix=".darklab-nuclei-config-", dir=live_parent))
    try:
        return _run(binary, stage_dir, config_root)
    except subprocess.TimeoutExpired as exc:
        return _failed("template_refresh_timed_out", "worker", error=exc)
    except (OSError, ValueError) as exc:
        return _failed("template_refresh_failed", "worker", error=exc)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
        shutil.rmtree(config_root, ignore_errors=True)


def main() -> int:
    result = refresh_worker()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if result.get("status") == "updated" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["UPDATE_TIMEOUT_SECONDS", "main", "refresh_worker"]
