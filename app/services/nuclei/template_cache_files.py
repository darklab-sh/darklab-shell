# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Safe file metadata and bounded reads for the managed Nuclei cache."""

from datetime import UTC, datetime
import os
from pathlib import Path
import stat
from typing import Any


def default_nuclei_config_path() -> Path:
    base = os.environ.get("NUCLEI_CONFIG_DIR")
    if base:
        return Path(base) / ".templates-config.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg or Path.home() / ".config") / "nuclei" / ".templates-config.json"


def regular_stat(path: Path, *, directory: bool = False) -> Any | None:
    try:
        value = path.lstat()
    except OSError:
        return None
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    return value if expected(value.st_mode) and not path.is_symlink() else None


def stat_key(value: Any | None) -> tuple[int, ...]:
    return () if value is None else (value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def refreshed_at(stat_value: Any | None) -> str:
    if stat_value is None or stat_value.st_mtime_ns <= 0:
        return ""
    value = datetime.fromtimestamp(stat_value.st_mtime_ns / 1_000_000_000, tz=UTC)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def read_bounded(path: Path, limit: int) -> bytes | None:
    info = regular_stat(path)
    if info is None or info.st_size > limit:
        return None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            payload = handle.read(limit + 1)
            return payload if len(payload) <= limit else None
    except OSError:
        return None


__all__ = [
    "default_nuclei_config_path",
    "read_bounded",
    "refreshed_at",
    "regular_stat",
    "stat_key",
]
