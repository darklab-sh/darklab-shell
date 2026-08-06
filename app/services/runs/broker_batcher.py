# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded live-output batching for brokered runs."""

import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from services.runs.output_model import LineEvent, LineKind, LineRole, line_event_from_legacy


class BrokerOutputBatcher:
    def __init__(
        self,
        run_id: str,
        capture,
        signal_classifier,
        *,
        run_started_dt,
        capture_event_with_signals_fn: Callable[..., tuple[Any, LineEvent]],
        broker_output_payload_fn: Callable[..., dict[str, Any]],
        publish_run_event_fn: Callable[[str, str, dict[str, Any]], Any],
        to_wire_fn: Callable[[LineEvent], dict[str, Any]],
        monotonic_fn: Callable[[], float] = time.monotonic,
        live_batch_size: int = 200,
        max_age_seconds: float = 0.75,
        max_latency_seconds: float = 0.075,
        coalesced_roles: set[LineRole] | None = None,
    ):
        self.run_id = run_id
        self.capture = capture
        self.signal_classifier = signal_classifier
        self.run_started_dt = run_started_dt
        self.capture_event_with_signals_fn = capture_event_with_signals_fn
        self.broker_output_payload_fn = broker_output_payload_fn
        self.publish_run_event_fn = publish_run_event_fn
        self.to_wire_fn = to_wire_fn
        self.monotonic_fn = monotonic_fn
        self.live_batch_size = live_batch_size
        self.max_age_seconds = max_age_seconds
        self.max_latency_seconds = max_latency_seconds
        self.coalesced_roles = coalesced_roles or {LineRole.progress, LineRole.status_line}
        self.events: list[LineEvent] = []
        self.first_event_monotonic = 0.0
        self.last_flush_monotonic = 0.0
        self.coalesced_line_count = 0

    def add(
        self,
        text: str,
        *,
        cls: str = "",
        kind: LineKind | str | None = None,
        event: LineEvent | None = None,
        publish: bool = True,
    ) -> None:
        now = self.monotonic_fn()
        line_dt = datetime.now(timezone.utc)
        base_event = event or line_event_from_legacy(
            text,
            cls,
            kind=kind,
            ts_clock=line_dt.strftime("%H:%M:%S"),
            ts_elapsed=f"+{(line_dt - self.run_started_dt).total_seconds():.1f}s",
        )
        _metadata, captured_event = self.capture_event_with_signals_fn(
            self.capture,
            self.signal_classifier,
            event=base_event,
        )
        if publish:
            self._append_live_event(captured_event, now=now)
        if (
            len(self.events) >= self.live_batch_size
            or self._is_due(now=now)
            or self._should_flush_for_latency(now)
        ):
            self.flush()

    def _append_live_event(self, event: LineEvent, *, now: float) -> None:
        if not self.events:
            self.first_event_monotonic = now
        if event.role in self.coalesced_roles and self.events and self.events[-1].role == event.role:
            self.events[-1] = event
            self.coalesced_line_count += 1
            return
        self.events.append(event)

    def _is_due(self, *, now: float | None = None) -> bool:
        current = self.monotonic_fn() if now is None else now
        return bool(
            self.events
            and self.first_event_monotonic
            and current - self.first_event_monotonic >= self.max_age_seconds
        )

    def _should_flush_for_latency(self, now: float) -> bool:
        if not self.events:
            return False
        if not self.last_flush_monotonic:
            return True
        return now - self.last_flush_monotonic >= self._max_latency_seconds()

    def _max_latency_seconds(self) -> float:
        if self.events and all(event.role in self.coalesced_roles for event in self.events):
            return self.max_age_seconds
        return self.max_latency_seconds

    def flush_due(self) -> None:
        if self._is_due():
            self.flush()

    def flush(self) -> None:
        if not self.events:
            return
        events = self.events
        coalesced_line_count = self.coalesced_line_count
        self.events = []
        self.first_event_monotonic = 0.0
        self.last_flush_monotonic = self.monotonic_fn()
        self.coalesced_line_count = 0
        if len(events) == 1:
            payload = self.broker_output_payload_fn("output", event=events[0])
            if coalesced_line_count:
                payload["coalesced_line_count"] = coalesced_line_count
            self.publish_run_event_fn(self.run_id, "output", payload)
            return
        payload: dict[str, object] = {"lines": [self.to_wire_fn(event) for event in events]}
        if coalesced_line_count:
            payload["coalesced_line_count"] = coalesced_line_count
        self.publish_run_event_fn(self.run_id, "output_batch", payload)
