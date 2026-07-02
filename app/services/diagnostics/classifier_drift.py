"""On-demand classifier drift sampling for operator diagnostics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Mapping, cast

from config import CFG
from core.output_signals import OutputSignalClassifier, strip_ansi_codes
from services.commands.registry import command_root, is_help_invocation
from services.runs.kinds import RUN_KIND_BUILTIN
from services.runs.output_model import LineEvent, LineRole, legacy_cls_for_event, line_event_from_legacy
from services.runs.output_store import load_run_output_events_for_run

_DEFAULT_RUN_LIMIT = 50
_MAX_RUN_LIMIT = 200
_DEFAULT_LINE_LIMIT = 200
_MAX_LINE_LIMIT = 1000
_SAMPLE_LIMIT = 5
_LINE_TEXT_LIMIT = 220
_STRUCTURAL_FINDING_ROLES = {
    LineRole.prompt_echo,
    LineRole.pty_marker,
    LineRole.progress,
    LineRole.status_line,
    LineRole.help_row,
    LineRole.section_header,
}


def classifier_drift_report(
    conn,
    *,
    run_limit: object = _DEFAULT_RUN_LIMIT,
    line_limit: object = _DEFAULT_LINE_LIMIT,
    command_root_filter: object = "",
    include_full: object = False,
) -> dict[str, object]:
    """Sample recent saved output and compare stored metadata with today's classifier."""
    normalized_run_limit = _bounded_int(run_limit, _DEFAULT_RUN_LIMIT, minimum=1, maximum=_MAX_RUN_LIMIT)
    normalized_line_limit = _bounded_int(line_limit, _DEFAULT_LINE_LIMIT, minimum=1, maximum=_MAX_LINE_LIMIT)
    root_filter = str(command_root_filter or "").strip().lower()
    prefer_full = _truthy(include_full)
    rows = _recent_run_rows(conn, normalized_run_limit)
    buckets: dict[str, dict[str, object]] = {
        "metadata_changed": _bucket("Metadata changed"),
        "finding_on_structural_role": _bucket("Finding on structural role"),
        "help_output_signal": _bucket("Help output signal"),
        "entity_without_signal": _bucket("Entity without signal"),
        "high_body_ratio": _bucket("High body-only ratio"),
    }
    runs_scanned = 0
    lines_sampled = 0
    truncated_runs = 0
    run_summaries = []

    for row in rows:
        run = _row_dict(row)
        run_root = command_root(str(run.get("command") or ""))
        if root_filter and run_root != root_filter:
            continue
        runs_scanned += 1
        events_result = load_run_output_events_for_run(
            run,
            prefer_full=prefer_full,
            log_event="CLASSIFIER_DRIFT_OUTPUT_LOAD_FAILED",
        )
        events = list(events_result.events[:normalized_line_limit])
        if len(events_result.events) > normalized_line_limit:
            truncated_runs += 1
        run_line_count = len(events)
        lines_sampled += run_line_count
        current_events = _reclassify_events(run, events)
        run_bucket_counts: Counter[str] = Counter()
        for stored, current in zip(events, current_events, strict=False):
            issues = _event_issues(run, stored, current)
            for issue in issues:
                run_bucket_counts[issue] += 1
                _record_sample(buckets[issue], run, stored, current)
        body_only_count = sum(1 for event in current_events if _is_body_only(event))
        if run_line_count >= 20 and body_only_count / max(1, run_line_count) >= 0.95:
            run_bucket_counts["high_body_ratio"] += 1
            _record_sample(
                buckets["high_body_ratio"],
                run,
                events[0] if events else None,
                current_events[0] if current_events else None,
                extra={
                    "body_only_lines": body_only_count,
                    "sampled_lines": run_line_count,
                    "ratio": round(body_only_count / max(1, run_line_count), 3),
                },
            )
        if run_bucket_counts:
            run_summaries.append({
                "run_id": str(run.get("id") or ""),
                "command": str(run.get("command") or ""),
                "command_root": run_root,
                "sampled_lines": run_line_count,
                "issues": dict(run_bucket_counts),
            })

    bucket_payloads = []
    total_issues = 0
    for key, bucket in buckets.items():
        count_value = bucket.get("count", 0)
        count = count_value if isinstance(count_value, int) else 0
        total_issues += count
        if count:
            bucket_payloads.append({"key": key, **bucket})

    return {
        "ok": True,
        "params": {
            "runs": normalized_run_limit,
            "lines": normalized_line_limit,
            "root": root_filter,
            "include_full": prefer_full,
        },
        "runs_scanned": runs_scanned,
        "lines_sampled": lines_sampled,
        "truncated_runs": truncated_runs,
        "issue_count": total_issues,
        "buckets": bucket_payloads,
        "runs": run_summaries[:20],
    }


def _recent_run_rows(conn, limit: int):
    return conn.execute(
        "SELECT r.id, r.session_id, r.command, r.run_kind, r.output, r.output_preview, "
        "r.preview_truncated, r.full_output_available, "
        "r.full_output_truncated, art.rel_path "
        "FROM runs r LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
        "WHERE r.finished IS NOT NULL "
        "ORDER BY r.finished DESC, r.started DESC "
        "LIMIT ?",
        (int(limit),),
    ).fetchall()


