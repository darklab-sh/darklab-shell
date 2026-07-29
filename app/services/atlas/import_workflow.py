# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Preview and apply Atlas imports from external report files."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import uuid
from typing import Any, BinaryIO, IO

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend, parse_database_backend
from core.helpers import get_log_session_id
from services.atlas.import_analysis import (
    analysis_counts as _analysis_counts,
    available_options as _available_options,
    current_apply_counts as _current_apply_counts,
    entity_id_for as _entity_id_for,
    entity_key as _entity_key,
    entity_occurrence_stats as _entity_occurrence_stats,
    finding_id_for as _finding_id_for,
    normalize_options as _normalize_options,
    preview_counts as _preview_counts,
    project_accessible as _project_accessible,
    project_target_exists as _project_target_exists,
    required_capabilities as _required_capabilities,
    required_capabilities_for_apply as _required_capabilities_for_apply,
    target_entity_candidates as _target_entity_candidates,
)
from services.atlas.import_helpers import (
    MAX_SOURCE_TOOL_LEN,
    apply_context_fields as _apply_context_fields,
    filename_log_fields as _filename_log_fields,
    option_log_fields as _option_log_fields,
    required_capability_values as _required_capability_values,
    row_set_digest as _row_set_digest,
    safe_count_fields as _safe_count_fields,
    safe_filename as _safe_filename,
    safe_label as _safe_label,
    safe_text as _safe_text,
    source_tool_key as _source_tool_key,
    update_apply_log_context as _update_apply_log_context,
)
from services.atlas.import_limits import (
    AtlasImportError,
    _INVALID_CFG_LIMIT_WARNED as _INVALID_CFG_LIMIT_WARNED,
    draft_ttl_minutes as _draft_ttl_minutes,
    enforce_import_limits as _enforce_import_limits,
    parser_limits as _parser_limits,
    preview_sample_limit as _preview_sample_limit,
    warning_sample_limit as _warning_sample_limit,
)
from services.atlas.import_parser import (
    ImportParseError,
    parse_import_file,
    read_import_source_bytes,
)
from services.atlas.import_sources import (
    insert_import_batch,
    insert_import_draft,
    upsert_entity_import_link,
    upsert_finding_import_occurrence,
)
from services.atlas.materializer import upsert_entity
from services.atlas.recalculation import recalculate_atlas_entities, recalculate_atlas_findings
from services.intel.canonical import entity_signature
from services.projects.findings import _finding_signature, _normalize_finding_signal_key
from services.projects.contracts import MAX_FINDING_REMEDIATION_LEN, ProjectWorkspaceQuotaExceeded
from services.projects.links import insert_project_link_with_quota
from services.projects.metadata import _finding_triage_by_id, upsert_finding_triage_details_on_conn
from services.projects.scope import normalize_team_id
from services.projects.targets import ensure_project_target_on_conn
from services.projects.utils import now as project_now
from services.teams.capabilities import Capability, role_can

log = logging.getLogger("shell")

DRAFT_TTL_MINUTES = 30
PREVIEW_SAMPLE_LIMIT = 20
WARNING_SAMPLE_LIMIT = 50
MAX_IMPORT_NAME_LEN = 120


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _utc_now()).strftime("%Y-%m-%d %H:%M:%S")


def _conn_dialect(conn):
    backend = getattr(conn, "database_backend", get_db_backend())
    return dialect_for_backend(parse_database_backend(backend))


def _decode_json_dict(conn, value: Any) -> dict[str, Any]:
    return _conn_dialect(conn).decode_json_dict(value)


def _decode_json_list(conn, value: Any) -> list[Any]:
    return _conn_dialect(conn).decode_json_list(value)


def required_capabilities_for_apply(options: dict[str, Any], preview_counts: dict[str, Any]) -> set[Capability]:
    return _required_capabilities_for_apply(options, preview_counts)


def _normalized_row_set(parse_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "format_id": parse_payload.get("format_id") or "",
        "entities": parse_payload.get("entities") if isinstance(parse_payload.get("entities"), list) else [],
        "findings": parse_payload.get("findings") if isinstance(parse_payload.get("findings"), list) else [],
        "warnings": parse_payload.get("warnings") if isinstance(parse_payload.get("warnings"), list) else [],
    }


