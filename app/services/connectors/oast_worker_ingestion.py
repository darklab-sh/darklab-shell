# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded interaction outcome handling for the private OAST worker."""

from __future__ import annotations

from typing import Any

from services.connectors.oast_correlations import OastCorrelationError
from services.connectors.oast_interactions import ingest_oast_interaction
from services.connectors.oast_observability import (
    clear_oast_retry,
    log_oast_interactions_ingested,
    log_oast_retry,
    safe_oast_error_code,
)
from services.connectors.oast_provider_contracts import OastProviderPollBatch
from services.connectors.oast_worker_state import record_oast_provider_rejections


def process_oast_provider_batch(
    correlation: dict[str, Any],
    batch: OastProviderPollBatch,
) -> None:
    """Persist one provider batch and emit count-only ingestion outcomes."""
    correlation_id = str(correlation.get("id") or "")
    provider_rejected = batch.rejected_count + batch.ignored_shared_count
    if provider_rejected:
        record_oast_provider_rejections(correlation_id, provider_rejected)
    accepted_count = 0
    duplicate_count = 0
    interaction_rejections: dict[str, tuple[OastCorrelationError, int]] = {}
    for interaction in batch.interactions:
        try:
            outcome = ingest_oast_interaction(
                str(correlation.get("session_id") or ""),
                correlation_id,
                interaction,
                team_id=str(correlation.get("team_id") or ""),
            )
            if outcome.get("created") is True:
                accepted_count += 1
            else:
                duplicate_count += 1
        except OastCorrelationError as exc:
            error_code = safe_oast_error_code(exc, "oast_interaction_rejected")
            previous = interaction_rejections.get(error_code)
            interaction_rejections[error_code] = (
                exc,
                1 + (previous[1] if previous else 0),
            )
    if not interaction_rejections:
        clear_oast_retry("OAST_INTERACTION_REJECTED", correlation_id)
    for exc, rejected_count in interaction_rejections.values():
        log_oast_retry(
            "OAST_INTERACTION_REJECTED",
            correlation,
            exc,
            retryable=False,
            next_retry_seconds=0,
            occurrence_count=rejected_count,
        )
    log_oast_interactions_ingested(
        correlation,
        accepted_count=accepted_count,
        rejected_count=(
            provider_rejected
            + sum(count for _exc, count in interaction_rejections.values())
        ),
        duplicate_count=duplicate_count,
    )


__all__ = ["process_oast_provider_batch"]
