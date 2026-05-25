"""Build redacted, deterministic run context for AI assists."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import logging
import re
from typing import Any, Mapping

from config import CFG, get_share_redaction_rules
from core.database import db_connect
from core.helpers import get_log_session_id
from core.redaction import apply_redaction_rules, redact_line_entries
from services.ai import ai_cfg
from services.ai.prompts import scrub_prompt_boundaries
from services.runs.output_model import LineEvent, LineKind, LineRole, LineSignal
from services.runs.output_store import load_run_output_events_for_run
from services.secrets.storage import list_secret_metadata
from services.workspace.files import WorkspaceDisabled, session_workspace_dir

_SECRET_NAME_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]{0,63}\b")
_TRANSCRIPT_PRIORITY_ROLES = {
    LineRole.denied,
    LineRole.exit_fail,
    LineRole.exit_ok,
    LineRole.kv,
    LineRole.section_header,
}
_TRANSCRIPT_LOW_VALUE_ROLES = {LineRole.progress, LineRole.status_line}
_MAX_ENTITIES_PER_TYPE = 100
_DEFAULT_TAIL_LINES = 160
_SUMMARY_TAIL_LINES = 25
_SUMMARY_MAX_INPUT_CHARS = 4000
_NEXT_COMMANDS_TAIL_LINES = 25
_NEXT_COMMANDS_MAX_INPUT_CHARS = 5000
_SUMMARY_FINDING_LINE_CHARS = 200
_MIN_USEFUL_CHARS = 200

log = logging.getLogger("shell")


@dataclass(frozen=True)
class AIContextResult:
    context: dict[str, Any]
    context_hash: str
    input_chars: int
    estimated_input_tokens: int
    pre_redaction_bytes: int
    redacted_bytes: int
    useful: bool
    omitted_sections: tuple[str, ...]


def build_run_context(
    run_id: str,
    *,
    session_id: str | None = None,
    cfg: dict | None = None,
    variant: str = "default",
) -> AIContextResult:
    """Return capped, redacted context for a saved run."""
    active_cfg = CFG if cfg is None else cfg
    settings = ai_cfg(active_cfg)
    with db_connect() as conn:
        run_row = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.id = ?",
            (run_id,),
        ).fetchone()
        if not run_row:
            raise ValueError("run not found")
        run = dict(run_row)
        owner_session_id = str(run.get("session_id") or "")
        if session_id is not None and str(session_id) != owner_session_id:
            raise PermissionError("run does not belong to this session")
        findings = _load_findings(conn, owner_session_id, run_id)
        entities = _load_entities(conn, owner_session_id, run_id)
        project_context = _load_project_context(conn, owner_session_id, entities)
        output_summary = _load_output_summary(conn, run_id)

    output_result = load_run_output_events_for_run(
        run,
        prefer_full=bool(settings["allow_full_output"]),
        log_event="AI_CONTEXT_FULL_OUTPUT_LOAD_FAILED",
    )
    redaction_rules = get_share_redaction_rules(active_cfg)
    secret_names = _secret_names(owner_session_id)
    configured_max_chars = int(settings["max_input_chars"])
    if variant == "summary":
        max_input_chars = min(configured_max_chars, _SUMMARY_MAX_INPUT_CHARS)
    elif variant == "next_commands":
        max_input_chars = min(configured_max_chars, _NEXT_COMMANDS_MAX_INPUT_CHARS)
    else:
        max_input_chars = configured_max_chars
    raw_context = _assemble_context(
        run,
        findings=findings,
        entities=entities,
        project_context=project_context,
        output_summary=output_summary,
        events=output_result.events,
        output_source=output_result.source,
        output_truncated=output_result.truncated,
        include_full=bool(settings["allow_full_output"]),
        max_input_chars=max_input_chars,
        redaction_rules=redaction_rules,
        secret_names=secret_names,
        active_cfg=active_cfg,
        variant=variant,
    )
    drop_order = (
        ("transcript_tail", "warnings_errors", "findings")
        if variant == "summary"
        else (
            "project_context",
            "output_summary",
            "warnings_errors",
            "transcript_tail",
            "entities",
            "findings",
        )
        if variant == "next_commands"
        else (
            "full_transcript",
            "transcript_tail",
            "project_context",
            "output_summary",
            "entities",
            "warnings_errors",
            "findings",
        )
    )
    result = _finalize_context(raw_context, max_input_chars=max_input_chars, drop_order=drop_order)
    log.debug(
        "AI_CONTEXT_BUILT",
        extra={
            "run_id": run_id,
            "session": get_log_session_id(owner_session_id),
            "variant": variant,
            "output_source": output_result.source,
            "output_truncated": output_result.truncated,
            "max_input_chars": max_input_chars,
            "input_chars": result.input_chars,
            "estimated_input_tokens": result.estimated_input_tokens,
            "redacted_bytes": result.redacted_bytes,
            "pre_redaction_bytes": result.pre_redaction_bytes,
            "useful": result.useful,
            "omitted_sections": list(result.omitted_sections),
            "section_count": len(result.context),
            "context_hash": result.context_hash,
        },
    )
    return result


def _assemble_context(
    run: Mapping[str, Any],
    *,
    findings: list[dict[str, Any]],
    entities: dict[str, list[str]],
    project_context: list[dict[str, Any]],
    output_summary: dict[str, dict[str, int]],
    events: list[LineEvent],
    output_source: str,
    output_truncated: bool,
    include_full: bool,
    max_input_chars: int,
    redaction_rules: list[dict[str, Any]],
    secret_names: set[str],
    active_cfg: dict,
    variant: str,
) -> dict[str, Any]:
    runtime_seconds = _runtime_seconds(run)
    run_context = {
        "id": run.get("id") or "",
        "command": run.get("command") or "",
        "target": _first_event_target(events),
        "run_kind": run.get("run_kind") or "external",
        "exit_code": run.get("exit_code"),
        "runtime_seconds": runtime_seconds,
        "started": run.get("started") or "",
        "finished": run.get("finished") or "",
        "output_source": output_source,
        "output_truncated": bool(output_truncated),
    }
    if variant == "summary":
        return {
            "run": _redact_value({
                "command": run_context["command"],
                "target": run_context["target"],
                "run_kind": run_context["run_kind"],
                "exit_code": run_context["exit_code"],
                "runtime_seconds": run_context["runtime_seconds"],
                "output_truncated": run_context["output_truncated"],
            }, redaction_rules, secret_names, active_cfg),
            "findings": _redact_value(_summary_findings(findings), redaction_rules, secret_names, active_cfg),
            "warnings_errors": _redact_value(_warning_error_lines(events), redaction_rules, secret_names, active_cfg),
            "transcript_tail": _redact_events(
                _transcript_tail(events, limit=_SUMMARY_TAIL_LINES),
                redaction_rules,
                secret_names,
                active_cfg,
                compact=True,
            ),
        }
    if variant == "next_commands":
        return {
            "run": _redact_value({
                "command": run_context["command"],
                "target": run_context["target"],
                "run_kind": run_context["run_kind"],
                "exit_code": run_context["exit_code"],
                "runtime_seconds": run_context["runtime_seconds"],
                "output_truncated": run_context["output_truncated"],
            }, redaction_rules, secret_names, active_cfg),
            "findings": _redact_value(_summary_findings(findings), redaction_rules, secret_names, active_cfg),
            "warnings_errors": _redact_value(_warning_error_lines(events), redaction_rules, secret_names, active_cfg),
            "entities": _redact_value(_compact_entities(entities, limit_per_type=25), redaction_rules, secret_names, active_cfg),
            "project_context": _redact_value(project_context[:25], redaction_rules, secret_names, active_cfg),
            "output_summary": output_summary,
            "transcript_tail": _redact_events(
                _transcript_tail(events, limit=_NEXT_COMMANDS_TAIL_LINES),
                redaction_rules,
                secret_names,
                active_cfg,
                compact=True,
            ),
        }
    context: dict[str, Any] = {
        "run": _redact_value(run_context, redaction_rules, secret_names, active_cfg),
        "findings": _redact_value(findings, redaction_rules, secret_names, active_cfg),
        "warnings_errors": _redact_value(_warning_error_lines(events), redaction_rules, secret_names, active_cfg),
        "entities": _redact_value(entities, redaction_rules, secret_names, active_cfg),
        "project_context": _redact_value(project_context, redaction_rules, secret_names, active_cfg),
        "output_summary": output_summary,
        "transcript_tail": _redact_events(_transcript_tail(events), redaction_rules, secret_names, active_cfg),
    }
    if include_full:
        full_transcript = _redact_events(events, redaction_rules, secret_names, active_cfg)
        if _json_len({**context, "full_transcript": full_transcript}) <= max_input_chars:
            context["full_transcript"] = full_transcript
    return context


def _compact_entities(entities: dict[str, list[str]], *, limit_per_type: int) -> dict[str, list[str]]:
    return {
        str(entity_type): list(values[:limit_per_type])
        for entity_type, values in entities.items()
        if values
    }


def _finalize_context(
    context: dict[str, Any],
    *,
    max_input_chars: int,
    drop_order: tuple[str, ...],
) -> AIContextResult:
    omitted: list[str] = []
    working, pre_redaction_bytes, redacted_bytes = _strip_redaction_markers(dict(context))
    for key in drop_order:
        if _json_len(working) <= max_input_chars:
            break
        if key in working:
            working.pop(key, None)
            omitted.append(key)
    if _json_len(working) > max_input_chars:
        command = str(working.get("run", {}).get("command") or "")
        if len(command) > 500:
            working["run"] = {**working.get("run", {}), "command": command[:500] + "...[truncated]"}
            omitted.append("run.command_tail")
    canonical = json.dumps(working, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    encoded = canonical.encode("utf-8", errors="replace")
    pre_redaction_bytes = pre_redaction_bytes or len(encoded)
    useful_chars = _useful_context_chars(working)
    return AIContextResult(
        context=working,
        context_hash=hashlib.sha256(encoded).hexdigest(),
        input_chars=len(canonical),
        estimated_input_tokens=max(1, len(canonical) // 4),
        pre_redaction_bytes=pre_redaction_bytes,
        redacted_bytes=redacted_bytes,
        useful=useful_chars >= _MIN_USEFUL_CHARS,
        omitted_sections=tuple(omitted),
    )


def _redact_value(value: Any, rules: list[dict[str, Any]], secret_names: set[str], cfg: dict) -> Any:
    pre_bytes = 0
    redacted_bytes = 0

    def walk(item: Any) -> Any:
        nonlocal pre_bytes, redacted_bytes
        if isinstance(item, dict):
            return {str(key): walk(child) for key, child in item.items()}
        if isinstance(item, list):
            return [walk(child) for child in item]
        if isinstance(item, tuple):
            return [walk(child) for child in item]
        if isinstance(item, str):
            text, before, changed = _redact_text(item, rules, secret_names, cfg)
            pre_bytes += before
            redacted_bytes += changed
            return text
        return item

    loaded = walk(value)
    marker = {"pre_redaction_bytes": pre_bytes, "redacted_bytes": redacted_bytes}
    if isinstance(loaded, dict):
        loaded["_redaction"] = marker
    elif isinstance(loaded, list):
        loaded = [{"_redaction": marker}, *loaded]
    return loaded


def _redact_text(text: str, rules: list[dict[str, Any]], secret_names: set[str], cfg: dict) -> tuple[str, int, int]:
    scrubbed = scrub_prompt_boundaries(_strip_workspace_paths(text, cfg))
    redacted = apply_redaction_rules(scrubbed, rules)
    redacted = _strip_secret_names(redacted, secret_names)
    pre_bytes = len(scrubbed.encode("utf-8", errors="replace"))
    changed_bytes = _changed_source_bytes(scrubbed, redacted)
    return redacted, pre_bytes, changed_bytes


def _redact_events(
    events: list[LineEvent],
    rules: list[dict[str, Any]],
    secret_names: set[str],
    cfg: dict,
    *,
    compact: bool = False,
) -> list[dict[str, Any]]:
    from dataclasses import replace

    scrubbed = []
    pre_bytes = 0
    for event in events:
        text = scrub_prompt_boundaries(_strip_workspace_paths(event.text, cfg))
        target = scrub_prompt_boundaries(_strip_workspace_paths(event.target, cfg)) if event.target else ""
        pre_bytes += len(text.encode("utf-8", errors="replace"))
        pre_bytes += len(target.encode("utf-8", errors="replace"))
        scrubbed.append(replace(
            event,
            text=text,
            target=target,
        ))
    redacted_events = redact_line_entries(scrubbed, rules)
    rows = []
    redacted_bytes = 0
    for original, event in zip(scrubbed, redacted_events, strict=False):
        text = _strip_secret_names(event.text, secret_names)
        target = _strip_secret_names(event.target, secret_names) if event.target else ""
        redacted_bytes += _changed_source_bytes(original.text, text)
        redacted_bytes += _changed_source_bytes(original.target, target)
        if compact:
            rows.append({
                "line_index": event.line_index,
                "text": text,
            })
        else:
            rows.append({
                "line_index": event.line_index,
                "kind": event.kind.value,
                "role": event.role.value,
                "signals": [signal.value for signal in event.signals],
                "text": text,
                **({"target": target} if target else {}),
            })
    if rows:
        rows[0]["_redaction"] = {
            "pre_redaction_bytes": pre_bytes,
            "redacted_bytes": redacted_bytes,
        }
    return rows


def _changed_source_bytes(before: str, after: str) -> int:
    """Return bytes from ``before`` that were replaced or removed."""
    if before == after:
        return 0
    changed = 0
    matcher = SequenceMatcher(a=before, b=after, autojunk=False)
    for tag, start, end, _next_start, _next_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed += len(before[start:end].encode("utf-8", errors="replace"))
    return changed


def _strip_redaction_markers(value: Any) -> tuple[Any, int, int]:
    pre_bytes = 0
    redacted_bytes = 0

    def walk(item: Any) -> Any:
        nonlocal pre_bytes, redacted_bytes
        if isinstance(item, dict):
            marker = item.get("_redaction")
            if isinstance(marker, dict):
                pre_bytes += int(marker.get("pre_redaction_bytes") or 0)
                redacted_bytes += int(marker.get("redacted_bytes") or 0)
            return {key: walk(child) for key, child in item.items() if key != "_redaction"}
        if isinstance(item, list):
            return [walk(child) for child in item if not (isinstance(child, dict) and set(child) == {"_redaction"})]
        return item

    return walk(value), pre_bytes, redacted_bytes


def _load_findings(conn, session_id: str, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT severity, kind, title, raw_line, line_number, status "
        "FROM findings WHERE session_id = ? AND run_id = ? AND COALESCE(suppressed, FALSE) = FALSE "
        "ORDER BY line_number, created LIMIT 200",
        (session_id, run_id),
    ).fetchall()
    return [{
        "severity": row["severity"],
        "kind": row["kind"],
        "title": row["title"],
        "line": row["raw_line"],
        "line_number": row["line_number"],
        "status": row["status"],
    } for row in rows]


def _load_entities(conn, session_id: str, run_id: str) -> dict[str, list[str]]:
    rows = conn.execute(
        "SELECT e.type, e.canonical_value FROM entities e "
        "JOIN entity_run_links erl ON erl.entity_id = e.id "
        "WHERE e.session_id = ? AND erl.run_id = ? AND COALESCE(e.suppressed, FALSE) = FALSE "
        "ORDER BY e.type, e.canonical_value",
        (session_id, run_id),
    ).fetchall()
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        values = grouped[str(row["type"])]
        if len(values) < _MAX_ENTITIES_PER_TYPE and row["canonical_value"] not in values:
            values.append(str(row["canonical_value"]))
    return dict(grouped)


def _load_project_context(conn, session_id: str, entities: dict[str, list[str]]) -> list[dict[str, Any]]:
    if not entities:
        return []
    values = [value for items in entities.values() for value in items]
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        "SELECT DISTINCT p.name, p.slug, pl.entity_type, e.canonical_value "
        "FROM projects p JOIN project_links pl ON pl.project_id = p.id "
        "JOIN entities e ON e.id = pl.entity_id "
        f"WHERE p.session_id = ? AND e.canonical_value IN ({placeholders}) "  # nosec
        "ORDER BY p.name, e.canonical_value LIMIT 100",
        (session_id, *values),
    ).fetchall()
    return [{
        "project": row["name"],
        "slug": row["slug"],
        "entity_type": row["entity_type"],
        "target": row["canonical_value"],
    } for row in rows]


def _load_output_summary(conn, run_id: str) -> dict[str, dict[str, int]]:
    rows = conn.execute(
        "SELECT family, value, count FROM run_output_summary WHERE run_id = ? ORDER BY family, value",
        (run_id,),
    ).fetchall()
    summary: dict[str, dict[str, int]] = defaultdict(dict)
    for row in rows:
        summary[str(row["family"])][str(row["value"])] = int(row["count"])
    return dict(summary)


def _summary_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for finding in findings:
        line = str(finding.get("line") or "")
        if len(line) > _SUMMARY_FINDING_LINE_CHARS:
            line = line[:_SUMMARY_FINDING_LINE_CHARS] + "...[truncated]"
        rows.append({
            "severity": finding.get("severity"),
            "kind": finding.get("kind"),
            "title": finding.get("title"),
            "line": line,
            "line_number": finding.get("line_number"),
        })
    return rows


def _transcript_tail(events: list[LineEvent], *, limit: int = _DEFAULT_TAIL_LINES) -> list[LineEvent]:
    if len(events) <= limit:
        return events
    primary = [
        event for event in events
        if any(signal in {LineSignal.findings, LineSignal.summaries} for signal in event.signals)
    ]
    secondary = [
        event for event in events
        if event.kind in {LineKind.warn, LineKind.error}
        or event.role in _TRANSCRIPT_PRIORITY_ROLES
        or any(signal in {LineSignal.warnings, LineSignal.errors} for signal in event.signals)
    ]
    low_value = {LineRole.progress, LineRole.status_line}
    tail = [event for event in events[-limit:] if event.role not in low_value]
    selected: list[LineEvent] = []
    seen: set[int] = set()

    def append_group(group: list[LineEvent]) -> None:
        remaining = limit - len(selected)
        if remaining <= 0:
            return
        for event in group[-remaining:]:
            key = event.line_index if event.line_index is not None else id(event)
            if key in seen:
                continue
            seen.add(key)
            selected.append(event)

    append_group(primary)
    append_group(secondary)
    append_group(tail)
    return sorted(selected, key=lambda event: event.line_index if event.line_index is not None else 0)


def _warning_error_lines(events: list[LineEvent]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        if event.kind not in {LineKind.warn, LineKind.error} and not any(
            signal in {LineSignal.warnings, LineSignal.errors} for signal in event.signals
        ):
            continue
        rows.append({
            "line_index": event.line_index,
            "kind": event.kind.value,
            "role": event.role.value,
            "text": event.text,
        })
    return rows


def _first_event_target(events: list[LineEvent]) -> str:
    for event in events:
        if event.target:
            return event.target
    return ""


def _runtime_seconds(run: Mapping[str, Any]) -> float | None:
    started = str(run.get("started") or "")
    finished = str(run.get("finished") or "")
    if not started or not finished:
        return None
    try:
        from datetime import datetime

        start = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, round((end - start).total_seconds(), 3))


def _secret_names(session_id: str) -> set[str]:
    try:
        return {str(item.get("name") or "") for item in list_secret_metadata(session_id)}
    except Exception:
        log.warning(
            "AI_CONTEXT_SECRET_METADATA_LOAD_FAILED",
            exc_info=True,
            extra={"session": get_log_session_id(session_id)},
        )
        return set()


def _strip_secret_names(text: str, secret_names: set[str]) -> str:
    if not secret_names:
        return text
    return _SECRET_NAME_TOKEN_RE.sub(
        lambda match: "[secret-name-redacted]" if match.group(0) in secret_names else match.group(0),
        text,
    )


def _strip_workspace_paths(text: str, cfg: dict) -> str:
    if not cfg.get("workspace_enabled"):
        return text
    try:
        prefix = str(session_workspace_dir("", cfg).parent.resolve(strict=False)).rstrip("/")
    except (WorkspaceDisabled, OSError):
        return text
    if not prefix:
        return text
    return re.sub(
        re.escape(prefix) + r"/[^/\s]+(/[\w@%+=:,./-]*)?",
        lambda match: "/" + str(match.group(1) or "").lstrip("/"),
        text,
    )


def _json_len(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _useful_context_chars(context: dict[str, Any]) -> int:
    text = json.dumps({
        "run": context.get("run", {}),
        "findings": context.get("findings", []),
        "entities": context.get("entities", {}),
        "transcript_tail": context.get("transcript_tail", []),
    }, ensure_ascii=False, sort_keys=True)
    return len(text.strip())
