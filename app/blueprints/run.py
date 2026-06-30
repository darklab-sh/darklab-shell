"""
Execution routes: /runs (brokered command streaming), /run/client, and /kill.

The /runs start route is rate-limited per-IP via the shared limiter singleton.
"""

import json
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
import uuid
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, NotRequired, TypedDict

from flask import Blueprint, Response, jsonify, request

from services.commands.registry import (
    CommandValidationResult,
    command_project_target_inputs,
    command_root,
    interactive_pty_spec_for_command,
    is_command_allowed,
    is_help_invocation,
    parse_synthetic_postfilter,
    required_secrets_for_command,
    rewrite_command,
    runtime_missing_command_message,
    runtime_missing_command_name,
    split_command_argv,
    validate_command,
)
from config import CFG, SCANNER_PREFIX, get_share_redaction_rules
from core.database import DB_BACKEND, db_connect
from core.database_backend import DatabaseBackend, dialect_for_backend
from core.redaction import REDACTED_ENTITY_SENTINEL, line_entries_from_events, redact_line_entries
from extensions import limiter
from services.commands.builtins import (
    execute_builtin_command,
    resolve_builtin_command,
    resolves_exact_special_builtin_command,
)
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from core.process import (
    active_run_belongs_to_scope,
    active_run_pid_start_matches,
    active_run_register,
    active_run_remove,
    active_run_touch_owner,
    active_runs_for_team,
    active_runs_for_session,
    pid_for_session,
    pid_for_team,
    pid_pop,
    pid_register,
)
from services.teams.request_scope import (
    RequestScope,
    RequestScopeError,
    current_request_scope,
    requested_team_id,
    scope_error_payload,
)
from services.teams.scope import OwnerContext, owner_context_for_scope, personal_owner_context
from services.teams.capabilities import Capability, require_capability, role_can
from services.teams.contracts import TeamPermissionDenied
from services.runs.broker import (
    broker_available,
    broker_mode,
    broker_unavailable_reason,
    get_run_events,
    publish_run_event,
    stream_run_events,
)
from services.runs.output_store import RunOutputCapture, load_full_output_entries, unknown_line_event_collector
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL, run_kind_for_cmd_type
from services.runs.output_model import (
    LineEvent,
    LineKind,
    LineRole,
    event_search_text,
    from_wire,
    is_noise_event,
    legacy_cls_for_event,
    line_event_from_legacy,
    to_legacy_output_event,
    to_wire,
)
from services.runs.structured_summary import replace_run_output_summary
from services.runs.start import (
    RunPreparationError as _RunPreparationError,
    RunSpawnError as _RunSpawnError,
    RunStartHandlers,
    start_brokered_run as _start_brokered_run_service,
)
from services.storage.body_store import inline_threshold_bytes, maybe_store_text_body
from services.atlas.materializer import materialize_run_entities
from services.secrets.audit import emit_secret_event
from services.secrets.storage import InvalidSecretName, get_secret_value_for_env
from services.secrets.vault import MasterKeyError, SecretDecryptError
from services.runs.streaming import (
    cleanup_proc_stream as _cleanup_proc_stream,
    make_nonblocking_stream_reader as _make_nonblocking_stream_reader,
    read_available_stream_lines as _read_available_stream_lines,
    stdout_ready as _stdout_ready,
    timeout_notice as _timeout_notice,
    wait_for_proc_exit_code as _wait_for_proc_exit_code,
)
from services.runs.workspace_artifacts import (
    workspace_artifacts_from_validation as _workspace_artifacts_from_validation,
    workspace_artifacts_with_sizes as _workspace_artifacts_with_sizes,
)
from core.output_signals import OutputSignalClassifier
from services.projects.artifacts import record_run_file_artifacts
from services.projects.auto_promote import apply_run_rules_on_conn as apply_auto_promote_rules_for_run
from services.projects.findings import record_run_findings
from services.projects.links import (
    link_active_project_run_entities,
    link_run_to_project_on_conn,
    link_run_to_active_project,
)
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.targets import (
    record_project_target_discoveries,
)
from services import metrics as app_metrics
from services.notifications.hooks import enqueue_run_complete
from services.session.variables import SessionVariableError, expand_session_variables
from services.workspace.files import WorkspaceDisabled, owner_workspace_dir
from services.pty.service import (
    PtyDependencyError,
    claim_pty_stream_owner,
    notify_pty_killed_event,
    pty_broker_available,
    pty_broker_unavailable_reason,
    pty_enabled,
    pty_run_snapshot,
    pty_run_belongs_to_scope,
    resize_pty,
    start_pty_run,
    stream_pty_events,
    write_pty_input,
)
from services.pty.transcript import shape_completed_pty_entries as _shape_completed_pty_entries

log = logging.getLogger("shell")

run_bp = Blueprint("run", __name__)

AUTO_PROMOTE_RUN_LOG_RESULT_LIMIT = 10


class _RunSessionVisibility(TypedDict):
    allowed: bool
    active_match: bool
    db_match: bool
    active_count: int
    scope_mismatch: NotRequired[bool]
    actual_team_id: NotRequired[str]


def _active_run_owner_value(value: object) -> str:
    return str(value or "").strip()[:128]


def _workspace_cwd_value(value: object) -> str:
    return str(value or "").strip()[:1024]


def _team_capability_error_response(exc: TeamPermissionDenied):
    return jsonify({"error": "team_forbidden", "message": str(exc)}), 403


def _require_team_capability(owner_scope, capability: Capability):
    if not owner_scope.is_team:
        return None
    try:
        require_capability(str((owner_scope.member or {}).get("role") or ""), capability)
    except TeamPermissionDenied as exc:
        return _team_capability_error_response(exc)
    return None


def _scope_has_team_capability(owner_scope, capability: Capability) -> bool:
    if not owner_scope.is_team:
        return True
    return role_can(str((owner_scope.member or {}).get("role") or ""), capability)


def _team_audit_fields(owner_scope) -> dict[str, str]:
    member = owner_scope.member or {}
    return {
        "team_id": str(owner_scope.team_id or ""),
        "actor_member_id": str(member.get("id") or ""),
        "team_role": str(member.get("role") or ""),
    }


def _auto_promote_summary_results(summary) -> list[dict]:
    if not isinstance(summary, dict):
        return []
    results = summary.get("results")
    if not isinstance(results, list):
        return []
    return [result for result in results if isinstance(result, dict)]


def _auto_promote_summary_ids(results: list[dict], key: str) -> list[str]:
    return sorted({
        str(result.get(key) or "")
        for result in results
        if str(result.get(key) or "")
    })


def _auto_promote_summary_log_results(results: list[dict]) -> list[dict[str, object]]:
    safe_results = []
    for result in results[:AUTO_PROMOTE_RUN_LOG_RESULT_LIMIT]:
        safe_results.append({
            "project_id": str(result.get("project_id") or ""),
            "rule_id": str(result.get("rule_id") or ""),
            "matched_count": int(result.get("matched_count") or 0),
            "linked_count": int(result.get("linked_count") or 0),
            "promoted_count": int(result.get("promoted_count") or 0),
            "quota_limited_count": int(result.get("quota_limited_count") or 0),
            "match_cap_limited_count": int(result.get("match_cap_limited_count") or 0),
        })
    return safe_results


def _validate_command_for_run(
    command: str,
    session_id: str,
    workspace_cwd: str = "",
    *,
    extra_allowed_prefixes: list[str] | None = None,
    owner_context: OwnerContext | None = None,
) -> CommandValidationResult:
    # Several route tests monkeypatch this module's legacy is_command_allowed
    # symbol to keep subprocess behavior focused. Honor that seam while the
    # runtime path uses the richer validator for workspace rewrites.
    if getattr(is_command_allowed, "__module__", "") != "services.commands.registry":
        allowed, reason = is_command_allowed(command)
        return CommandValidationResult(
            allowed,
            reason,
            display_command=command,
            exec_command=command,
        )
    effective_owner_context = _effective_owner_context(owner_context, session_id)
    if effective_owner_context is not None:
        return validate_command(
            command,
            session_id=session_id,
            cfg=CFG,
            workspace_cwd=workspace_cwd,
            extra_allowed_prefixes=extra_allowed_prefixes,
            owner_context=effective_owner_context,
        )
    return validate_command(
        command,
        session_id=session_id,
        cfg=CFG,
        workspace_cwd=workspace_cwd,
        extra_allowed_prefixes=extra_allowed_prefixes,
    )


def _validate_command_with_effective_owner(
    command: str,
    session_id: str,
    workspace_cwd: str = "",
    *,
    extra_allowed_prefixes: list[str] | None = None,
    owner_context: OwnerContext | None = None,
) -> CommandValidationResult:
    effective_owner_context = _effective_owner_context(owner_context, session_id)
    if effective_owner_context is not None:
        return _validate_command_for_run(
            command,
            session_id,
            workspace_cwd,
            extra_allowed_prefixes=extra_allowed_prefixes,
            owner_context=effective_owner_context,
        )
    if extra_allowed_prefixes is not None:
        return _validate_command_for_run(
            command,
            session_id,
            workspace_cwd,
            extra_allowed_prefixes=extra_allowed_prefixes,
        )
    return _validate_command_for_run(command, session_id, workspace_cwd)


def _effective_owner_context(owner_context: OwnerContext | None, session_id: str) -> OwnerContext | None:
    if owner_context is None:
        return None
    if owner_context.is_team:
        return owner_context
    if owner_context.owner_id != str(session_id or "").strip():
        return owner_context
    return None


def _workspace_notice_lines(validation: CommandValidationResult) -> list[str]:
    notices: list[str] = []
    for path in validation.workspace_reads:
        notices.append(f"[workspace] reading {path}")
    for path in validation.workspace_writes:
        notices.append(f"[workspace] writing {path}")
    return notices


SHELL_BIN = shutil.which("sh") or "/bin/sh"
STDBUF_BIN = shutil.which("stdbuf")
SUDO_BIN  = shutil.which("sudo") or "/usr/bin/sudo"
KILL_BIN  = shutil.which("kill") or "/bin/kill"

CLIENT_SIDE_RUN_ROOTS = {
    "cat",
    "cd",
    "config",
    "file",
    "grep",
    "head",
    "ll",
    "ls",
    "mkdir",
    "pwd",
    "rm",
    "session-token",
    "sort",
    "tail",
    "theme",
    "tour",
    "uniq",
    "wc",
}


def _insert_run_row(
    conn,
    *,
    run_id: str,
    session_id: str,
    team_id: str,
    run_kind: str,
    owner_tab_id: str,
    command: str,
    started: str,
    finished: str,
    exit_code: int,
    output_preview: str,
    preview_truncated: object,
    output_line_count: int,
    full_output_available: object,
    full_output_truncated: object,
    output_search_text: str,
) -> None:
    dialect = dialect_for_backend(DB_BACKEND)
    conn.execute(
        "INSERT INTO runs "
        "("
        "id, session_id, team_id, run_kind, owner_tab_id, command, started, finished, exit_code, output, output_preview, "
        "preview_truncated, output_line_count, full_output_available, full_output_truncated, "
        "output_search_text"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            session_id,
            team_id,
            run_kind,
            owner_tab_id,
            command,
            started,
            finished,
            exit_code,
            None,
            output_preview,
            dialect.boolean_param(preview_truncated),
            int(output_line_count or 0),
            dialect.boolean_param(full_output_available),
            dialect.boolean_param(full_output_truncated),
            output_search_text,
        ),
    )


def _upsert_run_output_artifact(
    conn,
    *,
    run_id: str,
    rel_path: str,
    compression: str,
    byte_size: int,
    line_count: int,
    truncated: object,
    created: str,
) -> None:
    dialect = dialect_for_backend(DB_BACKEND)
    params = (
        run_id,
        rel_path,
        compression,
        int(byte_size or 0),
        int(line_count or 0),
        dialect.boolean_param(truncated),
        created,
    )
    if DB_BACKEND == DatabaseBackend.POSTGRES:
        conn.execute(
            "INSERT INTO run_output_artifacts "
            "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET "
            "rel_path = excluded.rel_path, "
            "compression = excluded.compression, "
            "byte_size = excluded.byte_size, "
            "line_count = excluded.line_count, "
            "truncated = excluded.truncated, "
            "created = excluded.created",
            params,
        )
        return
    conn.execute(
        "INSERT OR REPLACE INTO run_output_artifacts "
        "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        params,
    )


def _variable_notice_line(expanded_command: str, used_names: tuple[str, ...]) -> str:
    variables = ", ".join(f"${name}" for name in used_names)
    return f"[vars] expanded {variables}: {expanded_command}"
RUN_SUBPROCESS_UMASK = 0o027


def _prepare_run_child() -> None:
    os.setsid()
    os.umask(RUN_SUBPROCESS_UMASK)


def _terminate_process_group(proc) -> None:
    pgid = os.getpgid(proc.pid)
    _signal_process_group(pgid)


# ── Run output helpers ────────────────────────────────────────────────────────

def _run_output_capture(run_id):
    # Keep an inline preview for fast history reads, but spill large/full output
    # into compressed artifacts once a run exceeds the preview window.
    return RunOutputCapture(
        run_id=run_id,
        preview_limit=CFG["max_output_lines"],
        persist_full_output=CFG.get("persist_full_run_output", False),
        full_output_max_bytes=CFG.get("full_output_max_bytes", 0),
        preview_max_bytes=CFG.get("output_preview_max_bytes", 0),
    )


