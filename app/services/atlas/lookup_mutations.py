# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atlas entity and finding mutation helpers used by route handlers."""

from __future__ import annotations

from typing import Any

from services.projects.finding_dispositions import (
    set_remediation_group_review_state as update_finding_review_states,  # noqa: F401
)
from services.teams.ownership_queries import personal_only_owner_predicate
from services.teams.scope import personal_owner_context


def run_belongs_to_session(conn: Any, session_id: str, run_id: str) -> bool:
    owner = personal_only_owner_predicate(personal_owner_context(session_id))
    row = conn.execute(
        f"SELECT id FROM runs WHERE id = ? AND {owner.sql}",  # nosec
        (run_id, *owner.params),
    ).fetchone()
    return row is not None


def entity_ids_in_session(conn: Any, session_id: str, entity_ids: list[str]) -> set[str]:
    if not entity_ids:
        return set()
    placeholders = ",".join("?" for _ in entity_ids)
    owner = personal_only_owner_predicate(personal_owner_context(session_id))
    rows = conn.execute(
        f"SELECT id FROM entities WHERE {owner.sql} "  # nosec
        f"AND id IN ({placeholders})",
        [*owner.params, *entity_ids],
    ).fetchall()
    return {str(row["id"] or "") for row in rows}


def finding_ids_in_session(conn: Any, session_id: str, finding_ids: list[str]) -> set[str]:
    if not finding_ids:
        return set()
    placeholders = ",".join("?" for _ in finding_ids)
    owner = personal_only_owner_predicate(personal_owner_context(session_id))
    rows = conn.execute(
        f"SELECT id FROM findings WHERE {owner.sql} "  # nosec
        f"AND id IN ({placeholders})",
        [*owner.params, *finding_ids],
    ).fetchall()
    return {str(row["id"] or "") for row in rows}


def update_entity_suppression(
    conn: Any,
    entity_id: str,
    *,
    suppressed: bool,
    reason: str,
    suppressed_at: str,
) -> None:
    conn.execute(
        "UPDATE entities SET suppressed = ?, suppressed_reason = ?, suppressed_at = ? "
        "WHERE id = ?",
        (suppressed, reason, suppressed_at, entity_id),
    )


def update_entities_suppression(
    conn: Any,
    entity_ids: set[str],
    *,
    suppressed: bool,
    reason: str,
    suppressed_at: str,
) -> None:
    if not entity_ids:
        return
    conn.executemany(
        "UPDATE entities SET suppressed = ?, suppressed_reason = ?, suppressed_at = ? "
        "WHERE id = ?",
        [
            (suppressed, reason, suppressed_at, item_id)
            for item_id in sorted(entity_ids)
        ],
    )


def update_finding_suppression(
    conn: Any,
    finding_id: str,
    *,
    suppressed: bool,
    reason: str,
    suppressed_at: str,
) -> None:
    conn.execute(
        "UPDATE findings SET suppressed = ?, suppressed_reason = ?, suppressed_at = ? "
        "WHERE id = ?",
        (suppressed, reason, suppressed_at, finding_id),
    )


def update_findings_suppression(
    conn: Any,
    finding_ids: set[str],
    *,
    suppressed: bool,
    reason: str,
    suppressed_at: str,
) -> None:
    if not finding_ids:
        return
    conn.executemany(
        "UPDATE findings SET suppressed = ?, suppressed_reason = ?, suppressed_at = ? "
        "WHERE id = ?",
        [
            (suppressed, reason, suppressed_at, item_id)
            for item_id in sorted(finding_ids)
        ],
    )
