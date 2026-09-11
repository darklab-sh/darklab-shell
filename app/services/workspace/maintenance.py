# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace maintenance helpers for migration and inactive cleanup."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import stat
from typing import Any, Mapping

log = logging.getLogger("services.workspace.files")


def _target_parent_has_file(root: Path, target: Path) -> bool:
    try:
        relative_parts = target.relative_to(root).parts
    except ValueError:
        return True
    cursor = root
    for part in relative_parts[:-1]:
        cursor = cursor / part
        if cursor.exists() and not cursor.is_dir():
            return True
    return False


def _cleanup_empty_workspace_dirs(root: Path) -> None:
    if not root.exists() or not root.is_dir():
        return
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass


def _log_workspace_cleanup_skip(path: Path, exc: BaseException) -> None:
    from services.workspace.files import log

    log.warning(
        "WORKSPACE_CLEANUP_SKIP path=%s reason=%s error=%s",
        path,
        exc.__class__.__name__,
        exc,
        extra={"path": str(path), "reason": exc.__class__.__name__},
    )


def _repair_workspace_tree_for_cleanup(path: Path) -> None:
    from services.workspace.files import (
        _workspace_repair_dir_if_needed,
        _workspace_repair_file_if_needed,
    )

    for current, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        current_path = Path(current)
        try:
            _workspace_repair_dir_if_needed(current_path, current_path.lstat())
        except OSError as exc:
            _log_workspace_cleanup_skip(current_path, exc)
        for name in list(dirnames):
            child = current_path / name
            try:
                if child.is_symlink():
                    dirnames.remove(name)
                    continue
                _workspace_repair_dir_if_needed(child, child.lstat())
            except OSError as exc:
                dirnames.remove(name)
                _log_workspace_cleanup_skip(child, exc)
        for name in filenames:
            child = current_path / name
            try:
                _workspace_repair_file_if_needed(child, child.lstat())
            except OSError as exc:
                _log_workspace_cleanup_skip(child, exc)


def _remove_unreadable_direct_child_directories(path: Path) -> None:
    try:
        children = list(path.iterdir())
    except OSError:
        return
    for child in children:
        try:
            child_stat = child.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(child_stat.st_mode) or not stat.S_ISDIR(child_stat.st_mode):
            continue
        try:
            list(child.iterdir())
        except PermissionError:
            try:
                child.rmdir()
            except (FileNotFoundError, OSError):
                continue
        except OSError as exc:
            _log_workspace_cleanup_skip(child, exc)


def _scanner_owned_cleanup_targets(path: Path) -> list[Path]:
    from services.workspace.files import _is_scanner_owned, _workspace_repair_dir_if_needed

    targets: list[Path] = []
    for current, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in list(dirnames):
            child = current_path / name
            try:
                child_stat = child.lstat()
            except OSError as exc:
                dirnames.remove(name)
                _log_workspace_cleanup_skip(child, exc)
                continue
            if child.is_symlink():
                dirnames.remove(name)
                continue
            if _is_scanner_owned(child_stat):
                targets.append(child)
                dirnames.remove(name)
                continue
            try:
                _workspace_repair_dir_if_needed(child, child_stat)
            except OSError as exc:
                dirnames.remove(name)
                _log_workspace_cleanup_skip(child, exc)
        for name in filenames:
            child = current_path / name
            try:
                if _is_scanner_owned(child.lstat()):
                    targets.append(child)
            except OSError as exc:
                _log_workspace_cleanup_skip(child, exc)
    return sorted(targets, key=lambda item: len(item.parts), reverse=True)


def _remove_workspace_cleanup_target(path: Path) -> None:
    from services.workspace.files import _remove_workspace_directory

    if path.is_dir() and not path.is_symlink():
        _remove_workspace_directory(path)
        return
    path.unlink(missing_ok=True)


def _remove_inactive_workspace_directory(path: Path) -> None:
    from services.workspace.files import (
        log,
        _remove_unreadable_direct_child_directories,
        _remove_workspace_directory,
        _repair_workspace_tree_for_cleanup,
        _scanner_owned_cleanup_targets,
    )

    try:
        _remove_workspace_directory(path)
        return
    except PermissionError as exc:
        repair_reason = type(exc).__name__
        log.debug(
            "WORKSPACE_CLEANUP_REPAIR_ATTEMPTED",
            extra={"path": str(path), "reason": repair_reason},
        )
        try:
            _repair_workspace_tree_for_cleanup(path)
            _remove_workspace_directory(path)
            return
        except PermissionError as repair_exc:
            _remove_unreadable_direct_child_directories(path)
            targets = _scanner_owned_cleanup_targets(path)
            repair_reason = type(repair_exc).__name__
            log.warning(
                "WORKSPACE_CLEANUP_DEGRADED",
                extra={"path": str(path), "target_count": len(targets), "reason": repair_reason},
            )
    except OSError as exc:
        _remove_unreadable_direct_child_directories(path)
        targets = _scanner_owned_cleanup_targets(path)
        log.warning(
            "WORKSPACE_CLEANUP_DEGRADED",
            extra={"path": str(path), "target_count": len(targets), "reason": type(exc).__name__},
        )

    for target in targets:
        _remove_workspace_cleanup_target(target)
    _remove_workspace_directory(path)


def cleanup_inactive_workspaces(
    cfg: Mapping[str, Any] | None = None,
    *,
    now: float | None = None,
    skip_session_id: str | None = None,
) -> int:
    from services.metrics_lazy import app_metrics
    from services.workspace.files import session_workspace_name, workspace_root, workspace_settings

    settings = workspace_settings(cfg)
    if not settings.enabled or settings.inactivity_ttl_hours <= 0:
        return 0
    root = workspace_root(settings)
    if not root.exists():
        return 0
    skip_name = session_workspace_name(skip_session_id) if skip_session_id else ""
    ttl_seconds = settings.inactivity_ttl_hours * 60 * 60
    cutoff = (datetime.now(timezone.utc).timestamp() if now is None else float(now)) - ttl_seconds
    removed = 0
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir() or not child.name.startswith("sess_"):
            continue
        if skip_name and child.name == skip_name:
            continue
        try:
            expired = child.stat().st_mtime < cutoff
        except OSError as exc:
            _log_workspace_cleanup_skip(child, exc)
            continue
        if expired:
            try:
                _remove_inactive_workspace_directory(child)
            except OSError as exc:
                _log_workspace_cleanup_skip(child, exc)
                continue
            removed += 1
    app_metrics.record_workspace_evictions(removed, "inactive")
    return removed


cleanup_empty_workspace_dirs = _cleanup_empty_workspace_dirs