def _capture_event_with_signals(
    capture,
    classifier,
    text: str = "",
    *,
    cls: str = "",
    ts_clock: str = "",
    ts_elapsed: str = "",
    event: LineEvent | None = None,
):
    base_event = event or line_event_from_legacy(text, cls, ts_clock=ts_clock, ts_elapsed=ts_elapsed)
    metadata = classifier.classify_line(base_event.text, cls=legacy_cls_for_event(base_event)) if classifier else {}
    metadata_event = line_event_from_legacy(
        base_event.text,
        legacy_cls_for_event(base_event),
        role=metadata.get("role") if isinstance(metadata.get("role"), str) else base_event.role,
        signals=metadata.get("signals") if isinstance(metadata.get("signals"), list) else None,
        entities=metadata.get("entities") if isinstance(metadata.get("entities"), list) else None,
    )
    captured_event = replace(
        base_event,
        signals=metadata_event.signals,
        role=metadata_event.role if metadata_event.role != LineRole.body else base_event.role,
        line_index=metadata.get("line_index") if isinstance(metadata.get("line_index"), int) else None,
        command_root=str(metadata.get("command_root", "")),
        target=str(metadata.get("target", "")),
        entities=metadata_event.entities,
        source_detail=metadata.get("source_detail") if isinstance(metadata.get("source_detail"), dict) else {},
    )
    capture.add_event(captured_event)
    return metadata, captured_event


def _broker_output_payload(_event_type, text: str = "", *, cls: str = "", event: LineEvent | None = None):
    payload_event = event or line_event_from_legacy(text, cls)
    return to_wire(payload_event)


_RUN_OUTPUT_LIVE_BATCH_SIZE = 200
_RUN_OUTPUT_LIVE_BATCH_MAX_AGE_SECONDS = 0.75
_RUN_OUTPUT_LIVE_BATCH_MAX_LATENCY_SECONDS = 0.075
_RUN_OUTPUT_POLL_SECONDS = 0.05
_RUN_OUTPUT_LIVE_BATCH_COALESCED_ROLES = {LineRole.progress, LineRole.status_line}
_KILL_PROCESS_GROUP_GONE_DELAYS = (0.0, 0.05, 0.15, 0.3, 0.5)
_ACTIVE_RUN_OWNER_TOUCH_INTERVAL_SECONDS = 5.0
_active_run_owner_touch_monotonic = time.monotonic


def _maybe_touch_active_run_owner(
    run_id: str,
    owner_client_id: str,
    owner_tab_id: str,
    *,
    last_touch_monotonic: float | None,
) -> float | None:
    if not owner_client_id:
        return last_touch_monotonic
    now = _active_run_owner_touch_monotonic()
    if (
        last_touch_monotonic is not None
        and now - last_touch_monotonic < _ACTIVE_RUN_OWNER_TOUCH_INTERVAL_SECONDS
    ):
        return last_touch_monotonic
    active_run_touch_owner(run_id, owner_client_id, owner_tab_id)
    return now


class _BrokerOutputBatcher:
    def __init__(self, run_id: str, capture, signal_classifier, *, run_started_dt):
        self.run_id = run_id
        self.capture = capture
        self.signal_classifier = signal_classifier
        self.run_started_dt = run_started_dt
        self.events: list[LineEvent] = []
        self.first_event_monotonic = 0.0
        self.last_flush_monotonic = 0.0
        self.coalesced_line_count = 0

    def add(self, text: str, *, cls: str = "", kind: LineKind | str | None = None, event: LineEvent | None = None) -> None:
        now = time.monotonic()
        line_dt = datetime.now(timezone.utc)
        base_event = event or line_event_from_legacy(
            text,
            cls,
            kind=kind,
            ts_clock=line_dt.strftime("%H:%M:%S"),
            ts_elapsed=f"+{(line_dt - self.run_started_dt).total_seconds():.1f}s",
        )
        _metadata, captured_event = _capture_event_with_signals(
            self.capture,
            self.signal_classifier,
            event=base_event,
        )
        self._append_live_event(captured_event, now=now)
        if (
            len(self.events) >= _RUN_OUTPUT_LIVE_BATCH_SIZE
            or self._is_due(now=now)
            or self._should_flush_for_latency(now)
        ):
            self.flush()

    def _append_live_event(self, event: LineEvent, *, now: float) -> None:
        if not self.events:
            self.first_event_monotonic = now
        if (
            event.role in _RUN_OUTPUT_LIVE_BATCH_COALESCED_ROLES
            and self.events
            and self.events[-1].role == event.role
        ):
            self.events[-1] = event
            self.coalesced_line_count += 1
            return
        self.events.append(event)

    def _is_due(self, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        return bool(
            self.events
            and self.first_event_monotonic
            and current - self.first_event_monotonic >= _RUN_OUTPUT_LIVE_BATCH_MAX_AGE_SECONDS
        )

    def _should_flush_for_latency(self, now: float) -> bool:
        if not self.events:
            return False
        if not self.last_flush_monotonic:
            return True
        return now - self.last_flush_monotonic >= self._max_latency_seconds()

    def _max_latency_seconds(self) -> float:
        if self.events and all(event.role in _RUN_OUTPUT_LIVE_BATCH_COALESCED_ROLES for event in self.events):
            return _RUN_OUTPUT_LIVE_BATCH_MAX_AGE_SECONDS
        return _RUN_OUTPUT_LIVE_BATCH_MAX_LATENCY_SECONDS

    def flush_due(self) -> None:
        if self._is_due():
            self.flush()

    def flush(self) -> None:
        if not self.events:
            return
        events = self.events
        coalesced_line_count = self.coalesced_line_count
        self.events = []
        self.first_event_monotonic = 0.0
        self.last_flush_monotonic = time.monotonic()
        self.coalesced_line_count = 0
        if len(events) == 1:
            payload = _broker_output_payload("output", event=events[0])
            if coalesced_line_count:
                payload["coalesced_line_count"] = coalesced_line_count
            publish_run_event(
                self.run_id,
                "output",
                payload,
            )
            return
        payload: dict[str, object] = {"lines": [to_wire(event) for event in events]}
        if coalesced_line_count:
            payload["coalesced_line_count"] = coalesced_line_count
        publish_run_event(
            self.run_id,
            "output_batch",
            payload,
        )


def _process_group_is_gone(pgid: int) -> bool:
    for delay in _KILL_PROCESS_GROUP_GONE_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        except OSError:
            return False
    return False


def _signal_process_group(pgid: int) -> None:
    if SCANNER_PREFIX:
        result = subprocess.run(
            [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", "--", f"-{pgid}"],
            timeout=5,
        )
        if result.returncode != 0 and not _process_group_is_gone(pgid):
            raise OSError(f"sudo kill exited with status {result.returncode}")
        return

    os.killpg(pgid, signal.SIGTERM)


def _ensure_scanner_process_group_current(
    run_id: str,
    pid: int,
    session_id: str,
    team_id: str = "",
) -> None:
    if not SCANNER_PREFIX:
        return
    if active_run_pid_start_matches(run_id, pid, session_id=session_id, team_id=team_id):
        return
    raise ProcessLookupError("active run PID start time no longer matches")


_SEARCH_ENTITY_MAX_BYTES = 4096


def _line_events_from_output_entries(entries) -> list[LineEvent]:
    events = []
    unknown_collector = unknown_line_event_collector({"source": "run_output_entries"})
    for line in entries or []:
        if line is None:
            continue
        if isinstance(line, dict):
            events.append(from_wire(line, unknown_collector))
        else:
            events.append(line_event_from_legacy(str(line)))
    return events


def _bounded_entity_search_values(values: Sequence[str], max_bytes: int = _SEARCH_ENTITY_MAX_BYTES) -> list[str]:
    selected: list[str] = []
    used = 0
    for value in values:
        encoded = value.encode("utf-8")
        separator = 1 if selected else 0
        if used + separator + len(encoded) > max_bytes:
            continue
        selected.append(value)
        used += separator + len(encoded)
    return selected


def _search_text_from_events(events: Sequence[LineEvent]) -> str:
    lines = [text for event in events if (text := event_search_text(event))]
    entity_values = []
    seen_entities = set()
    for event in events:
        if is_noise_event(event):
            continue
        for entity in event.entities:
            canonical_value = entity.canonical_value.strip()
            if not canonical_value or canonical_value == REDACTED_ENTITY_SENTINEL:
                continue
            key = (entity.type.strip(), canonical_value)
            if not key[0] or key in seen_entities:
                continue
            seen_entities.add(key)
            entity_values.append(key)
    sorted_values = []
    seen_values = set()
    for _, value in sorted(entity_values):
        if value in seen_values:
            continue
        seen_values.add(value)
        sorted_values.append(value)
    lines.extend(_bounded_entity_search_values(sorted_values))
    return "\n".join(lines)


def _extract_output_search_text(preview_lines):
    return _search_text_from_events(_line_events_from_output_entries(preview_lines))


def _link_active_project_run_entities_for_finalize(conn, session_id, project_id, run_id, *, team_id=""):
    return _run_finalize_savepoint(
        conn,
        "active_project_entity_link",
        lambda: link_active_project_run_entities(
            conn,
            session_id,
            project_id,
            run_id,
            team_id=team_id,
        ),
    )


def _run_finalize_savepoint(conn, name, callback):
    savepoint = f"run_finalize_{name}"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        result = callback()
    except Exception:
        try:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        finally:
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise
    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    return result


def _structured_output_summary_fields(entries):
    kind_counts: dict[str, int] = {}
    signal_counts: dict[str, int] = {}
    entity_type_counts: dict[str, int] = {}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "")
        if kind:
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
        signals = entry.get("signals")
        if isinstance(signals, list):
            for signal in signals:
                value = str(signal or "")
                if value:
                    signal_counts[value] = signal_counts.get(value, 0) + 1
        entities = entry.get("entities")
        if isinstance(entities, list):
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                entity_type = str(entity.get("type") or "")
                if entity_type:
                    entity_type_counts[entity_type] = entity_type_counts.get(entity_type, 0) + 1
    return {
        "output_kind_counts": kind_counts,
        "output_signal_counts": signal_counts,
        "output_entity_type_counts": entity_type_counts,
    }


@dataclass
class _CompletedRunOutputState:
    preview_lines: list
    persisted_entries: list
    stored_search_text: str


@dataclass
class _RunFinalizeRecords:
    active_project_link: dict | None = None
    recorded_artifacts: list = field(default_factory=list)
    recorded_entities: list = field(default_factory=list)
    recorded_findings: list = field(default_factory=list)
    recorded_targets: list = field(default_factory=list)
    scan_observation_count: int = 0
    auto_promote_summary: dict | None = None


def _entity_type_counts_for_log(recorded_entities: Sequence[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in recorded_entities:
        if not isinstance(entity, dict):
            continue
        entity_type = str(entity.get("type") or "")
        if entity_type:
            counts[entity_type] = counts.get(entity_type, 0) + 1
    return counts


def _scan_target_observation_count(conn, run_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM scan_target_observations WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return 0
    try:
        return int(row["count"] or 0)
    except (KeyError, TypeError, IndexError):
        return int(row[0] or 0)


def _log_atlas_entities_captured(
    session_id: str,
    team_id: str,
    run_id: str,
    recorded_entities: Sequence[object],
    scan_observation_count: int,
) -> None:
    if not recorded_entities and scan_observation_count <= 0:
        return
    entity_type_counts = _entity_type_counts_for_log(recorded_entities)
    log.info("ATLAS_ENTITIES_CAPTURED", extra={
        "run_id": run_id,
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "count": len(recorded_entities),
        "entity_type_counts": entity_type_counts,
        "port_entity_count": int(entity_type_counts.get("port") or 0),
        "scan_observation_count": int(scan_observation_count),
    })


def _completed_run_output_state(run_id, session_id, capture) -> _CompletedRunOutputState:
    preview_lines = list(capture.preview_lines)
    persisted_entries = preview_lines
    if capture.full_output_available and capture.artifact_rel_path:
        try:
            full_entries = load_full_output_entries(capture.artifact_rel_path)
            search_text = _extract_output_search_text(full_entries)
            persisted_entries = full_entries
        except Exception as exc:
            log.warning("RUN_FULL_OUTPUT_INDEX_FALLBACK", extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "rel_path": capture.artifact_rel_path,
                "error": str(exc),
            })
            search_text = _extract_output_search_text(preview_lines)
    else:
        search_text = _extract_output_search_text(preview_lines)
    stored_search_text = maybe_store_text_body(
        "run_search",
        run_id,
        search_text,
        inline_threshold_bytes(CFG.get("runs_search_text_inline_max_bytes")),
    )
    return _CompletedRunOutputState(
        preview_lines=preview_lines,
        persisted_entries=persisted_entries,
        stored_search_text=stored_search_text,
    )


def _save_run_project_link_for_finalize(
    conn,
    session_id,
    team_id,
    run_id,
    command,
    *,
    link_project_id="",
    link_active_project=True,
):
    if link_project_id:
        try:
            return _run_finalize_savepoint(
                conn,
                "project_link",
                lambda: link_run_to_project_on_conn(
                    conn,
                    session_id,
                    link_project_id,
                    run_id,
                    source="manual",
                    team_id=team_id,
                ),
            )
        except Exception:
            log.error("PROJECT_RUN_LINK_ERROR", exc_info=True, extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "project_id": link_project_id,
                "cmd": command,
            })
            return None
    if link_active_project:
        try:
            return _run_finalize_savepoint(
                conn,
                "active_project_link",
                lambda: link_run_to_active_project(conn, session_id, run_id, team_id=team_id),
            )
        except Exception:
            log.error("PROJECT_ACTIVE_RUN_LINK_ERROR", exc_info=True, extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "cmd": command,
            })
    return None


def _save_run_file_artifacts_for_finalize(
    conn,
    session_id,
    team_id,
    run_id,
    command,
    workspace_artifacts,
    workspace_owner,
) -> list:
    if not workspace_artifacts:
        return []
    try:
        if team_id:
            sized_workspace_artifacts = _workspace_artifacts_with_sizes(
                session_id,
                workspace_artifacts,
                owner_context=workspace_owner,
            )
        else:
            sized_workspace_artifacts = _workspace_artifacts_with_sizes(session_id, workspace_artifacts)
        return _run_finalize_savepoint(
            conn,
            "run_file_artifacts",
            lambda: record_run_file_artifacts(
                conn,
                session_id,
                run_id,
                sized_workspace_artifacts,
                **({"owner_context": workspace_owner} if team_id else {}),
            ),
        )
    except Exception:
        log.error("PROJECT_RUN_ARTIFACT_CAPTURE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "cmd": command,
        })
    return []


