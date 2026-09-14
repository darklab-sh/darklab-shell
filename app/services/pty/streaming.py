# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read local PTY events without holding the condition lock while yielding."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import TYPE_CHECKING

from services.auth.contracts import STREAM_AUTH_POLL_SECONDS

if TYPE_CHECKING:
    from services.pty.service import PtyRun


def stream_local_pty_events(run: PtyRun, after: str = "0-0", *, heartbeat_seconds: float) -> Iterator[str]:
    try:
        cursor = max(0, int(after or 0))
    except ValueError:
        cursor = 0
    while True:
        with run.condition:
            events = [event for event in run.events if event.seq > cursor]
            if not events and run.closed:
                return
            if not events:
                run.condition.wait(timeout=min(heartbeat_seconds, STREAM_AUTH_POLL_SECONDS))
                events = [event for event in run.events if event.seq > cursor]
        if not events:
            yield "event: heartbeat\ndata: {}\n\n"
            continue
        for event in events:
            cursor = event.seq
            payload = dict(event.payload)
            payload["type"] = event.type
            payload["event_id"] = str(event.seq)
            yield f"id: {event.seq}\ndata: {json.dumps(payload)}\n\n"
        if run.closed and events and events[-1].type == "exit":
            return