def preview_atlas_import(
    *,
    session_id: str,
    file_content: bytes | str | BinaryIO | IO[bytes],
    filename: str = "",
    format_id: str,
    source_tool: str,
    import_name: str,
    team_id: str = "",
    actor_member_id: str = "",
    role: str = "",
) -> dict[str, Any]:
    source_tool = _safe_label(source_tool or format_id, MAX_SOURCE_TOOL_LEN)
    import_name = _safe_label(import_name or source_tool or "Atlas import", MAX_IMPORT_NAME_LEN)
    filename = _safe_filename(filename)
    limits = _parser_limits()
    source_bytes = b""
    stage = "read_source"
    try:
        source_tool_key = _source_tool_key(source_tool)
        source_bytes = read_import_source_bytes(file_content, limits)
        stage = "parse"
        parsed = parse_import_file(source_bytes, format_id=format_id, limits=limits)
        parse_payload = parsed.to_dict()
        normalized_rows = _normalized_row_set(parse_payload)
        row_digest = _row_set_digest(normalized_rows)
        draft_id = "impd_" + uuid.uuid4().hex
        created_dt = _utc_now()
        expires_dt = created_dt + timedelta(minutes=_draft_ttl_minutes())
        original_digest = hashlib.sha256(source_bytes).hexdigest()
        with get_db_connect()() as conn:
            stage = "cleanup_expired_drafts"
            cleanup_expired_import_drafts(conn=conn, now=_timestamp(created_dt))
            stage = "analyze_rows"
            analysis = _analysis_counts(conn, session_id, team_id, normalized_rows)
            counts = _preview_counts(parse_payload, analysis)
            _enforce_import_limits(
                counts,
                normalized_rows,
                stage="preview",
                draft_id=draft_id,
                format_id=str(parsed.format_id),
                team_id=team_id,
            )
            warning_limit = _warning_sample_limit()
            stage = "insert_draft"
            insert_import_draft(
                conn,
                draft_id=draft_id,
                session_id=session_id,
                team_id=team_id,
                actor_session_id=session_id,
                actor_member_id=actor_member_id,
                source_tool=source_tool,
                format_id=str(parsed.format_id),
                import_name=import_name,
                filename=filename,
                original_file_sha256=original_digest,
                normalized_rows_sha256=row_digest,
                normalized_rows=normalized_rows,
                preview_counts=counts,
                warning_summary=normalized_rows["warnings"][:warning_limit],
                created=_timestamp(created_dt),
                expires_at=_timestamp(expires_dt),
            )
            conn.commit()
        log.info(
            "ATLAS_IMPORT_PREVIEW_CREATED",
            extra={
                "session": get_log_session_id(session_id),
                "draft_id": draft_id,
                "format_id": str(parsed.format_id),
                "source_tool_key": source_tool_key,
                "team_id": team_id,
                "actor_member_id": actor_member_id,
                "actor_role": role,
                "upload_bytes": len(source_bytes),
                "expires_at": _timestamp(expires_dt),
                **_filename_log_fields(filename),
                **_safe_count_fields(counts),
            },
        )
        return {
            "ok": True,
            "draft_id": draft_id,
            "row_set_digest": row_digest,
            "expires_at": _timestamp(expires_dt),
            "counts": counts,
            "samples": {
                "entities": normalized_rows["entities"][:_preview_sample_limit()],
                "findings": normalized_rows["findings"][:_preview_sample_limit()],
            },
            "warnings": normalized_rows["warnings"][:_warning_sample_limit()],
            "apply_options": _available_options(
                role=role,
                is_team=bool(team_id),
                preview_counts=counts,
            ),
        }
    except ImportParseError as exc:
        log.warning(
            "ATLAS_IMPORT_PREVIEW_REJECTED",
            extra={
                "reason": "parser_error",
                "format_id": str(format_id or ""),
                "source_tool_key": _source_tool_key(source_tool),
                "team_id": team_id,
                "stage": stage,
                "upload_bytes": len(source_bytes),
                **_filename_log_fields(filename),
            },
        )
        raise AtlasImportError("invalid_import_file", str(exc)) from exc
    except AtlasImportError:
        raise
    except Exception:
        log.exception("ATLAS_IMPORT_PREVIEW_FAILED", extra={
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "actor_member_id": actor_member_id,
            "actor_role": role,
            "format_id": str(format_id or ""),
            "source_tool_key": _source_tool_key(source_tool),
            "stage": stage,
            "upload_bytes": len(source_bytes),
            **_filename_log_fields(filename),
        })
        raise


