# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Completed-run finalization and output indexing helpers."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import logging
from typing import Any, Callable

import config as app_config
from core.helpers import get_log_session_id
from core.output_signals import OutputSignalClassifier
from core.redaction import REDACTED_ENTITY_SENTINEL, line_entries_from_events, redact_line_entries
from services.atlas.materializer import materialize_run_entities
from services.assessments.coverage import reconcile_run_evidence_on_conn
from services.assessments.nmap_inference_materialization import materialize_nmap_xml_version_inferences
from services.assessments.nmap_service_evidence_persistence import (
    persist_nmap_xml_service_observations,
)
from services.commands.registry import command_project_target_inputs
from services.metrics_lazy import app_metrics
from services.notifications.hooks import enqueue_run_complete
from services.projects.auto_promote import apply_run_rules_on_conn as apply_auto_promote_rules_for_run
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.findings import record_run_findings
from services.projects.links import (
    link_active_project_run_entities,
    link_run_to_active_project,
    link_run_to_project_on_conn,
)
from services.projects.targets import record_project_target_discoveries
from services.pty.transcript import shape_completed_pty_entries
from services.runs.kinds import RUN_KIND_EXTERNAL, run_kind_for_cmd_type
from services.runs.completion_policy_contracts import RunCompletionPolicy
from services.runs.finalization_artifacts import save_run_file_artifacts_for_finalize
from services.runs.finalization_assessments import reconcile_assessment_evidence_for_finalize
from services.runs.finalization_dalfox_xss import materialize_dalfox_xss_findings_for_finalize
from services.runs.finalization_nmap_evidence import materialize_nmap_evidence_for_finalize
from services.runs.finalization_schemathesis import persist_schemathesis_evidence_for_finalize
from services.runs.finalization_version_inference import (
    materialize_run_entities_for_finalize,
)
from services.runs.finalization_takeover import materialize_takeover_confirmation_for_finalize
from services.runs.finalization_summaries import (
    AUTO_PROMOTE_RUN_LOG_RESULT_LIMIT,
    auto_promote_summary_ids,
    auto_promote_summary_log_results,
    auto_promote_summary_results,
)
from services.runs.output_model import (
    LineEvent,
    LineRole,
    event_search_text,
    from_wire,
    is_noise_event,
    legacy_cls_for_event,
    line_event_from_legacy,
)
from services.runs.output_store import RunOutputCapture, load_full_output_entries, unknown_line_event_collector
from services.workflows.hooks import finalize_workflow_run_safely
from services.runs.persistence import (
    insert_run_row,
    run_finalize_savepoint,
    run_persistence_transaction,
    scan_target_observation_count,
    upsert_run_output_artifact,
)
from services.runs.structured_summary import replace_run_output_summary
from services.runs.workspace_artifacts import workspace_artifacts_with_sizes
from services.storage.body_store import inline_threshold_bytes, maybe_store_text_body
from services.teams.scope import owner_context_for_scope
from services.workspace.files import read_owner_workspace_text_file

log = logging.getLogger("shell")
SEARCH_ENTITY_MAX_BYTES = 4096


@dataclass
class CompletedRunOutputState:
    preview_lines: list
    persisted_entries: list
    stored_search_text: str


@dataclass
class RunFinalizeRecords:
    active_project_link: dict | None = None
    recorded_artifacts: list = field(default_factory=list)
    recorded_entities: list = field(default_factory=list)
    recorded_findings: list = field(default_factory=list)
    recorded_targets: list = field(default_factory=list)
    scan_observation_count: int = 0
    nmap_service_summary: dict | None = None
    version_inference_summary: dict | None = None
    auto_promote_summary: dict | None = None
    schemathesis_summary: dict | None = None


def run_output_capture(run_id: str, cfg: Mapping[str, Any] | None = None) -> RunOutputCapture:
    active_cfg = app_config.CFG if cfg is None else cfg
    return RunOutputCapture(
        run_id=run_id,
        preview_limit=active_cfg["max_output_lines"],
        persist_full_output=active_cfg.get("persist_full_run_output", False),
        full_output_max_bytes=active_cfg.get("full_output_max_bytes", 0),
        preview_max_bytes=active_cfg.get("output_preview_max_bytes", 0),
    )


