# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Private, short-lived files for protected HTTP assessment runs."""

from __future__ import annotations

import logging
import os
import pwd
import secrets
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Mapping

from config import resolve_data_dir, resolve_effective_cfg
from services.assessments.http_profile_runtime_read import PrivateHttpRunMaterialReader


log = logging.getLogger("shell")
_RUNTIME_ROOT_NAME = "private-http-runs"
_SCANNER_RUNTIME_PARENT = Path(tempfile.gettempdir())
_ROOT_MODE = 0o730
_RUN_MODE = 0o700
_FILE_MODE = 0o600


class PrivateHttpMaterialError(RuntimeError):
    """Raised when protected run material cannot be created safely."""


def _scanner_user_exists() -> bool:
    try:
        pwd.getpwnam("scanner")
        return True
    except (AttributeError, KeyError, TypeError):
        return False


def _sudo_bin() -> str:
    return shutil.which("sudo") or ""


def _runtime_root(cfg: Mapping[str, object] | None = None) -> Path:
    active_cfg = resolve_effective_cfg(cfg)
    parent = (
        _SCANNER_RUNTIME_PARENT
        if _scanner_user_exists()
        else Path(resolve_data_dir(active_cfg))
    )
    root = parent / _RUNTIME_ROOT_NAME
    try:
        root.mkdir(mode=_ROOT_MODE, parents=True, exist_ok=True)
        root_stat = root.lstat()
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise PrivateHttpMaterialError("Protected HTTP runtime root is invalid")
        os.chmod(root, _ROOT_MODE)
    except (OSError, RuntimeError) as exc:
        if isinstance(exc, PrivateHttpMaterialError):
            raise
        raise PrivateHttpMaterialError(
            "Protected HTTP runtime storage is unavailable"
        ) from exc
    return root


def _scanner_run(arguments: list[str], *, input_bytes: bytes | None = None) -> None:
    sudo = _sudo_bin()
    if not sudo or not _scanner_user_exists():
        raise PrivateHttpMaterialError("Protected scanner file handoff is unavailable")
    try:
        subprocess.run(
            [sudo, "-u", "scanner", "-g", "appuser", *arguments],
            input=input_bytes,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrivateHttpMaterialError(
            "Protected scanner file handoff failed"
        ) from exc


class PrivateHttpRunMaterial(PrivateHttpRunMaterialReader):
    """Own one private runtime directory and its scanner-readable files."""

    _material_error = PrivateHttpMaterialError

    def __init__(self, *, cfg: Mapping[str, object] | None = None):
        self.root = _runtime_root(cfg)
        self.path = self.root / ("run-" + secrets.token_hex(16))
        self._scanner_owned = _scanner_user_exists()
        if self._scanner_owned:
            _scanner_run(["mkdir", "-m", f"{_RUN_MODE:o}", str(self.path)])
        else:
            self.path.mkdir(mode=_RUN_MODE)
            os.chmod(self.path, _RUN_MODE)

    def write_bytes(self, name: str, content: bytes) -> Path:
        destination = self._file_path(name)
        if self._scanner_owned:
            _scanner_run(["tee", str(destination)], input_bytes=content)
            _scanner_run(["chmod", f"{_FILE_MODE:o}", str(destination)])
        else:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(destination, flags, _FILE_MODE)
            try:
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                os.close(fd)
            os.chmod(destination, _FILE_MODE)
        return destination

    def cleanup(self) -> None:
        try:
            _remove_runtime_path(self.root, self.path, scanner_owned=self._scanner_owned)
        except PrivateHttpMaterialError:
            log.error(
                "HTTP_PROFILE_RUNTIME_MATERIAL_CLEANUP_FAILED",
                exc_info=True,
                extra={"material_count": 1},
            )


def _remove_runtime_path(root: Path, path: Path, *, scanner_owned: bool) -> None:
    if path.parent != root or not path.name.startswith("run-"):
        raise PrivateHttpMaterialError("Protected HTTP runtime cleanup path is invalid")
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink():
        path.unlink()
    elif scanner_owned:
        _scanner_run(["rm", "-rf", "--", str(path)])
    else:
        shutil.rmtree(path)


def cleanup_stale_http_profile_runtime(
    *,
    cfg: Mapping[str, object] | None = None,
    now_timestamp: float | None = None,
) -> int:
    """Remove abandoned private directories older than the run timeout boundary."""
    active_cfg = resolve_effective_cfg(cfg)
    root = _runtime_root(active_cfg)
    command_timeout = int(active_cfg.get("command_timeout_seconds") or 0)
    minimum_age = max(command_timeout + 300, 3600)
    cutoff = (time.time() if now_timestamp is None else now_timestamp) - minimum_age
    removed = 0
    for path in root.iterdir():
        try:
            path_stat = path.lstat()
            if not path.name.startswith("run-") or path_stat.st_mtime > cutoff:
                continue
            _remove_runtime_path(
                root,
                path,
                scanner_owned=(not stat.S_ISLNK(path_stat.st_mode) and _scanner_user_exists()),
            )
            removed += 1
        except (OSError, PrivateHttpMaterialError):
            log.warning(
                "HTTP_PROFILE_RUNTIME_RECOVERY_CLEANUP_FAILED",
                exc_info=True,
                extra={"removed_count": removed},
            )
    return removed
