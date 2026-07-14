# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atlas import source persistence helpers."""

from __future__ import annotations

from typing import Any

from core.database_backend import DatabaseBackend, dialect_for_backend, parse_database_backend


def _conn_dialect(conn):
    backend = getattr(conn, "database_backend", DatabaseBackend.SQLITE)
    return dialect_for_backend(parse_database_backend(backend))


def _json_param(conn, value: Any, default: Any) -> Any:
    return _conn_dialect(conn).json_param(default if value is None else value)


def insert_import_draft(
    conn,
    *,
    draft_id: str,
    session_id: str,
    source_tool: str,
    import_name: str,
    created: str,
    expires_at: str,
    team_id: str = "",
    actor_session_id: str = "",
    actor_member_id: str = "",
    format_id: str = "",
    filename: str = "",
    original_file_sha256: str = "",
    normalized_rows_sha256: str = "",
    normalized_rows: list[Any] | dict[str, Any] | None = None,
    preview_counts: dict[str, Any] | None = None,
    warning_summary: list[Any] | dict[str, Any] | None = None,
    status: str = "previewed",
) -> None:
    conn.execute(
        """
        INSERT INTO atlas_import_drafts
        (id, session_id, team_id, actor_session_id, actor_member_id, source_tool,
         format_id, import_name, filename, original_file_sha256, normalized_rows_sha256,
         normalized_rows_json, preview_counts_json, warning_summary_json, created, expires_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            normalized_rows_sha256 = excluded.normalized_rows_sha256,
            normalized_rows_json = excluded.normalized_rows_json,
            preview_counts_json = excluded.preview_counts_json,
            warning_summary_json = excluded.warning_summary_json,
            expires_at = excluded.expires_at,
            status = excluded.status
        """,
        (
            draft_id,
            session_id,
            team_id,
            actor_session_id,
            actor_member_id,
            source_tool,
            format_id,
            import_name,
            filename,
            original_file_sha256,
            normalized_rows_sha256,
            _json_param(conn, normalized_rows, []),
            _json_param(conn, preview_counts, {}),
            _json_param(conn, warning_summary, []),
            created,
            expires_at,
            status,
        ),
    )


def insert_import_batch(
    conn,
    *,
    batch_id: str,
    session_id: str,
    source_tool: str,
    import_name: str,
    created: str,
    applied_at: str,
    team_id: str = "",
    draft_id: str = "",
    actor_session_id: str = "",
    actor_member_id: str = "",
    format_id: str = "",
    filename: str = "",
    original_file_sha256: str = "",
    normalized_rows_sha256: str = "",
    counts: dict[str, Any] | None = None,
    warning_summary: list[Any] | dict[str, Any] | None = None,
    status: str = "applied",
) -> None:
    conn.execute(
        """
        INSERT INTO atlas_import_batches
        (id, draft_id, session_id, team_id, actor_session_id, actor_member_id, source_tool,
         format_id, import_name, filename, original_file_sha256, normalized_rows_sha256,
         counts_json, warning_summary_json, created, applied_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            counts_json = excluded.counts_json,
            warning_summary_json = excluded.warning_summary_json,
            applied_at = excluded.applied_at,
            status = excluded.status
        """,
        (
            batch_id,
            draft_id,
            session_id,
            team_id,
            actor_session_id,
            actor_member_id,
            source_tool,
            format_id,
            import_name,
            filename,
            original_file_sha256,
            normalized_rows_sha256,
            _json_param(conn, counts, {}),
            _json_param(conn, warning_summary, []),
            created,
            applied_at,
            status,
        ),
    )


def upsert_entity_import_link(
    conn,
    *,
    entity_id: str,
    batch_id: str,
    observed_at: str,
    last_observed_at: str | None = None,
    created: str,
    occurrence_count: int = 1,
    row_number: int = 0,
    external_id: str = "",
    source_detail: dict[str, Any] | None = None,
    created_entity: bool = False,
) -> None:
    conn.execute(
        """
        INSERT INTO atlas_entity_import_links
        (entity_id, batch_id, first_observed_at, last_observed_at, occurrence_count,
         row_number, external_id, source_detail_json, created_entity, created, updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_id, batch_id) DO UPDATE SET
            first_observed_at = CASE
                WHEN excluded.first_observed_at < atlas_entity_import_links.first_observed_at
                THEN excluded.first_observed_at
                ELSE atlas_entity_import_links.first_observed_at
            END,
            last_observed_at = CASE
                WHEN excluded.last_observed_at > atlas_entity_import_links.last_observed_at
                THEN excluded.last_observed_at
                ELSE atlas_entity_import_links.last_observed_at
            END,
            occurrence_count = CASE
                WHEN excluded.occurrence_count > atlas_entity_import_links.occurrence_count
                THEN excluded.occurrence_count
                ELSE atlas_entity_import_links.occurrence_count
            END,
            updated = excluded.updated
        """,
        (
            entity_id,
            batch_id,
            observed_at,
            last_observed_at or observed_at,
            max(0, int(occurrence_count or 0)),
            max(0, int(row_number or 0)),
            external_id,
            _json_param(conn, source_detail, {}),
            created_entity,
            created,
            created,
        ),
    )


def upsert_finding_import_occurrence(
    conn,
    *,
    finding_id: str,
    batch_id: str,
    row_number: int,
    observed_at: str,
    created: str,
    snippet: str = "",
    evidence: str = "",
    external_id: str = "",
    source_detail: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO atlas_finding_import_occurrences
        (finding_id, batch_id, row_number, snippet, evidence, observed_at, external_id,
         source_detail_json, created, updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(finding_id, batch_id, row_number) DO UPDATE SET
            snippet = excluded.snippet,
            evidence = excluded.evidence,
            observed_at = excluded.observed_at,
            external_id = excluded.external_id,
            source_detail_json = excluded.source_detail_json,
            updated = excluded.updated
        """,
        (
            finding_id,
            batch_id,
            max(0, int(row_number or 0)),
            snippet,
            evidence,
            observed_at,
            external_id,
            _json_param(conn, source_detail, {}),
            created,
            created,
        ),
    )
