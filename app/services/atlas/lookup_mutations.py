"""Atlas entity and finding mutation helpers used by route handlers."""

from __future__ import annotations

from typing import Any


def run_belongs_to_session(conn: Any, session_id: str, run_id: str) -> bool:
    row = conn.execute(
        "SELECT id FROM runs WHERE id = ? AND session_id = ?",
        (run_id, session_id),
    ).fetchone()
    return row is not None


def entity_ids_in_session(conn: Any, session_id: str, entity_ids: list[str]) -> set[str]:
    if not entity_ids:
        return set()
    placeholders = ",".join("?" for _ in entity_ids)
    rows = conn.execute(
        "SELECT id FROM entities WHERE session_id = ? "  # nosec
        f"AND id IN ({placeholders})",
        [session_id, *entity_ids],
    ).fetchall()
    return {str(row["id"] or "") for row in rows}


def finding_ids_in_session(conn: Any, session_id: str, finding_ids: list[str]) -> set[str]:
    if not finding_ids:
        return set()
    placeholders = ",".join("?" for _ in finding_ids)
    rows = conn.execute(
        "SELECT id FROM findings WHERE session_id = ? "  # nosec
        f"AND id IN ({placeholders})",
        [session_id, *finding_ids],
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


def update_finding_review_states(
    conn: Any,
    finding_ids: set[str],
    *,
    review_state: str,
    updated_at: str,
) -> None:
    if not finding_ids:
        return
    conn.executemany(
        "UPDATE findings SET status = ?, status_updated_at = ? WHERE id = ?",
        [(review_state, updated_at, finding_id) for finding_id in sorted(finding_ids)],
    )