def _discover_project_targets_for_finalize(
    conn,
    session_id,
    run_id,
    command,
    active_project_link,
) -> list:
    if not active_project_link:
        return []
    try:
        return _run_finalize_savepoint(
            conn,
            "project_target_discovery",
            lambda: record_project_target_discoveries(
                conn,
                session_id,
                active_project_link["project_id"],
                run_id,
                command_project_target_inputs(command, cfg=CFG),
            ),
        )
    except ProjectWorkspaceQuotaExceeded as exc:
        active_project_link["target_discovery_skipped_reason"] = str(exc)
        log.warning("PROJECT_TARGET_DISCOVERY_SKIPPED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "project_id": active_project_link["project_id"],
            "cmd": command,
            "reason": str(exc),
        })
    except Exception:
        log.error("PROJECT_TARGET_DISCOVERY_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "cmd": command,
        })
    return []


def _record_run_findings_for_finalize(conn, session_id, team_id, run_id, command, persisted_entries) -> list:
    try:
        return _run_finalize_savepoint(
            conn,
            "run_findings",
            lambda: record_run_findings(conn, session_id, run_id, persisted_entries, team_id=team_id),
        )
    except Exception:
        app_metrics.record_run_finalize_error("db_write")
        log.error("PROJECT_RUN_FINDING_CAPTURE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "cmd": command,
        })
    return []


def _materialize_run_entities_for_finalize(conn, session_id, team_id, run_id, command, persisted_entries, finished_iso) -> list:
    try:
        return _run_finalize_savepoint(
            conn,
            "atlas_entities",
            lambda: materialize_run_entities(
                conn,
                session_id,
                run_id,
                persisted_entries,
                team_id=team_id,
                seen_at=finished_iso,
                command=command,
            ),
        )
    except Exception:
        app_metrics.record_run_finalize_error("entity_materialize")
        log.error("ATLAS_ENTITY_CAPTURE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "cmd": command,
        })
    return []


def _apply_auto_promote_for_finalize(conn, session_id, team_id, run_id, command, recorded_entities) -> dict | None:
    if not recorded_entities:
        return None
    try:
        return _run_finalize_savepoint(
            conn,
            "project_auto_promote_rules",
            lambda: apply_auto_promote_rules_for_run(
                conn,
                session_id,
                run_id,
                team_id=team_id,
            ),
        )
    except Exception:
        log.error("PROJECT_AUTO_PROMOTE_RUN_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "cmd": command,
        })
    return None


def _link_active_project_entities_for_finalize(
    conn,
    session_id,
    team_id,
    run_id,
    command,
    active_project_link,
    recorded_entities,
) -> None:
    if not active_project_link or not recorded_entities:
        return
    try:
        linked_entities = _link_active_project_run_entities_for_finalize(
            conn,
            session_id,
            active_project_link["project_id"],
            run_id,
            team_id=team_id,
        )
        if linked_entities:
            active_project_link["linked_entity_count"] = int(linked_entities.get("added") or 0)
            active_project_link["available_entity_count"] = int(linked_entities.get("available") or 0)
            active_project_link["rejected_entity_count"] = int(linked_entities.get("rejected") or 0)
    except Exception:
        log.error("PROJECT_ACTIVE_RUN_ENTITY_LINK_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "cmd": command,
        })


def _log_run_finalize_records(
        run_id, session_id,
        team_id,
        run_kind,
        records: _RunFinalizeRecords) -> tuple[list[dict], list[str]]:
    app_metrics.record_findings_materialized(run_kind, len(records.recorded_findings))
    if records.active_project_link:
        log.info("PROJECT_ACTIVE_RUN_LINKED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "project_id": records.active_project_link["project_id"],
        })
    if records.recorded_artifacts:
        log.info("PROJECT_RUN_ARTIFACTS_CAPTURED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "count": len(records.recorded_artifacts),
        })
    if records.recorded_findings:
        log.info("PROJECT_RUN_FINDINGS_CAPTURED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "count": len(records.recorded_findings),
        })
    if records.recorded_targets:
        if records.active_project_link:
            records.active_project_link["discovered_target_count"] = len(records.recorded_targets)
        log.info("PROJECT_TARGETS_DISCOVERED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "count": len(records.recorded_targets),
        })
    _log_atlas_entities_captured(
        session_id,
        team_id,
        run_id,
        records.recorded_entities,
        records.scan_observation_count,
    )
    auto_promote_results = _auto_promote_summary_results(records.auto_promote_summary)
    auto_promote_project_ids = _auto_promote_summary_ids(auto_promote_results, "project_id")
    auto_promote_rule_ids = _auto_promote_summary_ids(auto_promote_results, "rule_id")
    if records.auto_promote_summary and int(records.auto_promote_summary.get("rules_evaluated") or 0):
        log.info("PROJECT_AUTO_PROMOTE_RUN_APPLIED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_ids": auto_promote_project_ids,
            "rule_ids": auto_promote_rule_ids,
            "rule_results": _auto_promote_summary_log_results(auto_promote_results),
            "rule_results_truncated": len(auto_promote_results) > AUTO_PROMOTE_RUN_LOG_RESULT_LIMIT,
            "rules_evaluated": int(records.auto_promote_summary.get("rules_evaluated") or 0),
            "projects_evaluated": int(records.auto_promote_summary.get("projects_evaluated") or 0),
            "matched_count": int(records.auto_promote_summary.get("matched_count") or 0),
            "linked_count": int(records.auto_promote_summary.get("linked_count") or 0),
            "already_linked_count": int(records.auto_promote_summary.get("already_linked_count") or 0),
            "skipped_suppressed_count": int(records.auto_promote_summary.get("skipped_suppressed_count") or 0),
            "quota_limited_count": int(records.auto_promote_summary.get("quota_limited_count") or 0),
            "match_cap_limited_count": int(records.auto_promote_summary.get("match_cap_limited_count") or 0),
            "rule_cap_limited_count": int(records.auto_promote_summary.get("rule_cap_limited_count") or 0),
        })
    return auto_promote_results, auto_promote_project_ids


def _update_run_finalize_summary(
    finalize_summary,
    records: _RunFinalizeRecords,
    persisted_entries,
    auto_promote_project_ids: list[str],
) -> None:
    if not isinstance(finalize_summary, dict):
        return
    finalize_summary.update({
        "artifact_count": len(records.recorded_artifacts),
        "finding_count": len(records.recorded_findings),
        "atlas_entity_count": len(records.recorded_entities),
        "project_target_count": len(records.recorded_targets),
        "project_auto_promote_count": int(records.auto_promote_summary.get("linked_count") or 0)
        if isinstance(records.auto_promote_summary, dict) else 0,
        "project_auto_promote_promoted_count": int(records.auto_promote_summary.get("promoted_count") or 0)
        if isinstance(records.auto_promote_summary, dict) else 0,
        "project_auto_promote_project_ids": auto_promote_project_ids,
        **_structured_output_summary_fields(persisted_entries),
    })


def _save_completed_run(
    run_id,
    session_id,
    team_id,
    command,
    run_started,
    finished_iso,
    exit_code,
    capture,
    *,
    workspace_artifacts=None,
    link_active_project=True,
    link_project_id="",
    run_kind=RUN_KIND_EXTERNAL,
    owner_tab_id="",
    finalize_summary=None,
):
    # Persist preview text and artifact metadata together so history/permalink
    # readers never observe half-written run state.
    capture.finalize()
    try:
        output_state = _completed_run_output_state(run_id, session_id, capture)
        records = _RunFinalizeRecords()
        workspace_owner = owner_context_for_scope(session_id, team_id=team_id)
        with db_connect() as conn:
            _insert_run_row(
                conn,
                run_id=run_id,
                session_id=session_id,
                team_id=team_id,
                run_kind=run_kind,
                owner_tab_id=owner_tab_id,
                command=command,
                started=run_started,
                finished=finished_iso,
                exit_code=exit_code,
                output_preview=json.dumps(output_state.preview_lines),
                preview_truncated=capture.preview_truncated,
                output_line_count=capture.output_line_count,
                full_output_available=capture.full_output_available,
                full_output_truncated=capture.full_output_truncated,
                output_search_text=output_state.stored_search_text,
            )
            if capture.full_output_available and capture.artifact_rel_path:
                _upsert_run_output_artifact(
                    conn,
                    run_id=run_id,
                    rel_path=capture.artifact_rel_path,
                    compression="gzip",
                    byte_size=capture.full_output_bytes,
                    line_count=capture.output_line_count,
                    truncated=capture.full_output_truncated,
                    created=finished_iso,
                )
            replace_run_output_summary(conn, run_id, output_state.persisted_entries)
            records.active_project_link = _save_run_project_link_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                link_project_id=link_project_id,
                link_active_project=link_active_project,
            )
            records.recorded_artifacts = _save_run_file_artifacts_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                workspace_artifacts,
                workspace_owner,
            )
            records.recorded_targets = _discover_project_targets_for_finalize(
                conn,
                session_id,
                run_id,
                command,
                records.active_project_link,
            )
            records.recorded_findings = _record_run_findings_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                output_state.persisted_entries,
            )
            records.recorded_entities = _materialize_run_entities_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                output_state.persisted_entries,
                finished_iso,
            )
            records.scan_observation_count = _scan_target_observation_count(conn, run_id)
            records.auto_promote_summary = _apply_auto_promote_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                records.recorded_entities,
            )
            _link_active_project_entities_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                records.active_project_link,
                records.recorded_entities,
            )
            conn.commit()
        _auto_promote_results, auto_promote_project_ids = _log_run_finalize_records(
            run_id,
            session_id,
            team_id,
            run_kind,
            records,
        )
        _update_run_finalize_summary(
            finalize_summary,
            records,
            output_state.persisted_entries,
            auto_promote_project_ids,
        )
        return records.active_project_link
    except Exception:
        app_metrics.record_run_finalize_error("db_write")
        log.error("RUN_SAVED_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "cmd": command,
        })
    return None


def _finalize_completed_run(
    run_id,
    session_id,
    team_id,
    client_ip,
    original_command,
    run_started,
    exit_code,
    capture,
    *,
    cmd_type="real",
    workspace_artifacts=None,
    owner_tab_id="",
    link_project_id="",
):
    finished = datetime.now(timezone.utc)
    elapsed = round((finished - datetime.fromisoformat(run_started)).total_seconds(), 1)
    finalize_summary = {}
    active_project_link = _save_completed_run(
        run_id, session_id, team_id, original_command, run_started,
        finished.isoformat(), exit_code, capture,
        workspace_artifacts=workspace_artifacts,
        link_active_project=cmd_type == "real",
        link_project_id=link_project_id,
        run_kind=run_kind_for_cmd_type(cmd_type),
        owner_tab_id=owner_tab_id,
        finalize_summary=finalize_summary,
    )
    log.info("RUN_END", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "exit_code": exit_code, "elapsed": elapsed, "cmd": original_command,
        "cmd_type": cmd_type,
        "output_line_count": int(capture.output_line_count or 0),
        "full_output_truncated": bool(capture.full_output_truncated),
        "full_output_available": bool(capture.full_output_available),
        "artifact_count": int(finalize_summary.get("artifact_count") or len(workspace_artifacts or [])),
        "finding_count": int(finalize_summary.get("finding_count") or 0),
        "atlas_entity_count": int(finalize_summary.get("atlas_entity_count") or 0),
        "project_target_count": int(finalize_summary.get("project_target_count") or 0),
    })
    app_metrics.record_completed_run(
        original_command,
        run_kind_for_cmd_type(cmd_type),
        exit_code,
        elapsed,
        capture,
    )
    enqueue_run_complete(
        run_id=run_id,
        session_id=session_id,
        command=original_command,
        exit_code=exit_code,
        run_kind=run_kind_for_cmd_type(cmd_type),
        team_id=team_id,
        finalize_summary=finalize_summary,
        cfg=CFG,
    )
    try:
        from services.watchers.finalize import finalize_watcher_run  # noqa: PLC0415

        finalize_watcher_run(run_id)
    except Exception:
        log.error("WATCHER_FINALIZE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
        })
    return {"elapsed": elapsed, "active_project_link": active_project_link, "finalize_summary": finalize_summary}


