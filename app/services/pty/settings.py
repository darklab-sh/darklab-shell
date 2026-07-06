"""Interactive PTY configuration defaults and bounded config helpers."""

from __future__ import annotations

from typing import cast

from config import resolve_effective_cfg
from services.pty import capture as pty_capture

_PTY_CAPTURE_MAX_HISTORY_LINES = pty_capture._PTY_CAPTURE_MAX_HISTORY_LINES
_PTY_CAPTURE_MIN_HISTORY_LINES = pty_capture._PTY_CAPTURE_MIN_HISTORY_LINES
_PTY_SNAPSHOT_MAX_BYTES = pty_capture._PTY_SNAPSHOT_MAX_BYTES

_PTY_BUFFER_LIMIT = 512
_PTY_INPUT_MAX_BYTES = 4096
_PTY_HEARTBEAT_SECONDS = 15.0
_PTY_CONTROL_POLL_SECONDS = 0.2
_PTY_STREAM_FETCH_COUNT = 100
_PTY_STREAM_MAXLEN = 5000
_PTY_SNAPSHOT_PUBLISH_BYTES = 8192
_PTY_SNAPSHOT_PUBLISH_SECONDS = 1.0
_PTY_SNAPSHOT_MIN_PUBLISH_SECONDS = 0.2
_PTY_SNAPSHOT_FALLBACK_ENTRY_LIMIT = 200


def _coerce_non_negative_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        number = int(value)
    elif isinstance(value, (str, bytes, bytearray)):
        try:
            number = int(value)
        except ValueError:
            return default
    else:
        return default
    return number if number >= 0 else default


def _cfg_positive_int(key: str, default: int) -> int:
    return max(1, _coerce_non_negative_int(resolve_effective_cfg().get(key), default))


def _cfg_positive_float(key: str, default: float) -> float:
    value = resolve_effective_cfg().get(key)
    if value is None or isinstance(value, bool):
        return default
    try:
        number = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _pty_buffer_limit() -> int:
    return _cfg_positive_int("interactive_pty_buffer_limit", _PTY_BUFFER_LIMIT)


def _pty_input_max_bytes() -> int:
    return _cfg_positive_int("interactive_pty_input_max_bytes", _PTY_INPUT_MAX_BYTES)


def _pty_heartbeat_seconds() -> float:
    return _cfg_positive_float("interactive_pty_heartbeat_seconds", _PTY_HEARTBEAT_SECONDS)


def _pty_control_poll_seconds() -> float:
    return _cfg_positive_float("interactive_pty_control_poll_seconds", _PTY_CONTROL_POLL_SECONDS)


def _pty_stream_fetch_count() -> int:
    return _cfg_positive_int("interactive_pty_stream_fetch_count", _PTY_STREAM_FETCH_COUNT)


def _pty_stream_maxlen() -> int:
    return _cfg_positive_int("interactive_pty_stream_maxlen", _PTY_STREAM_MAXLEN)


def _pty_snapshot_publish_bytes() -> int:
    return _cfg_positive_int("interactive_pty_snapshot_publish_bytes", _PTY_SNAPSHOT_PUBLISH_BYTES)


def _pty_snapshot_publish_seconds() -> float:
    return _cfg_positive_float("interactive_pty_snapshot_publish_seconds", _PTY_SNAPSHOT_PUBLISH_SECONDS)


def _pty_snapshot_min_publish_seconds() -> float:
    return _cfg_positive_float("interactive_pty_snapshot_min_publish_seconds", _PTY_SNAPSHOT_MIN_PUBLISH_SECONDS)


def _pty_snapshot_fallback_entry_limit() -> int:
    return _cfg_positive_int("interactive_pty_snapshot_fallback_entry_limit", _PTY_SNAPSHOT_FALLBACK_ENTRY_LIMIT)
