# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded metrics for Project-scoped one-off probes."""

from __future__ import annotations

from typing import Any

from prometheus_client import Counter


PROBE_PHASES = frozenset({"catalog", "plan", "confirm", "launch", "cleanup", "resolve"})
PROBE_OUTCOMES = frozenset({"success", "rejected", "unavailable", "failed"})
PROBE_CREDENTIAL_USE = frozenset({"none", "protected"})

PROBE_OPERATIONS = Counter(
    "darklab_probe_operations",
    "Project probe operations by bounded phase, outcome, and credential use.",
    ("phase", "outcome", "credential_use"),
)

LABEL_CARDINALITY_POLICIES: dict[str, dict[str, dict[str, Any]]] = {
    "darklab_probe_operations": {
        "phase": {
            "kind": "enum",
            "values": PROBE_PHASES,
            "fallback": "plan",
        },
        "outcome": {
            "kind": "enum",
            "values": PROBE_OUTCOMES,
            "fallback": "failed",
        },
        "credential_use": {
            "kind": "enum",
            "values": PROBE_CREDENTIAL_USE,
            "fallback": "none",
        },
    },
}

METRIC_DEFINITIONS = (PROBE_OPERATIONS,)
HISTOGRAM_DEFINITIONS: tuple[Any, ...] = ()


def _label(value: object, allowed: frozenset[str], fallback: str) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in allowed else fallback


def record_probe_operation(
    phase: object,
    outcome: object,
    *,
    protected: bool = False,
) -> None:
    """Record one operation without target, Project, action, or run labels."""
    PROBE_OPERATIONS.labels(
        _label(phase, PROBE_PHASES, "plan"),
        _label(outcome, PROBE_OUTCOMES, "failed"),
        "protected" if protected else "none",
    ).inc()


__all__ = ["record_probe_operation"]