def _persist_completed_pty_run(
    run,
    execution_command: str,
    finished_iso: str,
    exit_code: int,
    synthesized_lines,
    *,
    transcript_mode: object = "final_frame",
    owner_tab_id: str = "",
):
    capture = _run_output_capture(run.run_id)
    signal_classifier = OutputSignalClassifier(execution_command, cmd_type="real")
    for item in _shape_completed_pty_entries(synthesized_lines, transcript_mode):
        text = str(item.get("text", ""))
        cls = str(item.get("cls", ""))
        if cls == "pty-marker":
            capture.add_event(line_event_from_legacy(text, cls))
            continue
        _capture_event_with_signals(capture, signal_classifier, text, cls=cls)
    _save_completed_run(
        run.run_id,
        run.session_id,
        str(getattr(run, "team_id", "") or ""),
        run.command,
        run.started,
        finished_iso,
        exit_code,
        capture,
        run_kind=RUN_KIND_EXTERNAL,
        owner_tab_id=owner_tab_id or str(getattr(run, "owner_tab_id", "") or ""),
    )
    try:
        elapsed = (
            datetime.fromisoformat(finished_iso) -
            datetime.fromisoformat(str(run.started))
        ).total_seconds()
    except (TypeError, ValueError):
        elapsed = 0.0
    app_metrics.record_completed_run(run.command, RUN_KIND_EXTERNAL, exit_code, elapsed, capture)
    app_metrics.record_completed_pty(run.command, exit_code, elapsed)
    return {
        "preview_truncated": capture.preview_truncated,
        "output_line_count": capture.output_line_count,
        "full_output_available": capture.full_output_available,
    }


def _client_side_run_command_allowed(command: str) -> bool:
    root = command.strip().split(maxsplit=1)[0].lower() if command.strip() else ""
    return root in CLIENT_SIDE_RUN_ROOTS


def _normalize_client_side_run_lines(lines, command: str):
    if not isinstance(lines, list):
        return [], False, 0
    signal_classifier = OutputSignalClassifier(command, cmd_type="builtin")
    capture = RunOutputCapture(
        run_id="client-side-run-preview",
        preview_limit=CFG["max_output_lines"],
        persist_full_output=False,
        full_output_max_bytes=0,
        preview_max_bytes=CFG.get("output_preview_max_bytes", 0),
    )
    for item in lines:
        if isinstance(item, dict):
            text = str(item.get("text", ""))
            legacy_class = str(item.get("cls", ""))
        else:
            text = str(item)
            legacy_class = ""
        _capture_event_with_signals(capture, signal_classifier, text, cls=legacy_class)
    redaction_rules = get_share_redaction_rules(CFG)
    if redaction_rules:
        redacted_events = redact_line_entries(capture.preview_lines, redaction_rules)
        redacted_entries: list[dict[str, object]] = []
        for entry in line_entries_from_events(redacted_events):
            if isinstance(entry, dict):
                redacted_entries.append(entry)
            else:
                redacted_entries.append({"text": str(entry), "cls": ""})
        capture.preview_lines = deque(redacted_entries)
    return list(capture.preview_lines), capture.preview_truncated, capture.output_line_count


@run_bp.route("/run/client", methods=["POST"])
def save_client_side_run():
    """Persist browser-owned built-in command output as a normal history run."""
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    command = data.get("command", "")
    if not isinstance(command, str):
        return jsonify({"error": "Command must be a string"}), 400
    command = command.strip()
    if not command:
        return jsonify({"error": "No command provided"}), 400
    if not _client_side_run_command_allowed(command):
        return jsonify({"error": "Client-side run persistence is limited to browser-owned built-ins"}), 403

    try:
        exit_code = int(data.get("exit_code", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "exit_code must be an integer"}), 400

    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = _require_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    client_ip = get_client_ip()
    raw_lines = data.get("lines", [])
    raw_line_count = len(raw_lines) if isinstance(raw_lines, list) else 0
    if not isinstance(raw_lines, list):
        log.warning("CLIENT_RUN_OUTPUT_INVALID", extra={
            "session": get_log_session_id(session_id),
            "ip": client_ip,
            "cmd": command,
            "payload_type": type(raw_lines).__name__,
        })
    lines, preview_truncated, output_line_count = _normalize_client_side_run_lines(raw_lines, command)
    if isinstance(raw_lines, list) and preview_truncated:
        log.warning("CLIENT_RUN_OUTPUT_TRUNCATED", extra={
            "session": get_log_session_id(session_id),
            "ip": client_ip,
            "cmd": command,
            "raw_line_count": raw_line_count,
            "stored_line_count": len(lines),
            "limit": CFG["max_output_lines"],
        })
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    finished = datetime.now(timezone.utc)
    output_search_text = _extract_output_search_text(lines)
    stored_output_search_text = maybe_store_text_body(
        "run_search",
        run_id,
        output_search_text,
        inline_threshold_bytes(CFG.get("runs_search_text_inline_max_bytes")),
    )

    log.info("RUN_START", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "pid": 0, "cmd": command, "cmd_type": "client-builtin",
    })
    app_metrics.record_run_started(command, RUN_KIND_BUILTIN, active=False)
    app_metrics.record_completed_run_values(
        command,
        RUN_KIND_BUILTIN,
        exit_code,
        0.0,
        output_bytes=sum(len(str(line.get("text", ""))) for line in lines),
        truncated=bool(preview_truncated),
    )

    with db_connect() as conn:
        _insert_run_row(
            conn,
            run_id=run_id,
            session_id=session_id,
            team_id=owner_scope.team_id,
            run_kind=RUN_KIND_BUILTIN,
            owner_tab_id=_active_run_owner_value(data.get("tab_id", "")),
            command=command,
            started=started.isoformat(),
            finished=finished.isoformat(),
            exit_code=exit_code,
            output_preview=json.dumps(lines),
            preview_truncated=int(preview_truncated),
            output_line_count=output_line_count,
            full_output_available=False,
            full_output_truncated=False,
            output_search_text=stored_output_search_text,
        )
        replace_run_output_summary(conn, run_id, lines)
        recorded_entities: list = []
        scan_observation_count = 0
        try:
            recorded_entities = _run_finalize_savepoint(
                conn,
                "atlas_entities",
                lambda: materialize_run_entities(
                    conn,
                    session_id,
                    run_id,
                    lines,
                    team_id=owner_scope.team_id,
                    seen_at=finished.isoformat(),
                    command=command,
                ),
            )
            scan_observation_count = _scan_target_observation_count(conn, run_id)
        except Exception:
            app_metrics.record_run_finalize_error("entity_materialize")
            log.error("ATLAS_ENTITY_CAPTURE_ERROR", exc_info=True, extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "cmd": command,
            })
        _log_atlas_entities_captured(
            session_id,
            owner_scope.team_id,
            run_id,
            recorded_entities,
            scan_observation_count,
        )
        conn.commit()

    elapsed = round((finished - started).total_seconds(), 1)
    log.info("RUN_END", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "exit_code": exit_code, "elapsed": elapsed, "cmd": command,
        "cmd_type": "client-builtin",
        "output_line_count": output_line_count,
        "full_output_truncated": False,
        "full_output_available": False,
        "artifact_count": 0,
    })
    return jsonify({"ok": True, "run_id": run_id, "output_line_count": output_line_count})


class _SyntheticPostFilterStageProcessor:
    """Apply one narrow app-native post-filter stage without enabling pipes."""

    def __init__(self, spec):
        self.spec = spec or {}
        self.kind = self.spec.get("kind")
        self._count = 0
        self._emitted = 0
        self._tail_buffer = deque(maxlen=int(self.spec.get("count", 0) or 0))
        self._grep_match = None
        self._line_buffer = []
        self._line_buffer_limit = max(0, int(CFG.get("max_output_lines", 0) or 0))
        self._line_buffer_dropped = 0

        if self.kind == "grep":
            pattern = self.spec["pattern"]
            flags = re.IGNORECASE if self.spec.get("ignore_case") else 0
            if self.spec.get("extended"):
                try:
                    compiled = re.compile(pattern, flags)
                except re.error as exc:
                    raise ValueError(f"Invalid synthetic grep regex: {exc}") from exc

                def _matches(line):
                    return bool(compiled.search(line))
            else:
                needle = pattern.lower() if self.spec.get("ignore_case") else pattern

                def _matches(line):
                    haystack = line.lower() if self.spec.get("ignore_case") else line
                    return needle in haystack

            if self.spec.get("invert_match"):
                self._grep_match = lambda line: not _matches(line)
            else:
                self._grep_match = _matches

    def process_output_line(self, line: str) -> list[str]:
        if not self.kind:
            return [line]

        normalized = str(line).rstrip("\n")
        if self.kind == "grep":
            return [line] if self._grep_match and self._grep_match(normalized) else []

        if self.kind == "head":
            if self._emitted >= int(self.spec.get("count", 0) or 0):
                return []
            self._emitted += 1
            return [line]

        if self.kind == "tail":
            self._tail_buffer.append(line)
            return []

        if self.kind == "wc_l":
            self._count += 1
            return []

        if self.kind in ("sort", "uniq"):
            if self._line_buffer_limit and len(self._line_buffer) >= self._line_buffer_limit:
                self._line_buffer_dropped += 1
                return []
            self._line_buffer.append(line)
            return []

        if self.kind == "jq":
            if self._line_buffer_limit and len(self._line_buffer) >= self._line_buffer_limit:
                self._line_buffer_dropped += 1
                return []
            self._line_buffer.append(line)
            return []

        return [line]

    def finalize_output_lines(self) -> list[str]:
        def _buffer_truncation_notice() -> list[str]:
            if self._line_buffer_dropped <= 0:
                return []
            return [
                "[post-filter] output truncated to "
                f"{self._line_buffer_limit} lines before {self.kind}; "
                f"{self._line_buffer_dropped} later lines were skipped.\n"
            ]

        if self.kind == "tail":
            return list(self._tail_buffer)
        if self.kind == "wc_l":
            return [str(self._count)]

        if self.kind == "sort":
            numeric = self.spec.get("numeric", False)

            def _sort_key(ln):
                s = ln.rstrip("\n").lstrip()
                if numeric:
                    m = re.match(r'^[-+]?\d+\.?\d*', s)
                    return float(m.group(0)) if m else float("-inf")
                return s.lower()

            result = sorted(self._line_buffer, key=_sort_key,
                            reverse=self.spec.get("reverse", False))
            if self.spec.get("unique"):
                seen: set = set()
                deduped = []
                for ln in result:
                    key = ln.rstrip("\n")
                    if key not in seen:
                        seen.add(key)
                        deduped.append(ln)
                result = deduped
            return [*_buffer_truncation_notice(), *result]

        if self.kind == "uniq":
            result = []
            prev = None
            if self.spec.get("count"):
                groups: list[tuple[int, str]] = []
                cnt = 0
                for ln in self._line_buffer:
                    n = ln.rstrip("\n")
                    if n == prev:
                        cnt += 1
                    else:
                        if prev is not None:
                            groups.append((cnt, prev))
                        prev = n
                        cnt = 1
                if prev is not None:
                    groups.append((cnt, prev))
                return [*_buffer_truncation_notice(), *[f"{c:7d} {ln}\n" for c, ln in groups]]
            for ln in self._line_buffer:
                n = ln.rstrip("\n")
                if n != prev:
                    result.append(ln)
                    prev = n
            return [*_buffer_truncation_notice(), *result]

        if self.kind == "jq":
            selector = self.spec.get("selector") if isinstance(self.spec, dict) else {}
            selector_op = selector.get("op", "") if isinstance(selector, dict) else ""
            if self._line_buffer_dropped > 0:
                log.warning("JQ_SELECTOR_CAP_HIT", extra={
                    "cap": "input_lines",
                    "limit": self._line_buffer_limit,
                    "dropped_count": self._line_buffer_dropped,
                    "selector_op": selector_op,
                })
                return [
                    "[error] jq input exceeded the buffered line safety cap\n",
                ]
            parsed = _parse_jq_input_values(self._line_buffer)
            if isinstance(parsed, str):
                log.debug("JQ_SELECTOR_PARSE_FAILED", extra={
                    "selector_op": selector_op,
                    "input_line_count": len(self._line_buffer),
                    "error": parsed,
                })
                return [f"[error] {parsed}\n"]
            selected: list[Any] = []
            for value in parsed:
                selected.extend(_select_jq_values(value, selector if isinstance(selector, dict) else {}))
                if len(selected) > 1000:
                    log.warning("JQ_SELECTOR_CAP_HIT", extra={
                        "cap": "output_lines",
                        "limit": 1000,
                        "selector_op": selector_op,
                    })
                    return ["[error] jq output exceeded the 1000-line safety cap\n"]
            output_lines: list[str] = []
            total_chars = 0
            for value in selected:
                rendered = _format_jq_value(
                    value,
                    raw=bool(self.spec.get("raw")),
                    compact=bool(self.spec.get("compact")),
                )
                total_chars += len(rendered)
                if total_chars > 200000:
                    log.warning("JQ_SELECTOR_CAP_HIT", extra={
                        "cap": "output_bytes",
                        "limit": 200000,
                        "selector_op": selector_op,
                    })
                    return ["[error] jq output exceeded the 200 KB safety cap\n"]
                output_lines.extend(f"{line}\n" for line in rendered.split("\n"))
            log.debug("JQ_SELECTOR_STAGE_COMPLETED", extra={
                "selector_op": selector_op,
                "input_line_count": len(self._line_buffer),
                "selected_count": len(selected),
                "raw_output": bool(self.spec.get("raw")),
                "compact_output": bool(self.spec.get("compact")),
            })
            return output_lines

        return []


