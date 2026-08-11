# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded Prometheus metrics for Project assessment operations."""

from __future__ import annotations

import math
import re
from typing import Any

from prometheus_client import Counter, Histogram


ASSESSMENT_CHECK_STATES = frozenset(
    {
        "not_started",
        "running",
        "covered",
        "needs_review",
        "failed",
        "blocked",
        "skipped",
        "not_applicable",
        "unknown",
    }
)
ASSESSMENT_TRANSITION_SOURCES = frozenset({"manual", "derived"})
ASSESSMENT_EVIDENCE_KINDS = frozenset(
    {
        "run",
        "workflow_execution",
        "finding",
        "atlas_entity",
        "run_artifact",
        "workspace_artifact",
        "screenshot",
        "other",
    }
)
ASSESSMENT_EVIDENCE_OUTCOMES = frozenset({"matched", "unmatched", "unavailable"})
ASSESSMENT_ACTION_KINDS = frozenset({"command", "workflow", "oast", "zap", "other"})
ASSESSMENT_POLICY_LEVELS = frozenset(
    {"safe", "standard", "intrusive", "destructive", "unknown"}
)
ASSESSMENT_ACTION_OUTCOMES = frozenset(
    {"launched", "rejected", "unavailable", "failed"}
)
ASSESSMENT_PARSERS = frozenset({"command_registry"})
ASSESSMENT_PARSER_OUTCOMES = frozenset({"parsed", "fallback_empty", "fallback_error"})
ASSESSMENT_CONNECTORS = frozenset({"zap", "oast"})
ASSESSMENT_CONNECTOR_PHASES = frozenset(
    {
        "submit",
        "progress",
        "cancel",
        "download",
        "register",
        "poll",
        "deregister",
        "job",
        "session",
        "other",
    }
)
ASSESSMENT_CONNECTOR_OUTCOMES = frozenset(
    {
        "success",
        "error",
        "ready",
        "canceled",
        "failed",
        "closed",
        "other",
    }
)
ASSESSMENT_CONNECTOR_DURATION_BUCKETS = (
    0.01,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
)
ASSESSMENT_PROFILE_KEY_LIMIT = 32
_PROFILE_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")

ASSESSMENT_CHECK_TRANSITIONS = Counter(
    "darklab_assessment_check_transitions",
    "Assessment check transitions by bounded state and source.",
    ("from_state", "to_state", "source"),
)
ASSESSMENT_EVIDENCE_MATCHES = Counter(
    "darklab_assessment_evidence_matches",
    "Derived assessment evidence match results by bounded kind and outcome.",
    ("evidence_kind", "outcome"),
)
ASSESSMENT_ACTIONS = Counter(
    "darklab_assessment_actions",
    "Assessment action launches and failures by bounded action and policy.",
    ("action_kind", "policy_level", "outcome"),
)
ASSESSMENT_PARSER_RESULTS = Counter(
    "darklab_assessment_parser_results",
    "Assessment parser results by bounded parser and outcome.",
    ("parser", "outcome"),
)
ASSESSMENT_CONNECTOR_OPERATIONS = Counter(
    "darklab_assessment_connector_operations",
    "Assessment connector operations by bounded connector, phase, and outcome.",
    ("connector", "phase", "outcome"),
)
ASSESSMENT_CONNECTOR_DURATION = Histogram(
    "darklab_assessment_connector_operation_duration_seconds",
    "Assessment connector operation duration by bounded connector, phase, and outcome.",
    ("connector", "phase", "outcome"),
    buckets=ASSESSMENT_CONNECTOR_DURATION_BUCKETS,
)


