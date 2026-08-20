# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Cross-process read and maintenance lock for managed Nuclei templates."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterator


MANAGED_TEMPLATE_LOCK_PATH = str(
    Path(tempfile.gettempdir()) / ".darklab-nuclei-template.lock"
)


class NucleiTemplateLockBusy(RuntimeError):
    """Raised when a non-blocking template-cache lock cannot be acquired."""


class NucleiTemplateLockError(RuntimeError):
    """Raised when the shared lock file cannot be opened safely."""


@contextmanager
def managed_nuclei_template_lock(
    *,
    exclusive: bool,
    blocking: bool = False,
    inheritable: bool = False,
    lock_path: str | Path = MANAGED_TEMPLATE_LOCK_PATH,
) -> Iterator[int]:
    """Hold a shared scan lock or exclusive maintenance lock."""
    path = Path(lock_path)
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            try:
                descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o660)
            except FileExistsError:
                descriptor = os.open(path, flags)
    except OSError as exc:
        raise NucleiTemplateLockError("managed Nuclei template lock is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise NucleiTemplateLockError("managed Nuclei template lock is unsafe")
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        if not blocking:
            operation |= fcntl.LOCK_NB
        try:
            fcntl.flock(descriptor, operation)
        except BlockingIOError as exc:
            raise NucleiTemplateLockBusy(
                "managed Nuclei template maintenance is already in progress"
            ) from exc
        os.set_inheritable(descriptor, inheritable)
        yield descriptor
    finally:
        os.close(descriptor)


__all__ = [
    "MANAGED_TEMPLATE_LOCK_PATH",
    "NucleiTemplateLockBusy",
    "NucleiTemplateLockError",
    "managed_nuclei_template_lock",
]