class _SyntheticPostFilterProcessor:
    """Apply one or more narrow app-native post-filter stages in order."""

    def __init__(self, spec):
        self.spec = spec or {}
        stages = self.spec.get("stages") if isinstance(self.spec, dict) else None
        if stages:
            self.stages = [_SyntheticPostFilterStageProcessor(stage) for stage in stages]
        else:
            self.stages = [_SyntheticPostFilterStageProcessor(self.spec)]

    def process_output_line(self, line: str) -> list[str]:
        lines = [line]
        for stage in self.stages:
            next_lines = []
            for current in lines:
                next_lines.extend(stage.process_output_line(current))
            lines = next_lines
        return lines

    def finalize_output_lines(self) -> list[str]:
        lines: list[str] = []
        for stage in self.stages:
            next_lines = []
            for current in lines:
                next_lines.extend(stage.process_output_line(current))
            next_lines.extend(stage.finalize_output_lines())
            lines = next_lines
        return lines


def _parse_jq_input_values(lines: list[str]) -> list[Any] | str:
    non_empty = [str(line).strip() for line in lines if str(line).strip()]
    if not non_empty:
        return []
    jsonl_values: list[Any] = []
    for line in non_empty:
        try:
            jsonl_values.append(json.loads(line))
        except json.JSONDecodeError:
            break
    else:
        return jsonl_values
    try:
        return [json.loads("\n".join(non_empty))]
    except json.JSONDecodeError:
        return "jq expected JSON or JSONL input"


def _jq_path_value(value: Any, path: list[str]) -> Any:
    current = value
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _jq_path_exists(value: Any, path: list[str]) -> bool:
    current = value
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _select_jq_values(value: Any, selector: dict[str, Any]) -> list[Any]:
    op = str(selector.get("op") or "")
    path = [str(part) for part in selector.get("path", []) or []]
    if op == "identity":
        return [value]
    if op == "field":
        return [_jq_path_value(value, path)] if _jq_path_exists(value, path) else []
    if op == "iterate":
        target = _jq_path_value(value, path) if path else value
        return list(target) if isinstance(target, list) else []
    if op == "filter_has":
        return [value] if _jq_path_exists(value, path) else []
    if op == "filter_eq":
        haystack = _jq_filter_text(_jq_path_value(value, path) if _jq_path_exists(value, path) else "")
        return [value] if haystack == str(selector.get("value", "")) else []
    if op == "filter_contains":
        haystack = _jq_filter_text(_jq_path_value(value, path) if _jq_path_exists(value, path) else "")
        return [value] if str(selector.get("value", "")) in haystack else []
    return []


def _jq_filter_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _format_jq_value(value: Any, *, raw: bool, compact: bool) -> str:
    if raw and (value is None or isinstance(value, str | int | float | bool)):
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
    if compact:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(value, ensure_ascii=False, indent=2)


class _WorkspacePathOutputFilter:
    """Display absolute owner-workspace paths as user-facing workspace paths."""

    def __init__(self, session_id: str, cfg: dict, *, owner_context: OwnerContext | None = None):
        self.prefix = ""
        self.pattern = None
        if not session_id or not cfg.get("workspace_enabled"):
            return
        try:
            owner = owner_context or personal_owner_context(session_id)
            self.prefix = str(owner_workspace_dir(owner, cfg).resolve(strict=False)).rstrip(os.sep)
        except (WorkspaceDisabled, OSError):
            self.prefix = ""
        if self.prefix:
            self.pattern = re.compile(re.escape(self.prefix) + r"(/[\w@%+=:,./-]*)?")

    def process_output_line(self, line: str) -> str:
        if not self.pattern:
            return line

        def _replace(match):
            suffix = str(match.group(1) or "").lstrip("/")
            return f"/{suffix}" if suffix else "/"

        return self.pattern.sub(_replace, line)


class _TruffleHogOutputFilter:
    _SECRET_FIELDS = {"Raw", "RawV2"}

    def __init__(self, command: str):
        self.enabled = command_root(command) == "trufflehog"

    def process_output_line(self, line: str) -> str:
        if not self.enabled:
            return line
        suffix = "\n" if str(line).endswith("\n") else ""
        try:
            parsed = json.loads(str(line).rstrip("\n"))
        except (TypeError, ValueError):
            return line
        if not isinstance(parsed, dict):
            return line
        redacted = False
        for secret_field in self._SECRET_FIELDS:
            if secret_field in parsed and parsed[secret_field] not in ("", None):
                parsed[secret_field] = "[redacted]"
                redacted = True
        if not redacted:
            return line
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":")) + suffix


@dataclass(frozen=True)
class _PreparedCommandInput:
    execution_command: str
    variable_notice: str
    postfilter: _SyntheticPostFilterProcessor


@dataclass(frozen=True)
class _PreparedRealCommand:
    registry_command: str
    execution_command: str
    command: str
    rewrite_notice: str | None
    validation: CommandValidationResult
    missing_runtime: str | None
    env_overrides: dict[str, str]
    secret_env_names: list[str]


@dataclass(frozen=True)
class _StartedRealCommand:
    run_id: str
    run_started: str
    proc: subprocess.Popen
    capture: RunOutputCapture
    signal_classifier: OutputSignalClassifier
    workspace_path_filter: _WorkspacePathOutputFilter


def _preparation_error_response(exc: _RunPreparationError):
    return jsonify({"error": str(exc)}), exc.status_code


def _run_start_handlers() -> RunStartHandlers:
    return RunStartHandlers(
        resolves_exact_special_builtin_command=resolves_exact_special_builtin_command,
        execute_builtin_command=execute_builtin_command,
        history_safe_command_for_storage=_history_safe_command_for_storage,
        brokered_synthetic_run=_brokered_synthetic_run,
        prepare_command_input=_prepare_command_input,
        resolve_builtin_command=resolve_builtin_command,
        filter_builtin_command_events=_filter_builtin_command_events,
        prepare_real_command=_prepare_real_command,
        runtime_missing_command_message=runtime_missing_command_message,
        start_real_command_process=_start_real_command_process,
        publish_run_event=publish_run_event,
        brokered_real_run_worker=_brokered_real_run_worker,
        workspace_notice_lines=_workspace_notice_lines,
        workspace_artifacts_from_validation=_workspace_artifacts_from_validation,
    )


def _coerce_positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        number = int(value)
    elif isinstance(value, (str, bytes, bytearray)):
        try:
            number = int(value)
        except ValueError:
            return default
    else:
        return default
    return number if number > 0 else default


def _interactive_pty_concurrency_limit() -> int:
    return _coerce_positive_int(CFG.get("interactive_pty_max_concurrent_per_session", 4), 4)


def _interactive_pty_input_limit() -> str:
    per_minute = _coerce_positive_int(CFG.get("interactive_pty_input_rate_limit_per_minute"), 500)
    per_second = _coerce_positive_int(CFG.get("interactive_pty_input_rate_limit_per_second"), 10)
    return f"{per_minute} per minute; {per_second} per second"


def _interactive_pty_resize_limit() -> str:
    per_minute = _coerce_positive_int(CFG.get("interactive_pty_resize_rate_limit_per_minute"), 600)
    per_second = _coerce_positive_int(CFG.get("interactive_pty_resize_rate_limit_per_second"), 30)
    return f"{per_minute} per minute; {per_second} per second"


def _active_interactive_pty_count(session_id: str) -> int:
    return sum(
        1 for item in active_runs_for_session(session_id)
        if str(item.get("run_type", "command") or "command") == "pty"
    )


def _cmd_denied_log_extra(client_ip: str, session_id: str, command: str, reason: str) -> dict:
    reason_text = str(reason or "")
    deny_kind = "policy"
    if "secret" in reason_text.lower() or "vault" in reason_text.lower():
        deny_kind = "secret"
    elif "workspace" in reason_text.lower() or "path" in reason_text.lower():
        deny_kind = "workspace"
    elif "shell operators" in reason_text.lower():
        deny_kind = "shell_operator"
    return {
        "ip": client_ip,
        "session": get_log_session_id(session_id),
        "cmd": command,
        "reason": reason_text,
        "deny_kind": deny_kind,
        "rule_id": "",
    }


def _prepare_interactive_pty_command(
    original_command: str,
    session_id: str,
    client_ip: str,
    workspace_cwd: str = "",
    *,
    owner_context: OwnerContext | None = None,
) -> tuple[list[str], str, dict[str, object]]:
    tokens = split_command_argv(original_command)
    spec = interactive_pty_spec_for_command(original_command)
    if not tokens or not spec:
        root = tokens[0].lower() if tokens else "command"
        raise _RunPreparationError(f"Interactive PTY mode is not available for {root}", status_code=403)
    trigger_flag = str(spec.get("trigger_flag") or "").strip()
    if not trigger_flag or trigger_flag not in tokens[1:]:
        root = str(spec.get("root") or tokens[0].lower())
        raise _RunPreparationError(
            f"{root} interactive PTY commands must include {trigger_flag or 'the configured trigger flag'}",
            status_code=400,
        )
    argv = [token for token in tokens if token != trigger_flag]
    if bool(spec.get("requires_args", False)) and len(argv) < 2:
        root = str(spec.get("root") or tokens[0].lower())
        raise _RunPreparationError(f"{root} {trigger_flag} requires command arguments", status_code=400)
    execution_command = shlex.join(argv)
    extra_allowed_prefixes = [str(spec.get("root") or tokens[0].lower())]
    validation = _validate_command_with_effective_owner(
        execution_command,
        session_id,
        workspace_cwd,
        extra_allowed_prefixes=extra_allowed_prefixes,
        owner_context=owner_context,
    )
    if not validation.allowed:
        log.warning("CMD_DENIED", extra=_cmd_denied_log_extra(client_ip, session_id, original_command, validation.reason))
        raise _RunPreparationError(validation.reason)
    execution_command = validation.exec_command or execution_command
    missing_runtime = runtime_missing_command_name(execution_command)
    if missing_runtime:
        raise _RunPreparationError(runtime_missing_command_message(missing_runtime), status_code=503)
    return split_command_argv(execution_command), execution_command, spec


def _prepare_command_input(
    original_command: str,
    session_id: str,
    client_ip: str,
    *,
    log_pipe: bool = False,
) -> _PreparedCommandInput:
    expanded_command = original_command
    variable_notice = ""
    if command_root(original_command) != "var":
        try:
            expansion = expand_session_variables(original_command, session_id)
            expanded_command = expansion.command
            if expanded_command != original_command:
                variable_notice = _variable_notice_line(expanded_command, expansion.used_names)
        except SessionVariableError as exc:
            log.warning("CMD_DENIED", extra=_cmd_denied_log_extra(client_ip, session_id, original_command, str(exc)))
            raise _RunPreparationError(str(exc)) from exc

    postfilter_spec, postfilter_error = parse_synthetic_postfilter(expanded_command)
    if postfilter_error:
        log.warning("CMD_DENIED", extra=_cmd_denied_log_extra(client_ip, session_id, original_command, postfilter_error))
        raise _RunPreparationError(postfilter_error)
    execution_command = postfilter_spec["base_command"] if postfilter_spec else expanded_command
    if log_pipe and postfilter_spec:
        stage_kinds = [stage.get("kind") for stage in postfilter_spec.get("stages", []) if stage.get("kind")]
        log.debug("CMD_PIPE", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": original_command,
            "kind": " -> ".join(stage_kinds) if stage_kinds else postfilter_spec.get("kind"),
        })
    try:
        postfilter = _SyntheticPostFilterProcessor(postfilter_spec)
    except ValueError as exc:
        raise _RunPreparationError(str(exc)) from exc
    return _PreparedCommandInput(
        execution_command=execution_command,
        variable_notice=variable_notice,
        postfilter=postfilter,
    )


def _filter_builtin_command_events(events, variable_notice: str, postfilter: _SyntheticPostFilterProcessor):
    if variable_notice:
        events = [to_legacy_output_event(line_event_from_legacy(variable_notice, kind=LineKind.notice))] + events
    filtered_events = []
    for event in events:
        if event.get("type") != "output":
            filtered_events.append(event)
            continue
        for filtered_line in postfilter.process_output_line(str(event.get("text", ""))):
            filtered_event = dict(event)
            filtered_event["text"] = filtered_line.rstrip("\n")
            filtered_events.append(filtered_event)
    for filtered_line in postfilter.finalize_output_lines():
        filtered_events.append({"type": "output", "text": filtered_line.rstrip("\n")})
    return filtered_events


