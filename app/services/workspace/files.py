"""App-mediated workspace helpers.

This module intentionally does not expose shell navigation or redirection.
Every file operation resolves a user-facing relative path inside one hashed
workspace directory and enforces quota limits before writes.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fnmatch
from functools import lru_cache
import hashlib
import logging
import os
from pathlib import Path, PurePosixPath
import pwd
import shutil
import stat
import subprocess
import tempfile
from typing import Any, BinaryIO

from config import CFG
from services.teams.scope import OwnerContext, owner_context_for_scope

log = logging.getLogger(__name__)


class _MetricsProxy:
    def __getattr__(self, name: str) -> Any:
        from services import metrics  # noqa: PLC0415
        return getattr(metrics, name)


app_metrics = _MetricsProxy()

# Session directories are sticky + setgid so files created by scanner tools
# inherit the shared appuser group without becoming world-readable.
WORKSPACE_DIR_MODE = 0o3730
WORKSPACE_FILE_MODE = 0o640
WORKSPACE_COMMAND_WRITE_FILE_MODE = 0o660
WORKSPACE_COMMAND_DIR_MODE = 0o3770


@lru_cache(maxsize=1)
def _sudo_bin() -> str:
    return shutil.which("sudo") or ""


@lru_cache(maxsize=1)
def _scanner_user():
    try:
        return pwd.getpwnam("scanner")
    except (AttributeError, KeyError, TypeError):
        return None


def _scanner_user_exists() -> bool:
    return _scanner_user() is not None


class WorkspaceError(ValueError):
    """Base class for workspace validation and operation errors."""


class WorkspaceDisabled(WorkspaceError):
    """Raised when workspace operations are requested while disabled."""


class InvalidWorkspacePath(WorkspaceError):
    """Raised when a user-facing workspace path is unsafe or unsupported."""


class WorkspaceQuotaExceeded(WorkspaceError):
    """Raised when a write would exceed configured workspace limits."""


class WorkspaceFileNotFound(WorkspaceError):
    """Raised when a validated workspace path does not point at a file."""


class WorkspacePathNotFound(WorkspaceError):
    """Raised when a validated workspace path does not exist."""


class WorkspaceBinaryFile(WorkspaceError):
    """Raised when a workspace file is not safe to display as text."""


class WorkspacePermissionDenied(WorkspaceError):
    """Raised when workspace permissions prevent an app-mediated operation."""


@dataclass(frozen=True)
class WorkspaceSettings:
    enabled: bool
    backend: str
    root: Path
    quota_bytes: int
    max_file_bytes: int
    max_files: int
    inactivity_ttl_hours: int


@dataclass(frozen=True)
class WorkspaceUsage:
    bytes_used: int
    file_count: int


@dataclass(frozen=True)
class WorkspaceDeleteResult:
    path: str
    kind: str
    file_count: int


@dataclass(frozen=True)
class WorkspaceMoveResult:
    source: str
    destination: str
    kind: str
    file_count: int


@dataclass(frozen=True)
class WorkspacePathMatch:
    path: str
    kind: str
    file_count: int


@dataclass(frozen=True)
class WorkspaceMigrationResult:
    migrated_files: int = 0
    skipped_files: int = 0
    migrated_directories: int = 0
    skipped_directories: int = 0
    migrated_file_paths: tuple[str, ...] = ()
    skipped_file_paths: tuple[str, ...] = ()


def _coerce_owner_context(owner: OwnerContext | Any) -> OwnerContext:
    context = getattr(owner, "context", owner)
    if isinstance(context, OwnerContext):
        return context
    raise WorkspaceError("workspace owner context is required")


def _coerce_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _mb_to_bytes(value: Any, default_mb: int) -> int:
    return _coerce_int(value, default_mb, minimum=0) * 1024 * 1024


def workspace_settings(cfg: dict[str, Any] | None = None) -> WorkspaceSettings:
    active = CFG if cfg is None else cfg
    backend = str(active.get("workspace_backend") or "tmpfs").strip().lower()
    if backend not in {"tmpfs", "volume"}:
        backend = "tmpfs"
    return WorkspaceSettings(
        enabled=bool(active.get("workspace_enabled", False)),
        backend=backend,
        # Intentional fallback for the disabled-by-default workspace feature.
        # Every operation still resolves through strict per-session path checks.
        root=Path(str(active.get("workspace_root") or "/tmp/darklab_shell-workspaces")).expanduser(),  # nosec
        quota_bytes=_mb_to_bytes(active.get("workspace_quota_mb"), 50),
        max_file_bytes=_mb_to_bytes(active.get("workspace_max_file_mb"), 5),
        max_files=_coerce_int(active.get("workspace_max_files"), 100, minimum=1),
        inactivity_ttl_hours=_coerce_int(
            active.get("workspace_inactivity_ttl_hours"),
            1,
            minimum=0,
        ),
    )


def _workspace_project_names_expr() -> str:
    from core.database import DB_BACKEND  # noqa: PLC0415
    from core.database_backend import dialect_for_backend  # noqa: PLC0415

    return dialect_for_backend(DB_BACKEND).string_agg_distinct("p.name")


def _workspace_label_order_sql() -> str:
    from core.database import DB_BACKEND  # noqa: PLC0415
    from core.database_backend import dialect_for_backend  # noqa: PLC0415

    return dialect_for_backend(DB_BACKEND).case_insensitive_order("label") + ", created ASC"


def _workspace_metadata_owner_where(scope: Any, table_alias: str = "") -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    if getattr(scope, "is_team", False):
        team_id = str(getattr(scope, "team_id", "") or "")
        return (
            f"({prefix}team_id = ? OR "
            f"(({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?))",
            (team_id, team_id),
        )
    return (
        f"({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?",
        (str(getattr(scope, "owner_id", "") or ""),),
    )


def workspace_file_metadata_by_path(scope: Any, paths: list[Any]) -> dict[str, dict[str, Any]]:
    from core.database import db_connect  # noqa: PLC0415

    clean_paths = sorted({str(path) for path in paths if path})
    if not clean_paths:
        return {}
    placeholders = ",".join("?" for _ in clean_paths)
    project_names_expr = _workspace_project_names_expr()
    label_order_sql = _workspace_label_order_sql()
    run_owner_sql, run_owner_params = scope.predicate(table_alias="r")
    project_owner_sql, project_owner_params = scope.predicate(table_alias="p")
    metadata_owner_sql, metadata_owner_params = _workspace_metadata_owner_where(scope)
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT rfa.workspace_path, COUNT(DISTINCT rfa.id) AS artifact_count, "  # nosec
            "COUNT(DISTINCT rfa.run_id) AS run_count, MAX(r.started) AS last_seen, "
            f"{project_names_expr} AS project_names "
            "FROM run_file_artifacts rfa "
            "LEFT JOIN runs r ON r.id = rfa.run_id "
            "LEFT JOIN project_links pl ON pl.entity_type = 'run' AND pl.entity_id = rfa.run_id "
            "LEFT JOIN projects p ON p.id = pl.project_id AND " + project_owner_sql + " "
            "WHERE " + run_owner_sql + " "
            f"AND rfa.workspace_path IN ({placeholders}) "
            "GROUP BY rfa.workspace_path",
            [*project_owner_params, *run_owner_params, *clean_paths],
        ).fetchall()
        label_rows = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, label, source, created "  # nosec
            "FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "
            f"AND entity_id IN ({placeholders}) "
            f"ORDER BY {label_order_sql}",
            [*metadata_owner_params, *clean_paths],
        ).fetchall()
        note_rows = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, body, created, updated "  # nosec
            "FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *clean_paths],
        ).fetchall()
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        project_names = [
            name for name in str(row["project_names"] or "").split(",")
            if name
        ]
        metadata[str(row["workspace_path"])] = {
            "artifact_count": int(row["artifact_count"] or 0),
            "artifact_run_count": int(row["run_count"] or 0),
            "artifact_last_seen": row["last_seen"] or "",
            "project_names": project_names,
        }
    for row in label_rows:
        path = str(row["entity_id"])
        item = metadata.setdefault(path, {})
        item.setdefault("labels", []).append({
            "id": row["id"],
            "session_id": row["session_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "label": row["label"],
            "source": row["source"],
            "created": row["created"],
        })
    for row in note_rows:
        path = str(row["entity_id"])
        item = metadata.setdefault(path, {})
        item["note"] = {
            "id": row["id"],
            "session_id": row["session_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "body": row["body"],
            "created": row["created"],
            "updated": row["updated"],
        }
    return metadata


def delete_workspace_file_metadata(scope: Any, paths: list[str]) -> None:
    from core.database import db_connect  # noqa: PLC0415

    clean_paths = sorted({str(path) for path in paths if path})
    if not clean_paths:
        return
    placeholders = ",".join("?" for _ in clean_paths)
    metadata_owner_sql, metadata_owner_params = _workspace_metadata_owner_where(scope)
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *clean_paths],
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *clean_paths],
        )
        conn.commit()


def move_workspace_file_metadata(scope: Any, path_map: dict[str, str]) -> None:
    from core.database import db_connect  # noqa: PLC0415

    clean_map = {
        str(source): str(destination)
        for source, destination in path_map.items()
        if source and destination and str(source) != str(destination)
    }
    if not clean_map:
        return
    destinations = sorted(set(clean_map.values()))
    placeholders = ",".join("?" for _ in destinations)
    metadata_owner_sql, metadata_owner_params = _workspace_metadata_owner_where(scope)
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *destinations],
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *destinations],
        )
        for source, destination in clean_map.items():
            conn.execute(  # nosec
                "UPDATE entity_labels SET entity_id = ? "  # nosec
                "WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' AND entity_id = ?",
                (destination, *metadata_owner_params, source),
            )
            conn.execute(  # nosec
                "UPDATE entity_notes SET entity_id = ? "  # nosec
                "WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' AND entity_id = ?",
                (destination, *metadata_owner_params, source),
            )
        conn.commit()


def _require_enabled(settings: WorkspaceSettings) -> None:
    if not settings.enabled:
        raise WorkspaceDisabled("Files are disabled on this instance")


def session_workspace_name(session_id: str) -> str:
    digest = hashlib.sha256(str(session_id or "anonymous").encode("utf-8")).hexdigest()
    return f"sess_{digest[:32]}"


def owner_workspace_name(owner: OwnerContext | Any) -> str:
    context = _coerce_owner_context(owner)
    digest = hashlib.sha256(context.owner_id.encode("utf-8")).hexdigest()
    prefix = "team" if context.is_team else "sess"
    return f"{prefix}_{digest[:32]}"


def _workspace_session_owner_context(session_id: str) -> OwnerContext:
    return owner_context_for_scope(session_id)


def workspace_root(settings: WorkspaceSettings) -> Path:
    return settings.root.resolve(strict=False)


def owner_workspace_dir(owner: OwnerContext | Any, cfg: dict[str, Any] | None = None) -> Path:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    return workspace_root(settings) / owner_workspace_name(owner)


def session_workspace_dir(session_id: str, cfg: dict[str, Any] | None = None) -> Path:
    return owner_workspace_dir(_workspace_session_owner_context(session_id), cfg)


def ensure_owner_workspace(owner: OwnerContext | Any, cfg: dict[str, Any] | None = None) -> Path:
    path = owner_workspace_dir(owner, cfg)
    path.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
    try:
        os.chmod(path, WORKSPACE_DIR_MODE)
    except OSError as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, WORKSPACE_DIR_MODE, exc)
    return path


def ensure_session_workspace(session_id: str, cfg: dict[str, Any] | None = None) -> Path:
    return ensure_owner_workspace(_workspace_session_owner_context(session_id), cfg)


def touch_owner_workspace(owner: OwnerContext | Any, cfg: dict[str, Any] | None = None) -> None:
    """Mark an owner workspace active without exposing that detail to users."""
    path = ensure_owner_workspace(owner, cfg)
    try:
        os.utime(path, None)
    except OSError:
        pass


def touch_session_workspace(session_id: str, cfg: dict[str, Any] | None = None) -> None:
    """Mark the session workspace active without exposing that detail to users."""
    touch_owner_workspace(_workspace_session_owner_context(session_id), cfg)


def _validate_relative_path(relative_path: str) -> PurePosixPath:
    raw = str(relative_path or "")
    if not raw:
        raise InvalidWorkspacePath("file name is required")
    if raw != raw.strip():
        raise InvalidWorkspacePath("file name cannot start or end with whitespace")
    if any(ord(char) < 32 for char in raw) or "\\" in raw:
        raise InvalidWorkspacePath("file name contains unsupported characters")
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise InvalidWorkspacePath("file name must be relative")
    parts = path.parts
    if not parts:
        raise InvalidWorkspacePath("file name is required")
    for part in parts:
        if part in {"", ".", ".."}:
            raise InvalidWorkspacePath("file name cannot contain traversal")
        if len(part) > 255:
            raise InvalidWorkspacePath("file name is too long")
    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _reject_symlink_components(root: Path, candidate: Path) -> None:
    cursor = root
    for part in candidate.relative_to(root).parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            raise InvalidWorkspacePath("workspace file symlinks are not allowed")


def _reject_symlinks_under(path: Path) -> None:
    if path.is_symlink():
        raise InvalidWorkspacePath("workspace file symlinks are not allowed")
    if not path.is_dir():
        return
    for child in path.rglob("*"):
        if child.is_symlink():
            raise InvalidWorkspacePath("workspace file symlinks are not allowed")


def resolve_owner_workspace_path(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
    *,
    ensure_parent: bool = False,
) -> Path:
    root = ensure_owner_workspace(owner, cfg).resolve(strict=True)
    touch_owner_workspace(owner, cfg)
    rel = _validate_relative_path(relative_path)
    candidate = root.joinpath(*rel.parts)
    _reject_symlink_components(root, candidate)
    parent = candidate.parent
    if parent.exists():
        resolved_parent = parent.resolve(strict=True)
        if not _is_relative_to(resolved_parent, root):
            raise InvalidWorkspacePath("file path escapes the workspace directory")
    elif ensure_parent:
        parent.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
        try:
            os.chmod(parent, WORKSPACE_DIR_MODE)
        except OSError as exc:
            log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", parent, WORKSPACE_DIR_MODE, exc)
        resolved_parent = parent.resolve(strict=True)
        if not _is_relative_to(resolved_parent, root):
            raise InvalidWorkspacePath("file path escapes the workspace directory")
    else:
        raise InvalidWorkspacePath("parent directory does not exist")
    resolved = resolved_parent / candidate.name
    if not _is_relative_to(resolved.resolve(strict=False), root):
        raise InvalidWorkspacePath("file path escapes the workspace directory")
    return resolved


def resolve_workspace_path(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
    *,
    ensure_parent: bool = False,
) -> Path:
    return resolve_owner_workspace_path(
        _workspace_session_owner_context(session_id),
        relative_path,
        cfg,
        ensure_parent=ensure_parent,
    )


def _is_final_symlink_error(exc: OSError) -> bool:
    return exc.errno in {errno.ELOOP, getattr(errno, "EMLINK", errno.ELOOP)}


def _open_workspace_file_no_follow(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError as exc:
        raise WorkspaceFileNotFound("workspace file was not found") from exc
    except OSError as exc:
        if _is_final_symlink_error(exc):
            raise InvalidWorkspacePath("workspace file symlinks are not allowed") from exc
        if exc.errno in {errno.EACCES, errno.EPERM}:
            raise WorkspacePermissionDenied("workspace file is not readable") from exc
        raise
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise WorkspaceFileNotFound("workspace file was not found")
        return fd, file_stat
    except Exception:
        os.close(fd)
        raise


def open_workspace_file_for_download(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> BinaryIO:
    return open_owner_workspace_file_for_download(_workspace_session_owner_context(session_id), relative_path, cfg)


def open_owner_workspace_file_for_download(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> BinaryIO:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    _repair_owner_workspace_relative_path_for_access(owner, relative_path, cfg, include_final_file=True)
    path = resolve_owner_workspace_path(owner, relative_path, cfg)
    fd, _ = _open_workspace_file_no_follow(path)
    return os.fdopen(fd, "rb")


def _sudo_chmod_workspace_path(path: Path, mode: int) -> bool:
    sudo_bin = _sudo_bin()
    if not sudo_bin or not _scanner_user_exists():
        return False
    try:
        subprocess.run(
            [sudo_bin, "-u", "scanner", "-g", "appuser", "chgrp", "appuser", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        subprocess.run(
            [sudo_bin, "-u", "scanner", "-g", "appuser", "chmod", f"{mode:o}", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return True
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, mode, exc)
        return False


@lru_cache(maxsize=1)
def _scanner_uid() -> int | None:
    user = _scanner_user()
    if user is None:
        return None
    try:
        return int(user.pw_uid)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _appuser_gid() -> int | None:
    try:
        return int(pwd.getpwnam("appuser").pw_gid)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _is_scanner_owned(path_stat: os.stat_result) -> bool:
    scanner_uid = _scanner_uid()
    return scanner_uid is not None and path_stat.st_uid == scanner_uid


def _has_appuser_group(path_stat: os.stat_result) -> bool:
    appuser_gid = _appuser_gid()
    return appuser_gid is not None and path_stat.st_gid == appuser_gid


def _workspace_child_dir_repair_mode(child_stat: os.stat_result) -> int | None:
    if not _is_scanner_owned(child_stat):
        return None
    current = stat.S_IMODE(child_stat.st_mode)
    if current == WORKSPACE_COMMAND_DIR_MODE and _has_appuser_group(child_stat):
        return None
    return WORKSPACE_COMMAND_DIR_MODE


def _workspace_child_file_repair_mode(child_stat: os.stat_result) -> int | None:
    if not _is_scanner_owned(child_stat):
        return None
    current = stat.S_IMODE(child_stat.st_mode)
    repaired = (current | 0o040) & ~0o007
    return None if repaired == current and _has_appuser_group(child_stat) else repaired


def _chmod_workspace_entry(path: Path, mode: int) -> None:
    try:
        appuser_gid = _appuser_gid()
        if appuser_gid is not None:
            os.chown(path, -1, appuser_gid)
        os.chmod(path, mode)
        return
    except PermissionError as exc:
        if _sudo_chmod_workspace_path(path, mode):
            return
        raise WorkspacePermissionDenied("workspace permissions need repair") from exc
    except OSError as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, mode, exc)


def _prepare_workspace_write_file_owner(path: Path, mode: int) -> bool:
    """Own command output files by scanner so tools can truncate them reliably."""
    scanner_uid = _scanner_uid()
    appuser_gid = _appuser_gid()
    if scanner_uid is None:
        return False
    try:
        os.chown(path, scanner_uid, appuser_gid if appuser_gid is not None else -1)
        os.chmod(path, mode)
        return True
    except PermissionError:
        return _recreate_workspace_write_file_as_scanner(path, mode)
    except OSError as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, mode, exc)
        return False


def _recreate_workspace_write_file_as_scanner(path: Path, mode: int) -> bool:
    sudo_bin = _sudo_bin()
    if not sudo_bin or not _scanner_user_exists():
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return False
    try:
        subprocess.run(
            [sudo_bin, "-u", "scanner", "-g", "appuser", "touch", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        subprocess.run(
            [sudo_bin, "-u", "scanner", "-g", "appuser", "chmod", f"{mode:o}", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return True
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, mode, exc)
        return False


def _workspace_repair_dir_if_needed(path: Path, path_stat: os.stat_result) -> None:
    repair_mode = _workspace_child_dir_repair_mode(path_stat)
    if repair_mode is not None:
        _chmod_workspace_entry(path, repair_mode)


def _workspace_repair_file_if_needed(path: Path, path_stat: os.stat_result) -> None:
    repair_mode = _workspace_child_file_repair_mode(path_stat)
    if repair_mode is not None:
        _chmod_workspace_entry(path, repair_mode)


def _workspace_iterdir_after_permission_repair(path: Path, path_stat: os.stat_result | None = None) -> list[Path]:
    try:
        return list(path.iterdir())
    except PermissionError:
        if path_stat is None:
            path_stat = path.lstat()
        _workspace_repair_dir_if_needed(path, path_stat)
        try:
            return list(path.iterdir())
        except PermissionError as exc:
            raise WorkspacePermissionDenied("workspace folder is not readable") from exc


def _iter_workspace_entries(root: Path):
    root_stat = root.lstat()
    stack = [(root, root_stat)]
    while stack:
        current, current_stat = stack.pop()
        for child in _workspace_iterdir_after_permission_repair(current, current_stat):
            try:
                child_stat = child.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(child_stat.st_mode):
                raise InvalidWorkspacePath("workspace file symlinks are not allowed")
            if stat.S_ISDIR(child_stat.st_mode):
                _workspace_repair_dir_if_needed(child, child_stat)
                yield child, child_stat
                stack.append((child, child.lstat()))
            elif stat.S_ISREG(child_stat.st_mode):
                yield child, child_stat


def normalize_session_workspace_permissions(
    session_id: str,
    cfg: dict[str, Any] | None = None,
) -> None:
    """Repair command-created workspace modes so appuser can list and read them."""
    normalize_owner_workspace_permissions(_workspace_session_owner_context(session_id), cfg)


def normalize_owner_workspace_permissions(
    owner: OwnerContext | Any,
    cfg: dict[str, Any] | None = None,
) -> None:
    """Repair command-created workspace modes so appuser can list and read them."""
    root = ensure_owner_workspace(owner, cfg).resolve(strict=True)
    for path, path_stat in _iter_workspace_entries(root):
        if stat.S_ISREG(path_stat.st_mode):
            _workspace_repair_file_if_needed(path, path_stat)


def _repair_owner_workspace_relative_path_for_access(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
    *,
    include_final_file: bool = False,
) -> None:
    root = ensure_owner_workspace(owner, cfg).resolve(strict=True)
    rel = _validate_relative_path(relative_path)
    current = root
    for index, part in enumerate(rel.parts):
        current = current / part
        try:
            current_stat = current.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(current_stat.st_mode):
            raise InvalidWorkspacePath("workspace file symlinks are not allowed")
        is_final = index == len(rel.parts) - 1
        if stat.S_ISDIR(current_stat.st_mode):
            _workspace_repair_dir_if_needed(current, current_stat)
        elif include_final_file and is_final and stat.S_ISREG(current_stat.st_mode):
            _workspace_repair_file_if_needed(current, current_stat)


def _repair_workspace_relative_path_for_access(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
    *,
    include_final_file: bool = False,
) -> None:
    _repair_owner_workspace_relative_path_for_access(
        _workspace_session_owner_context(session_id),
        relative_path,
        cfg,
        include_final_file=include_final_file,
    )


def prepare_workspace_file_for_command(path: Path, *, mode: str) -> None:
    """Make a validated workspace path usable by the unprivileged scanner user."""
    if path.exists() and path.is_file():
        target_mode = WORKSPACE_COMMAND_WRITE_FILE_MODE if mode in {"write", "read_write"} else WORKSPACE_FILE_MODE
        if mode == "write" and _prepare_workspace_write_file_owner(path, target_mode):
            return
        try:
            _chmod_workspace_entry(path, target_mode)
        except WorkspacePermissionDenied:
            raise
        except OSError as exc:
            log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, target_mode, exc)


def prepare_workspace_directory_for_command(path: Path, *, mode: str) -> None:
    """Make a validated workspace directory usable by command-managed databases."""
    if path.exists() and not path.is_dir():
        raise InvalidWorkspacePath("workspace path is not a directory")
    sudo_bin = _sudo_bin()
    scanner_exists = _scanner_user_exists()
    if sudo_bin and scanner_exists:
        if path.exists():
            try:
                subprocess.run(
                    [sudo_bin, "-u", "scanner", "-g", "appuser", "chgrp", "appuser", str(path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                subprocess.run(
                    [sudo_bin, "-u", "scanner", "-g", "appuser", "chmod", f"{WORKSPACE_COMMAND_DIR_MODE:o}", str(path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                return
            except (subprocess.SubprocessError, OSError):
                try:
                    next(path.iterdir())
                except StopIteration:
                    path.rmdir()
                except OSError:
                    pass
        if not path.exists():
            if mode not in {"write", "read_write"}:
                raise WorkspaceFileNotFound(f"workspace directory not found: {path.name}")
            try:
                subprocess.run(
                    [sudo_bin, "-u", "scanner", "-g", "appuser", "mkdir", "-p", str(path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                subprocess.run(
                    [sudo_bin, "-u", "scanner", "-g", "appuser", "chgrp", "appuser", str(path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                subprocess.run(
                    [sudo_bin, "-u", "scanner", "-g", "appuser", "chmod", f"{WORKSPACE_COMMAND_DIR_MODE:o}", str(path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                return
            except (subprocess.SubprocessError, OSError) as exc:
                raise InvalidWorkspacePath("failed to prepare workspace directory for command") from exc
    if not path.exists():
        if mode not in {"write", "read_write"}:
            raise WorkspaceFileNotFound(f"workspace directory not found: {path.name}")
        path.mkdir(mode=WORKSPACE_COMMAND_DIR_MODE, parents=True, exist_ok=True)
    try:
        os.chmod(path, WORKSPACE_COMMAND_DIR_MODE)
    except OSError as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, WORKSPACE_COMMAND_DIR_MODE, exc)


def prepare_owner_workspace_target_for_command(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
    *,
    mode: str,
    kind: str = "file",
) -> Path:
    """Resolve and prepare a command-declared workspace target under owner quota rules."""
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    write_mode = mode in {"write", "read_write"}
    is_directory = kind == "directory"
    resolved = resolve_owner_workspace_path(
        owner,
        relative_path,
        cfg,
        ensure_parent=write_mode or is_directory,
    )
    if not write_mode:
        if is_directory:
            prepare_workspace_directory_for_command(resolved, mode=mode)
        else:
            if mode in {"read", "read_write"} and not resolved.is_file():
                raise WorkspaceFileNotFound(f"workspace file not found: {relative_path}")
            prepare_workspace_file_for_command(resolved, mode=mode)
        return resolved

    with workspace_owner_write_lock(owner):
        if is_directory:
            prepare_workspace_directory_for_command(resolved, mode=mode)
            return resolved
        if mode == "read_write" and not resolved.is_file():
            raise WorkspaceFileNotFound(f"workspace file not found: {relative_path}")
        reserve_bytes = 0 if resolved.exists() else 1
        _check_owner_write_limits(owner, resolved, reserve_bytes, settings, cfg)
        if not resolved.exists():
            resolved.touch(mode=WORKSPACE_COMMAND_WRITE_FILE_MODE, exist_ok=True)
        prepare_workspace_file_for_command(resolved, mode=mode)
    return resolved


def owner_workspace_usage(owner: OwnerContext | Any, cfg: dict[str, Any] | None = None) -> WorkspaceUsage:
    root = ensure_owner_workspace(owner, cfg).resolve(strict=True)
    touch_owner_workspace(owner, cfg)
    bytes_used = 0
    file_count = 0
    for path, path_stat in _iter_workspace_entries(root):
        if stat.S_ISREG(path_stat.st_mode):
            file_count += 1
            bytes_used += path_stat.st_size
    return WorkspaceUsage(bytes_used=bytes_used, file_count=file_count)


def workspace_usage(session_id: str, cfg: dict[str, Any] | None = None) -> WorkspaceUsage:
    return owner_workspace_usage(_workspace_session_owner_context(session_id), cfg)


def list_owner_workspace_files(owner: OwnerContext | Any, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    root = ensure_owner_workspace(owner, cfg).resolve(strict=True)
    touch_owner_workspace(owner, cfg)
    items: list[dict[str, Any]] = []
    for path, path_stat in _iter_workspace_entries(root):
        if not stat.S_ISREG(path_stat.st_mode):
            continue
        items.append({
            "path": path.relative_to(root).as_posix(),
            "size": path_stat.st_size,
            "mtime": datetime.fromtimestamp(path_stat.st_mtime, timezone.utc).isoformat(),
        })
    return sorted(items, key=lambda item: str(item["path"]))


def list_workspace_files(session_id: str, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return list_owner_workspace_files(_workspace_session_owner_context(session_id), cfg)


def list_owner_workspace_directories(owner: OwnerContext | Any, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    root = ensure_owner_workspace(owner, cfg).resolve(strict=True)
    touch_owner_workspace(owner, cfg)
    items: list[dict[str, Any]] = []
    for path, path_stat in _iter_workspace_entries(root):
        if not stat.S_ISDIR(path_stat.st_mode):
            continue
        items.append({
            "path": path.relative_to(root).as_posix(),
            "mtime": datetime.fromtimestamp(path_stat.st_mtime, timezone.utc).isoformat(),
        })
    return sorted(items, key=lambda item: str(item["path"]))


def list_workspace_directories(session_id: str, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return list_owner_workspace_directories(_workspace_session_owner_context(session_id), cfg)


def create_owner_workspace_directory(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    _repair_owner_workspace_relative_path_for_access(owner, relative_path, cfg)
    path = resolve_owner_workspace_path(owner, relative_path, cfg, ensure_parent=True)
    if path.exists() and not path.is_dir():
        raise InvalidWorkspacePath("workspace path is not a directory")
    path.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
    try:
        os.chmod(path, WORKSPACE_DIR_MODE)
    except OSError as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, WORKSPACE_DIR_MODE, exc)
    return {"path": _validate_relative_path(relative_path).as_posix()}


def create_workspace_directory(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return create_owner_workspace_directory(_workspace_session_owner_context(session_id), relative_path, cfg)


def _check_owner_write_limits(
    owner: OwnerContext | Any,
    destination: Path,
    new_size: int,
    settings: WorkspaceSettings,
    cfg: dict[str, Any] | None,
) -> None:
    if new_size > settings.max_file_bytes:
        app_metrics.record_workspace_quota_rejection()
        raise WorkspaceQuotaExceeded("file exceeds workspace max file size")
    usage = owner_workspace_usage(owner, cfg)
    try:
        destination_stat = destination.lstat()
    except FileNotFoundError:
        destination_stat = None
    if destination_stat is not None and stat.S_ISLNK(destination_stat.st_mode):
        raise InvalidWorkspacePath("workspace file symlinks are not allowed")
    existing_size = destination_stat.st_size if destination_stat and stat.S_ISREG(destination_stat.st_mode) else 0
    new_file_count = usage.file_count + (0 if destination_stat is not None else 1)
    if new_file_count > settings.max_files:
        app_metrics.record_workspace_quota_rejection()
        raise WorkspaceQuotaExceeded("workspace file count limit exceeded")
    projected = usage.bytes_used - existing_size + new_size
    if projected > settings.quota_bytes:
        app_metrics.record_workspace_quota_rejection()
        raise WorkspaceQuotaExceeded("workspace file quota exceeded")


def _check_write_limits(
    session_id: str,
    destination: Path,
    new_size: int,
    settings: WorkspaceSettings,
    cfg: dict[str, Any] | None,
) -> None:
    _check_owner_write_limits(_workspace_session_owner_context(session_id), destination, new_size, settings, cfg)


@contextmanager
def workspace_owner_write_lock(owner: OwnerContext | Any):
    """Serialize quota-gated writes; Postgres locks per owner, SQLite locks all writers."""
    context = _coerce_owner_context(owner)
    from core import database  # noqa: PLC0415
    from core.database_backend import DatabaseBackend, postgres_advisory_lock_id  # noqa: PLC0415

    namespace = f"darklab_shell_workspace:{context.scope}:{context.owner_id}"
    with database.db_connect() as conn:
        if database.DB_BACKEND == DatabaseBackend.POSTGRES:
            conn.execute("SELECT pg_advisory_xact_lock(?)", (postgres_advisory_lock_id(namespace),))
        else:
            conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def write_owner_workspace_text_file(
    owner: OwnerContext | Any,
    relative_path: str,
    text: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    _repair_owner_workspace_relative_path_for_access(owner, relative_path, cfg)
    destination = resolve_owner_workspace_path(owner, relative_path, cfg, ensure_parent=True)
    encoded = str(text or "").encode("utf-8")
    with workspace_owner_write_lock(owner):
        _check_owner_write_limits(owner, destination, len(encoded), settings, cfg)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(destination.parent)) as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(encoded)
            os.chmod(tmp_path, WORKSPACE_FILE_MODE)
            tmp_path.replace(destination)
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
    return {
        "path": _validate_relative_path(relative_path).as_posix(),
        "size": len(encoded),
    }


def write_workspace_text_file(
    session_id: str,
    relative_path: str,
    text: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return write_owner_workspace_text_file(_workspace_session_owner_context(session_id), relative_path, text, cfg)


def read_owner_workspace_text_file(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> str:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    _repair_owner_workspace_relative_path_for_access(owner, relative_path, cfg, include_final_file=True)
    path = resolve_owner_workspace_path(owner, relative_path, cfg)
    fd, file_stat = _open_workspace_file_no_follow(path)
    if file_stat.st_size > settings.max_file_bytes:
        os.close(fd)
        raise WorkspaceQuotaExceeded("file exceeds workspace max file size")
    with os.fdopen(fd, "rb") as handle:
        content = handle.read()
    if b"\x00" in content:
        raise WorkspaceBinaryFile("file appears to be binary; download it instead")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceBinaryFile("file is not valid UTF-8 text; download it instead") from exc


def read_workspace_text_file(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> str:
    return read_owner_workspace_text_file(_workspace_session_owner_context(session_id), relative_path, cfg)


def delete_owner_workspace_file(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> None:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    _repair_owner_workspace_relative_path_for_access(owner, relative_path, cfg, include_final_file=True)
    path = resolve_owner_workspace_path(owner, relative_path, cfg)
    try:
        path_stat = path.lstat()
    except FileNotFoundError as exc:
        raise WorkspaceFileNotFound("workspace file was not found") from exc
    if stat.S_ISLNK(path_stat.st_mode):
        raise InvalidWorkspacePath("workspace file symlinks are not allowed")
    if not stat.S_ISREG(path_stat.st_mode):
        raise WorkspaceFileNotFound("workspace file was not found")
    try:
        path.unlink()
        return
    except PermissionError:
        sudo_bin = _sudo_bin()
        if not sudo_bin or not _scanner_user_exists():
            raise
        subprocess.run(
            [sudo_bin, "-u", "scanner", "-g", "appuser", "rm", "--", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )


def delete_workspace_file(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> None:
    delete_owner_workspace_file(_workspace_session_owner_context(session_id), relative_path, cfg)


def _workspace_directory_file_count(path: Path) -> int:
    _reject_symlinks_under(path)
    return sum(1 for child in path.rglob("*") if child.is_file())


def _remove_workspace_directory(path: Path) -> None:
    try:
        shutil.rmtree(path)
        return
    except PermissionError:
        sudo_bin = _sudo_bin()
        if not sudo_bin or not _scanner_user_exists():
            raise
        subprocess.run(
            [sudo_bin, "-u", "scanner", "-g", "appuser", "rm", "-rf", "--", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )


def _log_workspace_cleanup_skip(path: Path, exc: BaseException) -> None:
    log.warning(
        "WORKSPACE_CLEANUP_SKIP path=%s reason=%s error=%s",
        path,
        exc.__class__.__name__,
        exc,
        extra={"path": str(path), "reason": exc.__class__.__name__},
    )


def _repair_workspace_tree_for_cleanup(path: Path) -> None:
    def on_walk_error(exc: OSError) -> None:
        raise exc

    for dirpath, dirnames, filenames in os.walk(path, topdown=True, onerror=on_walk_error):
        current = Path(dirpath)
        try:
            _workspace_repair_dir_if_needed(current, current.lstat())
        except FileNotFoundError:
            continue
        for name in list(dirnames):
            child = current / name
            try:
                _workspace_repair_dir_if_needed(child, child.lstat())
            except FileNotFoundError:
                dirnames.remove(name)
        for name in filenames:
            child = current / name
            try:
                _workspace_repair_file_if_needed(child, child.lstat())
            except FileNotFoundError:
                continue


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
        except OSError:
            continue


def _scanner_owned_cleanup_targets(path: Path) -> list[Path]:
    targets: list[Path] = []
    try:
        root_stat = path.lstat()
    except FileNotFoundError:
        return targets
    if _is_scanner_owned(root_stat):
        return [path]

    def on_walk_error(exc: OSError) -> None:
        raise exc

    for dirpath, dirnames, filenames in os.walk(path, topdown=True, onerror=on_walk_error):
        current = Path(dirpath)
        for name in list(dirnames):
            child = current / name
            try:
                child_stat = child.lstat()
            except FileNotFoundError:
                dirnames.remove(name)
                continue
            if _is_scanner_owned(child_stat):
                targets.append(child)
                dirnames.remove(name)
        for name in filenames:
            child = current / name
            try:
                child_stat = child.lstat()
            except FileNotFoundError:
                continue
            if _is_scanner_owned(child_stat):
                targets.append(child)
    return targets


def _remove_workspace_cleanup_target(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        _remove_workspace_directory(path)
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _remove_inactive_workspace_directory(path: Path) -> None:
    try:
        shutil.rmtree(path)
        return
    except OSError:
        try:
            _repair_workspace_tree_for_cleanup(path)
        except OSError:
            _remove_unreadable_direct_child_directories(path)
    try:
        shutil.rmtree(path)
        return
    except OSError:
        try:
            targets = _scanner_owned_cleanup_targets(path)
        except OSError:
            _remove_unreadable_direct_child_directories(path)
            targets = []
        for target in targets:
            _remove_workspace_cleanup_target(target)
    shutil.rmtree(path)


def _workspace_path_kind_and_count(path: Path) -> tuple[str, int]:
    try:
        path_stat = path.lstat()
    except FileNotFoundError as exc:
        raise WorkspacePathNotFound("workspace file or folder was not found") from exc
    if stat.S_ISLNK(path_stat.st_mode):
        raise InvalidWorkspacePath("workspace file symlinks are not allowed")
    if stat.S_ISREG(path_stat.st_mode):
        return "file", 1
    if stat.S_ISDIR(path_stat.st_mode):
        return "directory", _workspace_directory_file_count(path)
    raise WorkspacePathNotFound("workspace file or folder was not found")


def workspace_path_has_glob(relative_path: str) -> bool:
    return "*" in str(relative_path or "")


def _workspace_glob_matches(pattern: PurePosixPath, path: PurePosixPath) -> bool:
    pattern_parts = pattern.parts
    path_parts = path.parts
    if len(pattern_parts) != len(path_parts):
        return False
    return all(fnmatch.fnmatchcase(path_part, pattern_part) for pattern_part, path_part in zip(pattern_parts, path_parts))


def expand_owner_workspace_path_pattern(
    owner: OwnerContext | Any,
    relative_pattern: str,
    cfg: dict[str, Any] | None = None,
    *,
    kind: str = "any",
) -> list[WorkspacePathMatch]:
    root = ensure_owner_workspace(owner, cfg).resolve(strict=True)
    touch_owner_workspace(owner, cfg)
    pattern = _validate_relative_path(relative_pattern)
    normalized_kind = str(kind or "any").strip().lower()
    matches: list[WorkspacePathMatch] = []
    for candidate, candidate_stat in sorted(
        _iter_workspace_entries(root),
        key=lambda item: item[0].relative_to(root).as_posix(),
    ):
        relative = PurePosixPath(candidate.relative_to(root).as_posix())
        if not _workspace_glob_matches(pattern, relative):
            continue
        if stat.S_ISREG(candidate_stat.st_mode):
            candidate_kind, file_count = "file", 1
        elif stat.S_ISDIR(candidate_stat.st_mode):
            candidate_kind, file_count = "directory", _workspace_directory_file_count(candidate)
        else:
            continue
        if normalized_kind != "any" and candidate_kind != normalized_kind:
            continue
        matches.append(WorkspacePathMatch(
            path=relative.as_posix(),
            kind=candidate_kind,
            file_count=file_count,
        ))
    return matches


def expand_workspace_path_pattern(
    session_id: str,
    relative_pattern: str,
    cfg: dict[str, Any] | None = None,
    *,
    kind: str = "any",
) -> list[WorkspacePathMatch]:
    return expand_owner_workspace_path_pattern(
        _workspace_session_owner_context(session_id),
        relative_pattern,
        cfg,
        kind=kind,
    )


def owner_workspace_path_info(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    _repair_owner_workspace_relative_path_for_access(owner, relative_path, cfg, include_final_file=True)
    path = resolve_owner_workspace_path(owner, relative_path, cfg)
    normalized = _validate_relative_path(relative_path).as_posix()
    kind, file_count = _workspace_path_kind_and_count(path)
    if kind == "file":
        return {"path": normalized, "kind": "file", "file_count": 1, "size": path.stat().st_size}
    return {"path": normalized, "kind": "directory", "file_count": file_count}


def workspace_path_info(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return owner_workspace_path_info(_workspace_session_owner_context(session_id), relative_path, cfg)


def delete_owner_workspace_path(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> WorkspaceDeleteResult:
    info = owner_workspace_path_info(owner, relative_path, cfg)
    path = resolve_owner_workspace_path(owner, relative_path, cfg)
    if info["kind"] == "file":
        delete_owner_workspace_file(owner, relative_path, cfg)
    elif info["kind"] == "directory":
        _remove_workspace_directory(path)
    else:
        raise WorkspacePathNotFound("workspace file or folder was not found")
    app_metrics.record_workspace_evictions(max(1, int(info["file_count"] or 0)), "manual")
    return WorkspaceDeleteResult(
        path=str(info["path"]),
        kind=str(info["kind"]),
        file_count=int(info["file_count"]),
    )


def delete_workspace_path(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> WorkspaceDeleteResult:
    return delete_owner_workspace_path(_workspace_session_owner_context(session_id), relative_path, cfg)


def _move_workspace_path_direct(source: Path, destination: Path) -> None:
    try:
        shutil.move(str(source), str(destination))
        return
    except PermissionError:
        sudo_bin = _sudo_bin()
        if not sudo_bin or not _scanner_user_exists():
            raise
        _remove_partial_move_destination(source, destination)
        try:
            subprocess.run(
                [sudo_bin, "-u", "scanner", "-g", "appuser", "mv", "--", str(source), str(destination)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            _remove_partial_move_destination(source, destination)
            raise WorkspacePermissionDenied("workspace path could not be moved") from exc


def _remove_partial_move_destination(source: Path, destination: Path) -> None:
    if not source.exists() or not destination.exists():
        return
    try:
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    except OSError as exc:
        raise WorkspacePermissionDenied("workspace path could not be moved") from exc


def move_owner_workspace_path(
    owner: OwnerContext | Any,
    source_relative_path: str,
    destination_relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> WorkspaceMoveResult:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    _repair_owner_workspace_relative_path_for_access(owner, source_relative_path, cfg, include_final_file=True)
    if destination_relative_path not in {"", "/"}:
        destination_parent = PurePosixPath(destination_relative_path or "").parent
        if destination_parent != PurePosixPath("."):
            _repair_owner_workspace_relative_path_for_access(owner, destination_parent.as_posix(), cfg)
    root = ensure_owner_workspace(owner, cfg).resolve(strict=True)
    source_path = resolve_owner_workspace_path(owner, source_relative_path, cfg)
    source_normalized = _validate_relative_path(source_relative_path).as_posix()
    raw_destination = str(destination_relative_path or "")
    kind, file_count = _workspace_path_kind_and_count(source_path)
    _reject_symlinks_under(source_path)

    if raw_destination in {"", "/"}:
        destination_path = root
        destination_normalized = ""
    else:
        destination_normalized = _validate_relative_path(destination_relative_path).as_posix()
        destination_path = resolve_owner_workspace_path(owner, destination_relative_path, cfg)
    if destination_path.exists():
        if not destination_path.is_dir():
            raise InvalidWorkspacePath("destination already exists")
        final_destination = destination_path / source_path.name
        if destination_normalized:
            final_destination_relative = (PurePosixPath(destination_normalized) / source_path.name).as_posix()
        else:
            final_destination_relative = source_path.name
    else:
        final_destination = destination_path
        final_destination_relative = destination_normalized

    if final_destination.exists():
        raise InvalidWorkspacePath("destination already exists")
    if not _is_relative_to(final_destination.resolve(strict=False), root):
        raise InvalidWorkspacePath("file path escapes the workspace directory")
    if source_path.resolve(strict=False) == final_destination.resolve(strict=False):
        raise InvalidWorkspacePath("source and destination are the same")
    if kind == "directory":
        source_resolved = source_path.resolve(strict=True)
        final_resolved = final_destination.resolve(strict=False)
        if _is_relative_to(final_resolved, source_resolved):
            raise InvalidWorkspacePath("cannot move a folder into itself")

    final_destination.parent.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
    _chmod_workspace_dir(final_destination.parent)
    with workspace_owner_write_lock(owner):
        _move_workspace_path_direct(source_path, final_destination)
    touch_owner_workspace(owner, cfg)
    return WorkspaceMoveResult(
        source=source_normalized,
        destination=final_destination_relative,
        kind=kind,
        file_count=file_count,
    )


def move_workspace_path(
    session_id: str,
    source_relative_path: str,
    destination_relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> WorkspaceMoveResult:
    return move_owner_workspace_path(
        _workspace_session_owner_context(session_id),
        source_relative_path,
        destination_relative_path,
        cfg,
    )


def _chmod_workspace_dir(path: Path) -> None:
    try:
        os.chmod(path, WORKSPACE_DIR_MODE)
    except OSError as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, WORKSPACE_DIR_MODE, exc)


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


def migrate_session_workspace(
    from_session_id: str,
    to_session_id: str,
    cfg: dict[str, Any] | None = None,
) -> WorkspaceMigrationResult:
    """Merge one session workspace into another without overwriting files."""
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

    usage = workspace_usage(to_session_id, cfg)
    bytes_used = usage.bytes_used
    file_count = usage.file_count
    migrated_files = 0
    skipped_files = 0
    migrated_directories = 0
    skipped_directories = 0
    migrated_file_paths: list[str] = []
    skipped_file_paths: list[str] = []

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
            skipped_directories += 1
            continue
        if _target_parent_has_file(destination, target_dir):
            skipped_directories += 1
            continue
        try:
            target_dir.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
            _chmod_workspace_dir(target_dir)
            migrated_directories += 1
        except OSError:
            skipped_directories += 1

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
            skipped_files += 1
            skipped_file_paths.append(rel_path)
            continue
        if (
            target_file.exists()
            or _target_parent_has_file(destination, target_file)
            or size > settings.max_file_bytes
            or file_count + 1 > settings.max_files
            or bytes_used + size > settings.quota_bytes
        ):
            skipped_files += 1
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
            skipped_files += 1
            skipped_file_paths.append(rel_path)

    _cleanup_empty_workspace_dirs(source)
    touch_session_workspace(to_session_id, cfg)
    return WorkspaceMigrationResult(
        migrated_files=migrated_files,
        skipped_files=skipped_files,
        migrated_directories=migrated_directories,
        skipped_directories=skipped_directories,
        migrated_file_paths=tuple(migrated_file_paths),
        skipped_file_paths=tuple(skipped_file_paths),
    )


def cleanup_inactive_workspaces(
    cfg: dict[str, Any] | None = None,
    *,
    now: float | None = None,
    skip_session_id: str | None = None,
) -> int:
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
