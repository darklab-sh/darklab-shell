# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded strict-JSON decoding for Schemathesis NDJSON reports."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from services.assessments.schemathesis_report_contracts import (
    SchemathesisReportError,
)


SCHEMATHESIS_REPORT_MAX_LINES = 512
SCHEMATHESIS_REPORT_MAX_LINE_BYTES = 2 * 1024 * 1024
_MAX_JSON_NODES = 200_000
_MAX_JSON_DEPTH = 64
_EVENT_TYPES = frozenset(
    {
        "Initialize",
        "LoadingStarted",
        "LoadingFinished",
        "EngineStarted",
        "PhaseStarted",
        "PhaseFinished",
        "SchemaAnalysisWarnings",
        "SuiteStarted",
        "SuiteFinished",
        "ScenarioStarted",
        "ScenarioFinished",
        "FuzzScenarioStarted",
        "FuzzScenarioFinished",
        "Interrupted",
        "NonFatalError",
        "FatalError",
        "RateLimitRetry",
        "EngineFinished",
    }
)


def decode_schemathesis_events(raw: bytes) -> list[tuple[str, dict[str, Any]]]:
    """Decode one newline-complete event stream under fixed shape limits."""
    if not raw.endswith(b"\n"):
        raise _error(
            "incomplete_report", "Schemathesis report must end at an NDJSON boundary."
        )
    lines = raw.splitlines()
    if not lines or len(lines) > SCHEMATHESIS_REPORT_MAX_LINES:
        raise _error(
            "report_line_limit_exceeded", "Schemathesis report has too many events."
        )
    events: list[tuple[str, dict[str, Any]]] = []
    initialize_count = terminal_count = total_nodes = 0
    for line in lines:
        if not line or len(line) > SCHEMATHESIS_REPORT_MAX_LINE_BYTES:
            raise _error(
                "invalid_report_line",
                "Schemathesis report contains an invalid event line.",
            )
        decoded = _decode_line(line)
        if not isinstance(decoded, dict) or len(decoded) != 1:
            raise _error(
                "invalid_event_envelope",
                "Schemathesis report event envelope is invalid.",
            )
        event_name, payload = next(iter(decoded.items()))
        if event_name not in _EVENT_TYPES or not isinstance(payload, dict):
            raise _error(
                "unsupported_report_event",
                "Schemathesis report contains an unsupported event.",
            )
        initialize_count += event_name == "Initialize"
        terminal_count += event_name == "EngineFinished"
        total_nodes += _json_node_count(decoded)
        if total_nodes > _MAX_JSON_NODES:
            raise _error(
                "report_complexity_exceeded",
                "Schemathesis report is too complex to parse.",
            )
        events.append((event_name, payload))
    if initialize_count != 1 or terminal_count != 1:
        raise _error(
            "invalid_report_boundaries", "Schemathesis report boundaries are ambiguous."
        )
    return events


def _decode_line(line: bytes) -> Any:
    try:
        return json.loads(
            line.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        if isinstance(exc, SchemathesisReportError):
            raise
        raise _error(
            "invalid_report_json", "Schemathesis report contains invalid JSON."
        ) from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error(
                "duplicate_report_key",
                "Schemathesis report contains a duplicate JSON key.",
            )
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError


def _json_node_count(value: Any) -> int:
    count = 0
    stack = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        count += 1
        if depth > _MAX_JSON_DEPTH:
            raise _error(
                "report_complexity_exceeded",
                "Schemathesis report is too deeply nested.",
            )
        if isinstance(current, Mapping):
            stack.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            stack.extend((child, depth + 1) for child in current)
    return count


def _error(code: str, message: str) -> SchemathesisReportError:
    return SchemathesisReportError(code, message)


__all__ = [
    "SCHEMATHESIS_REPORT_MAX_LINE_BYTES",
    "SCHEMATHESIS_REPORT_MAX_LINES",
    "decode_schemathesis_events",
]