def _runtime_env_names(command: str) -> list[str]:
    names: list[str] = []
    tokens = split_command_argv(command)
    start = 1 if tokens and tokens[0] == "env" else 0
    for token in tokens[start:]:
        if "=" not in token or token.startswith("-"):
            break
        name = token.split("=", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            names.append(name)
            continue
        break
    return names


def _resolve_secret_environment(command: str, session_id: str, *, team_id: str = "") -> tuple[dict[str, str], list[str]]:
    if is_help_invocation(command):
        return {}, []
    declarations = required_secrets_for_command(command)
    if not declarations:
        return {}, []
    if not session_id:
        raise _RunPreparationError(
            "A valid session is required before commands can use encrypted secrets.",
            status_code=401,
        )

    secret_scope_id = team_id or session_id
    env_overrides: dict[str, str] = {}
    missing_required: list[str] = []
    missing_optional: list[str] = []
    missing_labels: dict[str, str] = {}
    for declaration in declarations:
        env_name = str(declaration.get("env") or "").strip().upper()
        if not env_name:
            continue
        inject_env_name = str(declaration.get("inject_env") or env_name).strip().upper()
        if not inject_env_name:
            continue
        raw_fallback_envs = declaration.get("fallback_envs")
        fallback_envs = [
            str(item or "").strip().upper()
            for item in (raw_fallback_envs if isinstance(raw_fallback_envs, list) else [])
            if str(item or "").strip()
        ]
        lookup_env_names = [env_name, *[item for item in fallback_envs if item != env_name]]
        try:
            value = None
            for lookup_env_name in lookup_env_names:
                value = get_secret_value_for_env(
                    secret_scope_id,
                    lookup_env_name,
                    audit_session_id=session_id,
                    team_id=team_id,
                )
                if value is not None:
                    break
        except (InvalidSecretName, MasterKeyError, SecretDecryptError) as exc:
            log.error("SECRET_ENV_RESOLVE_FAILED", exc_info=True, extra={
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "command_root": command_root(command) or "",
                "secret_name": env_name,
                "lookup_env_names": lookup_env_names,
                "error_type": type(exc).__name__,
            })
            raise _RunPreparationError("Secrets vault unavailable. Check server logs.", status_code=503) from exc
        if value is None:
            missing_label = " or ".join(lookup_env_names)
            if bool(declaration.get("optional", False)):
                missing_optional.append(env_name)
            else:
                missing_required.append(env_name)
                missing_labels[env_name] = missing_label
            continue
        env_overrides[inject_env_name] = value

    if missing_required:
        if len(missing_required) == 1:
            subject = f"secret {missing_labels.get(missing_required[0], missing_required[0])}"
            setup_hint = "Set it via \"secret set NAME\" or the Options > Secrets panel."
            if team_id:
                setup_hint = "Set it in Options > Secrets while the team scope is active."
        else:
            subject = "secrets " + ", ".join(missing_labels.get(env_name, env_name) for env_name in missing_required)
            setup_hint = "Set each one via \"secret set NAME\" or the Options > Secrets panel."
            if team_id:
                setup_hint = "Set them in Options > Secrets while the team scope is active."
        raise _RunPreparationError(
            f"Run requires {subject} which is not set. " +
            setup_hint,
            status_code=403,
        )
    for env_name in missing_optional:
        log.warning("SECRET_OPTIONAL_MISSING", extra={
            "session": get_log_session_id(session_id),
            "secret_name": env_name,
            "command_root": command_root(command) or "",
        })
    return env_overrides, sorted(env_overrides)


def _prepare_real_command(
    original_command: str,
    execution_command: str,
    session_id: str,
    client_ip: str,
    workspace_cwd: str = "",
    *,
    team_id: str = "",
    owner_context: OwnerContext | None = None,
) -> _PreparedRealCommand:
    registry_command = execution_command
    effective_owner_context = _effective_owner_context(owner_context, session_id)
    validation = _validate_command_with_effective_owner(
        execution_command,
        session_id,
        workspace_cwd,
        owner_context=effective_owner_context,
    )
    if not validation.allowed:
        log.warning("CMD_DENIED", extra=_cmd_denied_log_extra(client_ip, session_id, original_command, validation.reason))
        raise _RunPreparationError(validation.reason)
    execution_command = validation.exec_command or execution_command

    if effective_owner_context is not None:
        command, notice = rewrite_command(
            execution_command,
            session_id=session_id,
            cfg=CFG,
            owner_context=effective_owner_context,
        )
    else:
        command, notice = rewrite_command(execution_command, session_id=session_id, cfg=CFG)
    if command != execution_command:
        log.debug("CMD_REWRITE_APPLIED", extra={
            "ip": client_ip,
            "session": get_log_session_id(session_id),
            "command_root": command_root(original_command) or "",
            "rewrite_notice": notice or "",
            "workspace_read_count": len(validation.workspace_reads),
            "workspace_write_count": len(validation.workspace_writes),
            "workspace_exec_path_count": len(validation.workspace_exec_paths),
            "runtime_env_names": _runtime_env_names(command),
        })

    missing_runtime = runtime_missing_command_name(command)
    if missing_runtime:
        log.warning("CMD_MISSING", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": original_command, "missing": missing_runtime,
        })
    env_overrides, secret_env_names = _resolve_secret_environment(registry_command, session_id, team_id=team_id)
    return _PreparedRealCommand(
        registry_command=registry_command,
        execution_command=execution_command,
        command=command,
        rewrite_notice=notice,
        validation=validation,
        missing_runtime=missing_runtime,
        env_overrides=env_overrides,
        secret_env_names=secret_env_names,
    )


def _real_command_popen_argv(prepared_real: _PreparedRealCommand) -> list[str]:
    scanner_prefix = list(SCANNER_PREFIX)
    if scanner_prefix and prepared_real.secret_env_names and scanner_prefix[0] == "sudo":
        scanner_prefix.insert(1, "--preserve-env=" + ",".join(prepared_real.secret_env_names))
    command = _secret_aware_shell_command(prepared_real)
    command_argv = _line_buffered_shell_argv(command)
    return scanner_prefix + command_argv if scanner_prefix else command_argv


def _line_buffered_shell_argv(command: str) -> list[str]:
    shell_argv = [SHELL_BIN, "-c", command]
    if not STDBUF_BIN:
        return shell_argv
    return [STDBUF_BIN, "-oL", "-eL", *shell_argv]


def _secret_aware_shell_command(prepared_real: _PreparedRealCommand) -> str:
    if (
        command_root(prepared_real.registry_command) == "shodan" and
        "SHODAN_API_KEY" in prepared_real.secret_env_names
    ):
        return _shodan_configured_shell_command(prepared_real.command)
    return prepared_real.command


def _shodan_configured_shell_command(command: str) -> str:
    warnings_filter = "ignore:pkg_resources is deprecated as an API:UserWarning"
    return (
        "__darklab_shodan_home=$(mktemp -d) && "
        "trap 'rm -rf \"$__darklab_shodan_home\"' EXIT HUP INT TERM && "
        "mkdir -p \"$__darklab_shodan_home/.shodan\" && "
        "chmod 700 \"$__darklab_shodan_home/.shodan\" && "
        "printf '%s' \"$SHODAN_API_KEY\" > \"$__darklab_shodan_home/.shodan/api_key\" && "
        "chmod 600 \"$__darklab_shodan_home/.shodan/api_key\" && "
        f"HOME=\"$__darklab_shodan_home\" PYTHONWARNINGS={shlex.quote(warnings_filter)} {command}"
    )


def _history_safe_command_for_storage(command: str) -> str:
    parts = split_command_argv(command)
    if len(parts) > 3 and parts[0].lower() == "secret" and parts[1].lower() == "set":
        return f"secret set {parts[2]}"
    return command


def _start_real_command_process(
    original_command: str,
    session_id: str,
    client_ip: str,
    prepared_real: _PreparedRealCommand,
    *,
    owner_client_id: str = "",
    owner_tab_id: str = "",
    team_id: str = "",
    owner_context: OwnerContext | None = None,
) -> _StartedRealCommand:
    run_id = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    capture = _run_output_capture(run_id)
    signal_classifier = OutputSignalClassifier(prepared_real.execution_command, cmd_type="real")
    workspace_owner = owner_context
    if workspace_owner is None:
        workspace_owner = owner_context_for_scope(session_id, team_id=team_id)
    workspace_path_filter = _WorkspacePathOutputFilter(session_id, CFG, owner_context=workspace_owner)
    env_overrides = dict(prepared_real.env_overrides)
    popen_env = None

    try:
        if env_overrides:
            popen_env = os.environ.copy()
            popen_env.update(env_overrides)
        proc = subprocess.Popen(
            _real_command_popen_argv(prepared_real),
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=_prepare_run_child,
            env=popen_env,
        )
    except Exception as exc:
        log.error("RUN_SPAWN_ERROR", exc_info=True, extra={
            "ip": client_ip, "session": get_log_session_id(session_id), "cmd": original_command,
        })
        raise _RunSpawnError(str(exc)) from exc
    finally:
        # Best-effort scrub of plaintext from the parent process after spawn.
        # Python strings are immutable, so this drops references rather than
        # guaranteeing bytewise heap clearing. The subprocess has its own copy.
        for key in env_overrides:
            env_overrides[key] = ""
        prepared_real.env_overrides.clear()
        if popen_env is not None:
            for key in prepared_real.secret_env_names:
                popen_env[key] = ""

    pid_register(run_id, proc.pid)
    active_kwargs = {
        "owner_client_id": owner_client_id,
        "owner_tab_id": owner_tab_id,
    }
    if team_id:
        active_kwargs["team_id"] = team_id
    active_run_register(
        run_id,
        proc.pid,
        session_id,
        original_command,
        run_started,
        **active_kwargs,
    )
    log.info("RUN_START", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "pid": proc.pid, "cmd": original_command, "cmd_type": "real",
    })
    if prepared_real.secret_env_names:
        emit_secret_event(
            "SECRET_INJECTED",
            session_id,
            consumer_envs=prepared_real.secret_env_names,
            run_id=run_id,
            command_root=command_root(prepared_real.registry_command) or "",
        )
    return _StartedRealCommand(
        run_id=run_id,
        run_started=run_started,
        proc=proc,
        capture=capture,
        signal_classifier=signal_classifier,
        workspace_path_filter=workspace_path_filter,
    )


def _publish_broker_captured_line(
    run_id: str,
    capture,
    signal_classifier,
    event_type: str,
    text: str,
    *,
    cls: str = "",
    kind: LineKind | str | None = None,
    event: LineEvent | None = None,
    run_started_dt,
):
    line_dt = datetime.now(timezone.utc)
    base_event = event or line_event_from_legacy(
        text,
        cls,
        kind=kind,
        ts_clock=line_dt.strftime("%H:%M:%S"),
        ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
    )
    _metadata, captured_event = _capture_event_with_signals(
        capture,
        signal_classifier,
        event=base_event,
    )
    publish_run_event(
        run_id,
        event_type,
        _broker_output_payload(event_type, event=captured_event),
    )


def _brokered_synthetic_run(
    original_command,
    session_id,
    client_ip,
    events,
    exit_code=0,
    *,
    cmd_type="builtin",
    owner_tab_id="",
    team_id="",
):
    run_id = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    capture = _run_output_capture(run_id)
    signal_classifier = OutputSignalClassifier(original_command, cmd_type=cmd_type)
    run_started_dt = datetime.fromisoformat(run_started)

    log.info("RUN_START", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "pid": 0, "cmd": original_command, "cmd_type": cmd_type,
    })
    app_metrics.record_run_started(
        original_command,
        run_kind_for_cmd_type(cmd_type),
        active=False,
    )
    publish_run_event(run_id, "started", {"run_id": run_id, "started": run_started})
    try:
        for event in events:
            if event.get("type") == "output":
                _publish_broker_captured_line(
                    run_id,
                    capture,
                    signal_classifier,
                    "output",
                    str(event.get("text", "")),
                    cls=str(event.get("cls", "")),
                    run_started_dt=run_started_dt,
                )
            elif event.get("type") == "clear":
                publish_run_event(run_id, "clear", {})
        finished = datetime.now(timezone.utc)
        elapsed = round((finished - datetime.fromisoformat(run_started)).total_seconds(), 1)
        log.info("RUN_END", extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
            "exit_code": exit_code, "elapsed": elapsed, "cmd": original_command,
            "cmd_type": cmd_type,
            "output_line_count": capture.output_line_count,
            "preview_truncated": capture.preview_truncated,
            "full_output_available": capture.full_output_available,
            "full_output_truncated": capture.full_output_truncated,
        })
        publish_run_event(run_id, "exit", {
            "code": exit_code,
            "elapsed": elapsed,
            "preview_truncated": capture.preview_truncated,
            "output_line_count": capture.output_line_count,
            "full_output_available": capture.full_output_available,
        })
        _save_completed_run(
            run_id, session_id, team_id, original_command, run_started,
            finished.isoformat(), exit_code, capture,
            link_active_project=cmd_type == "real",
            run_kind=run_kind_for_cmd_type(cmd_type),
            owner_tab_id=owner_tab_id,
        )
        app_metrics.record_completed_run(
            original_command,
            run_kind_for_cmd_type(cmd_type),
            exit_code,
            elapsed,
            capture,
        )
    except Exception as exc:
        log.error("RUN_BROKER_SYNTHETIC_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
            "cmd": original_command,
        })
        publish_run_event(run_id, "error", {"text": str(exc)})
    return run_id


