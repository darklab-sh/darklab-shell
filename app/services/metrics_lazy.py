# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Lazy access to Prometheus metrics for import-pure modules."""

from __future__ import annotations

from typing import Any


class _MetricsProxy:
    def __getattr__(self, name: str) -> Any:
        from services import metrics  # noqa: PLC0415
        try:
            return getattr(metrics, name)
        except AttributeError:
            from services.metrics import assessment_batch_lifecycle  # noqa: PLC0415
            from services.metrics import assessment_batches  # noqa: PLC0415
            from services.metrics import assessments  # noqa: PLC0415
            from services.metrics import probes  # noqa: PLC0415
            from services.metrics import workflows  # noqa: PLC0415

            try:
                return getattr(assessment_batch_lifecycle, name)
            except AttributeError:
                try:
                    return getattr(assessment_batches, name)
                except AttributeError:
                    try:
                        return getattr(assessments, name)
                    except AttributeError:
                        try:
                            return getattr(probes, name)
                        except AttributeError:
                            return getattr(workflows, name)


app_metrics = _MetricsProxy()
