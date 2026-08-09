# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded review of OWASP ZAP Automation Framework progress."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any


_PLAN_ID_RE = re.compile(r"(?:0|[1-9][0-9]{0,9})")
_MESSAGE_LEVELS = ("info", "warn", "error")
_MAX_MESSAGES_PER_LEVEL = 8
_MAX_MESSAGE_CHARS = 500
_MAX_TIMESTAMP_CHARS = 64


class ZapRemoteProgressError(ValueError):
    """Raised when ZAP returns malformed or mismatched progress."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ZapRemoteProgressMessage:
    level: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "message": self.message}


@dataclass(frozen=True)
class ReviewedZapRemoteProgress:
    remote_plan_id: str
    started_at: str
    finished_at: str
    info_count: int
    warning_count: int
    error_count: int
    recent_messages: tuple[ZapRemoteProgressMessage, ...]

    @property
    def complete(self) -> bool:
        return bool(self.finished_at)

    def to_dict(self) -> dict[str, Any]:
        """Return the bounded progress safe to persist and display."""
        return {
            "remote_plan_id": self.remote_plan_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "complete": self.complete,
            "info_count": self.info_count,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "recent_messages": [item.to_dict() for item in self.recent_messages],
        }


def _progress_body(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = payload.get("planProgress")
    if nested is None:
        return payload
    if not isinstance(nested, Mapping):
        raise ZapRemoteProgressError(
            "zap_progress_invalid",
            "ZAP returned an invalid plan progress response",
        )
    return nested


def _timestamp(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > _MAX_TIMESTAMP_CHARS:
        raise ZapRemoteProgressError(
            "zap_progress_invalid",
            "ZAP returned an invalid plan progress timestamp",
        )
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ZapRemoteProgressError(
            "zap_progress_invalid",
            "ZAP returned an invalid plan progress timestamp",
        ) from exc
    if parsed.tzinfo is None:
        raise ZapRemoteProgressError(
            "zap_progress_invalid",
            "ZAP returned an invalid plan progress timestamp",
        )
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _message_tail(
    progress: Mapping[str, Any],
    level: str,
) -> tuple[int, tuple[ZapRemoteProgressMessage, ...]]:
    values = progress.get(level, [])
    if not isinstance(values, (list, tuple)):
        raise ZapRemoteProgressError(
            "zap_progress_invalid",
            "ZAP returned invalid plan progress messages",
        )
    messages: list[ZapRemoteProgressMessage] = []
    for value in values[-_MAX_MESSAGES_PER_LEVEL:]:
        if not isinstance(value, str):
            raise ZapRemoteProgressError(
                "zap_progress_invalid",
                "ZAP returned invalid plan progress messages",
            )
        normalized = " ".join(value.split())[:_MAX_MESSAGE_CHARS]
        if normalized:
            messages.append(ZapRemoteProgressMessage(level=level, message=normalized))
    return len(values), tuple(messages)


def review_zap_remote_progress(
    payload: Mapping[str, Any],
    *,
    expected_plan_id: str,
) -> ReviewedZapRemoteProgress:
    """Validate one response without retaining ZAP's unbounded message history."""
    progress = _progress_body(payload)
    remote_plan_id = str(progress.get("planId") or "").strip()
    expected = str(expected_plan_id or "").strip()
    if (
        not _PLAN_ID_RE.fullmatch(remote_plan_id)
        or remote_plan_id != expected
    ):
        raise ZapRemoteProgressError(
            "zap_progress_plan_mismatch",
            "ZAP returned progress for an unexpected plan",
        )
    counts: dict[str, int] = {}
    recent: list[ZapRemoteProgressMessage] = []
    for level in _MESSAGE_LEVELS:
        count, messages = _message_tail(progress, level)
        counts[level] = count
        recent.extend(messages)
    return ReviewedZapRemoteProgress(
        remote_plan_id=remote_plan_id,
        started_at=_timestamp(progress.get("started")),
        finished_at=_timestamp(progress.get("finished")),
        info_count=counts["info"],
        warning_count=counts["warn"],
        error_count=counts["error"],
        recent_messages=tuple(recent),
    )
