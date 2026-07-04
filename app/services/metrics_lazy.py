"""Lazy access to Prometheus metrics for import-pure modules."""

from __future__ import annotations

from typing import Any


class _MetricsProxy:
    def __getattr__(self, name: str) -> Any:
        from services import metrics  # noqa: PLC0415

        return getattr(metrics, name)


app_metrics = _MetricsProxy()
