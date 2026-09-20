# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Gunicorn lifecycle hooks for darklab_shell."""

import logging

from gunicorn.glogging import Logger
from prometheus_client import multiprocess

from core.database_backend import close_postgres_pool
from core.log_streams import console_handlers

log = logging.getLogger("shell")


class ConsoleSeverityLogger(Logger):
    """Split Gunicorn process logs while retaining its format and file options."""

    def _set_handler(self, log, output, fmt, stream=None):
        if log is self.error_log and output == "-":
            for handler in console_handlers(fmt):
                handler._gunicorn = True
                log.addHandler(handler)
        else:
            super()._set_handler(log, output, fmt, stream)


logger_class = ConsoleSeverityLogger


def post_worker_init(_worker):
    """Log worker startup after app initialization has completed."""
    log.info("GUNICORN_WORKER_BOOTED", extra={"pid": _worker.pid})


def child_exit(_server, worker):
    """Remove dead-worker metric shards for Prometheus live gauges."""
    log.info("GUNICORN_CHILD_EXIT", extra={"pid": worker.pid, "hook": "child_exit"})
    try:
        multiprocess.mark_process_dead(worker.pid)
    except Exception:
        log.error("GUNICORN_WORKER_CLEANUP_FAILED", exc_info=True, extra={"hook": "child_exit", "pid": worker.pid})
        raise


def worker_exit(_server, _worker):
    """Close per-worker database pools before Gunicorn exits the worker."""
    log.info("GUNICORN_WORKER_EXIT", extra={"pid": _worker.pid, "hook": "worker_exit"})
    try:
        close_postgres_pool()
    except Exception:
        log.error("GUNICORN_WORKER_CLEANUP_FAILED", exc_info=True, extra={"hook": "worker_exit", "pid": _worker.pid})
        raise
