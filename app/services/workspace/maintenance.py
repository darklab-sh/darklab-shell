"""Workspace maintenance helpers for migration and inactive cleanup."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
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


def migrate_session_workspace(
    from_session_id: str,
    to_session_id: str,
    cfg: Mapping[str, Any] | None = None,
):
    """Merge one session workspace into another without overwriting files."""
    from services.workspace.files import (
        WORKSPACE_DIR_MODE,
        InvalidWorkspacePath,
        WorkspaceMigrationResult,
        _chmod_workspace_dir,
        _reject_symlinks_under,
        session_workspace_name,
        touch_session_workspace,
        workspace_root,
        workspace_settings,
        workspace_usage,
    )

    if str(from_session_id or "").startswith("team_") or str(to_session_id or "").startswith("team_"):
        raise InvalidWorkspacePath("session workspace migration is personal-only")
    settings = workspace_settings(cfg)
    if not settings.enabled or from_session_id == to_session_id:
        return WorkspaceMigrationResult()

    root = workspace_root(settings)
    source = root / session_workspace_name(from_session_id)
    destination = root / session_workspace_name(to_session_id)
    if not source.exists():
        return WorkspaceMigrationResult()
    if source.is_symlink() or not source.is_dir():
        raise InvalidWorkspacePath("source session workspace is invalid")
    if destination.exists() and (destination.is_symlink() or not destination.is_dir()):
        raise InvalidWorkspacePath("destination session workspace is invalid")

    _reject_symlinks_under(source)
    if destination.exists():
        _reject_symlinks_under(destination)

    destination.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
    _chmod_workspace_dir(destination)

    log.info(
        "WORKSPACE_MIGRATION_STARTED",
        extra={
            "source": session_workspace_name(from_session_id),
            "destination": session_workspace_name(to_session_id),
        },
    )
    usage = workspace_usage(to_session_id, cfg)
    bytes_used = usage.bytes_used
    file_count = usage.file_count
    migrated_files = 0
    skipped_files = 0
    migrated_directories = 0
    skipped_directories = 0
    skip_reasons: dict[str, int] = {}
    migrated_file_paths: list[str] = []
    skipped_file_paths: list[str] = []

    def _record_skip(reason: str, *, is_file: bool) -> None:
        nonlocal skipped_files, skipped_directories
        if is_file:
            skipped_files += 1
        else:
            skipped_directories += 1
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    directories = sorted(
        (path for path in source.rglob("*") if path.is_dir()),
        key=lambda item: len(item.relative_to(source).parts),
    )
    for source_dir in directories:
        rel = source_dir.relative_to(source)
        target_dir = destination / rel
        if target_dir.exists():
            if target_dir.is_dir():
                continue
            _record_skip("target_conflict", is_file=False)
            continue
        if _target_parent_has_file(destination, target_dir):
            _record_skip("parent_conflict", is_file=False)
            continue
        try:
            target_dir.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
            _chmod_workspace_dir(target_dir)
            migrated_directories += 1
        except OSError:
            _record_skip("mkdir_failed", is_file=False)

    files = sorted(
        (path for path in source.rglob("*") if path.is_file()),
        key=lambda item: item.relative_to(source).as_posix(),
    )
    for source_file in files:
        rel = source_file.relative_to(source)
        rel_path = rel.as_posix()
        target_file = destination / rel
        try:
            size = source_file.stat().st_size
        except OSError:
            _record_skip("stat_failed", is_file=True)
            skipped_file_paths.append(rel_path)
            continue
        skip_reason = ""
        if target_file.exists():
            skip_reason = "target_conflict"
        elif _target_parent_has_file(destination, target_file):
            skip_reason = "parent_conflict"
        elif size > settings.max_file_bytes:
            skip_reason = "file_too_large"
        elif file_count + 1 > settings.max_files:
            skip_reason = "file_count_quota"
        elif bytes_used + size > settings.quota_bytes:
            skip_reason = "byte_quota"
        if skip_reason:
            _record_skip(skip_reason, is_file=True)
            skipped_file_paths.append(rel_path)
            continue
        try:
            target_file.parent.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
            _chmod_workspace_dir(target_file.parent)
            shutil.move(str(source_file), str(target_file))
            migrated_files += 1
            migrated_file_paths.append(rel_path)
            file_count += 1
            bytes_used += size
        except (OSError, shutil.Error):
            _record_skip("move_failed", is_file=True)
            skipped_file_paths.append(rel_path)

    _cleanup_empty_workspace_dirs(source)
    touch_session_workspace(to_session_id, cfg)
    log.info(
        "WORKSPACE_MIGRATION_COMPLETED",
        extra={
            "source": session_workspace_name(from_session_id),
            "destination": session_workspace_name(to_session_id),
            "migrated_files": migrated_files,
            "migrated_directories": migrated_directories,
            "skipped_files": skipped_files,
            "skipped_directories": skipped_directories,
        },
    )
    if skipped_files or skipped_directories:
        log.warning(
            "WORKSPACE_MIGRATION_SKIPPED_ITEMS",
            extra={
                "source": session_workspace_name(from_session_id),
                "destination": session_workspace_name(to_session_id),
                "skipped_files": skipped_files,
                "skipped_directories": skipped_directories,
                "reasons": dict(sorted(skip_reasons.items())),
            },
        )
    return WorkspaceMigrationResult(
        migrated_files=migrated_files,
        skipped_files=skipped_files,
        migrated_directories=migrated_directories,
        skipped_directories=skipped_directories,
        migrated_file_paths=tuple(migrated_file_paths),
        skipped_file_paths=tuple(skipped_file_paths),
    )


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
