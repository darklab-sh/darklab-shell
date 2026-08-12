# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded dangling-record review from persisted DNSx event wires."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any

from services.assessments.dns_takeover_correlation import (
    DNSX_TARGET_CORRELATION_VERSION,
    DNSX_TARGET_MAX_ALLOWED_RUNS,
    correlate_dnsx_target_observation,
)
from services.assessments.takeover_detection import evaluate_takeover_signal


DNSX_REVIEW_MAX_EVENTS = 1_000
DNSX_REVIEW_MAX_OBSERVATIONS = 256
DNSX_REVIEW_MAX_JOIN_CANDIDATES = 1_024
DNSX_REVIEW_MAX_RESULTS = 100


def build_dnsx_takeover_event_review(
    events: object,
    *,
    allowed_source_run_ids: Collection[str],
) -> dict[str, Any]:
    """Build one read-only review without provider calls, writes, or partial eviction."""
    allowed = _allowed_runs(allowed_source_run_ids)
    if allowed is None:
        return _rejected("invalid_run_allowlist")
    observations = _event_observations(events)
    if observations is None:
        return _rejected("event_or_observation_limit_exceeded")
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    candidate_count = 0
    for source in observations:
        for target in observations:
            joined = correlate_dnsx_target_observation(
                source, target, allowed_source_run_ids=allowed,
            )
            if not joined:
                continue
            source_id = str(joined["source_observation"]["observation_id"])
            target_id = str(joined["target_observation"]["observation_id"])
            if (source_id, target_id) in seen:
                continue
            seen.add((source_id, target_id))
            candidate_count += 1
            if candidate_count > DNSX_REVIEW_MAX_JOIN_CANDIDATES:
                return _rejected("join_candidate_limit_exceeded", len(observations))
            grouped.setdefault(source_id, []).append(joined)
    reviews = [_latest_review(rows) for rows in grouped.values() if rows]
    if len(reviews) > DNSX_REVIEW_MAX_RESULTS:
        return _rejected("review_result_limit_exceeded", len(observations))
    reviews.sort(key=lambda row: (str(row.get("hostname") or ""), _source_id(row)))
    return {
        "status": "ready" if reviews else "empty",
        "observation_count": len(observations),
        "review_count": len(reviews),
        "reviews": reviews,
    }


def _event_observations(events: object) -> list[dict[str, Any]] | None:
    if not isinstance(events, list) or len(events) > DNSX_REVIEW_MAX_EVENTS:
        return None
    rows: list[dict[str, Any]] = []
    for event in events:
        detail = event.get("source_detail") if isinstance(event, Mapping) else None
        values = detail.get("takeover_observations") if isinstance(detail, Mapping) else None
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, Mapping):
                continue
            rows.append(dict(value))
            if len(rows) > DNSX_REVIEW_MAX_OBSERVATIONS:
                return None
    return rows


def _latest_review(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest_time = max(_target_time(row) for row in rows)
    latest = [row for row in rows if _target_time(row) == latest_time]
    fingerprints = {
        (str(row.get("target_resolution_state") or ""), tuple(row.get("cname_chain") or []))
        for row in latest
    }
    if len(fingerprints) > 1:
        source = latest[0]["source_observation"]
        targets = [
            dict(row["target_observation"])
            for row in sorted(latest, key=lambda item: str(item["target_observation"]["observation_id"]))
        ]
        return {
            "state": "uncertain",
            "reason": "conflicting_target_results",
            "hostname": str(latest[0].get("hostname") or ""),
            "source_observation": dict(source),
            "target_observations": targets[:4],
            "target_observation_count": len(targets),
            "target_observations_truncated": len(targets) > 4,
            "correlation_version": DNSX_TARGET_CORRELATION_VERSION,
        }
    selected = min(latest, key=lambda row: str(row["target_observation"]["observation_id"]))
    review = evaluate_takeover_signal(selected)
    review["source_observation"] = dict(selected["source_observation"])
    review["target_observation"] = dict(selected["target_observation"])
    review["correlation_version"] = DNSX_TARGET_CORRELATION_VERSION
    return review


def _target_time(row: dict[str, Any]) -> datetime:
    value = str(row["target_observation"]["observed_at"])
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _allowed_runs(values: Collection[str]) -> set[str] | None:
    if (
        isinstance(values, (str, bytes))
        or not isinstance(values, Collection)
        or not 0 < len(values) <= DNSX_TARGET_MAX_ALLOWED_RUNS
    ):
        return None
    rows = {str(value or "").strip() for value in values}
    if any(not value or len(value) > 128 or any(ord(char) < 32 for char in value) for value in rows):
        return None
    return rows


def _source_id(row: dict[str, Any]) -> str:
    source = row.get("source_observation")
    return str(source.get("observation_id") or "") if isinstance(source, dict) else ""


def _rejected(reason: str, observation_count: int = 0) -> dict[str, Any]:
    return {
        "status": "rejected",
        "reason": reason,
        "observation_count": observation_count,
        "review_count": 0,
        "reviews": [],
    }


__all__ = ["build_dnsx_takeover_event_review"]
