# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Rollback-safe filesystem swap for one staged Nuclei template cache."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import uuid

from services.nuclei.template_cache import MAX_CONFIG_BYTES
from services.nuclei.template_cache_files import read_bounded, regular_stat


def staged_release_config(config_path: Path, live_dir: Path) -> bytes:
    payload = read_bounded(config_path, MAX_CONFIG_BYTES)
    if payload is None:
        raise ValueError("staged template release metadata is unavailable")
    try:
        config = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("staged template release metadata is invalid") from exc
    if not isinstance(config, dict) or not str(config.get("nuclei-templates-version") or ""):
        raise ValueError("staged template release metadata is incomplete")
    config["nuclei-templates-directory"] = os.path.abspath(live_dir)
    return (json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n").encode()


def install_staged_template_cache(
    stage_dir: Path,
    live_dir: Path,
    live_config_path: Path,
    config_payload: bytes,
) -> None:
    """Install a complete stage and restore the old cache on any commit failure."""
    if regular_stat(stage_dir, directory=True) is None:
        raise ValueError("staged template cache is unsafe")
    if live_dir.exists() and regular_stat(live_dir, directory=True) is None:
        raise ValueError("managed template cache is unsafe")
    config_parent = live_config_path.parent
    if regular_stat(config_parent, directory=True) is None:
        raise ValueError("managed template config directory is unsafe")
    # scanner owns the cache; appuser needs group traversal to read its manifest.
    os.chmod(stage_dir, 0o750)  # nosec B103
    checksum = stage_dir / ".checksum"
    if regular_stat(checksum) is None:
        raise ValueError("staged template manifest is unavailable")
    os.chmod(checksum, 0o640)

    token = uuid.uuid4().hex
    marker_temp = config_parent / f".darklab-nuclei-config-{token}.tmp"
    backup_dir = live_dir.parent / f".darklab-nuclei-backup-{token}"
    marker_fd = os.open(
        marker_temp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o640,
    )
    try:
        with os.fdopen(marker_fd, "wb") as handle:
            handle.write(config_payload)
            handle.flush()
            os.fsync(handle.fileno())
        had_live = live_dir.exists()
        if had_live:
            os.replace(live_dir, backup_dir)
        try:
            os.replace(stage_dir, live_dir)
            try:
                os.replace(marker_temp, live_config_path)
            except OSError:
                os.replace(live_dir, stage_dir)
                if had_live:
                    os.replace(backup_dir, live_dir)
                raise
        except OSError:
            if had_live and backup_dir.exists() and not live_dir.exists():
                os.replace(backup_dir, live_dir)
            raise
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
    finally:
        marker_temp.unlink(missing_ok=True)


__all__ = ["install_staged_template_cache", "staged_release_config"]