def normalize_client_side_run_lines(
    lines,
    command: str,
    *,
    cfg: Mapping[str, Any] | None = None,
    capture_event_with_signals_fn: Callable | None = None,
    output_signal_classifier_cls: Callable = OutputSignalClassifier,
    get_share_redaction_rules_fn: Callable = app_config.get_share_redaction_rules,
):
    active_cfg = app_config.CFG if cfg is None else cfg
    capture_with_signals = capture_event_with_signals if capture_event_with_signals_fn is None else capture_event_with_signals_fn
    if not isinstance(lines, list):
        return [], False, 0
    signal_classifier = output_signal_classifier_cls(
        command,
        cmd_type="builtin",
        extra_domain_suffixes=active_cfg.get("output_entity_extra_domain_suffixes", []),
    )
    capture = RunOutputCapture(
        run_id="client-side-run-preview",
        preview_limit=active_cfg["max_output_lines"],
        persist_full_output=False,
        full_output_max_bytes=0,
        preview_max_bytes=active_cfg.get("output_preview_max_bytes", 0),
    )
    for item in lines:
        if isinstance(item, dict):
            text = str(item.get("text", ""))
            legacy_class = str(item.get("cls", ""))
        else:
            text = str(item)
            legacy_class = ""
        capture_with_signals(capture, signal_classifier, text, cls=legacy_class)
    redaction_rules = get_share_redaction_rules_fn(active_cfg)
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


