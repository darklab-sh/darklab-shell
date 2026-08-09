# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Evidence-safe comparison of Project Web Surface captures."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from services.intel.canonical import CanonicalizationError, canonical_url


CHANGE_STATES = frozenset({"changed", "unchanged", "no_baseline", "incomparable", "unknown"})
COMPARISON_BASIS = "exact_url_and_profile_role"


def attach_capture_comparisons(
    captures: list[dict[str, object]],
    candidates: list[dict[str, object]],
    *,
    history_truncated: bool = False,
) -> None:
    """Attach the nearest compatible prior visual hash without creating findings."""
    records = _comparison_records(candidates)
    for capture in captures:
        current = _comparison_record(capture)
        if current is None:
            capture["comparison"] = _comparison_payload("incomparable")
            continue
        previous = _previous_record(current, records)
        if previous is None:
            state = "unknown" if history_truncated else "no_baseline"
            capture["comparison"] = _comparison_payload(state)
            continue
        current_hash = str(current["visual_hash"] or "").strip().casefold()
        previous_hash = str(previous["visual_hash"] or "").strip().casefold()
        state = "incomparable" if not current_hash or not previous_hash else (
            "unchanged" if current_hash == previous_hash else "changed"
        )
        capture["comparison"] = _comparison_payload(state, previous)


def capture_matches_change_state(capture: object, change_state: object) -> bool:
    """Return whether one capture matches a normalized comparison state."""
    expected = str(change_state or "").strip().casefold()
    if not expected:
        return True
    comparison = capture.get("comparison") if isinstance(capture, Mapping) else None
    return isinstance(comparison, Mapping) and comparison.get("state") == expected


def normalize_change_state(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in CHANGE_STATES else ""


def _comparison_records(captures: list[dict[str, object]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for capture in captures:
        record = _comparison_record(capture)
        if record is not None:
            unique[str(record["artifact_id"])] = record
    return list(unique.values())


def _comparison_record(capture: Mapping[str, object]) -> dict[str, Any] | None:
    artifact = capture.get("artifact")
    source_run = capture.get("source_run")
    if not isinstance(artifact, Mapping) or not isinstance(source_run, Mapping):
        return None
    artifact_id = str(artifact.get("id") or "")
    run_id = str(source_run.get("id") or "")
    target = _canonical_target(capture.get("url"))
    order = _capture_order(capture, artifact, source_run, artifact_id)
    if not artifact_id or not run_id or not target or order is None:
        return None
    return {
        "artifact_id": artifact_id,
        "run_id": run_id,
        "captured_at": str(capture.get("captured_at") or artifact.get("created") or ""),
        "visual_hash": str(capture.get("visual_hash") or ""),
        "key": (target, str(capture.get("profile_role") or "").strip().casefold()),
        "order": order,
    }


def _capture_order(
    capture: Mapping[str, object],
    artifact: Mapping[str, object],
    source_run: Mapping[str, object],
    artifact_id: str,
) -> tuple[datetime, datetime, datetime, str] | None:
    captured = _timestamp(capture.get("captured_at"))
    artifact_created = _timestamp(artifact.get("created"))
    run_time = _timestamp(source_run.get("finished")) or _timestamp(source_run.get("started"))
    primary = captured or artifact_created or run_time
    if primary is None:
        return None
    return primary, artifact_created or primary, run_time or primary, artifact_id


def _previous_record(
    current: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    compatible = [
        record
        for record in records
        if record["key"] == current["key"]
        and record["run_id"] != current["run_id"]
        and record["order"] < current["order"]
    ]
    return max(compatible, key=lambda item: item["order"], default=None)


def _comparison_payload(
    state: str,
    previous: Mapping[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"state": state, "basis": COMPARISON_BASIS}
    if previous:
        payload["previous_capture"] = {
            "artifact_id": previous["artifact_id"],
            "source_run_id": previous["run_id"],
            "captured_at": previous["captured_at"],
            "visual_hash": previous["visual_hash"],
        }
    return payload


def _canonical_target(value: object) -> str:
    try:
        return canonical_url(str(value or ""))
    except CanonicalizationError:
        return ""


def _timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = [
    "CHANGE_STATES", "attach_capture_comparisons",
    "capture_matches_change_state", "normalize_change_state",
]
