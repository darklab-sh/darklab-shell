"""App-mediated workspace helpers.

This module intentionally does not expose shell navigation or redirection.
Every file operation resolves a user-facing relative path inside one hashed
workspace directory and enforces quota limits before writes.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import fnmatch
from functools import lru_cache
import logging
import os
from pathlib import Path, PurePosixPath
import pwd
import shutil
import stat
import subprocess
import tempfile
from typing import Any, BinaryIO

from services.teams.scope import OwnerContext
from services.workspace.modes import (
    WORKSPACE_COMMAND_DIR_MODE as WORKSPACE_COMMAND_DIR_MODE,
    WORKSPACE_COMMAND_WRITE_FILE_MODE as WORKSPACE_COMMAND_WRITE_FILE_MODE,
    WORKSPACE_DIR_MODE as WORKSPACE_DIR_MODE,
    WORKSPACE_FILE_MODE as WORKSPACE_FILE_MODE,
)
from services.workspace.models import (
    InvalidWorkspacePath,
    WorkspaceBinaryFile,
    WorkspaceDeleteResult,
    WorkspaceDisabled as WorkspaceDisabled,
    WorkspaceError as WorkspaceError,
    WorkspaceFileNotFound,
    WorkspaceMigrationResult,
    WorkspaceMoveResult,
    WorkspacePathMatch,
    WorkspacePathNotFound,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
    WorkspaceSettings,
    WorkspaceUsage,
)
from services.workspace.paths import (
    ensure_owner_workspace as ensure_owner_workspace,
    ensure_session_workspace as ensure_session_workspace,
    is_relative_to as _is_relative_to,
    owner_workspace_dir as owner_workspace_dir,
    reject_symlinks_under as _reject_symlinks_under,
    resolve_owner_workspace_path as resolve_owner_workspace_path,
    resolve_workspace_path as resolve_workspace_path,
    session_workspace_dir as session_workspace_dir,
    touch_owner_workspace as touch_owner_workspace,
    touch_session_workspace as touch_session_workspace,
    validate_relative_path as _validate_relative_path,
)
from services.workspace.settings import (
    coerce_owner_context as _coerce_owner_context,
    owner_workspace_name as owner_workspace_name,
    require_enabled as _require_enabled,
    session_workspace_name as session_workspace_name,
    workspace_root as workspace_root,
    workspace_session_owner_context as _workspace_session_owner_context,
    workspace_settings as workspace_settings,
)
from services.workspace.metadata import (
    delete_workspace_file_metadata,
    move_workspace_file_metadata,
    workspace_file_metadata_by_path,
)

log = logging.getLogger(__name__)


class _MetricsProxy:
    def __getattr__(self, name: str) -> Any:
        from services import metrics  # noqa: PLC0415
        return getattr(metrics, name)


app_metrics = _MetricsProxy()

__all__ = [
    "delete_workspace_file_metadata",
    "move_workspace_file_metadata",
    "workspace_file_metadata_by_path",
]


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
    from core.database_access import get_db_backend, get_db_connect  # noqa: PLC0415
    from core.database_backend import DatabaseBackend, postgres_advisory_lock_id  # noqa: PLC0415

    namespace = f"darklab_shell_workspace:{context.scope}:{context.owner_id}"
    with get_db_connect()() as conn:
        if get_db_backend() == DatabaseBackend.POSTGRES:
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
        command = [sudo_bin, "-u", "scanner", "-g", "appuser", "rm", "-rf", "--", str(path)]
        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=5)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            error = str(getattr(exc, "stderr", "") or exc).strip()[:500]
            raise PermissionError(f"scanner cleanup helper failed: {error}") from exc


def _repair_workspace_tree_for_cleanup(path: Path) -> None:
    from services.workspace.maintenance import _repair_workspace_tree_for_cleanup as _repair_cleanup_tree

    _repair_cleanup_tree(path)


def _remove_unreadable_direct_child_directories(path: Path) -> None:
    from services.workspace.maintenance import (
        _remove_unreadable_direct_child_directories as _remove_unreadable_cleanup_dirs,
    )

    _remove_unreadable_cleanup_dirs(path)


def _scanner_owned_cleanup_targets(path: Path) -> list[Path]:
    from services.workspace.maintenance import _scanner_owned_cleanup_targets as _scanner_cleanup_targets

    return _scanner_cleanup_targets(path)


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


def migrate_session_workspace(
    from_session_id: str,
    to_session_id: str,
    cfg: dict[str, Any] | None = None,
) -> WorkspaceMigrationResult:
    from services.workspace.maintenance import migrate_session_workspace as _migrate_session_workspace

    return _migrate_session_workspace(from_session_id, to_session_id, cfg)


def cleanup_inactive_workspaces(
    cfg: dict[str, Any] | None = None,
    *,
    now: float | None = None,
    skip_session_id: str | None = None,
) -> int:
    from services.workspace.maintenance import cleanup_inactive_workspaces as _cleanup_inactive_workspaces

    return _cleanup_inactive_workspaces(cfg, now=now, skip_session_id=skip_session_id)