def _reclassify_events(run: Mapping[str, object], events: list[LineEvent]) -> list[LineEvent]:
    command = str(run.get("command") or "")
    cmd_type = "builtin" if str(run.get("run_kind") or "") == RUN_KIND_BUILTIN else "real"
    classifier = OutputSignalClassifier(
        command,
        cmd_type=cmd_type,
        extra_domain_suffixes=CFG.get("output_entity_extra_domain_suffixes", []),
    )
    current_events = []
    for stored in events:
        cls = legacy_cls_for_event(stored)
        metadata = classifier.classify_line(stored.text, cls=cls)
        role_value = metadata.get("role")
        signals_value = metadata.get("signals")
        entities_value = metadata.get("entities")
        metadata_event = line_event_from_legacy(
            stored.text,
            cls,
            role=role_value if isinstance(role_value, str) else None,
            signals=cast(Sequence[object], signals_value) if isinstance(signals_value, list) else None,
            entities=(
                cast(Sequence[Mapping[str, object]], entities_value)
                if isinstance(entities_value, list)
                else None
            ),
        )
        current_events.append(replace(
            metadata_event,
            line_index=metadata.get("line_index") if isinstance(metadata.get("line_index"), int) else None,
            command_root=str(metadata.get("command_root") or ""),
            target=str(metadata.get("target") or ""),
        ))
    return current_events


def _event_issues(run: Mapping[str, object], stored: LineEvent, current: LineEvent) -> list[str]:
    issues = []
    if _event_signature(stored) != _event_signature(current):
        issues.append("metadata_changed")
    if "findings" in _signal_values(stored) | _signal_values(current):
        if stored.role in _STRUCTURAL_FINDING_ROLES or current.role in _STRUCTURAL_FINDING_ROLES:
            issues.append("finding_on_structural_role")
    command = str(run.get("command") or "")
    if is_help_invocation(command, root=command_root(command)):
        if stored.signals or current.signals or stored.entities or current.entities:
            issues.append("help_output_signal")
    if (stored.entities or current.entities) and not (_signal_values(stored) | _signal_values(current)):
        issues.append("entity_without_signal")
    return issues


def _event_signature(event: LineEvent) -> tuple[object, ...]:
    return (
        event.kind.value,
        event.role.value,
        tuple(signal.value for signal in event.signals),
        tuple((entity.type, entity.canonical_value) for entity in event.entities),
        event.command_root,
        event.target,
    )


def _signal_values(event: LineEvent) -> set[str]:
    return {signal.value for signal in event.signals}


def _is_body_only(event: LineEvent) -> bool:
    return (
        event.kind.value == "info"
        and event.role is LineRole.body
        and not event.signals
        and not event.entities
        and bool(event.text.strip())
    )


def _bucket(label: str) -> dict[str, object]:
    return {"label": label, "count": 0, "samples": []}


def _record_sample(
    bucket: dict[str, object],
    run: Mapping[str, object],
    stored: LineEvent | None,
    current: LineEvent | None,
    *,
    extra: Mapping[str, object] | None = None,
) -> None:
    count_value = bucket.get("count", 0)
    bucket["count"] = (count_value if isinstance(count_value, int) else 0) + 1
    samples = bucket["samples"]
    if not isinstance(samples, list) or len(samples) >= _SAMPLE_LIMIT:
        return
    text = stored.text if stored is not None else ""
    sample: dict[str, object] = {
        "run_id": str(run.get("id") or ""),
        "command": str(run.get("command") or ""),
        "command_root": command_root(str(run.get("command") or "")),
        "line_index": stored.line_index if stored is not None else None,
        "text": _sample_text(text),
        "stored": _event_summary(stored),
        "current": _event_summary(current),
    }
    if extra:
        sample["extra"] = dict(extra)
    samples.append(sample)


def _event_summary(event: LineEvent | None) -> dict[str, object]:
    if event is None:
        return {}
    return {
        "kind": event.kind.value,
        "role": event.role.value,
        "signals": [signal.value for signal in event.signals],
        "entities": [
            {"type": entity.type, "canonical_value": entity.canonical_value}
            for entity in event.entities
        ],
        "command_root": event.command_root,
        "target": event.target,
    }


def _sample_text(value: str) -> str:
    text = strip_ansi_codes(str(value or "")).replace("\n", " ").strip()
    if len(text) <= _LINE_TEXT_LIMIT:
        return text
    return text[: _LINE_TEXT_LIMIT - 3] + "..."


def _row_dict(row) -> dict[str, object]:
    if isinstance(row, dict):
        return dict(row)
    keys = getattr(row, "keys", lambda: [])()
    if keys:
        return {key: row[key] for key in keys}
    return dict(row)


def _bounded_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(cast(Any, value))
    except (TypeError, ValueError):
        parsed = default
    return min(maximum, max(minimum, parsed))


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
