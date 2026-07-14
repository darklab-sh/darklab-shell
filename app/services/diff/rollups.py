# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Dashboard and digest rollups for persisted diff summaries."""

from __future__ import annotations

from typing import Any

SEVERITY_CRITICAL = "critical"
SEVERITY_IMPORTANT = "important"
SEVERITY_INFORMATIONAL = "informational"
SEVERITY_NONE = "none"
SEVERITY_ORDER = {
    SEVERITY_NONE: 0,
    SEVERITY_INFORMATIONAL: 1,
    SEVERITY_IMPORTANT: 2,
    SEVERITY_CRITICAL: 3,
}


def build_fire_rollup(
    summary: dict[str, Any] | None,
    *,
    diff_kind: str = "",
    truncated: bool = False,
    run_id: str = "",
    baseline_run_id: str = "",
    top_limit: int = 5,
) -> dict[str, Any]:
    """Return a stable, bounded rollup for watcher-fire dashboards and digests."""
    source = summary if isinstance(summary, dict) else {}
    classifier = str(source.get("classifier") or "unclassified")
    rollup = {
        "classifier": classifier,
        "severity": SEVERITY_NONE,
        "added": 0,
        "removed": 0,
        "changed": 0,
        "entity_added": int(source.get("entity_added_count") or 0),
        "entity_removed": int(source.get("entity_removed_count") or 0),
        "truncated": bool(truncated),
        "diff_kind": str(diff_kind or ""),
        "source_run_id": str(run_id or ""),
        "baseline_run_id": str(baseline_run_id or ""),
        "top_signals": [],
    }
    if classifier == "ports":
        _merge(rollup, _ports_rollup(source, top_limit=top_limit))
    elif classifier == "findings":
        _merge(rollup, _findings_rollup(source, top_limit=top_limit))
    elif classifier == "tls":
        _merge(rollup, _tls_rollup(source, top_limit=top_limit))
    elif classifier == "hosts":
        _merge(rollup, _hosts_rollup(source, top_limit=top_limit))
    elif classifier == "textual":
        _merge(rollup, _textual_rollup(source, top_limit=top_limit))
    elif classifier == "baseline":
        _merge(rollup, {"severity": SEVERITY_INFORMATIONAL})
    elif source:
        _merge(rollup, _generic_rollup(source, top_limit=top_limit))
    rollup["top_signals"] = _bounded_signals(rollup.get("top_signals"), top_limit)
    return rollup


