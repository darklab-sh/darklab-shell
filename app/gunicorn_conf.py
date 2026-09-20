# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Gunicorn lifecycle hooks for darklab_shell."""

import logging

from gunicorn.config import Config
from gunicorn.glogging import Logger
from prometheus_client import multiprocess

from core.database_backend import close_postgres_pool
from core.log_streams import console_handlers

log = logging.getLogger("shell")


class _GunicornConsoleHandler(logging.StreamHandler):
    # Gunicorn removes its owned handlers when setup runs again on reload.
    _gunicorn = True


class ConsoleSeverityLogger(Logger):
    """Split Gunicorn process logs while retaining its format and file options."""

    def setup(self, cfg: Config) -> None:
        super().setup(cfg)
        if cfg.errorlog != "-" or cfg.logconfig_dict or cfg.logconfig_json or cfg.logconfig:
            return
        for handler in list(self.error_log.handlers):
            if not (getattr(handler, "_gunicorn", False) and isinstance(handler, logging.StreamHandler)):
                continue
            formatter = handler.formatter or logging.Formatter(self.error_fmt, self.datefmt)
            self.error_log.removeHandler(handler)
            handler.close()
            for replacement in console_handlers(formatter, handler_type=_GunicornConsoleHandler):
                self.error_log.addHandler(replacement)


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
