# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Capture and optionally publish one brokered run event."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from services.runs.output_model import LineEvent, LineKind, line_event_from_legacy


def publish_broker_captured_line(
    run_id: str,
    capture,
    signal_classifier,
    event_type: str,
    text: str,
    *,
    cls: str = "",
    kind: LineKind | str | None = None,
    event: LineEvent | None = None,
    run_started_dt,
    capture_event_with_signals_fn: Callable[..., tuple[Any, LineEvent]],
    broker_output_payload_fn: Callable[..., dict[str, Any]],
    publish_run_event_fn: Callable[[str, str, dict[str, Any]], Any],
    publish: bool = True,
) -> None:
    line_dt = datetime.now(timezone.utc)
    base_event = event or line_event_from_legacy(
        text,
        cls,
        kind=kind,
        ts_clock=line_dt.strftime("%H:%M:%S"),
        ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
    )
    _metadata, captured_event = capture_event_with_signals_fn(
        capture,
        signal_classifier,
        event=base_event,
    )
    if publish:
        publish_run_event_fn(
            run_id,
            event_type,
            broker_output_payload_fn(event_type, event=captured_event),
        )
