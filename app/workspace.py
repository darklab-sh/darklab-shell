"""App-mediated per-session workspace helpers.

This module intentionally does not expose shell navigation or redirection.
Every file operation resolves a user-facing relative path inside one hashed
session directory and enforces quota limits before writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any

from config import CFG

# Session directories are sticky + setgid so files created by scanner tools
# inherit the shared appuser group without becoming world-readable.
WORKSPACE_DIR_MODE = 0o3730
WORKSPACE_FILE_MODE = 0o640
WORKSPACE_COMMAND_WRITE_FILE_MODE = 0o660


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
        raise WorkspaceDisabled("workspace storage is disabled")


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
    except OSError:
        pass
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
        if part.startswith("."):
            raise InvalidWorkspacePath("hidden file names are not allowed")
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
            raise InvalidWorkspacePath("workspace symlinks are not allowed")


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
            raise InvalidWorkspacePath("workspace path escapes the session directory")
    elif ensure_parent:
        parent.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
        try:
            os.chmod(parent, WORKSPACE_DIR_MODE)
        except OSError:
            pass
        resolved_parent = parent.resolve(strict=True)
        if not _is_relative_to(resolved_parent, root):
            raise InvalidWorkspacePath("workspace path escapes the session directory")
    else:
        raise InvalidWorkspacePath("workspace parent directory does not exist")
    resolved = resolved_parent / candidate.name
    if not _is_relative_to(resolved.resolve(strict=False), root):
        raise InvalidWorkspacePath("workspace path escapes the session directory")
    return resolved


def prepare_workspace_file_for_command(path: Path, *, mode: str) -> None:
    """Make a validated workspace path usable by the unprivileged scanner user."""
    if path.exists() and path.is_file():
        target_mode = WORKSPACE_COMMAND_WRITE_FILE_MODE if mode in {"write", "read_write"} else WORKSPACE_FILE_MODE
        try:
            os.chmod(path, target_mode)
        except OSError:
            pass


def workspace_usage(session_id: str, cfg: dict[str, Any] | None = None) -> WorkspaceUsage:
    root = ensure_session_workspace(session_id, cfg).resolve(strict=True)
    touch_session_workspace(session_id, cfg)
    bytes_used = 0
    file_count = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise InvalidWorkspacePath("workspace symlinks are not allowed")
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
            raise InvalidWorkspacePath("workspace symlinks are not allowed")
        if not path.is_file():
            continue
        stat = path.stat()
        items.append({
            "path": path.relative_to(root).as_posix(),
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })
    return sorted(items, key=lambda item: str(item["path"]))


def _check_write_limits(
    session_id: str,
    destination: Path,
    new_size: int,
    settings: WorkspaceSettings,
    cfg: dict[str, Any] | None,
) -> None:
    if new_size > settings.max_file_bytes:
        raise WorkspaceQuotaExceeded("file exceeds workspace max file size")
    usage = workspace_usage(session_id, cfg)
    existing_size = destination.stat().st_size if destination.exists() and destination.is_file() else 0
    new_file_count = usage.file_count + (0 if destination.exists() else 1)
    if new_file_count > settings.max_files:
        raise WorkspaceQuotaExceeded("workspace file count limit exceeded")
    projected = usage.bytes_used - existing_size + new_size
    if projected > settings.quota_bytes:
        raise WorkspaceQuotaExceeded("workspace quota exceeded")


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
    if not path.is_file():
        raise WorkspaceFileNotFound("workspace file was not found")
    if path.stat().st_size > settings.max_file_bytes:
        raise WorkspaceQuotaExceeded("file exceeds workspace max file size")
    return path.read_text(encoding="utf-8")


def delete_workspace_file(
    session_id: str,
    relative_path: str,
    cfg: dict[str, Any] | None = None,
) -> None:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    path = resolve_workspace_path(session_id, relative_path, cfg)
    if not path.is_file():
        raise WorkspaceFileNotFound("workspace file was not found")
    path.unlink()


def cleanup_inactive_workspaces(cfg: dict[str, Any] | None = None, *, now: float | None = None) -> int:
    settings = workspace_settings(cfg)
    if not settings.enabled or settings.inactivity_ttl_hours <= 0:
        return 0
    root = workspace_root(settings)
    if not root.exists():
        return 0
    ttl_seconds = settings.inactivity_ttl_hours * 60 * 60
    cutoff = (datetime.now(timezone.utc).timestamp() if now is None else float(now)) - ttl_seconds
    removed = 0
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir() or not child.name.startswith("sess_"):
            continue
        if child.stat().st_mtime < cutoff:
            shutil.rmtree(child)
            removed += 1
    return removed
