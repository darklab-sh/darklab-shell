# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded no-follow reads from protected assessment run material."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys


_MAX_PRIVATE_READ_BYTES = 16 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_SCANNER_READ_SCRIPT = """
import os
import stat
import sys

path = sys.argv[1]
limit = int(sys.argv[2])
flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
flags |= getattr(os, "O_NONBLOCK", 0)
fd = os.open(path, flags)
try:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise SystemExit(2)
    chunks = []
    remaining = limit + 1
    while remaining:
        chunk = os.read(fd, min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    if len(content) > limit:
        raise SystemExit(3)
    os.write(1, content)
finally:
    os.close(fd)
""".strip()


class PrivateHttpMaterialReadError(RuntimeError):
    """Raised when one protected runtime file cannot be read safely."""


class PrivateHttpRunMaterialReader:
    """Add validated bounded reads to one private runtime directory owner."""

    path: Path
    _scanner_owned: bool
    _material_error: type[RuntimeError] = PrivateHttpMaterialReadError

    def read_bytes(self, name: str, *, max_bytes: int) -> bytes:
        destination = self._file_path(name)
        try:
            return read_private_material_file(
                destination,
                max_bytes=max_bytes,
                scanner_owned=self._scanner_owned,
            )
        except PrivateHttpMaterialReadError as exc:
            raise self._material_error(str(exc)) from exc

    def _file_path(self, name: str) -> Path:
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise self._material_error("Protected HTTP runtime file name is invalid")
        destination = self.path / name
        if destination.parent != self.path:
            raise self._material_error("Protected HTTP runtime path is invalid")
        return destination


def read_private_material_file(
    path: Path,
    *,
    max_bytes: int,
    scanner_owned: bool,
) -> bytes:
    """Read one exact regular file without following a replacement symlink."""
    if type(max_bytes) is not int or not 0 < max_bytes <= _MAX_PRIVATE_READ_BYTES:
        raise PrivateHttpMaterialReadError("Protected runtime read limit is invalid")
    if scanner_owned:
        return _read_scanner_file(path, max_bytes)
    return _read_local_file(path, max_bytes)


def _read_local_file(path: Path, max_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise PrivateHttpMaterialReadError("Protected runtime file is invalid")
            if info.st_size > max_bytes:
                raise PrivateHttpMaterialReadError(
                    "Protected runtime file exceeds its limit"
                )
            content = _read_bounded_descriptor(fd, max_bytes)
        finally:
            os.close(fd)
    except OSError as exc:
        raise PrivateHttpMaterialReadError(
            "Protected runtime file could not be read"
        ) from exc
    return content


def _read_bounded_descriptor(fd: int, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    remaining = max_bytes + 1
    while remaining:
        chunk = os.read(fd, min(_READ_CHUNK_BYTES, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    if len(content) > max_bytes:
        raise PrivateHttpMaterialReadError("Protected runtime file exceeds its limit")
    return content


def _read_scanner_file(path: Path, max_bytes: int) -> bytes:
    sudo = shutil.which("sudo") or ""
    if not sudo:
        raise PrivateHttpMaterialReadError("Protected scanner read is unavailable")
    try:
        completed = subprocess.run(
            [
                sudo,
                "-u",
                "scanner",
                "-g",
                "appuser",
                sys.executable,
                "-c",
                _SCANNER_READ_SCRIPT,
                str(path),
                str(max_bytes),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrivateHttpMaterialReadError(
            "Protected scanner file could not be read"
        ) from exc
    content = completed.stdout
    if not isinstance(content, bytes) or len(content) > max_bytes:
        raise PrivateHttpMaterialReadError("Protected scanner read is invalid")
    return content


__all__ = [
    "PrivateHttpMaterialReadError",
    "PrivateHttpRunMaterialReader",
    "read_private_material_file",
]
