# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Rollback-safe filesystem swap for one staged Nuclei template cache."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import uuid

from services.nuclei.template_cache import (
    MAX_CHECKSUM_BYTES,
    MAX_CHECKSUM_ENTRIES,
    MAX_CONFIG_BYTES,
)
from services.nuclei.template_cache_files import read_bounded, regular_stat


_CHECKSUM_RE = re.compile(r"[a-fA-F0-9]{32}")


def rebase_staged_template_manifest(
    stage_dir: Path,
    live_dir: Path,
    *,
    recorded_root: Path | None = None,
) -> None:
    """Replace staging-only absolute paths before promoting the snapshot."""
    checksum = stage_dir / ".checksum"
    payload = read_bounded(checksum, MAX_CHECKSUM_BYTES)
    if payload is None:
        raise ValueError("staged template manifest is unavailable")
    stage_root = os.path.abspath(recorded_root or stage_dir)
    live_root = os.path.abspath(live_dir)
    rebased: list[str] = []
    try:
        raw_entries = payload.decode("utf-8", errors="strict").split(";")
    except UnicodeDecodeError as exc:
        raise ValueError("staged template manifest is invalid") from exc
    for raw_entry in raw_entries:
        if not raw_entry.strip():
            continue
        if len(rebased) >= MAX_CHECKSUM_ENTRIES or "," not in raw_entry:
            raise ValueError("staged template manifest is invalid")
        raw_path, raw_digest = raw_entry.rsplit(",", 1)
        digest = raw_digest.strip().lower()
        candidate = os.path.abspath(
            raw_path if os.path.isabs(raw_path) else Path(stage_root) / raw_path
        )
        if os.path.commonpath((stage_root, candidate)) != stage_root \
            or not _CHECKSUM_RE.fullmatch(digest):
            raise ValueError("staged template manifest is invalid")
        relative = os.path.relpath(candidate, stage_root)
        rebased.append(f"{os.path.join(live_root, relative)},{digest};")
    if not rebased:
        raise ValueError("staged template manifest is invalid")
    replacement = stage_dir / f".darklab-checksum-{uuid.uuid4().hex}.tmp"
    descriptor = os.open(
        replacement,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o640,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("".join(rebased))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(replacement, checksum)
    finally:
        replacement.unlink(missing_ok=True)


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


__all__ = [
    "install_staged_template_cache",
    "rebase_staged_template_manifest",
    "staged_release_config",
]
