"""Lazy access to Prometheus metrics for import-pure modules."""

from __future__ import annotations

from typing import Any


class _MetricsProxy:
    def __getattr__(self, name: str) -> Any:
        from services import metrics  # noqa: PLC0415
        try:
            return getattr(metrics, name)
        except AttributeError:
            from services.metrics import workflows  # noqa: PLC0415

            return getattr(workflows, name)


app_metrics = _MetricsProxy()