def cleanup_expired_import_drafts(*, conn=None, now: str | None = None) -> int:
    """Delete abandoned, unapplied import drafts whose preview window expired."""
    timestamp = now or project_now()
    if conn is None:
        with get_db_connect()() as owned_conn:
            count = cleanup_expired_import_drafts(conn=owned_conn, now=timestamp)
            owned_conn.commit()
            return count
    status_rows = conn.execute(
        "SELECT status, COUNT(*) AS count FROM atlas_import_drafts "
        "WHERE status IN ('previewed', 'applying') AND expires_at < ? GROUP BY status",
        (timestamp,),
    ).fetchall()
    status_counts = {str(row["status"] or ""): int(row["count"] or 0) for row in status_rows}
    cursor = conn.execute(
        "DELETE FROM atlas_import_drafts WHERE status IN ('previewed', 'applying') AND expires_at < ?",
        (timestamp,),
    )
    deleted = max(0, int(getattr(cursor, "rowcount", 0) or 0))
    previewed_count = int(status_counts.get("previewed") or 0)
    applying_count = int(status_counts.get("applying") or 0)
    if previewed_count > 0:
        log.info("ATLAS_IMPORT_DRAFTS_CLEANED", extra={
            "previewed_count": previewed_count,
            "applying_count": applying_count,
            "cutoff": timestamp,
        })
    if applying_count > 0:
        log.warning("ATLAS_IMPORT_APPLY_STALE_CLEANED", extra={
            "previewed_count": previewed_count,
            "applying_count": applying_count,
            "cutoff": timestamp,
        })
    return deleted


def _load_draft(conn, session_id: str, draft_id: str, *, team_id: str = ""):
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        return conn.execute(
            "SELECT * FROM atlas_import_drafts WHERE team_id = ? AND id = ?",
            (normalized_team_id, draft_id),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM atlas_import_drafts WHERE (team_id IS NULL OR team_id = '') AND session_id = ? AND id = ?",
        (str(session_id or "").strip(), draft_id),
    ).fetchone()


def _load_batch_for_draft(conn, session_id: str, draft_id: str, *, team_id: str = ""):
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        return conn.execute(
            "SELECT * FROM atlas_import_batches WHERE team_id = ? AND draft_id = ? "
            "ORDER BY applied_at DESC, id DESC LIMIT 1",
            (normalized_team_id, draft_id),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM atlas_import_batches WHERE (team_id IS NULL OR team_id = '') AND session_id = ? AND draft_id = ? "
        "ORDER BY applied_at DESC, id DESC LIMIT 1",
        (str(session_id or "").strip(), draft_id),
    ).fetchone()