def _publish_counted_project_notice(
    run_id: str,
    *,
    count: int,
    singular: str,
    plural: str,
    text_template: str,
    payload: dict[str, object],
) -> None:
    if count <= 0:
        return
    label = singular if count == 1 else plural
    publish_run_event(run_id, "notice", {
        **payload,
        "text": text_template.format(count=count, label=label),
    })


def _publish_project_finalize_notices(run_id: str, active_project_link, finalize_summary) -> None:
    if active_project_link:
        project_name = str(
            active_project_link.get("project_name")
            or active_project_link.get("project_id")
            or "active project"
        )
        project_payload = {
            "project_id": active_project_link.get("project_id"),
            "project_name": project_name,
        }
        publish_run_event(run_id, "notice", {
            **project_payload,
            "text": f"[project] linked run to {project_name}",
            "project_linked": True,
        })
        discovered_target_count = int(active_project_link.get("discovered_target_count") or 0)
        linked_entity_count = int(active_project_link.get("linked_entity_count") or 0)
        rejected_entity_count = int(active_project_link.get("rejected_entity_count") or 0)
        for spec in (
            {
                "count": discovered_target_count,
                "singular": "target",
                "plural": "targets",
                "text_template": f"[project] discovered {{count}} {{label}} for {project_name}",
                "payload": {
                    **project_payload,
                    "project_targets_discovered": True,
                    "target_count": discovered_target_count,
                },
            },
            {
                "count": linked_entity_count,
                "singular": "Atlas entity",
                "plural": "Atlas entities",
                "text_template": f"[project] linked {{count}} {{label}} to {project_name}",
                "payload": {
                    **project_payload,
                    "project_entities_linked": True,
                    "entity_count": linked_entity_count,
                },
            },
            {
                "count": rejected_entity_count,
                "singular": "Atlas entity",
                "plural": "Atlas entities",
                "text_template": (
                    f"[project] skipped {{count}} {{label}} for {project_name} "
                    "because the project link limit was reached"
                ),
                "payload": {
                    **project_payload,
                    "project_entities_rejected": True,
                    "entity_count": rejected_entity_count,
                    "reason": "project_link_limit",
                },
            },
        ):
            _publish_counted_project_notice(run_id, **spec)
    if isinstance(finalize_summary, dict):
        auto_promote_count = int(finalize_summary.get("project_auto_promote_count") or 0)
        promoted_count = int(finalize_summary.get("project_auto_promote_promoted_count") or 0)
        project_ids = [
            str(project_id)
            for project_id in (finalize_summary.get("project_auto_promote_project_ids") or [])
            if str(project_id or "")
        ]
        _publish_counted_project_notice(
            run_id,
            count=auto_promote_count,
            singular="Atlas entity",
            plural="Atlas entities",
            text_template="[project] auto-promoted {count} {label}",
            payload={
                "project_id": project_ids[0] if len(project_ids) == 1 else "",
                "project_ids": project_ids,
                "project_auto_promoted": True,
                "entity_count": auto_promote_count,
                "promoted_count": promoted_count,
            },
        )


def _brokered_real_run_worker(
    *,
    run_id,
    proc,
    session_id,
    team_id,
    client_ip,
    original_command,
    run_started,
    capture,
    signal_classifier,
    postfilter,
    workspace_path_filter,
    variable_notice,
    rewrite_notice,
    workspace_notices,
    workspace_artifacts,
    owner_tab_id,
    link_project_id="",
):
    command_timeout = CFG["command_timeout_seconds"] or None
    heartbeat_interval = CFG.get("run_broker_heartbeat_seconds") or CFG["heartbeat_interval_seconds"]
    run_started_dt = datetime.fromisoformat(run_started)
    trufflehog_output_filter = _TruffleHogOutputFilter(original_command)

    def _process_real_output_line(line: str) -> list[str]:
        filtered = workspace_path_filter.process_output_line(line)
        filtered = trufflehog_output_filter.process_output_line(filtered)
        return postfilter.process_output_line(filtered)

    try:
        if variable_notice:
            _publish_broker_captured_line(
                run_id, capture, signal_classifier, "notice", variable_notice,
                kind=LineKind.notice, run_started_dt=run_started_dt,
            )
        if rewrite_notice:
            _publish_broker_captured_line(
                run_id, capture, signal_classifier, "notice", f"[notice] {rewrite_notice}",
                kind=LineKind.notice, run_started_dt=run_started_dt,
            )
        for workspace_notice in workspace_notices:
            _publish_broker_captured_line(
                run_id, capture, signal_classifier, "notice", workspace_notice,
                kind=LineKind.notice, run_started_dt=run_started_dt,
            )

        if proc.stdout is None:
            raise RuntimeError("Process stdout pipe was not created")
        stream_reader = _make_nonblocking_stream_reader(proc.stdout)
        output_batcher = _BrokerOutputBatcher(
            run_id,
            capture,
            signal_classifier,
            run_started_dt=run_started_dt,
        )
        stream_fd = stream_reader.get("fd")
        stream_is_nonblocking = stream_fd is not None
        stream_poll_target = stream_fd if stream_is_nonblocking else proc.stdout
        if stream_poll_target is None:
            raise RuntimeError("Process stdout pipe was not created")
        heartbeat_seconds = max(_RUN_OUTPUT_POLL_SECONDS, float(heartbeat_interval or 0))
        next_heartbeat_monotonic = time.monotonic() + heartbeat_seconds
        while True:
            if command_timeout:
                now_dt = datetime.now(timezone.utc)
                elapsed = (now_dt - run_started_dt).total_seconds()
                if elapsed >= command_timeout:
                    try:
                        _terminate_process_group(proc)
                    except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                        log.warning("CMD_TIMEOUT_TERMINATE_FAILED", exc_info=True, extra={
                            "run_id": run_id,
                            "session": get_log_session_id(session_id),
                            "ip": client_ip,
                            "cmd": original_command,
                        })
                    timeout_msg = _timeout_notice(command_timeout)
                    log.warning("CMD_TIMEOUT", extra={
                        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
                        "timeout": command_timeout, "cmd": original_command,
                    })
                    output_batcher.flush()
                    _publish_broker_captured_line(
                        run_id, capture, signal_classifier, "notice", timeout_msg,
                        kind=LineKind.notice, run_started_dt=run_started_dt,
                    )
                    break

            stdout_ready = _stdout_ready(stream_poll_target, _RUN_OUTPUT_POLL_SECONDS)
            if stdout_ready or stream_is_nonblocking:
                lines, eof = _read_available_stream_lines(stream_reader)
                if not lines and eof:
                    break
                if not lines:
                    if proc.poll() is not None:
                        break
                    now_monotonic = time.monotonic()
                    if now_monotonic >= next_heartbeat_monotonic:
                        publish_run_event(run_id, "heartbeat", {})
                        next_heartbeat_monotonic = now_monotonic + heartbeat_seconds
                    continue
                for line in lines:
                    for filtered_line in _process_real_output_line(line):
                        output_batcher.add(filtered_line)
                output_batcher.flush_due()
            else:
                output_batcher.flush_due()
                if proc.poll() is not None:
                    break
                now_monotonic = time.monotonic()
                if now_monotonic >= next_heartbeat_monotonic:
                    publish_run_event(run_id, "heartbeat", {})
                    next_heartbeat_monotonic = now_monotonic + heartbeat_seconds

        trailing_lines, _ = _read_available_stream_lines(stream_reader, finalize=True)
        for line in trailing_lines:
            for filtered_line in _process_real_output_line(line):
                output_batcher.add(filtered_line)
        for filtered_line in postfilter.finalize_output_lines():
            output_batcher.add(filtered_line)
        output_batcher.flush()
        exit_code = _wait_for_proc_exit_code(proc)
        finalize_info = _finalize_completed_run(
            run_id,
            session_id,
            team_id,
            client_ip,
            original_command,
            run_started,
            exit_code,
            capture,
            workspace_artifacts=workspace_artifacts,
            owner_tab_id=owner_tab_id,
            link_project_id=link_project_id,
        )
        elapsed = finalize_info["elapsed"]
        active_project_link = finalize_info.get("active_project_link")
        finalize_summary = finalize_info.get("finalize_summary") if isinstance(finalize_info, dict) else {}
        _publish_project_finalize_notices(run_id, active_project_link, finalize_summary)
        publish_run_event(run_id, "exit", {
            "code": exit_code,
            "elapsed": elapsed,
            "preview_truncated": capture.preview_truncated,
            "output_line_count": capture.output_line_count,
            "full_output_available": capture.full_output_available,
        })
    except Exception as exc:
        log.error("RUN_BROKER_STREAM_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
            "cmd": original_command,
        })
        publish_run_event(run_id, "error", {"text": str(exc)})
    finally:
        _cleanup_proc_stream(proc)
        pid_pop(run_id)
        active_run_remove(run_id)


def _run_belongs_to_session(run_id: str, session_id: str) -> bool:
    return bool(_run_session_visibility(run_id, session_id, "")["allowed"])


def pty_run_belongs_to_session(run_id: str, session_id: str) -> bool:
    return pty_run_belongs_to_scope(run_id, session_id, "")


def _run_scope_mismatch_payload(actual_team_id: str) -> dict[str, str]:
    if actual_team_id:
        return {
            "error": "run_scope_mismatch",
            "message": "Run exists in a different team scope. Switch to that team scope to view it.",
            "scope": "team",
            "team_id": actual_team_id,
        }
    return {
        "error": "run_scope_mismatch",
        "message": "Run exists in personal scope. Switch to personal scope to view it.",
        "scope": "personal",
        "team_id": "",
    }


def _run_visibility_error_response(visibility: _RunSessionVisibility):
    if visibility.get("scope_mismatch"):
        return jsonify(_run_scope_mismatch_payload(str(visibility.get("actual_team_id", "") or ""))), 409
    return jsonify({"error": "Run not found"}), 404


def _run_session_visibility(run_id: str, session_id: str, team_id: str = "") -> _RunSessionVisibility:
    if not run_id or not session_id:
        return {
            "allowed": False,
            "active_match": False,
            "db_match": False,
            "active_count": 0,
        }
    if active_run_belongs_to_scope(run_id, session_id, team_id):
        return {
            "allowed": True,
            "active_match": True,
            "db_match": False,
            "active_count": 1,
        }
    scoped_active_runs = (
        active_runs_for_team(team_id)
        if team_id
        else active_runs_for_session(session_id, team_id="")
    )
    active_ids = {str(item.get("run_id", "")) for item in scoped_active_runs}
    active_match = run_id in active_ids
    if active_match:
        return {
            "allowed": True,
            "active_match": True,
            "db_match": False,
            "active_count": len(active_ids),
        }
    for item in active_runs_for_session(session_id, team_id=None):
        if str(item.get("run_id", "")) == run_id:
            return {
                "allowed": False,
                "active_match": False,
                "db_match": False,
                "active_count": len(active_ids),
                "scope_mismatch": True,
                "actual_team_id": str(item.get("team_id", "") or ""),
            }
    try:
        with db_connect() as conn:
            if team_id:
                row = conn.execute(
                    "SELECT 1 FROM runs WHERE id = ? AND team_id = ?",
                    (run_id, team_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM runs WHERE id = ? AND session_id = ? AND team_id = ''",
                    (run_id, session_id),
                ).fetchone()
            db_match = row is not None
            other_scope_row = None
            if not db_match:
                other_scope_row = conn.execute(
                    "SELECT team_id FROM runs WHERE id = ?",
                    (run_id,),
                ).fetchone()
            return {
                "allowed": db_match,
                "active_match": False,
                "db_match": db_match,
                "active_count": len(active_ids),
                "scope_mismatch": other_scope_row is not None,
                "actual_team_id": str(other_scope_row["team_id"] or "") if other_scope_row else "",
            }
    except Exception:
        log.error("RUN_BROKER_SESSION_CHECK_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id),
        })
        return {
            "allowed": False,
            "active_match": False,
            "db_match": False,
            "active_count": len(active_ids),
        }


# ── Routes ────────────────────────────────────────────────────────────────────