def capture_event_with_signals(
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
    source_detail = (
        dict(metadata.get("source_detail"))
        if isinstance(metadata.get("source_detail"), dict)
        else {}
    )
    for key in ("screenshots", "historical_urls", "version_observations", "takeover_observations"):
        if isinstance(metadata.get(key), list):
            source_detail[key] = metadata[key]
    captured_event = replace(
        base_event,
        signals=metadata_event.signals,
        role=metadata_event.role if metadata_event.role != LineRole.body else base_event.role,
        line_index=metadata.get("line_index") if isinstance(metadata.get("line_index"), int) else None,
        command_root=str(metadata.get("command_root", "")),
        target=str(metadata.get("target", "")),
        entities=metadata_event.entities,
        source_detail=source_detail,
    )
    capture.add_event(captured_event)
    return metadata, captured_event


def line_events_from_output_entries(entries) -> list[LineEvent]:
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


def bounded_entity_search_values(values: Sequence[str], max_bytes: int = SEARCH_ENTITY_MAX_BYTES) -> list[str]:
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


def search_text_from_events(events: Sequence[LineEvent]) -> str:
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
    lines.extend(bounded_entity_search_values(sorted_values))
    return "\n".join(lines)


def extract_output_search_text(preview_lines):
    return search_text_from_events(line_events_from_output_entries(preview_lines))


def structured_output_summary_fields(entries):
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


def _link_active_project_run_entities_for_finalize(
    conn,
    session_id,
    project_id,
    run_id,
    *,
    team_id="",
    link_active_project_run_entities_fn: Callable = link_active_project_run_entities,
):
    return run_finalize_savepoint(
        conn,
        "active_project_entity_link",
        lambda: link_active_project_run_entities_fn(
            conn,
            session_id,
            project_id,
            run_id,
            team_id=team_id,
        ),
    )


def _entity_type_counts_for_log(recorded_entities: Sequence[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in recorded_entities:
        if not isinstance(entity, dict):
            continue
        entity_type = str(entity.get("type") or "")
        if entity_type:
            counts[entity_type] = counts.get(entity_type, 0) + 1
    return counts


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


def log_atlas_entities_captured(
    session_id: str,
    team_id: str,
    run_id: str,
    recorded_entities: Sequence[object],
    scan_observation_count: int,
) -> None:
    _log_atlas_entities_captured(session_id, team_id, run_id, recorded_entities, scan_observation_count)


def completed_run_output_state(
    run_id,
    session_id,
    capture,
    *,
    cfg: Mapping[str, Any] | None = None,
    load_full_output_entries_fn: Callable = load_full_output_entries,
) -> CompletedRunOutputState:
    active_cfg = app_config.CFG if cfg is None else cfg
    preview_lines = list(capture.preview_lines)
    persisted_entries = preview_lines
    if capture.full_output_available and capture.artifact_rel_path:
        try:
            full_entries = load_full_output_entries_fn(capture.artifact_rel_path)
            search_text = extract_output_search_text(full_entries)
            persisted_entries = full_entries
        except Exception as exc:
            log.warning("RUN_FULL_OUTPUT_INDEX_FALLBACK", extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "rel_path": capture.artifact_rel_path,
                "error": str(exc),
            })
            search_text = extract_output_search_text(preview_lines)
    else:
        search_text = extract_output_search_text(preview_lines)
    stored_search_text = maybe_store_text_body(
        "run_search",
        run_id,
        search_text,
        inline_threshold_bytes(active_cfg.get("runs_search_text_inline_max_bytes")),
    )
    return CompletedRunOutputState(
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
            return run_finalize_savepoint(
                conn,
                "project_link",
                lambda: link_run_to_project_on_conn(conn, session_id, link_project_id, run_id, source="manual", team_id=team_id),
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
            return run_finalize_savepoint(
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


def _discover_project_targets_for_finalize(
    conn,
    session_id,
    run_id,
    command,
    active_project_link,
    *,
    cfg: Mapping[str, Any] | None = None,
    command_project_target_inputs_fn: Callable = command_project_target_inputs,
    record_project_target_discoveries_fn: Callable = record_project_target_discoveries,
) -> list:
    if not active_project_link:
        return []
    try:
        return run_finalize_savepoint(
            conn,
            "project_target_discovery",
            lambda: record_project_target_discoveries_fn(
                conn,
                session_id,
                active_project_link["project_id"],
                run_id,
                command_project_target_inputs_fn(command, cfg=app_config.CFG if cfg is None else cfg),
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
            "team_id": str(active_project_link.get("team_id") or ""),
            "project_id": str(active_project_link.get("project_id") or ""),
            "cmd": command,
            "target_discovery_skipped_reason": str(active_project_link.get("target_discovery_skipped_reason") or ""),
        })
    return []


def _record_run_findings_for_finalize(
    conn,
    session_id,
    team_id,
    run_id,
    command,
    persisted_entries,
    *,
    record_run_findings_fn: Callable = record_run_findings,
) -> list:
    try:
        return run_finalize_savepoint(
            conn,
            "run_findings",
            lambda: record_run_findings_fn(conn, session_id, run_id, persisted_entries, team_id=team_id),
        )
    except Exception:
        app_metrics.record_run_finalize_error("db_write")
        log.error("PROJECT_RUN_FINDING_CAPTURE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "cmd": command,
        })
    return []


def _apply_auto_promote_for_finalize(
    conn,
    session_id,
    team_id,
    run_id,
    command,
    recorded_entities,
    *,
    apply_auto_promote_rules_for_run_fn: Callable = apply_auto_promote_rules_for_run,
) -> dict | None:
    if not recorded_entities:
        return None
    try:
        return run_finalize_savepoint(
            conn,
            "project_auto_promote_rules",
            lambda: apply_auto_promote_rules_for_run_fn(conn, session_id, run_id, team_id=team_id),
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
    *,
    link_active_project_run_entities_fn: Callable = link_active_project_run_entities,
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
            link_active_project_run_entities_fn=link_active_project_run_entities_fn,
        )
        if linked_entities:
            active_project_link["linked_entity_count"] = int(linked_entities.get("added") or 0)
            active_project_link["available_entity_count"] = int(linked_entities.get("available") or 0)
            active_project_link["rejected_entity_count"] = int(linked_entities.get("rejected") or 0)
    except Exception:
        log.error("PROJECT_ACTIVE_RUN_ENTITY_LINK_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": str(active_project_link.get("project_id") or ""),
            "entity_count": len(recorded_entities),
            "cmd": command,
        })


def log_run_finalize_records(run_id, session_id, team_id, run_kind, records: RunFinalizeRecords) -> tuple[list[dict], list[str]]:
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
    _log_atlas_entities_captured(session_id, team_id, run_id, records.recorded_entities, records.scan_observation_count)
    auto_promote_results = auto_promote_summary_results(records.auto_promote_summary)
    auto_promote_project_ids = auto_promote_summary_ids(auto_promote_results, "project_id")
    auto_promote_rule_ids = auto_promote_summary_ids(auto_promote_results, "rule_id")
    if records.auto_promote_summary and int(records.auto_promote_summary.get("rules_evaluated") or 0):
        log.info("PROJECT_AUTO_PROMOTE_RUN_APPLIED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_ids": auto_promote_project_ids,
            "rule_ids": auto_promote_rule_ids,
            "rule_results": auto_promote_summary_log_results(auto_promote_results),
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


def update_run_finalize_summary(
    finalize_summary,
    records: RunFinalizeRecords,
    persisted_entries,
    auto_promote_project_ids: list[str],
) -> None:
    if not isinstance(finalize_summary, dict):
        return
    finalize_summary.update({
        "persisted": True,
        "artifact_count": len(records.recorded_artifacts),
        "finding_count": len(records.recorded_findings),
        "atlas_entity_count": len(records.recorded_entities),
        "version_inference_count": int(
            (records.version_inference_summary or {}).get("materialized_count") or 0
        ),
        "nmap_service_observation_count": int(
            (records.nmap_service_summary or {}).get("observation_count") or 0
        ),
        "project_target_count": len(records.recorded_targets),
        "project_auto_promote_count": int(records.auto_promote_summary.get("linked_count") or 0)
        if isinstance(records.auto_promote_summary, dict) else 0,
        "project_auto_promote_promoted_count": int(records.auto_promote_summary.get("promoted_count") or 0)
        if isinstance(records.auto_promote_summary, dict) else 0,
        "project_auto_promote_project_ids": auto_promote_project_ids,
        "schemathesis_operation_count": int(
            (records.schemathesis_summary or {}).get("operation_count") or 0
        ),
        "schemathesis_failure_count": int(
            (records.schemathesis_summary or {}).get("failure_count") or 0
        ),
        **structured_output_summary_fields(persisted_entries),
    })


def save_completed_run(
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
    completion_policy: RunCompletionPolicy | None = None,
    cfg: Mapping[str, Any] | None = None,
    load_full_output_entries_fn: Callable = load_full_output_entries,
    workspace_artifacts_with_sizes_fn: Callable = workspace_artifacts_with_sizes,
    record_run_findings_fn: Callable = record_run_findings,
    materialize_run_entities_fn: Callable = materialize_run_entities,
    read_owner_workspace_text_file_fn: Callable = read_owner_workspace_text_file,
    persist_nmap_xml_service_observations_fn: Callable = persist_nmap_xml_service_observations,
    materialize_nmap_xml_version_inferences_fn: Callable = materialize_nmap_xml_version_inferences,
    run_persistence_transaction_fn: Callable = run_persistence_transaction,
    apply_auto_promote_rules_for_run_fn: Callable = apply_auto_promote_rules_for_run,
    command_project_target_inputs_fn: Callable = command_project_target_inputs,
    record_project_target_discoveries_fn: Callable = record_project_target_discoveries,
    link_active_project_run_entities_fn: Callable = link_active_project_run_entities,
    reconcile_assessment_evidence_fn: Callable = reconcile_run_evidence_on_conn,
):
    capture.finalize()
    try:
        output_state = completed_run_output_state(
            run_id,
            session_id,
            capture,
            cfg=cfg,
            load_full_output_entries_fn=load_full_output_entries_fn,
        )
        records = RunFinalizeRecords()
        workspace_owner = owner_context_for_scope(session_id, team_id=team_id)

        def _persist_completed(conn):
            insert_run_row(
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
                upsert_run_output_artifact(
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
            records.recorded_artifacts = save_run_file_artifacts_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                workspace_artifacts,
                workspace_owner,
                persisted_entries=output_state.persisted_entries,
                exit_code=exit_code,
                cfg=cfg,
                workspace_artifacts_with_sizes_fn=workspace_artifacts_with_sizes_fn,
            )
            records.recorded_findings = _record_run_findings_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                output_state.persisted_entries,
                record_run_findings_fn=record_run_findings_fn,
            )
            records.recorded_entities = materialize_run_entities_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                output_state.persisted_entries,
                finished_iso,
                materialize_run_entities_fn=materialize_run_entities_fn,
            )
            (
                records.nmap_service_summary,
                records.version_inference_summary,
            ) = materialize_nmap_evidence_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                exit_code,
                finished_iso,
                workspace_artifacts,
                workspace_owner,
                cfg=cfg,
                read_owner_workspace_text_file_fn=read_owner_workspace_text_file_fn,
                persist_nmap_xml_service_observations_fn=persist_nmap_xml_service_observations_fn,
                materialize_nmap_xml_version_inferences_fn=materialize_nmap_xml_version_inferences_fn,
            )
            records.recorded_targets = _discover_project_targets_for_finalize(
                conn,
                session_id,
                run_id,
                command,
                records.active_project_link,
                cfg=cfg,
                command_project_target_inputs_fn=command_project_target_inputs_fn,
                record_project_target_discoveries_fn=record_project_target_discoveries_fn,
            )
            records.scan_observation_count = scan_target_observation_count(conn, run_id)
            records.auto_promote_summary = _apply_auto_promote_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                records.recorded_entities,
                apply_auto_promote_rules_for_run_fn=apply_auto_promote_rules_for_run_fn,
            )
            _link_active_project_entities_for_finalize(
                conn,
                session_id,
                team_id,
                run_id,
                command,
                records.active_project_link,
                records.recorded_entities,
                link_active_project_run_entities_fn=link_active_project_run_entities_fn,
            )
            records.schemathesis_summary = persist_schemathesis_evidence_for_finalize(
                conn, session_id, team_id, run_id, finished_iso,
                records.active_project_link, records.recorded_findings, completion_policy,
            )
            materialize_dalfox_xss_findings_for_finalize(
                conn, session_id, team_id, run_id, command, exit_code,
                output_state.persisted_entries, records.active_project_link,
                records.recorded_findings,
            )
            materialize_takeover_confirmation_for_finalize(
                conn, session_id, team_id, run_id, command, exit_code,
                output_state.persisted_entries, records.active_project_link,
                records.recorded_findings,
            )
            reconcile_assessment_evidence_for_finalize(
                conn,
                run_id,
                session_id,
                team_id,
                records.active_project_link, records.auto_promote_summary,
                reconcile_run_evidence_fn=reconcile_assessment_evidence_fn,
            )

        run_persistence_transaction_fn(_persist_completed)
        _auto_promote_results, auto_promote_project_ids = log_run_finalize_records(run_id, session_id, team_id, run_kind, records)
        update_run_finalize_summary(finalize_summary, records, output_state.persisted_entries, auto_promote_project_ids)
        return records.active_project_link
    except Exception:
        app_metrics.record_run_finalize_error("db_write")
        log.error("RUN_SAVED_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "cmd": command,
        })
    return None


