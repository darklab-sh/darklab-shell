"""Gunicorn lifecycle hooks for darklab_shell."""

from prometheus_client import multiprocess

from core.database_backend import close_postgres_pool


def child_exit(_server, worker):
    """Remove dead-worker metric shards for Prometheus live gauges."""
    multiprocess.mark_process_dead(worker.pid)


def worker_exit(_server, _worker):
    """Close per-worker database pools before Gunicorn exits the worker."""
    close_postgres_pool()
