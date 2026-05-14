"""Structured audit events for the encrypted secrets vault."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from core.helpers import get_log_session_id

log = logging.getLogger("shell")


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
    payload.update(extra)
    log.info(event, extra=payload)