def finalize_completed_run(
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
    link_project_id: str | None = "",
    completion_policy: RunCompletionPolicy | None = None,
    cfg: Mapping[str, Any] | None = None,
    save_completed_run_fn: Callable = save_completed_run,
):
    active_cfg = app_config.CFG if cfg is None else cfg
    finished = datetime.now(timezone.utc)
    elapsed = round((finished - datetime.fromisoformat(run_started)).total_seconds(), 1)
    finalize_summary = {}
    save_kwargs = {
        "workspace_artifacts": workspace_artifacts,
        "link_active_project": cmd_type == "real" and link_project_id is not None,
        "link_project_id": link_project_id or "",
        "run_kind": run_kind_for_cmd_type(cmd_type),
        "owner_tab_id": owner_tab_id,
        "finalize_summary": finalize_summary,
        "cfg": active_cfg,
    }
    if completion_policy is not None:
        save_kwargs["completion_policy"] = completion_policy
    active_project_link = save_completed_run_fn(
        run_id, session_id, team_id, original_command, run_started,
        finished.isoformat(), exit_code, capture, **save_kwargs,
    )
    persisted = bool(finalize_summary.get("persisted"))
    finalize_status = "ok" if persisted else "degraded"
    finalize_error_count = 0 if persisted else 1
    if not persisted:
        log.warning("RUN_FINALIZE_DEGRADED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "cmd": original_command,
            "finalize_stage": "save_completed_run",
        })
    log.info("RUN_END", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "exit_code": exit_code, "elapsed": elapsed, "cmd": original_command,
        "cmd_type": cmd_type,
        "finalize_status": finalize_status,
        "persisted": persisted,
        "finalize_error_count": finalize_error_count,
        "output_line_count": int(capture.output_line_count or 0),
        "full_output_truncated": bool(capture.full_output_truncated),
        "full_output_available": bool(capture.full_output_available),
        "artifact_count": int(finalize_summary.get("artifact_count") or len(workspace_artifacts or [])),
        "finding_count": int(finalize_summary.get("finding_count") or 0),
        "atlas_entity_count": int(finalize_summary.get("atlas_entity_count") or 0),
        "version_inference_count": int(finalize_summary.get("version_inference_count") or 0),
        "nmap_service_observation_count": int(
            finalize_summary.get("nmap_service_observation_count") or 0
        ),
        "project_target_count": int(finalize_summary.get("project_target_count") or 0),
    })
    app_metrics.record_completed_run(original_command, run_kind_for_cmd_type(cmd_type), exit_code, elapsed, capture)
    enqueue_run_complete(
        run_id=run_id,
        session_id=session_id,
        command=original_command,
        exit_code=exit_code,
        run_kind=run_kind_for_cmd_type(cmd_type),
        team_id=team_id,
        finalize_summary=finalize_summary,
        cfg=active_cfg,
    )
    try:
        from services.watchers.finalize import finalize_watcher_run  # noqa: PLC0415

        finalize_watcher_run(run_id)
    except Exception:
        log.error("WATCHER_FINALIZE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
        })
    finalize_workflow_run_safely(persisted, run_id, session_id, exit_code, capture)
    return {"elapsed": elapsed, "active_project_link": active_project_link, "finalize_summary": finalize_summary}


