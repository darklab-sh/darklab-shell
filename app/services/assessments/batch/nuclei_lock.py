# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Template-cache lock boundary for confirmed Nuclei assessment batches."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.nuclei_preflight import batch_nuclei_preflight
from services.nuclei.template_lock import (
    NucleiTemplateLockBusy,
    NucleiTemplateLockError,
    managed_nuclei_template_lock,
)


@contextmanager
def assessment_batch_nuclei_cache_lock(summary: object) -> Iterator[None]:
    """Prevent a refresh from crossing Nuclei batch materialization."""
    if not batch_nuclei_preflight(summary):
        yield
        return
    try:
        with managed_nuclei_template_lock(exclusive=False, blocking=False):
            yield
    except NucleiTemplateLockBusy as exc:
        raise AssessmentBatchError(
            "nuclei_template_refresh_in_progress",
            "Managed Nuclei templates are being updated; rebuild the preview when the refresh finishes.",
            status_code=409,
        ) from exc
    except NucleiTemplateLockError as exc:
        raise AssessmentBatchError(
            "nuclei_template_lock_unavailable",
            "The managed Nuclei template lock is unavailable.",
            status_code=503,
        ) from exc


__all__ = ["assessment_batch_nuclei_cache_lock"]
