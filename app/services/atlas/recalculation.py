# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared Atlas aggregate recalculation helpers."""

from __future__ import annotations

from collections.abc import Iterable


def _unique_ids(values: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return result


def recalculate_atlas_entities(conn, entity_ids: Iterable[str] | None) -> None:
    for entity_id in _unique_ids(entity_ids):
        row = conn.execute(
            "SELECT COALESCE(SUM(occurrence_count), 0) AS occurrence_count, "
            "MIN(first_seen_at) AS first_seen_at, MAX(last_seen_at) AS last_seen_at "
            "FROM ("
            "  SELECT occurrence_count, first_seen_at, last_seen_at "
            "  FROM entity_run_links WHERE entity_id = ? "
            "  UNION ALL "
            "  SELECT occurrence_count, first_observed_at AS first_seen_at, last_observed_at AS last_seen_at "
            "  FROM atlas_entity_import_links WHERE entity_id = ?"
            ") entity_sources",
            (entity_id, entity_id),
        ).fetchone()
        occurrence_count = int(row["occurrence_count"] or 0) if row else 0
        if occurrence_count <= 0:
            conn.execute("UPDATE entities SET occurrence_count = 0 WHERE id = ?", (entity_id,))
            continue
        conn.execute(
            "UPDATE entities SET occurrence_count = ?, first_seen_at = ?, last_seen_at = ? WHERE id = ?",
            (occurrence_count, row["first_seen_at"] or "", row["last_seen_at"] or "", entity_id),
        )


def recalculate_atlas_findings(conn, finding_ids: Iterable[str] | None) -> None:
    for finding_id in _unique_ids(finding_ids):
        row = conn.execute(
            "SELECT COUNT(*) AS occurrence_count, MIN(seen_at) AS first_seen_at, MAX(seen_at) AS last_seen_at "
            "FROM ("
            "  SELECT seen_at FROM findings_occurrences WHERE finding_id = ? "
            "  UNION ALL "
            "  SELECT observed_at AS seen_at FROM atlas_finding_import_occurrences WHERE finding_id = ?"
            "  UNION ALL "
            "  SELECT observed_at AS seen_at FROM finding_version_inference_sources WHERE finding_id = ?"
            ") finding_sources",
            (finding_id, finding_id, finding_id),
        ).fetchone()
        occurrence_count = int(row["occurrence_count"] or 0) if row else 0
        if occurrence_count <= 0:
            conn.execute(
                "UPDATE findings SET occurrence_count = 0, run_id = '', first_run_id = '', last_run_id = '', "
                "first_seen_at = '', last_seen_at = '', line_number = NULL WHERE id = ?",
                (finding_id,),
            )
            continue
        first_run = conn.execute(
            "SELECT run_id, line_number FROM ("
            "  SELECT run_id, line_number, seen_at FROM findings_occurrences WHERE finding_id = ? "
            "  UNION ALL "
            "  SELECT '' AS run_id, row_number AS line_number, observed_at AS seen_at "
            "  FROM atlas_finding_import_occurrences WHERE finding_id = ?"
            "  UNION ALL "
            "  SELECT CASE WHEN source_kind = 'run' THEN source_id ELSE '' END AS run_id, "
            "  -1 AS line_number, observed_at AS seen_at "
            "  FROM finding_version_inference_sources WHERE finding_id = ?"
            ") finding_sources ORDER BY seen_at ASC, run_id ASC LIMIT 1",
            (finding_id, finding_id, finding_id),
        ).fetchone()
        last_run = conn.execute(
            "SELECT run_id FROM ("
            "  SELECT run_id, seen_at FROM findings_occurrences WHERE finding_id = ? "
            "  UNION ALL "
            "  SELECT '' AS run_id, observed_at AS seen_at "
            "  FROM atlas_finding_import_occurrences WHERE finding_id = ?"
            "  UNION ALL "
            "  SELECT CASE WHEN source_kind = 'run' THEN source_id ELSE '' END AS run_id, "
            "  observed_at AS seen_at FROM finding_version_inference_sources WHERE finding_id = ?"
            ") finding_sources ORDER BY seen_at DESC, run_id DESC LIMIT 1",
            (finding_id, finding_id, finding_id),
        ).fetchone()
        first_run_id = str(first_run["run_id"] or "") if first_run else ""
        last_run_id = str(last_run["run_id"] or "") if last_run else ""
        line_number = first_run["line_number"] if first_run else None
        conn.execute(
            "UPDATE findings SET occurrence_count = ?, run_id = ?, first_run_id = ?, last_run_id = ?, "
            "first_seen_at = ?, last_seen_at = ?, line_number = ? WHERE id = ?",
            (
                occurrence_count,
                first_run_id,
                first_run_id,
                last_run_id,
                row["first_seen_at"] or "",
                row["last_seen_at"] or "",
                line_number,
                finding_id,
            ),
        )
