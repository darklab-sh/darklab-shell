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
    log.info("GUNICORN_WORKER_EXITED", extra={"pid": worker.pid})
    multiprocess.mark_process_dead(worker.pid)


def worker_exit(_server, _worker):
    """Close per-worker database pools before Gunicorn exits the worker."""
    log.info("GUNICORN_WORKER_EXITED", extra={"pid": _worker.pid})
    close_postgres_pool()
