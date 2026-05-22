"""Dedicated notification delivery worker entry point."""

from __future__ import annotations

import logging
import signal
import time

from core.database_backend import is_transient_postgres_error
from services.notifications.dispatcher import dispatch_due_events, prune_sent_events

log = logging.getLogger("shell")

DEFAULT_POLL_SECONDS = 2.0
_STOP = False


def _handle_stop(signum, frame):  # noqa: ANN001
    global _STOP
    _STOP = True


def run_once(*, limit: int = 100) -> int:
    delivered = dispatch_due_events(limit=limit)
    prune_sent_events()
    return delivered


def run_forever(*, poll_seconds: float = DEFAULT_POLL_SECONDS, limit: int = 100) -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    log.info("NOTIFICATION_WORKER_STARTED")
    while not _STOP:
        phase = "run_once"
        try:
            delivered = run_once(limit=limit)
        except Exception as exc:  # noqa: BLE001
            if is_transient_postgres_error(exc):
                log.warning(
                    "NOTIFICATION_WORKER_DATABASE_INTERRUPTED",
                    extra={
                        "phase": phase,
                        "limit": limit,
                        "poll_seconds": poll_seconds,
                        "error_type": type(exc).__name__,
                        "sqlstate": str(getattr(exc, "sqlstate", "") or ""),
                    },
                )
                time.sleep(max(0.1, float(poll_seconds)))
                continue
            log.error(
                "NOTIFICATION_WORKER_CRASHED",
                exc_info=True,
                extra={"phase": phase, "limit": limit, "poll_seconds": poll_seconds},
            )
            raise
        log.debug("NOTIFICATION_WORKER_TICK", extra={"delivered": delivered, "limit": limit})
        if delivered == 0:
            time.sleep(max(0.1, float(poll_seconds)))
    log.info("NOTIFICATION_WORKER_STOPPED")


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
