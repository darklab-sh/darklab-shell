# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalization and persistence for typed Atlas import evidence."""

from __future__ import annotations

import hashlib
from typing import Any

from core.database_backend import DatabaseBackend, dialect_for_backend, parse_database_backend

_EVIDENCE_TYPES = frozenset({
    "cyclonedx_component",
    "cyclonedx_dependency",
    "cyclonedx_vulnerability",
})


def normalized_row_set(parse_payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only list-backed parser collections in the signed preview payload."""
    return {
        "format_id": parse_payload.get("format_id") or "",
        **{
            key: parse_payload.get(key) if isinstance(parse_payload.get(key), list) else []
            for key in ("entities", "findings", "evidence", "warnings")
        },
    }


def preview_samples(rows: dict[str, Any], limit: int) -> dict[str, list[Any]]:
    """Return bounded examples for every importable record family."""
    return {key: rows[key][:limit] for key in ("entities", "findings", "evidence")}


def insert_evidence_rows(
    conn,
    rows: Any,
    *,
    batch_id: str,
    project_id: str,
    created: str,
) -> int:
    """Persist bounded parser evidence under one immutable import batch."""
    count = 0
    for raw in rows if isinstance(rows, list) else []:
        item = raw if isinstance(raw, dict) else {}
        evidence_type = _text(item.get("evidence_type"), 64)
        subject_key = _text(item.get("subject_key"), 1024)
        row_number = _integer(item.get("row_number"))
        if evidence_type not in _EVIDENCE_TYPES or not subject_key or row_number is None:
            continue
        evidence_id = _evidence_id(batch_id, evidence_type, subject_key, row_number)
        conn.execute(
            """
            INSERT INTO atlas_import_evidence
            (id, batch_id, project_id, evidence_type, subject_key, label, row_number,
             external_id, observed_at, source_detail_json, created, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                label = excluded.label,
                external_id = excluded.external_id,
                observed_at = excluded.observed_at,
                source_detail_json = excluded.source_detail_json,
                updated = excluded.updated
            """,
            (
                evidence_id,
                batch_id,
                _text(project_id, 128),
                evidence_type,
                subject_key,
                _text(item.get("label"), 512),
                row_number,
                _text(item.get("external_id"), 512),
                _text(item.get("observed_at"), 64) or created,
                _json_param(conn, item.get("source_detail"), {}),
                created,
                created,
            ),
        )
        count += 1
    return count


def _evidence_id(batch_id: str, evidence_type: str, subject_key: str, row_number: int) -> str:
    material = f"{batch_id}\x1f{evidence_type}\x1f{subject_key}\x1f{row_number}"
    return "impe_" + hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:32]


def _json_param(conn, value: Any, default: Any) -> Any:
    backend = getattr(conn, "database_backend", DatabaseBackend.SQLITE)
    dialect = dialect_for_backend(parse_database_backend(backend))
    return dialect.json_param(default if not isinstance(value, dict) else value)


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 10_000_000 else None


__all__ = ["insert_evidence_rows", "normalized_row_set", "preview_samples"]
