"""Dedicated notification delivery worker entry point."""

from __future__ import annotations

import logging
import signal
import time

from services.notifications.dispatcher import dispatch_due_events

log = logging.getLogger("shell")

DEFAULT_POLL_SECONDS = 2.0
_STOP = False


def _handle_stop(signum, frame):  # noqa: ANN001
    global _STOP
    _STOP = True


def run_once(*, limit: int = 100) -> int:
    return dispatch_due_events(limit=limit)


def run_forever(*, poll_seconds: float = DEFAULT_POLL_SECONDS, limit: int = 100) -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    log.info("NOTIFICATION_WORKER_STARTED")
    while not _STOP:
        delivered = run_once(limit=limit)
        if delivered == 0:
            time.sleep(max(0.1, float(poll_seconds)))
    log.info("NOTIFICATION_WORKER_STOPPED")


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