def _merge(target: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if key == "severity":
            target[key] = _max_severity(str(target.get(key) or SEVERITY_NONE), str(value or SEVERITY_NONE))
        elif key == "top_signals":
            target.setdefault("top_signals", [])
            target["top_signals"].extend(value if isinstance(value, list) else [])
        elif key in {"added", "removed", "changed", "entity_added", "entity_removed"}:
            target[key] = int(target.get(key) or 0) + int(value or 0)
        else:
            target[key] = value


def _max_severity(left: str, right: str) -> str:
    normalized_left = left if left in SEVERITY_ORDER else SEVERITY_NONE
    normalized_right = right if right in SEVERITY_ORDER else SEVERITY_NONE
    return normalized_left if SEVERITY_ORDER[normalized_left] >= SEVERITY_ORDER[normalized_right] else normalized_right


def _ports_rollup(summary: dict[str, Any], *, top_limit: int) -> dict[str, Any]:
    added_ports = _list(summary.get("added_ports"))
    removed_ports = _list(summary.get("removed_ports"))
    changed_ports = _list(summary.get("changed_ports"))
    severity = SEVERITY_NONE
    signals = []
    for item in added_ports:
        state = str(item.get("state") or "")
        if state == "open":
            severity = _max_severity(severity, SEVERITY_CRITICAL)
        else:
            severity = _max_severity(severity, SEVERITY_INFORMATIONAL)
        signals.append(_signal("port_added", f"New {state or 'unknown'} port {_port_label(item)}".strip(), item))
    for item in changed_ports:
        severity = _max_severity(severity, SEVERITY_IMPORTANT)
        after = item.get("after") if isinstance(item.get("after"), dict) else {}
        signals.append(_signal("port_changed", f"Changed port {_port_label(after or item)}", item))
    for item in removed_ports:
        severity = _max_severity(severity, SEVERITY_INFORMATIONAL)
        signals.append(_signal("port_removed", f"Removed port {_port_label(item)}", item))
    return {
        "severity": severity,
        "added": int(summary.get("added_port_count") or len(added_ports)),
        "removed": len(removed_ports),
        "changed": int(summary.get("changed_port_count") or len(changed_ports)),
        "top_signals": signals[:top_limit],
    }


def _findings_rollup(summary: dict[str, Any], *, top_limit: int) -> dict[str, Any]:
    added = _list(summary.get("added_findings"))
    removed = _list(summary.get("removed_findings"))
    severity = SEVERITY_NONE
    signals = []
    for item in added:
        severity = _max_severity(severity, _finding_severity(item.get("severity")))
        title = str(item.get("title") or item.get("raw_line") or item.get("id") or "Finding")
        signals.append(_signal("finding_added", f"New finding: {title}", item))
    for item in removed:
        severity = _max_severity(severity, SEVERITY_INFORMATIONAL)
        title = str(item.get("title") or item.get("raw_line") or item.get("id") or "Finding")
        signals.append(_signal("finding_removed", f"Removed finding: {title}", item))
    return {
        "severity": severity,
        "added": int(summary.get("added_finding_count") or len(added)),
        "removed": len(removed),
        "changed": 0,
        "top_signals": signals[:top_limit],
    }


def _tls_rollup(summary: dict[str, Any], *, top_limit: int) -> dict[str, Any]:
    changed = _list(summary.get("changed_tls_fields"))
    critical_fields = {"issuer", "sha256_fingerprint", "not_after"}
    severity = SEVERITY_NONE
    signals = []
    for item in changed:
        field = str(item.get("field") or "")
        severity = _max_severity(severity, SEVERITY_CRITICAL if field in critical_fields else SEVERITY_INFORMATIONAL)
        signals.append(_signal("tls_changed", f"TLS {field.replace('_', ' ') or 'field'} changed", item))
    return {
        "severity": severity,
        "added": 0,
        "removed": 0,
        "changed": int(summary.get("changed_tls_field_count") or len(changed)),
        "top_signals": signals[:top_limit],
    }


def _hosts_rollup(summary: dict[str, Any], *, top_limit: int) -> dict[str, Any]:
    added = _list(summary.get("added_hosts"))
    removed = _list(summary.get("removed_hosts"))
    signals = [
        _signal("host_added", f"New host {item.get('host') or item.get('key')}", item)
        for item in added
    ]
    signals.extend(
        _signal("host_removed", f"Removed host {item.get('host') or item.get('key')}", item)
        for item in removed
    )
    return {
        "severity": SEVERITY_IMPORTANT if added else (SEVERITY_INFORMATIONAL if removed else SEVERITY_NONE),
        "added": int(summary.get("added_host_count") or len(added)),
        "removed": len(removed),
        "changed": 0,
        "top_signals": signals[:top_limit],
    }


def _textual_rollup(summary: dict[str, Any], *, top_limit: int) -> dict[str, Any]:
    added = int(summary.get("added_line_count") or 0) + int(summary.get("entity_added_count") or 0)
    removed = int(summary.get("removed_line_count") or 0) - int(summary.get("suppressed_removed_line_count") or 0)
    changed = int(summary.get("changed_line_count") or 0)
    signals = []
    if added:
        signals.append(_signal("text_added", f"{added} added line/entity changes"))
    if changed:
        signals.append(_signal("text_changed", f"{changed} changed lines"))
    if removed:
        signals.append(_signal("text_removed", f"{removed} removed line/entity changes"))
    return {
        "severity": SEVERITY_INFORMATIONAL if added or removed or changed else SEVERITY_NONE,
        "added": added,
        "removed": max(0, removed),
        "changed": changed,
        "top_signals": signals[:top_limit],
    }


def _generic_rollup(summary: dict[str, Any], *, top_limit: int) -> dict[str, Any]:
    added = _count_keys(summary, ("added", "added_count"))
    removed = _count_keys(summary, ("removed", "removed_count"))
    changed = _count_keys(summary, ("changed", "changed_count"))
    signals = []
    if added:
        signals.append(_signal("added", f"{added} added changes"))
    if changed:
        signals.append(_signal("changed", f"{changed} changed items"))
    if removed:
        signals.append(_signal("removed", f"{removed} removed changes"))
    return {
        "severity": SEVERITY_INFORMATIONAL if added or removed or changed else SEVERITY_NONE,
        "added": added,
        "removed": removed,
        "changed": changed,
        "top_signals": signals[:top_limit],
    }


def _finding_severity(value: Any) -> str:
    severity = str(value or "").strip().lower()
    if severity in {"critical", "high"}:
        return SEVERITY_CRITICAL
    if severity == "medium":
        return SEVERITY_IMPORTANT
    if severity in {"low", "info", "informational"}:
        return SEVERITY_INFORMATIONAL
    return SEVERITY_INFORMATIONAL


def _port_label(item: dict[str, Any]) -> str:
    key = str(item.get("key") or "")
    service = str(item.get("service_text") or item.get("service") or "")
    return " ".join(part for part in (key, service) if part).strip() or "port"


def _signal(kind: str, label: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"kind": kind, "label": str(label or kind)}
    if details:
        payload["details"] = details
    return payload


def _bounded_signals(value: Any, limit: int) -> list[dict[str, Any]]:
    signals = value if isinstance(value, list) else []
    return [signal for signal in signals if isinstance(signal, dict) and str(signal.get("label") or "")][: max(1, limit)]


def _list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _count_keys(summary: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        value = summary.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return max(0, value)
        if isinstance(value, list):
            return len(value)
    return 0
