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


def _run(binary: str, stage_dir: Path, config_root: Path) -> dict[str, str]:
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
        return {"status": "failed", "reason_code": "template_update_failed"}
    snapshot = managed_nuclei_template_snapshot(
        stage_dir,
        config_path=config_path,
        acquire_lock=False,
    )
    if snapshot.state != "ready" or not snapshot.release_version:
        return {"status": "failed", "reason_code": "staged_cache_invalid"}
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
        return {"status": "failed", "reason_code": "staged_cache_incompatible"}
    live_dir = Path(MANAGED_TEMPLATE_DIR)
    try:
        rebase_staged_template_manifest(stage_dir, live_dir)
    except (OSError, ValueError):
        return {"status": "failed", "reason_code": "staged_manifest_rebase_failed"}
    try:
        config_payload = staged_release_config(config_path, live_dir)
    except ValueError:
        return {"status": "failed", "reason_code": "staged_release_metadata_invalid"}
    try:
        install_staged_template_cache(
            stage_dir,
            live_dir,
            default_nuclei_config_path(),
            config_payload,
        )
    except (OSError, ValueError):
        return {"status": "failed", "reason_code": "template_install_failed"}
    return {
        "status": "updated",
        "release_version": snapshot.release_version,
        "content_digest": snapshot.content_digest,
    }


def refresh_worker() -> dict[str, str]:
    binary = resolve_runtime_command("nuclei")
    if not binary:
        return {"status": "failed", "reason_code": "nuclei_not_installed"}
    live_parent = Path(MANAGED_TEMPLATE_DIR).parent
    stage_dir = Path(tempfile.mkdtemp(prefix=".darklab-nuclei-stage-", dir=live_parent))
    config_root = Path(tempfile.mkdtemp(prefix=".darklab-nuclei-config-", dir=live_parent))
    try:
        return _run(binary, stage_dir, config_root)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason_code": "template_refresh_timed_out"}
    except (OSError, ValueError):
        return {"status": "failed", "reason_code": "template_refresh_failed"}
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
