"""Gunicorn lifecycle hooks for darklab_shell."""

from prometheus_client import multiprocess


def child_exit(_server, worker):
    """Remove dead-worker metric shards for Prometheus live gauges."""
    multiprocess.mark_process_dead(worker.pid)