def _enum(value: object, allowed: frozenset[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else fallback


def assessment_profile_key_label(value: object) -> str:
    """Return a safe profile label; scrape-time collection applies the value cap."""
    normalized = str(value or "").strip().lower()
    return normalized if _PROFILE_KEY_RE.fullmatch(normalized) else "other"


LABEL_CARDINALITY_POLICIES: dict[str, dict[str, dict[str, Any]]] = {
    "darklab_assessment_active_cycles": {
        "owner_kind": {
            "kind": "enum",
            "values": frozenset({"personal", "team"}),
            "fallback": "personal",
        },
        "profile_key": {
            "kind": "bounded",
            "max_values": ASSESSMENT_PROFILE_KEY_LIMIT,
            "max_len": 64,
            "fallback": "other",
        },
    },
    "darklab_assessment_check_transitions": {
        "from_state": {
            "kind": "enum",
            "values": ASSESSMENT_CHECK_STATES,
            "fallback": "unknown",
        },
        "to_state": {
            "kind": "enum",
            "values": ASSESSMENT_CHECK_STATES,
            "fallback": "unknown",
        },
        "source": {
            "kind": "enum",
            "values": ASSESSMENT_TRANSITION_SOURCES,
            "fallback": "derived",
        },
    },
    "darklab_assessment_evidence_matches": {
        "evidence_kind": {
            "kind": "enum",
            "values": ASSESSMENT_EVIDENCE_KINDS,
            "fallback": "other",
        },
        "outcome": {
            "kind": "enum",
            "values": ASSESSMENT_EVIDENCE_OUTCOMES,
            "fallback": "unavailable",
        },
    },
    "darklab_assessment_actions": {
        "action_kind": {
            "kind": "enum",
            "values": ASSESSMENT_ACTION_KINDS,
            "fallback": "other",
        },
        "policy_level": {
            "kind": "enum",
            "values": ASSESSMENT_POLICY_LEVELS,
            "fallback": "unknown",
        },
        "outcome": {
            "kind": "enum",
            "values": ASSESSMENT_ACTION_OUTCOMES,
            "fallback": "failed",
        },
    },
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
    "darklab_assessment_connector_operations": {
        "connector": {
            "kind": "enum",
            "values": ASSESSMENT_CONNECTORS,
            "fallback": "oast",
        },
        "phase": {
            "kind": "enum",
            "values": ASSESSMENT_CONNECTOR_PHASES,
            "fallback": "other",
        },
        "outcome": {
            "kind": "enum",
            "values": ASSESSMENT_CONNECTOR_OUTCOMES,
            "fallback": "other",
        },
    },
    "darklab_assessment_connector_operation_duration_seconds": {
        "connector": {
            "kind": "enum",
            "values": ASSESSMENT_CONNECTORS,
            "fallback": "oast",
        },
        "phase": {
            "kind": "enum",
            "values": ASSESSMENT_CONNECTOR_PHASES,
            "fallback": "other",
        },
        "outcome": {
            "kind": "enum",
            "values": ASSESSMENT_CONNECTOR_OUTCOMES,
            "fallback": "other",
        },
    },
}

METRIC_DEFINITIONS = (
    ASSESSMENT_CHECK_TRANSITIONS,
    ASSESSMENT_EVIDENCE_MATCHES,
    ASSESSMENT_ACTIONS,
    ASSESSMENT_PARSER_RESULTS,
    ASSESSMENT_CONNECTOR_OPERATIONS,
    ASSESSMENT_CONNECTOR_DURATION,
)
HISTOGRAM_DEFINITIONS = (ASSESSMENT_CONNECTOR_DURATION,)


def _count(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def record_assessment_check_transition(
    from_state: object,
    to_state: object,
    source: object,
) -> None:
    ASSESSMENT_CHECK_TRANSITIONS.labels(
        _enum(from_state, ASSESSMENT_CHECK_STATES, "unknown"),
        _enum(to_state, ASSESSMENT_CHECK_STATES, "unknown"),
        _enum(source, ASSESSMENT_TRANSITION_SOURCES, "derived"),
    ).inc()


def record_assessment_evidence_matches(
    evidence_kind: object,
    outcome: object,
    count: object = 1,
) -> None:
    amount = _count(count)
    if amount:
        ASSESSMENT_EVIDENCE_MATCHES.labels(
            _enum(evidence_kind, ASSESSMENT_EVIDENCE_KINDS, "other"),
            _enum(outcome, ASSESSMENT_EVIDENCE_OUTCOMES, "unavailable"),
        ).inc(amount)


def record_assessment_action(
    action_kind: object,
    policy_level: object,
    outcome: object,
) -> None:
    ASSESSMENT_ACTIONS.labels(
        _enum(action_kind, ASSESSMENT_ACTION_KINDS, "other"),
        _enum(policy_level, ASSESSMENT_POLICY_LEVELS, "unknown"),
        _enum(outcome, ASSESSMENT_ACTION_OUTCOMES, "failed"),
    ).inc()


def record_assessment_parser_result(parser: object, outcome: object) -> None:
    """Record one parser path without target- or run-specific labels."""
    ASSESSMENT_PARSER_RESULTS.labels(
        _enum(parser, ASSESSMENT_PARSERS, "command_registry"),
        _enum(outcome, ASSESSMENT_PARSER_OUTCOMES, "fallback_error"),
    ).inc()


def record_assessment_connector_operation(
    connector: object,
    phase: object,
    outcome: object,
    duration_seconds: object | None = None,
) -> None:
    labels = (
        _enum(connector, ASSESSMENT_CONNECTORS, "oast"),
        _enum(phase, ASSESSMENT_CONNECTOR_PHASES, "other"),
        _enum(outcome, ASSESSMENT_CONNECTOR_OUTCOMES, "other"),
    )
    ASSESSMENT_CONNECTOR_OPERATIONS.labels(*labels).inc()
    if duration_seconds is None:
        return
    try:
        duration = float(duration_seconds)
    except (TypeError, ValueError):
        duration = 0.0
    if not math.isfinite(duration):
        duration = 0.0
    ASSESSMENT_CONNECTOR_DURATION.labels(*labels).observe(max(0.0, duration))


__all__ = [
    "ASSESSMENT_PROFILE_KEY_LIMIT",
    "assessment_profile_key_label",
    "record_assessment_action",
    "record_assessment_check_transition",
    "record_assessment_connector_operation",
    "record_assessment_evidence_matches",
    "record_assessment_parser_result",
]
