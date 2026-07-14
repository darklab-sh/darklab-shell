# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Debug-only query timing helpers."""

from __future__ import annotations

import logging
import time
from typing import Any


def query_debug_started(logger: logging.Logger) -> float | None:
    return time.perf_counter() if logger.isEnabledFor(logging.DEBUG) else None


def log_query_debug(logger: logging.Logger, event: str, started_at: float | None, **extra: Any) -> None:
    if started_at is None:
        return
    logger.debug(event, extra={**extra, "duration_ms": round((time.perf_counter() - started_at) * 1000)})


def log_project_list_metrics_debug(
    logger: logging.Logger,
    started_at: float | None,
    project_count: int,
    run_count: int,
    entity_count: int,
    run_chunk_count: int,
    entity_chunk_count: int,
    team_scope: bool,
) -> None:
    log_query_debug(
        logger,
        "PROJECT_LIST_METRICS_QUERY_COMPLETED",
        started_at,
        project_count=project_count,
        run_count=run_count,
        entity_count=entity_count,
        run_chunk_count=run_chunk_count,
        entity_chunk_count=entity_chunk_count,
        team_scope=team_scope,
    )


def log_atlas_findings_list_debug(
    logger: logging.Logger,
    started_at: float | None,
    context: dict[str, Any],
    *,
    row_count: int,
) -> None:
    log_query_debug(
        logger,
        "ATLAS_LIST_QUERY_COMPLETED",
        started_at,
        resource="findings",
        include_total=bool(context["include_total"]),
        include_counts=bool(context["include_counts"]),
        limit=context["page_limit"],
        offset=context["page_offset"],
        row_count=row_count,
        total=context["total"],
        total_exact=bool(context["total_exact"]),
        query_active=bool(context["search"]),
        project_filter=bool(context["project_filter"]),
        run_filter=bool(context["run_filter"]),
        review_state_filter=bool(context["statuses"]),
        verification_filter=bool(context["verified_statuses"]),
        orphan_filter=context["normalized_orphan_filter"],
        suppression_filter=context["normalized_suppression_filter"],
        team_scope=bool(context["team_id"]),
    )


def log_atlas_entities_list_debug(
    logger: logging.Logger,
    started_at: float | None,
    context: dict[str, Any],
    *,
    row_count: int,
) -> None:
    log_query_debug(
        logger,
        "ATLAS_LIST_QUERY_COMPLETED",
        started_at,
        resource="entities",
        include_total=bool(context["include_total"]),
        include_counts=False,
        limit=context["page_limit"],
        offset=context["page_offset"],
        row_count=row_count,
        total=context["total"],
        total_exact=bool(context["total_exact"]),
        entity_type=context["normalized_type"],
        query_active=bool(context["search"]),
        project_filter=bool(context["project_filter"]),
        run_filter=bool(context["run_filter"]),
        orphan_filter=context["normalized_orphan_filter"],
        suppression_filter=context["normalized_suppression_filter"],
        team_scope=bool(context["team_id"]),
    )
