# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded Prometheus metrics for Project assessment operations."""

from __future__ import annotations

from typing import Any

from prometheus_client import Counter


ASSESSMENT_PARSERS = frozenset({"command_registry"})
ASSESSMENT_PARSER_OUTCOMES = frozenset({"parsed", "fallback_empty", "fallback_error"})

ASSESSMENT_PARSER_RESULTS = Counter(
    "darklab_assessment_parser_results",
    "Assessment parser results by bounded parser and outcome.",
    ("parser", "outcome"),
)

LABEL_CARDINALITY_POLICIES: dict[str, dict[str, dict[str, Any]]] = {
    "darklab_assessment_parser_results": {
        "parser": {
            "kind": "enum",
            "values": ASSESSMENT_PARSERS,
            "fallback": "command_registry",
        },
        "outcome": {
            "kind": "enum",
            "values": ASSESSMENT_PARSER_OUTCOMES,
            "fallback": "fallback_error",
        },
    },
}

METRIC_DEFINITIONS = (ASSESSMENT_PARSER_RESULTS,)
HISTOGRAM_DEFINITIONS: tuple[Any, ...] = ()


def _enum(value: object, allowed: frozenset[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else fallback


def record_assessment_parser_result(parser: object, outcome: object) -> None:
    """Record one parser path without target- or run-specific labels."""
    ASSESSMENT_PARSER_RESULTS.labels(
        _enum(parser, ASSESSMENT_PARSERS, "command_registry"),
        _enum(outcome, ASSESSMENT_PARSER_OUTCOMES, "fallback_error"),
    ).inc()


__all__ = ["record_assessment_parser_result"]
