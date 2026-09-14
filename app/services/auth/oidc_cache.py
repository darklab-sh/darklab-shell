# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded provider caches and one private CA bundle per worker process."""

from __future__ import annotations

import atexit
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import ssl
import tempfile
import threading
import time
from typing import Any

from certifi import where as requests_ca_bundle


PROVIDER_CACHE_SECONDS = 300
MAX_PROVIDER_CACHE_ENTRIES = 8
_LOCK = threading.RLock()
_PID = os.getpid()
_TRUST_DIRECTORY: str | None = None
_TRUST_SOURCE: tuple[str, int, int] | None = None


@dataclass(frozen=True)
class _CachedValue:
    value: Any
    expires_at: float


_PROVIDER_VALUES: OrderedDict[tuple[Any, ...], _CachedValue] = OrderedDict()
_PENDING_VALUES: dict[tuple[Any, ...], Future[Any]] = {}


def _cleanup_trust_bundle() -> None:
    global _TRUST_DIRECTORY, _TRUST_SOURCE
    if _PID == os.getpid() and _TRUST_DIRECTORY is not None:
        shutil.rmtree(_TRUST_DIRECTORY, ignore_errors=True)
        _TRUST_DIRECTORY = None
        _TRUST_SOURCE = None


def reset_provider_cache() -> None:
    """Discard cached metadata and keys; used when a test provider changes."""
    with _LOCK:
        _PROVIDER_VALUES.clear()


def _after_fork() -> None:
    global _LOCK, _PID, _TRUST_DIRECTORY, _TRUST_SOURCE
    _LOCK = threading.RLock()
    _PID = os.getpid()
    _TRUST_DIRECTORY = None
    _TRUST_SOURCE = None
    _PROVIDER_VALUES.clear()
    _PENDING_VALUES.clear()


atexit.register(_cleanup_trust_bundle)
if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def combined_trust_bundle(path: str, mtime_ns: int, size: int) -> str:
    global _TRUST_DIRECTORY, _TRUST_SOURCE
    source = (path, mtime_ns, size)
    with _LOCK:
        if source == _TRUST_SOURCE and _TRUST_DIRECTORY is not None:
            return str(Path(_TRUST_DIRECTORY) / "ca.pem")
        if not 0 < size <= 262_144:
            raise ValueError("OIDC CA bundle size is invalid")
        with Path(path).open("rb") as stream:
            custom = stream.read(262_145)
        if not custom.strip() or len(custom) > 262_144:
            raise ValueError("OIDC CA bundle size is invalid")
        ssl.create_default_context(cadata=custom.decode("ascii"))
        system = Path(requests_ca_bundle()).read_bytes()
        if _TRUST_DIRECTORY is None:
            _TRUST_DIRECTORY = tempfile.mkdtemp(prefix="darklab-oidc-trust-")
        destination = Path(_TRUST_DIRECTORY) / "ca.pem"
        handle, temporary = tempfile.mkstemp(dir=_TRUST_DIRECTORY, prefix=".ca-", suffix=".pem")
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(system.rstrip(b"\n") + b"\n" + custom)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        _TRUST_SOURCE = source
        return str(destination)


def cached_provider_value(
    key: tuple[Any, ...], loader: Callable[[], Any], *, replace: Any = None,
) -> Any:
    """Cache validated values, coalescing concurrent loads and key refreshes."""
    with _LOCK:
        existing = _PROVIDER_VALUES.get(key)
        if existing is not None and existing.expires_at > time.monotonic():
            if replace is None or existing.value is not replace:
                _PROVIDER_VALUES.move_to_end(key)
                return existing.value
        pending = _PENDING_VALUES.get(key)
        first = pending is None
        if pending is None:
            pending = Future()
            _PENDING_VALUES[key] = pending
    if not first:
        return pending.result()
    try:
        value = loader()
    except BaseException as exc:
        with _LOCK:
            pending.set_exception(exc)
            _PENDING_VALUES.pop(key, None)
        raise
    with _LOCK:
        _PROVIDER_VALUES[key] = _CachedValue(value, time.monotonic() + PROVIDER_CACHE_SECONDS)
        _PROVIDER_VALUES.move_to_end(key)
        while len(_PROVIDER_VALUES) > MAX_PROVIDER_CACHE_ENTRIES:
            _PROVIDER_VALUES.popitem(last=False)
        pending.set_result(value)
        _PENDING_VALUES.pop(key, None)
        return value


def trust_cache_key(trust: str | bool) -> tuple[Any, ...]:
    if trust is True:
        return ("system",)
    path = Path(str(trust))
    state = path.stat()
    return (str(path), state.st_mtime_ns, state.st_size)
