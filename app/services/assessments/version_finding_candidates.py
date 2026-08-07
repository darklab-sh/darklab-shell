# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Unsaved finding candidates built from exact version matches."""

from __future__ import annotations

from typing import Any, Iterable


_SOURCE_KINDS = {"import", "run"}
_MATCH_FIELDS = (
    "confidence",
    "match_basis",
    "observed_identifier",
    "observed_version",
    "affected_range",
    "range_type",
    "advisory_source",
    "advisory_source_version",
    "advisory_origin",
    "advisory_expires_at",
    "advisory_source_state",
    "advisory_criteria",
    "advisory_match_criteria_id",
)


def materialize_version_match_candidates(
    observation: dict[str, Any] | None,
    matches: Iterable[dict[str, Any]],
    *,
    source_id: str = "",
    source_kind: str = "run",
    observed_at: str = "",
    tool_version: str = "",
    parser_version: str = "",
    require_complete_provenance: bool = False,
) -> list[dict[str, Any]]:
    """Build bounded, unsaved inference candidates from prevalidated matches."""
    item = observation if isinstance(observation, dict) else {}
    kind = _text(source_kind, 32).lower()
    observation_id = _text(item.get("observation_id"), 128)
    target = _text(item.get("target") or item.get("canonical_value"), 512)
    source_ref = _text(source_id, 128)
    provenance = {
        "kind": kind,
        "observation_id": observation_id,
        "observed_at": _text(observed_at, 64),
        "tool_version": _text(tool_version, 128),
    }
    provenance["run_id" if kind == "run" else "batch_id"] = source_ref
    normalized_parser = _text(parser_version, 128)
    if normalized_parser:
        provenance["parser_version"] = normalized_parser
    if kind not in _SOURCE_KINDS or (
        require_complete_provenance
        and not all((observation_id, target, source_ref, provenance["observed_at"],
                     provenance["tool_version"], normalized_parser))
    ):
        return []
    records = []
    for match in matches:
        record = _candidate(match, target=target, source=provenance)
        if record is not None:
            records.append(record)
    return records


def _candidate(
    match: dict[str, Any],
    *,
    target: str,
    source: dict[str, str],
) -> dict[str, Any] | None:
    if not isinstance(match, dict) or match.get("validation_method") != "version_inference":
        return None
    vulnerability_id = _text(match.get("vulnerability_id"), 128)
    if not vulnerability_id:
        return None
    candidate: dict[str, Any] = {
        "kind": "finding",
        "validation_method": "version_inference",
        "title": f"Version may be affected by {vulnerability_id}",
        "vulnerability_id": vulnerability_id,
        "target": target,
        "source": dict(source),
    }
    for key in _MATCH_FIELDS:
        candidate[key] = _text(match.get(key), 1024 if key == "advisory_criteria" else 256)
    return candidate


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


__all__ = ["materialize_version_match_candidates"]
