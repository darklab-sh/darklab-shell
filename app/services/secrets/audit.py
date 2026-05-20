"""Structured audit events for the encrypted secrets vault."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from core.helpers import get_log_session_id

log = logging.getLogger("shell")

_RESERVED_EXTRA_KEYS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def _safe_extra_key(key: str) -> str:
    return f"secret_{key}" if key in _RESERVED_EXTRA_KEYS else key


def emit_secret_event(
    event: str,
    session_id: str,
    *,
    name: str = "",
    consumer_envs: Iterable[str] | None = None,
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "session": get_log_session_id(session_id),
    }
    if name:
        payload["secret_name"] = name
    if consumer_envs is not None:
        payload["consumer_envs"] = list(consumer_envs)
    payload.update({_safe_extra_key(str(key)): value for key, value in extra.items()})
    log.info(event, extra=payload)