@run_bp.route("/pty/runs", methods=["POST"])
@limiter.limit(lambda: (
    f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"
))
def start_interactive_pty_run():
    if not pty_enabled():
        return jsonify({"error": "Interactive PTY mode is disabled on this instance"}), 403
    if not pty_broker_available():
        return jsonify({"error": pty_broker_unavailable_reason()}), 503

    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    original_command = data.get("command", "")
    if not isinstance(original_command, str):
        return jsonify({"error": "Command must be a string"}), 400
    original_command = original_command.strip()
    if not original_command:
        return jsonify({"error": "No command provided"}), 400

    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = _require_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    client_ip = get_client_ip()
    workspace_cwd = _workspace_cwd_value(data.get("workspace_cwd", ""))
    try:
        argv, execution_command, pty_spec = _prepare_interactive_pty_command(
            original_command,
            session_id,
            client_ip,
            workspace_cwd,
            owner_context=owner_scope.context,
        )
    except _RunPreparationError as exc:
        return _preparation_error_response(exc)

    pty_limit = _interactive_pty_concurrency_limit()
    active_pty_count = _active_interactive_pty_count(session_id)
    if active_pty_count >= pty_limit:
        app_metrics.record_rate_limit_rejection(request.endpoint or "start_interactive_pty_run", scope="pty_input")
        return jsonify({
            "error": (
                "Interactive PTY limit reached for this session "
                f"({active_pty_count}/{pty_limit} active). Close or kill an active PTY before starting another."
            ),
        }), 429

    try:
        run = start_pty_run(
            session_id=session_id,
            team_id=owner_scope.team_id,
            client_ip=client_ip,
            command=original_command,
            argv=argv,
            rows=data.get("rows"),
            cols=data.get("cols"),
            default_rows=pty_spec.get("default_rows"),
            default_cols=pty_spec.get("default_cols"),
            owner_client_id=_active_run_owner_value(request.headers.get("X-Client-ID", "")),
            owner_tab_id=_active_run_owner_value(data.get("tab_id", "")),
            allow_input=(
                bool(pty_spec.get("allow_input", True))
                and str(pty_spec.get("input_safety") or "") != "no_input"
            ),
            max_runtime_seconds=_coerce_positive_int(
                pty_spec.get("max_runtime_seconds"),
                _coerce_positive_int(CFG.get("interactive_pty_max_runtime_seconds", 900), 900),
            ),
            completion_callback=lambda completed_run, finished_iso, exit_code, synthesized_lines: (
                _persist_completed_pty_run(
                    completed_run,
                    execution_command,
                    finished_iso,
                    exit_code,
                    synthesized_lines,
                    transcript_mode=pty_spec.get("transcript_mode"),
                )
            ),
        )
    except PtyDependencyError as exc:
        log.error("PTY_DEPENDENCY_ERROR", extra={
            "ip": client_ip, "session": get_log_session_id(session_id), "cmd": original_command,
        })
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        log.error("PTY_SPAWN_ERROR", exc_info=True, extra={
            "ip": client_ip, "session": get_log_session_id(session_id), "cmd": original_command,
        })
        return jsonify({"error": str(exc)}), 500
    return jsonify({
        "run_id": run.run_id,
        "stream": f"/pty/runs/{run.run_id}/stream",
        "command": execution_command,
        "interactive": True,
        "rows": run.rows,
        "cols": run.cols,
    }), 202


@run_bp.route("/pty/runs/<run_id>/stream")
def stream_interactive_pty_run(run_id):
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    belongs_to_run = (
        pty_run_belongs_to_scope(run_id, session_id, owner_scope.team_id)
        if owner_scope.is_team
        else pty_run_belongs_to_session(run_id, session_id)
    )
    if not belongs_to_run:
        return jsonify({"error": "Run not found"}), 404
    after_id = request.args.get("after", "0-0") or "0-0"
    owner_client_id = _active_run_owner_value(request.headers.get("X-Client-ID", ""))
    owner_tab_id = _active_run_owner_value(request.args.get("tab_id", ""))
    can_control = _scope_has_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if owner_client_id and can_control:
        if owner_scope.is_team:
            claim_pty_stream_owner(
                run_id,
                session_id,
                owner_client_id,
                owner_tab_id,
                team_id=owner_scope.team_id,
            )
        else:
            claim_pty_stream_owner(run_id, session_id, owner_client_id, owner_tab_id)

    def generate():
        last_touch_monotonic = None
        for item in stream_pty_events(run_id, session_id, after=after_id, team_id=owner_scope.team_id):
            if owner_client_id and can_control:
                last_touch_monotonic = _maybe_touch_active_run_owner(
                    run_id,
                    owner_client_id,
                    owner_tab_id,
                    last_touch_monotonic=last_touch_monotonic,
                )
            yield item

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def _pty_snapshot_error_response(message: str):
    text = message or "PTY snapshot is not available"
    headers = {}
    if text == "Run not found":
        status = 404
    elif text in {"Run is closed", "PTY run is no longer active"}:
        status = 410
    elif "snapshot is not available" in text:
        status = 503
        headers["Retry-After"] = "1"
    else:
        status = 409
    return jsonify({"error": text}), status, headers


@run_bp.route("/pty/runs/<run_id>/snapshot")
def snapshot_interactive_pty_run(run_id):
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    if owner_scope.is_team:
        ok, message, snapshot = pty_run_snapshot(run_id, session_id, team_id=owner_scope.team_id)
    else:
        ok, message, snapshot = pty_run_snapshot(run_id, session_id)
    if not ok:
        return _pty_snapshot_error_response(message)
    return jsonify(snapshot)


@run_bp.route("/pty/runs/<run_id>/input", methods=["POST"])
@limiter.limit(_interactive_pty_input_limit)
def send_interactive_pty_input(run_id):
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = _require_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    ok, message = write_pty_input(
        run_id,
        session_id,
        data.get("data", ""),
        _active_run_owner_value(request.headers.get("X-Client-ID", "")),
        _active_run_owner_value(data.get("tab_id", "")),
        team_id=owner_scope.team_id,
    )
    if not ok:
        status = 404 if message == "Run not found" else 409 if "no longer active" in message else 400
        return jsonify({"error": message or "Input rejected"}), status
    return jsonify({"ok": True})


@run_bp.route("/pty/runs/<run_id>/resize", methods=["POST"])
@limiter.limit(_interactive_pty_resize_limit)
def resize_interactive_pty_run(run_id):
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = _require_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    ok, message, rows, cols = resize_pty(
        run_id,
        session_id,
        data.get("rows"),
        data.get("cols"),
        team_id=owner_scope.team_id,
    )
    if not ok:
        status = 404 if message == "Run not found" else 409 if "no longer active" in message else 400
        return jsonify({"error": message or "Resize rejected"}), status
    return jsonify({"ok": True, "rows": rows, "cols": cols})


@run_bp.route("/runs", methods=["POST"])
@limiter.limit(lambda: (
    f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"
))
def start_brokered_run():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    session_id = get_session_id()
    original_command = data.get("command", "")
    client_ip = get_client_ip()
    owner_client_id = _active_run_owner_value(request.headers.get("X-Client-ID", ""))
    owner_tab_id = _active_run_owner_value(data.get("tab_id", ""))
    workspace_cwd = _workspace_cwd_value(data.get("workspace_cwd", ""))
    if not isinstance(original_command, str):
        return jsonify({"error": "Command must be a string"}), 400
    original_command = original_command.strip()
    if not original_command:
        return jsonify({"error": "No command provided"}), 400
    team_id = ""
    team_role = ""
    if requested_team_id(request):
        try:
            owner_scope = current_request_scope(session_id, request)
        except RequestScopeError as exc:
            payload, status = scope_error_payload(exc)
            return jsonify(payload), status
        capability_response = _require_team_capability(owner_scope, Capability.RUN_COMMANDS)
        if capability_response:
            return capability_response
        team_id = owner_scope.team_id
        team_role = str((owner_scope.member or {}).get("role") or "")

    if not broker_available():
        return jsonify({"error": broker_unavailable_reason()}), 503

    try:
        started = _start_brokered_run_service(
            original_command=original_command,
            session_id=session_id,
            team_id=team_id,
            team_role=team_role,
            client_ip=client_ip,
            handlers=_run_start_handlers(),
            owner_client_id=owner_client_id,
            owner_tab_id=owner_tab_id,
            workspace_cwd=workspace_cwd,
            thread_name_prefix="run-broker",
        )
    except _RunPreparationError as exc:
        return _preparation_error_response(exc)
    except _RunSpawnError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"run_id": started.run_id, "stream": f"/runs/{started.run_id}/stream"}), 202


@run_bp.route("/runs/<run_id>/events")
def get_brokered_run_events(run_id):
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    visibility = _run_session_visibility(run_id, session_id, owner_scope.team_id)
    if not visibility["allowed"]:
        return _run_visibility_error_response(visibility)
    after_id = str(request.args.get("after", "0-0") or "0-0")
    try:
        limit = max(1, min(int(request.args.get("limit", 100) or 100), 500))
    except (TypeError, ValueError):
        limit = 100
    events = get_run_events(run_id, after_id=after_id, limit=limit)
    return jsonify({
        "run_id": run_id,
        "events": [event.as_payload() for event in events],
    })


@run_bp.route("/runs/<run_id>/stream")
def stream_brokered_run(run_id):
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    visibility = _run_session_visibility(run_id, session_id, owner_scope.team_id)
    if not visibility["allowed"]:
        log.warning("RUN_BROKER_STREAM_MISS", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "ip": get_client_ip(),
            "broker_mode": broker_mode(),
            "active_match": bool(visibility["active_match"]),
            "db_match": bool(visibility["db_match"]),
            "active_count": int(visibility["active_count"]),
            "after_id": str(request.args.get("after", "0-0") or "0-0"),
            "owner_client_id_present": bool(_active_run_owner_value(request.headers.get("X-Client-ID", ""))),
            "owner_tab_id_present": bool(_active_run_owner_value(request.args.get("tab_id", ""))),
            "scope_mismatch": bool(visibility.get("scope_mismatch")),
            "actual_team_id": str(visibility.get("actual_team_id", "") or ""),
        })
        return _run_visibility_error_response(visibility)
    after_id = str(request.args.get("after", "0-0") or "0-0")
    owner_client_id = _active_run_owner_value(request.headers.get("X-Client-ID", ""))
    owner_tab_id = _active_run_owner_value(request.args.get("tab_id", ""))

    def generate():
        last_touch_monotonic = None
        for item in stream_run_events(run_id, after_id=after_id):
            if owner_client_id:
                last_touch_monotonic = _maybe_touch_active_run_owner(
                    run_id,
                    owner_client_id,
                    owner_tab_id,
                    last_touch_monotonic=last_touch_monotonic,
                )
            yield item

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@run_bp.route("/kill", methods=["POST"])
def kill_command():
    data      = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    run_id    = data.get("run_id", "")
    killer_tab_id = _active_run_owner_value(data.get("tab_id", ""))
    client_ip = get_client_ip()
    if not isinstance(run_id, str):
        return jsonify({"error": "run_id must be a string"}), 400
    session_id = get_session_id()
    if session_id or requested_team_id(request):
        try:
            owner_scope = current_request_scope(session_id, request)
        except RequestScopeError as exc:
            payload, status = scope_error_payload(exc)
            return jsonify(payload), status
    else:
        owner_scope = RequestScope(OwnerContext(scope="personal", owner_id="", actor_session_id=""))
    capability_response = _require_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    kill_audit = {
        "session": get_log_session_id(session_id),
        **_team_audit_fields(owner_scope),
    }
    killer_client_id = _active_run_owner_value(request.headers.get("X-Client-ID", ""))
    active_runs = (
        active_runs_for_team(owner_scope.team_id)
        if owner_scope.is_team
        else active_runs_for_session(session_id, team_id="")
    )
    active_run = next(
        (run for run in active_runs if run.get("run_id") == run_id),
        {},
    )
    run_type = str(active_run.get("run_type", "command") or "command").lower()
    pid = pid_for_team(run_id, owner_scope.team_id) if owner_scope.is_team else pid_for_session(run_id, session_id)
    if not pid:
        log.debug("KILL_MISS", extra={
            "ip": client_ip,
            "run_id": run_id,
            **kill_audit,
        })
        return jsonify({"error": "No such process"}), 404
    killed_payload = {
        "killer_client_id": killer_client_id,
        "killer_tab_id": killer_tab_id,
    }
    pgid = pid
    try:
        # Subprocesses call os.setsid() during child setup, which makes PGID
        # == PID at creation time. Use the stored PID directly as the
        # PGID rather than calling os.getpgid() — if the subprocess has
        # already exited and its PID was reused (e.g. by a new Gunicorn
        # worker), os.getpgid() would return the wrong PGID and we would
        # accidentally send SIGTERM to a gunicorn worker process group.
        # Using the original PID as the PGID is safe: if the process group
        # no longer exists the signal fails with ESRCH instead of hitting
        # an unrelated process.
        _ensure_scanner_process_group_current(
            run_id,
            pgid,
            session_id,
            team_id=owner_scope.team_id if owner_scope.is_team else "",
        )
        _signal_process_group(pgid)
        if run_type == "pty":
            if owner_scope.is_team:
                notify_pty_killed_event(run_id, session_id, killed_payload, team_id=owner_scope.team_id)
            else:
                notify_pty_killed_event(run_id, session_id, killed_payload)
        else:
            publish_run_event(run_id, "killed", killed_payload)
        log.info("RUN_KILL", extra={
            "run_id": run_id,
            "ip": client_ip,
            **kill_audit,
            "pid": pid,
            "pgid": pgid,
        })
    except ProcessLookupError as e:
        if run_type == "pty":
            if owner_scope.is_team:
                notify_pty_killed_event(run_id, session_id, killed_payload, team_id=owner_scope.team_id)
            else:
                notify_pty_killed_event(run_id, session_id, killed_payload)
        else:
            publish_run_event(run_id, "killed", killed_payload)
        log.warning("KILL_FAILED", extra={
            "run_id": run_id,
            "ip": client_ip,
            **kill_audit,
            "pid": pid,
            "pgid": pgid,
            "error": str(e),
        })
    except (subprocess.TimeoutExpired, OSError) as e:
        log.warning("KILL_FAILED", extra={
            "run_id": run_id,
            "ip": client_ip,
            **kill_audit,
            "pid": pid,
            "pgid": pgid,
            "error": str(e),
        })
        return jsonify({"error": "Failed to signal process"}), 500
    return jsonify({"killed": True})