def persist_completed_pty_run(
    run,
    execution_command: str,
    finished_iso: str,
    exit_code: int,
    synthesized_lines,
    *,
    transcript_mode: object = "final_frame",
    owner_tab_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    capture_factory: Callable = run_output_capture,
    capture_event_with_signals_fn: Callable = capture_event_with_signals,
    save_completed_run_fn: Callable = save_completed_run,
):
    active_cfg = app_config.CFG if cfg is None else cfg
    capture = capture_factory(run.run_id)
    signal_classifier = OutputSignalClassifier(
        execution_command,
        cmd_type="real",
        extra_domain_suffixes=active_cfg.get("output_entity_extra_domain_suffixes", []),
        source_run_id=str(run.run_id),
    )
    for item in shape_completed_pty_entries(synthesized_lines, transcript_mode):
        text = str(item.get("text", ""))
        cls = str(item.get("cls", ""))
        if cls == "pty-marker":
            capture.add_event(line_event_from_legacy(text, cls))
            continue
        capture_event_with_signals_fn(capture, signal_classifier, text, cls=cls)
    save_completed_run_fn(
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
        elapsed = (datetime.fromisoformat(finished_iso) - datetime.fromisoformat(str(run.started))).total_seconds()
    except (TypeError, ValueError):
        elapsed = 0.0
    app_metrics.record_completed_run(run.command, RUN_KIND_EXTERNAL, exit_code, elapsed, capture)
    app_metrics.record_completed_pty(run.command, exit_code, elapsed)
    return {
        "preview_truncated": capture.preview_truncated,
        "output_line_count": capture.output_line_count,
        "full_output_available": capture.full_output_available,
    }