def _applied_draft_response(conn, session_id: str, draft_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    batch = _load_batch_for_draft(conn, session_id, draft_id, team_id=team_id)
    if not batch:
        return None
    return {
        "ok": True,
        "batch_id": str(batch["id"] or ""),
        "counts": _decode_json_dict(conn, batch["counts_json"]),
        "format_id": str(batch["format_id"] or ""),
        "source_tool": str(batch["source_tool"] or ""),
        "already_applied": True,
    }


def _log_apply_replayed(
    result: dict[str, Any],
    *,
    session_id: str,
    team_id: str,
    actor_member_id: str,
    role: str,
    draft_id: str,
    project_id: str,
    options: dict[str, bool],
    draft_status: str,
) -> None:
    raw_counts = result.get("counts")
    counts: dict[str, Any] = raw_counts if isinstance(raw_counts, dict) else {}
    log.info("ATLAS_IMPORT_APPLY_REPLAYED", extra={
        **_apply_context_fields(
            session_id=session_id,
            team_id=team_id,
            actor_member_id=actor_member_id,
            role=role,
            draft_id=draft_id,
            batch_id=str(result.get("batch_id") or ""),
            project_id=project_id,
            options=options,
        ),
        "draft_status": draft_status,
        **_safe_count_fields(counts),
    })


def _log_apply_rejected(
    exc: AtlasImportError,
    *,
    session_id: str,
    team_id: str,
    actor_member_id: str,
    role: str,
    draft_id: str,
    batch_id: str,
    project_id: str,
    options: dict[str, bool],
    draft_status: str,
    required: set[Capability],
) -> None:
    log.warning("ATLAS_IMPORT_APPLY_REJECTED", extra={
        **_apply_context_fields(
            session_id=session_id,
            team_id=team_id,
            actor_member_id=actor_member_id,
            role=role,
            draft_id=draft_id,
            batch_id=batch_id,
            project_id=project_id,
            options=options,
        ),
        "reason": exc.code,
        "http_status": exc.status_code,
        "draft_status": draft_status,
        "required_capabilities": _required_capability_values(required),
    })


def _claim_draft_for_apply(conn, draft_id: str) -> bool:
    cursor = conn.execute(
        "UPDATE atlas_import_drafts SET status = 'applying' WHERE id = ? AND status = 'previewed'",
        (draft_id,),
    )
    return int(getattr(cursor, "rowcount", 0) or 0) == 1


def _import_finding_identity(finding: dict[str, Any]) -> tuple[str, str]:
    subject_key = str(finding.get("subject_key") or "")
    signature_hash = str(finding.get("signature_hash") or "")
    affected = finding.get("affected_entity") if isinstance(finding.get("affected_entity"), dict) else {}
    if not affected:
        return subject_key, signature_hash
    affected_kind = str(affected.get("kind") or "")
    affected_canonical_value = str(affected.get("canonical_value") or "")
    normalized_subject = entity_signature(affected_kind, affected_canonical_value)
    if not normalized_subject:
        return subject_key, signature_hash
    raw_source_detail = finding.get("source_detail")
    source_detail: dict[str, Any] = raw_source_detail if isinstance(raw_source_detail, dict) else {}
    tool_root = str(source_detail.get("adapter") or "")
    severity = _safe_label(finding.get("severity"), 32)
    signal_key = _normalize_finding_signal_key(
        "\n".join(part for part in (
            str(finding.get("title") or ""),
            str(finding.get("evidence") or ""),
        ) if part)
    )
    return normalized_subject, _finding_signature(tool_root, "finding", severity, signal_key, normalized_subject)


def _insert_or_update_finding(
    conn,
    *,
    session_id: str,
    team_id: str,
    finding: dict[str, Any],
    entity_id: str,
    observed_at: str,
) -> tuple[str, bool]:
    subject_key, signature_hash = _import_finding_identity(finding)
    existing_id = _finding_id_for(conn, session_id, team_id, {**finding, "signature_hash": signature_hash})
    title = _safe_label(finding.get("title"), 300)
    severity = _safe_label(finding.get("severity"), 32)
    raw_line = _safe_label(finding.get("evidence") or finding.get("description") or title, 2000)
    if existing_id:
        conn.execute(
            "UPDATE findings SET "
            "target_id = CASE WHEN ? != '' THEN ? ELSE target_id END, "
            "entity_id = CASE WHEN ? != '' THEN ? ELSE entity_id END, "
            "last_seen_at = CASE WHEN ? > last_seen_at THEN ? ELSE last_seen_at END, "
            "severity = CASE WHEN ? != '' THEN ? ELSE severity END, "
            "title = CASE WHEN ? != '' THEN ? ELSE title END, "
            "raw_line = CASE WHEN ? != '' THEN ? ELSE raw_line END "
            "WHERE id = ?",
            (
                entity_id,
                entity_id,
                entity_id,
                entity_id,
                observed_at,
                observed_at,
                severity,
                severity,
                title,
                title,
                raw_line,
                raw_line,
                existing_id,
            ),
        )
        return existing_id, False
    owner_id = team_id or session_id
    finding_id = "fnd_" + hashlib.sha256(f"{owner_id}\x1f{signature_hash}".encode("utf-8", errors="replace")).hexdigest()[:32]
    fingerprint = _finding_signature(
        str(finding.get("source_detail", {}).get("adapter") if isinstance(finding.get("source_detail"), dict) else ""),
        "import",
        severity,
        str(finding.get("title") or ""),
        subject_key,
    )
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, team_id, run_id, target_id, scope, line_number, review_state, "
        "entity_id, subject_key, signature_hash, severity, kind, tool_root, "
        "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
        "status_updated_at, fingerprint, title, raw_line, created) "
        "VALUES (?, ?, ?, '', ?, 'finding', ?, 'new', ?, ?, ?, ?, 'finding', ?, "
        "'', '', ?, ?, 0, 'new', '', ?, ?, ?, ?)",
        (
            finding_id,
            session_id,
            team_id,
            entity_id,
            int(finding.get("row_number") or 0),
            entity_id or None,
            subject_key,
            signature_hash,
            severity,
            str((finding.get("source_detail") or {}).get("adapter") if isinstance(finding.get("source_detail"), dict) else ""),
            observed_at,
            observed_at,
            fingerprint,
            title,
            raw_line,
            observed_at,
        ),
    )
    return finding_id, True


