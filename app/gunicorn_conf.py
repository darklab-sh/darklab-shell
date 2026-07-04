"""Gunicorn lifecycle hooks for darklab_shell."""

import logging

from prometheus_client import multiprocess

from core.database_backend import close_postgres_pool

log = logging.getLogger("shell")


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
