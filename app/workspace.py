"""App-mediated per-session workspace helpers.

This module intentionally does not expose shell navigation or redirection.
Every file operation resolves a user-facing relative path inside one hashed
session directory and enforces quota limits before writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import logging
import os
from pathlib import Path, PurePosixPath
import pwd
import shutil
import stat
import subprocess  # nosec B404
import tempfile
from typing import Any, BinaryIO

from config import CFG

log = logging.getLogger(__name__)

# Session directories are sticky + setgid so files created by scanner tools
# inherit the shared appuser group without becoming world-readable.
WORKSPACE_DIR_MODE = 0o3730
WORKSPACE_FILE_MODE = 0o640
WORKSPACE_COMMAND_WRITE_FILE_MODE = 0o660
WORKSPACE_COMMAND_DIR_MODE = 0o3770


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
class WorkspaceMigrationResult:
    migrated_files: int = 0
    skipped_files: int = 0
    migrated_directories: int = 0
    skipped_directories: int = 0


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


def _require_enabled(settings: WorkspaceSettings) -> None:
    if not settings.enabled:
        raise WorkspaceDisabled("Files are disabled on this instance")


def session_workspace_name(session_id: str) -> str:
    digest = hashlib.sha256(str(session_id or "anonymous").encode("utf-8")).hexdigest()
    return f"sess_{digest[:32]}"


def workspace_root(settings: WorkspaceSettings) -> Path:
    return settings.root.resolve(strict=False)


def session_workspace_dir(session_id: str, cfg: dict[str, Any] | None = None) -> Path:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    return workspace_root(settings) / session_workspace_name(session_id)


def ensure_session_workspace(session_id: str, cfg: dict[str, Any] | None = None) -> Path:
    path = session_workspace_dir(session_id, cfg)
    path.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
    try:
        os.chmod(path, WORKSPACE_DIR_MODE)
    except OSError as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, WORKSPACE_DIR_MODE, exc)
    return path


def touch_session_workspace(session_id: str, cfg: dict[str, Any] | None = None) -> None:
    """Mark the session workspace active without exposing that detail to users."""
    path = ensure_session_workspace(session_id, cfg)
    try:
        os.utime(path, None)
    except OSError:
        pass


def _validate_relative_path(relative_path: str) -> PurePosixPath:
    raw = str(relative_path or "").strip()
    if not raw:
        raise InvalidWorkspacePath("file name is required")
    if "\x00" in raw or "\\" in raw:
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
            raise InvalidWorkspacePath("session file symlinks are not allowed")


def _reject_symlinks_under(path: Path) -> None:
    if path.is_symlink():
        raise InvalidWorkspacePath("session file symlinks are not allowed")
    if not path.is_dir():
        return
    for child in path.rglob("*"):
        if child.is_symlink():
            raise InvalidWorkspacePath("session file symlinks are not allowed")


def resolve_workspace_path(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
    *,
    ensure_parent: bool = False,
) -> Path:
    root = ensure_session_workspace(session_id, cfg).resolve(strict=True)
    touch_session_workspace(session_id, cfg)
    rel = _validate_relative_path(relative_path)
    candidate = root.joinpath(*rel.parts)
    _reject_symlink_components(root, candidate)
    parent = candidate.parent
    if parent.exists():
        resolved_parent = parent.resolve(strict=True)
        if not _is_relative_to(resolved_parent, root):
            raise InvalidWorkspacePath("file path escapes the session directory")
    elif ensure_parent:
        parent.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
        try:
            os.chmod(parent, WORKSPACE_DIR_MODE)
        except OSError as exc:
            log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", parent, WORKSPACE_DIR_MODE, exc)
        resolved_parent = parent.resolve(strict=True)
        if not _is_relative_to(resolved_parent, root):
            raise InvalidWorkspacePath("file path escapes the session directory")
    else:
        raise InvalidWorkspacePath("parent directory does not exist")
    resolved = resolved_parent / candidate.name
    if not _is_relative_to(resolved.resolve(strict=False), root):
        raise InvalidWorkspacePath("file path escapes the session directory")
    return resolved


def _is_final_symlink_error(exc: OSError) -> bool:
    return exc.errno in {errno.ELOOP, getattr(errno, "EMLINK", errno.ELOOP)}


def _open_workspace_file_no_follow(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError as exc:
        raise WorkspaceFileNotFound("session file was not found") from exc
    except OSError as exc:
        if _is_final_symlink_error(exc):
            raise InvalidWorkspacePath("session file symlinks are not allowed") from exc
        raise
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise WorkspaceFileNotFound("session file was not found")
        return fd, file_stat
    except Exception:
        os.close(fd)
        raise


def open_workspace_file_for_download(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> BinaryIO:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    path = resolve_workspace_path(session_id, relative_path, cfg)
    fd, _ = _open_workspace_file_no_follow(path)
    return os.fdopen(fd, "rb")


def prepare_workspace_file_for_command(path: Path, *, mode: str) -> None:
    """Make a validated workspace path usable by the unprivileged scanner user."""
    if path.exists() and path.is_file():
        target_mode = WORKSPACE_COMMAND_WRITE_FILE_MODE if mode in {"write", "read_write"} else WORKSPACE_FILE_MODE
        try:
            os.chmod(path, target_mode)
        except OSError as exc:
            log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, target_mode, exc)


def prepare_workspace_directory_for_command(path: Path, *, mode: str) -> None:
    """Make a validated workspace directory usable by command-managed databases."""
    if path.exists() and not path.is_dir():
        raise InvalidWorkspacePath("session path is not a directory")
    sudo_bin = shutil.which("sudo")
    scanner_exists = True
    try:
        pwd.getpwnam("scanner")
    except KeyError:
        scanner_exists = False
    if sudo_bin and scanner_exists:
        if path.exists():
            try:
                subprocess.run(
                    [sudo_bin, "-u", "scanner", "-g", "appuser", "chmod", f"{WORKSPACE_COMMAND_DIR_MODE:o}", str(path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )  # nosec B603
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
                raise WorkspaceFileNotFound(f"session directory not found: {path.name}")
            try:
                subprocess.run(
                    [sudo_bin, "-u", "scanner", "-g", "appuser", "mkdir", "-p", str(path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )  # nosec B603
                subprocess.run(
                    [sudo_bin, "-u", "scanner", "-g", "appuser", "chmod", f"{WORKSPACE_COMMAND_DIR_MODE:o}", str(path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )  # nosec B603
                return
            except (subprocess.SubprocessError, OSError) as exc:
                raise InvalidWorkspacePath("failed to prepare session directory for command") from exc
    if not path.exists():
        if mode not in {"write", "read_write"}:
            raise WorkspaceFileNotFound(f"session directory not found: {path.name}")
        path.mkdir(mode=WORKSPACE_COMMAND_DIR_MODE, parents=True, exist_ok=True)
    try:
        os.chmod(path, WORKSPACE_COMMAND_DIR_MODE)
    except OSError as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, WORKSPACE_COMMAND_DIR_MODE, exc)


def workspace_usage(session_id: str, cfg: dict[str, Any] | None = None) -> WorkspaceUsage:
    root = ensure_session_workspace(session_id, cfg).resolve(strict=True)
    touch_session_workspace(session_id, cfg)
    bytes_used = 0
    file_count = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise InvalidWorkspacePath("session file symlinks are not allowed")
        if path.is_file():
            file_count += 1
            bytes_used += path.stat().st_size
    return WorkspaceUsage(bytes_used=bytes_used, file_count=file_count)


def list_workspace_files(session_id: str, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    root = ensure_session_workspace(session_id, cfg).resolve(strict=True)
    touch_session_workspace(session_id, cfg)
    items: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise InvalidWorkspacePath("session file symlinks are not allowed")
        if not path.is_file():
            continue
        stat = path.stat()
        items.append({
            "path": path.relative_to(root).as_posix(),
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })
    return sorted(items, key=lambda item: str(item["path"]))


def list_workspace_directories(session_id: str, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    root = ensure_session_workspace(session_id, cfg).resolve(strict=True)
    touch_session_workspace(session_id, cfg)
    items: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise InvalidWorkspacePath("session file symlinks are not allowed")
        if not path.is_dir():
            continue
        stat = path.stat()
        items.append({
            "path": path.relative_to(root).as_posix(),
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })
    return sorted(items, key=lambda item: str(item["path"]))


def create_workspace_directory(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    path = resolve_workspace_path(session_id, relative_path, cfg, ensure_parent=True)
    if path.exists() and not path.is_dir():
        raise InvalidWorkspacePath("session path is not a directory")
    path.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
    try:
        os.chmod(path, WORKSPACE_DIR_MODE)
    except OSError as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, WORKSPACE_DIR_MODE, exc)
    return {"path": _validate_relative_path(relative_path).as_posix()}


def _check_write_limits(
    session_id: str,
    destination: Path,
    new_size: int,
    settings: WorkspaceSettings,
    cfg: dict[str, Any] | None,
) -> None:
    if new_size > settings.max_file_bytes:
        raise WorkspaceQuotaExceeded("file exceeds session max file size")
    usage = workspace_usage(session_id, cfg)
    try:
        destination_stat = destination.lstat()
    except FileNotFoundError:
        destination_stat = None
    if destination_stat is not None and stat.S_ISLNK(destination_stat.st_mode):
        raise InvalidWorkspacePath("session file symlinks are not allowed")
    existing_size = destination_stat.st_size if destination_stat and stat.S_ISREG(destination_stat.st_mode) else 0
    new_file_count = usage.file_count + (0 if destination_stat is not None else 1)
    if new_file_count > settings.max_files:
        raise WorkspaceQuotaExceeded("session file count limit exceeded")
    projected = usage.bytes_used - existing_size + new_size
    if projected > settings.quota_bytes:
        raise WorkspaceQuotaExceeded("session file quota exceeded")


def write_workspace_text_file(
    session_id: str,
    relative_path: str,
    text: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    destination = resolve_workspace_path(session_id, relative_path, cfg, ensure_parent=True)
    encoded = str(text or "").encode("utf-8")
    _check_write_limits(session_id, destination, len(encoded), settings, cfg)
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


def read_workspace_text_file(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> str:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    path = resolve_workspace_path(session_id, relative_path, cfg)
    fd, file_stat = _open_workspace_file_no_follow(path)
    if file_stat.st_size > settings.max_file_bytes:
        os.close(fd)
        raise WorkspaceQuotaExceeded("file exceeds session max file size")
    with os.fdopen(fd, "rb") as handle:
        content = handle.read()
    if b"\x00" in content:
        raise WorkspaceBinaryFile("file appears to be binary; download it instead")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceBinaryFile("file is not valid UTF-8 text; download it instead") from exc


def delete_workspace_file(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> None:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    path = resolve_workspace_path(session_id, relative_path, cfg)
    try:
        path_stat = path.lstat()
    except FileNotFoundError as exc:
        raise WorkspaceFileNotFound("session file was not found") from exc
    if stat.S_ISLNK(path_stat.st_mode):
        raise InvalidWorkspacePath("session file symlinks are not allowed")
    if not stat.S_ISREG(path_stat.st_mode):
        raise WorkspaceFileNotFound("session file was not found")
    try:
        path.unlink()
        return
    except PermissionError:
        sudo_bin = shutil.which("sudo")
        if not sudo_bin:
            raise
        try:
            pwd.getpwnam("scanner")
        except KeyError:
            raise
        subprocess.run(
            [sudo_bin, "-u", "scanner", "-g", "appuser", "rm", "--", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )  # nosec B603


def _workspace_directory_file_count(path: Path) -> int:
    _reject_symlinks_under(path)
    return sum(1 for child in path.rglob("*") if child.is_file())


def _remove_workspace_directory(path: Path) -> None:
    try:
        shutil.rmtree(path)
        return
    except PermissionError:
        sudo_bin = shutil.which("sudo")
        if not sudo_bin:
            raise
        try:
            pwd.getpwnam("scanner")
        except KeyError:
            raise
        subprocess.run(
            [sudo_bin, "-u", "scanner", "-g", "appuser", "rm", "-rf", "--", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )  # nosec B603


def workspace_path_info(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    path = resolve_workspace_path(session_id, relative_path, cfg)
    normalized = _validate_relative_path(relative_path).as_posix()
    try:
        path_stat = path.lstat()
    except FileNotFoundError as exc:
        raise WorkspacePathNotFound("session file or folder was not found") from exc
    if stat.S_ISLNK(path_stat.st_mode):
        raise InvalidWorkspacePath("session file symlinks are not allowed")
    if stat.S_ISREG(path_stat.st_mode):
        return {"path": normalized, "kind": "file", "file_count": 1, "size": path_stat.st_size}
    if stat.S_ISDIR(path_stat.st_mode):
        return {
            "path": normalized,
            "kind": "directory",
            "file_count": _workspace_directory_file_count(path),
        }
    raise WorkspacePathNotFound("session file or folder was not found")


def delete_workspace_path(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> WorkspaceDeleteResult:
    info = workspace_path_info(session_id, relative_path, cfg)
    path = resolve_workspace_path(session_id, relative_path, cfg)
    if info["kind"] == "file":
        delete_workspace_file(session_id, relative_path, cfg)
    elif info["kind"] == "directory":
        _remove_workspace_directory(path)
    else:
        raise WorkspacePathNotFound("session file or folder was not found")
    return WorkspaceDeleteResult(
        path=str(info["path"]),
        kind=str(info["kind"]),
        file_count=int(info["file_count"]),
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
        target_file = destination / rel
        try:
            size = source_file.stat().st_size
        except OSError:
            skipped_files += 1
            continue
        if (
            target_file.exists()
            or _target_parent_has_file(destination, target_file)
            or size > settings.max_file_bytes
            or file_count + 1 > settings.max_files
            or bytes_used + size > settings.quota_bytes
        ):
            skipped_files += 1
            continue
        try:
            target_file.parent.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
            _chmod_workspace_dir(target_file.parent)
            shutil.move(str(source_file), str(target_file))
            migrated_files += 1
            file_count += 1
            bytes_used += size
        except (OSError, shutil.Error):
            skipped_files += 1

    _cleanup_empty_workspace_dirs(source)
    touch_session_workspace(to_session_id, cfg)
    return WorkspaceMigrationResult(
        migrated_files=migrated_files,
        skipped_files=skipped_files,
        migrated_directories=migrated_directories,
        skipped_directories=skipped_directories,
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
        if child.stat().st_mtime < cutoff:
            shutil.rmtree(child)
            removed += 1
    return removed