def _apply_atlas_import_impl(
    *,
    session_id: str,
    draft_id: str,
    row_set_digest: str,
    options: dict[str, Any],
    project_id: str = "",
    team_id: str = "",
    actor_member_id: str = "",
    role: str = "",
    log_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_options = _normalize_options(options)
    _update_apply_log_context(log_context, stage="validate_options", options=clean_options)
    if not any(clean_options.values()):
        raise AtlasImportError("no_apply_options", "At least one import apply option is required.")
    if (clean_options["link_to_project"] or clean_options["create_project_targets"]) and not project_id:
        raise AtlasImportError(
            "project_required",
            "A project id is required when linking imported records or creating targets.",
        )
    now = project_now()
    batch_id = "impb_" + uuid.uuid4().hex
    _update_apply_log_context(log_context, batch_id=batch_id)
    with get_db_connect()() as conn:
        _update_apply_log_context(log_context, stage="load_draft")
        draft = _load_draft(conn, session_id, draft_id, team_id=team_id)
        if not draft:
            raise AtlasImportError("draft_not_found", "Import draft was not found.", status_code=404)
        draft_status = str(draft["status"] or "")
        _update_apply_log_context(log_context, draft_status=draft_status)
        draft_format_id = str(draft["format_id"] or "")
        _update_apply_log_context(
            log_context,
            format_id=draft_format_id,
            source_tool_key=_source_tool_key(draft["source_tool"]),
        )
        _update_apply_log_context(log_context, stage="validate_draft")
        if draft_status not in {"previewed", "applied"}:
            raise AtlasImportError(
                "draft_apply_in_progress",
                "Import draft is already being applied.",
                status_code=409,
            )
        if draft_status == "applied":
            applied_response = _applied_draft_response(conn, session_id, draft_id, team_id=team_id)
            if applied_response:
                _log_apply_replayed(
                    applied_response,
                    session_id=session_id,
                    team_id=team_id,
                    actor_member_id=actor_member_id,
                    role=role,
                    draft_id=draft_id,
                    project_id=project_id,
                    options=clean_options,
                    draft_status=draft_status,
                )
                return applied_response
            raise AtlasImportError("draft_not_applyable", "Import draft has already been applied or expired.")
        if draft_status == "previewed" and str(draft["expires_at"] or "") < now:
            raise AtlasImportError("draft_expired", "Import draft has expired.")
        _update_apply_log_context(log_context, stage="decode_rows")
        normalized_rows = _decode_json_dict(conn, draft["normalized_rows_json"])
        stored_digest = str(draft["normalized_rows_sha256"] or "")
        if not row_set_digest or row_set_digest != stored_digest or _row_set_digest(normalized_rows) != stored_digest:
            raise AtlasImportError("digest_mismatch", "Import draft no longer matches the previewed row set.")
        preview_counts = _decode_json_dict(conn, draft["preview_counts_json"])
        # Recompute before capability checks so finding-induced entity creation
        # reflects records created or removed after preview.
        _update_apply_log_context(log_context, stage="analyze_rows")
        current_counts = _current_apply_counts(conn, session_id, team_id, normalized_rows, preview_counts)
        _update_apply_log_context(log_context, stage="enforce_limits")
        _enforce_import_limits(
            current_counts,
            normalized_rows,
            stage="apply",
            draft_id=draft_id,
            format_id=draft_format_id,
            team_id=team_id,
        )
        required = _required_capabilities(clean_options, current_counts)
        _update_apply_log_context(log_context, required=required, stage="check_capabilities")
        if team_id:
            for capability in sorted(required, key=lambda item: item.value):
                if not role_can(role, capability):
                    raise AtlasImportError(
                        "team_forbidden",
                        f"Role {role!r} lacks team capability {capability.value!r}",
                        status_code=403,
                    )
        _update_apply_log_context(log_context, stage="check_project")
        if (
            clean_options["link_to_project"] or clean_options["create_project_targets"]
        ) and not _project_accessible(conn, session_id, project_id, team_id=team_id):
            raise AtlasImportError("project_not_found", "Project was not found.", status_code=404)
        _update_apply_log_context(log_context, stage="claim_draft")
        if not _claim_draft_for_apply(conn, draft_id):
            applied_response = _applied_draft_response(conn, session_id, draft_id, team_id=team_id)
            if applied_response:
                _log_apply_replayed(
                    applied_response,
                    session_id=session_id,
                    team_id=team_id,
                    actor_member_id=actor_member_id,
                    role=role,
                    draft_id=draft_id,
                    project_id=project_id,
                    options=clean_options,
                    draft_status=draft_status,
                )
                return applied_response
            raise AtlasImportError(
                "draft_apply_in_progress",
                "Import draft is already being applied.",
                status_code=409,
            )
        _update_apply_log_context(log_context, stage="create_batch")
        insert_import_batch(
            conn,
            batch_id=batch_id,
            draft_id=draft_id,
            session_id=session_id,
            team_id=team_id,
            actor_session_id=session_id,
            actor_member_id=actor_member_id,
            source_tool=str(draft["source_tool"] or ""),
            format_id=str(draft["format_id"] or ""),
            import_name=str(draft["import_name"] or ""),
            filename=str(draft["filename"] or ""),
            original_file_sha256=str(draft["original_file_sha256"] or ""),
            normalized_rows_sha256=stored_digest,
            warning_summary=_decode_json_list(conn, draft["warning_summary_json"]),
            created=str(draft["created"] or now),
            applied_at=now,
            status="applying",
        )
        counts: dict[str, Any] = {
            "entities_created": 0,
            "entities_updated": 0,
            "findings_created": 0,
            "findings_updated": 0,
            "finding_remediations_imported": 0,
            "entity_links": 0,
            "finding_occurrences": 0,
            "project_links_added": 0,
            "project_links_existing": 0,
            "project_targets_created": 0,
            "project_targets_existing": 0,
        }
        entity_ids: set[str] = set()
        finding_ids: set[str] = set()
        entity_id_by_key: dict[tuple[str, str], str] = {}
        entity_occurrences = _entity_occurrence_stats(normalized_rows, clean_options, now)
        target_entities: dict[tuple[str, str], dict[str, Any]] = {}
        target_candidates = _target_entity_candidates(normalized_rows) if clean_options["create_project_targets"] else {}
        preexisting_target_keys = {
            key for key in target_candidates
            if _project_target_exists(conn, project_id, key)
        }

        def ensure_entity(entity: dict[str, Any]) -> str:
            entity_type, canonical_value = _entity_key(entity)
            key = (entity_type, canonical_value)
            if key in entity_id_by_key:
                return entity_id_by_key[key]
            entity_stats = entity_occurrences.get(key) or {
                "count": 1,
                "first_observed_at": str(entity.get("observed_at") or now),
                "last_observed_at": str(entity.get("observed_at") or now),
                "row_number": int(entity.get("row_number") or 0),
                "external_id": str(entity.get("external_id") or ""),
                "source_detail": entity.get("source_detail") if isinstance(entity.get("source_detail"), dict) else {},
            }
            existing_id = _entity_id_for(conn, session_id, team_id, entity)
            entity_id = upsert_entity(
                conn,
                session_id,
                entity_type,
                canonical_value,
                team_id=team_id,
                seen_at=str(entity.get("observed_at") or now),
                occurrence_count=0,
            )
            upsert_entity_import_link(
                conn,
                entity_id=entity_id,
                batch_id=batch_id,
                observed_at=str(entity_stats["first_observed_at"]),
                last_observed_at=str(entity_stats["last_observed_at"]),
                created=now,
                occurrence_count=int(entity_stats["count"]),
                row_number=int(entity_stats["row_number"]),
                external_id=str(entity_stats["external_id"]),
                source_detail=entity_stats["source_detail"] if isinstance(entity_stats["source_detail"], dict) else {},
                created_entity=not existing_id,
            )
            counts["entity_links"] += 1
            if existing_id:
                counts["entities_updated"] += 1
            else:
                counts["entities_created"] += 1
            entity_ids.add(entity_id)
            entity_id_by_key[key] = entity_id
            if entity_type in {"domain", "ip", "url"}:
                target_entities[key] = entity
            return entity_id

        if clean_options["import_entities"]:
            _update_apply_log_context(log_context, stage="write_entities")
            for entity in normalized_rows.get("entities") or []:
                if isinstance(entity, dict):
                    ensure_entity(entity)
        if clean_options["import_findings"]:
            _update_apply_log_context(log_context, stage="write_findings")
            for finding in normalized_rows.get("findings") or []:
                if not isinstance(finding, dict):
                    continue
                affected = finding.get("affected_entity")
                entity_id = ensure_entity(affected) if isinstance(affected, dict) else ""
                finding_id, created = _insert_or_update_finding(
                    conn,
                    session_id=session_id,
                    team_id=team_id,
                    finding=finding,
                    entity_id=entity_id,
                    observed_at=str(finding.get("observed_at") or now),
                )
                upsert_finding_import_occurrence(
                    conn,
                    finding_id=finding_id,
                    batch_id=batch_id,
                    row_number=int(finding.get("row_number") or 0),
                    observed_at=str(finding.get("observed_at") or now),
                    created=now,
                    snippet=_safe_label(finding.get("title"), 1000),
                    evidence=_safe_label(finding.get("evidence") or finding.get("description"), 4000),
                    external_id=str(finding.get("external_id") or ""),
                    source_detail=finding.get("source_detail") if isinstance(finding.get("source_detail"), dict) else {},
                )
                remediation = _safe_text(finding.get("remediation"), MAX_FINDING_REMEDIATION_LEN)
                if remediation:
                    existing_triage_row = _finding_triage_by_id(
                        conn,
                        session_id,
                        [finding_id],
                        team_id=team_id,
                    ).get(finding_id)
                    existing_triage = existing_triage_row if isinstance(existing_triage_row, dict) else {}
                    previous_remediation = _safe_text(
                        existing_triage.get("remediation"),
                        MAX_FINDING_REMEDIATION_LEN,
                    )
                    if previous_remediation:
                        if previous_remediation != remediation:
                            log.warning("ATLAS_IMPORT_REMEDIATION_PRESERVED_EXISTING_TRIAGE", extra={
                                "session": get_log_session_id(session_id),
                                "team_id": team_id,
                                "draft_id": draft_id,
                                "batch_id": batch_id,
                                "project_id": project_id,
                                "finding_id": finding_id,
                                "source_tool_key": _source_tool_key(draft["source_tool"]),
                                "previous_remediation_chars": len(previous_remediation),
                                "imported_remediation_chars": len(remediation),
                            })
                    else:
                        log.debug("ATLAS_IMPORT_REMEDIATION_TRIAGE_UPSERT", extra={
                            "session": get_log_session_id(session_id),
                            "team_id": team_id,
                            "draft_id": draft_id,
                            "batch_id": batch_id,
                            "finding_id": finding_id,
                            "created_finding": created,
                            "existing_triage": bool(existing_triage),
                            "remediation_chars": len(remediation),
                        })
                        upsert_finding_triage_details_on_conn(
                            conn,
                            session_id,
                            finding_id,
                            {
                                "remediation": remediation,
                                "verification_steps": existing_triage.get("verification_steps", ""),
                                "verification_status": existing_triage.get("verification_status", "not_started"),
                                "verification_notes": existing_triage.get("verification_notes", ""),
                            },
                            team_id=team_id,
                            now=now,
                        )
                        counts["finding_remediations_imported"] += 1
                counts["finding_occurrences"] += 1
                counts["findings_created" if created else "findings_updated"] += 1
                finding_ids.add(finding_id)
        try:
            if clean_options["link_to_project"]:
                _update_apply_log_context(log_context, stage="link_project")
                for entity_id in sorted(entity_ids):
                    before = conn.execute(
                        "SELECT 1 FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
                        (project_id, entity_id),
                    ).fetchone()
                    insert_project_link_with_quota(
                        conn,
                        project_id,
                        "atlas_entity",
                        entity_id,
                        "manual",
                        source_detail={"atlas_import_batch_id": batch_id},
                    )
                    counts["project_links_existing" if before else "project_links_added"] += 1
            if clean_options["create_project_targets"]:
                _update_apply_log_context(log_context, stage="create_project_targets")
                target_entities.update(target_candidates)
                for key, entity in sorted(target_entities.items()):
                    entity_type, canonical_value = key
                    entity_id = ensure_entity(entity)
                    ensure_project_target_on_conn(
                        conn,
                        session_id,
                        project_id,
                        entity_type,
                        canonical_value,
                        source="auto_input_file",
                        source_detail={"atlas_import_batch_id": batch_id, "import_name": str(draft["import_name"] or "")},
                        team_id=team_id,
                    )
                    counts[
                        "project_targets_existing" if key in preexisting_target_keys else "project_targets_created"
                    ] += 1
        except ProjectWorkspaceQuotaExceeded as exc:
            raise AtlasImportError("project_quota_exceeded", str(exc), status_code=409) from exc
        _update_apply_log_context(log_context, stage="recalculate")
        if entity_ids:
            recalculate_atlas_entities(conn, entity_ids)
        if finding_ids:
            recalculate_atlas_findings(conn, finding_ids)
        counts["required_capabilities"] = sorted(capability.value for capability in required)
        _update_apply_log_context(log_context, stage="finalize_batch")
        insert_import_batch(
            conn,
            batch_id=batch_id,
            draft_id=draft_id,
            session_id=session_id,
            team_id=team_id,
            actor_session_id=session_id,
            actor_member_id=actor_member_id,
            source_tool=str(draft["source_tool"] or ""),
            format_id=str(draft["format_id"] or ""),
            import_name=str(draft["import_name"] or ""),
            filename=str(draft["filename"] or ""),
            original_file_sha256=str(draft["original_file_sha256"] or ""),
            normalized_rows_sha256=stored_digest,
            counts=counts,
            warning_summary=_decode_json_list(conn, draft["warning_summary_json"]),
            created=str(draft["created"] or now),
            applied_at=now,
            status="applied",
        )
        conn.execute("UPDATE atlas_import_drafts SET status = 'applied' WHERE id = ?", (draft_id,))
        conn.commit()
    log.info(
        "ATLAS_IMPORT_APPLIED",
        extra={
            "session": get_log_session_id(session_id),
            "draft_id": draft_id,
            "batch_id": batch_id,
            "team_id": team_id,
            "actor_member_id": actor_member_id,
            "actor_role": role,
            "project_id": project_id,
            "format_id": draft_format_id,
            "source_tool_key": _source_tool_key(draft["source_tool"]),
            "required_capabilities": _required_capability_values(required),
            **_option_log_fields(clean_options),
            **_safe_count_fields(counts),
        },
    )
    return {
        "ok": True,
        "batch_id": batch_id,
        "counts": counts,
        "format_id": draft_format_id,
        "source_tool": str(draft["source_tool"] or ""),
    }


def apply_atlas_import(
    *,
    session_id: str,
    draft_id: str,
    row_set_digest: str,
    options: dict[str, Any],
    project_id: str = "",
    team_id: str = "",
    actor_member_id: str = "",
    role: str = "",
) -> dict[str, Any]:
    clean_options = _normalize_options(options)
    log_context: dict[str, Any] = {
        "stage": "validate_options",
        "draft_status": "",
        "batch_id": "",
        "format_id": "",
        "source_tool_key": "",
        "required": set(),
    }
    try:
        return _apply_atlas_import_impl(
            session_id=session_id,
            draft_id=draft_id,
            row_set_digest=row_set_digest,
            options=clean_options,
            project_id=project_id,
            team_id=team_id,
            actor_member_id=actor_member_id,
            role=role,
            log_context=log_context,
        )
    except AtlasImportError as exc:
        required = log_context.get("required")
        required_set = required if isinstance(required, set) else set()
        _log_apply_rejected(
            exc,
            session_id=session_id,
            team_id=team_id,
            actor_member_id=actor_member_id,
            role=role,
            draft_id=draft_id,
            batch_id=str(log_context.get("batch_id") or ""),
            project_id=project_id,
            options=clean_options,
            draft_status=str(log_context.get("draft_status") or ""),
            required=required_set,
        )
        raise
    except Exception:
        required = log_context.get("required")
        required_set = required if isinstance(required, set) else set()
        log.exception("ATLAS_IMPORT_APPLY_FAILED", extra={
            **_apply_context_fields(
                session_id=session_id,
                team_id=team_id,
                actor_member_id=actor_member_id,
                role=role,
                draft_id=draft_id,
                batch_id=str(log_context.get("batch_id") or ""),
                project_id=project_id,
                options=clean_options,
            ),
            "stage": str(log_context.get("stage") or ""),
            "draft_status": str(log_context.get("draft_status") or ""),
            "format_id": str(log_context.get("format_id") or ""),
            "source_tool_key": str(log_context.get("source_tool_key") or ""),
            "required_capabilities": _required_capability_values(required_set),
        })
        raise
