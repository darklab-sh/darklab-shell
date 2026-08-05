# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persistence helpers for explicit remediation-group merges."""

from __future__ import annotations

from typing import Any, Mapping


MEMBER_UPSERT_SQL = (
    "INSERT INTO finding_remediation_merge_members "
    "(session_id, team_id, merge_id, affected_subject, identity_kind, identity_value, "
    "vulnerability_id, rule_identity, created_by_session_id, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(session_id, team_id, affected_subject, identity_value) DO UPDATE SET "
    "merge_id = excluded.merge_id, identity_kind = excluded.identity_kind, "
    "vulnerability_id = excluded.vulnerability_id, rule_identity = excluded.rule_identity"
)


def owner_scope(session_id: str, team_id: str) -> tuple[str, str]:
    normalized_team_id = str(team_id or "").strip()
    return ("", normalized_team_id) if normalized_team_id else (str(session_id or ""), "")


def remediation_identity_value(reference: Mapping[str, Any]) -> str:
    vulnerability_id = str(reference.get("vulnerability_id") or "").strip().upper()
    return vulnerability_id or f"RULE:{str(reference.get('rule_identity') or '').strip()}"


def remediation_reference_key(
    session_id: str,
    team_id: str,
    reference: Mapping[str, Any],
) -> tuple[str, str, str, str]:
    owner_session_id, owner_team_id = owner_scope(session_id, team_id)
    return (
        owner_session_id,
        owner_team_id,
        str(reference.get("affected_subject") or ""),
        remediation_identity_value(reference),
    )


def member_payload(
    key: tuple[str, str, str, str],
    reference: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "session_id": key[0],
        "team_id": key[1],
        "affected_subject": key[2],
        "identity_kind": str(reference.get("identity_kind") or "rule"),
        "identity_value": key[3],
        "vulnerability_id": str(reference.get("vulnerability_id") or ""),
        "rule_identity": str(reference.get("rule_identity") or ""),
        "remediation_id": str(reference.get("remediation_id") or ""),
    }


def rows_by_keys(conn: Any, keys: set[tuple[str, str, str, str]]) -> list[Any]:
    rows: list[Any] = []
    ordered = sorted(keys)
    for offset in range(0, len(ordered), 80):
        chunk = ordered[offset:offset + 80]
        clauses = " OR ".join(
            "(session_id = ? AND team_id = ? AND affected_subject = ? AND identity_value = ?)"
            for _ in chunk
        )
        # The clause shape is fixed; every owner and identity value remains bound.
        rows.extend(conn.execute(
            "SELECT session_id, team_id, merge_id, affected_subject, identity_kind, "
            "identity_value, vulnerability_id, rule_identity, created_by_session_id, created_at "
            "FROM finding_remediation_merge_members WHERE "  # nosec B608
            + clauses,
            tuple(value for key in chunk for value in key),
        ).fetchall())
    return rows


def rows_by_merge_ids(
    conn: Any,
    owner_merge_ids: set[tuple[str, str, str]],
) -> list[Any]:
    rows: list[Any] = []
    ordered = sorted(owner_merge_ids)
    for offset in range(0, len(ordered), 100):
        chunk = ordered[offset:offset + 100]
        clauses = " OR ".join(
            "(session_id = ? AND team_id = ? AND merge_id = ?)" for _ in chunk
        )
        # The clause shape is fixed; every owner and merge id remains bound.
        rows.extend(conn.execute(
            "SELECT session_id, team_id, merge_id, affected_subject, identity_kind, "
            "identity_value, vulnerability_id, rule_identity, created_by_session_id, created_at "
            "FROM finding_remediation_merge_members WHERE "  # nosec B608
            + clauses,
            tuple(value for key in chunk for value in key),
        ).fetchall())
    return rows


def remediation_group_membership(
    conn: Any,
    references_by_key: Mapping[tuple[str, str, str, str], Mapping[str, Any]],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """Return logical group ids without changing exact remediation identities."""
    if not references_by_key:
        return {}
    membership_rows = rows_by_keys(conn, set(references_by_key))
    merge_by_key = {
        (
            str(row["session_id"] or ""),
            str(row["team_id"] or ""),
            str(row["affected_subject"] or ""),
            str(row["identity_value"] or ""),
        ): str(row["merge_id"] or "")
        for row in membership_rows
    }
    counts: dict[tuple[str, str, str], int] = {}
    merge_ids = {
        (key[0], key[1], merge_id)
        for key, merge_id in merge_by_key.items()
        if merge_id
    }
    for row in rows_by_merge_ids(conn, merge_ids):
        merge_key = (
            str(row["session_id"] or ""),
            str(row["team_id"] or ""),
            str(row["merge_id"] or ""),
        )
        counts[merge_key] = counts.get(merge_key, 0) + 1
    result: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for key, reference in references_by_key.items():
        merge_id = merge_by_key.get(key, "")
        exact_id = str(reference.get("remediation_id") or "")
        member_count = counts.get((key[0], key[1], merge_id), 1) if merge_id else 1
        result[key] = {
            "remediation_group_id": merge_id or exact_id,
            "remediation_group_merged": bool(merge_id),
            "remediation_group_member_count": member_count,
        }
    return result


def expand_remediation_group_members(
    conn: Any,
    groups: Mapping[tuple[str, str, str, str], Mapping[str, Any]],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """Expand selected exact groups to every explicitly merged member."""
    expanded = {key: dict(value) for key, value in groups.items()}
    selected_rows = rows_by_keys(conn, set(expanded))
    template_by_merge: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in selected_rows:
        key = (
            str(row["session_id"] or ""),
            str(row["team_id"] or ""),
            str(row["affected_subject"] or ""),
            str(row["identity_value"] or ""),
        )
        merge_key = (key[0], key[1], str(row["merge_id"] or ""))
        if key in expanded:
            template_by_merge[merge_key] = dict(expanded[key])
    merge_ids = {
        (
            str(row["session_id"] or ""),
            str(row["team_id"] or ""),
            str(row["merge_id"] or ""),
        )
        for row in selected_rows
        if str(row["merge_id"] or "")
    }
    for row in rows_by_merge_ids(conn, merge_ids):
        key = (
            str(row["session_id"] or ""),
            str(row["team_id"] or ""),
            str(row["affected_subject"] or ""),
            str(row["identity_value"] or ""),
        )
        merge_key = (key[0], key[1], str(row["merge_id"] or ""))
        expanded[key] = {
            **template_by_merge.get(merge_key, {}),
            "identity_kind": str(row["identity_kind"] or "rule"),
            "vulnerability_id": str(row["vulnerability_id"] or ""),
            "rule_identity": str(row["rule_identity"] or ""),
        }
    return expanded


def migrate_remediation_merge_members(
    conn: Any,
    from_session_id: str,
    to_session_id: str,
) -> int:
    """Move personal merge memberships and union any colliding destination groups."""
    rows = conn.execute(
        "SELECT merge_id, affected_subject, identity_kind, identity_value, vulnerability_id, "
        "rule_identity, created_by_session_id, created_at "
        "FROM finding_remediation_merge_members WHERE session_id = ? AND team_id = '' "
        "ORDER BY merge_id, affected_subject, identity_value",
        (from_session_id,),
    ).fetchall()
    if not rows:
        return 0
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        grouped.setdefault(str(row["merge_id"] or ""), []).append(row)
    for source_merge_id, members in grouped.items():
        keys = {
            (to_session_id, "", str(row["affected_subject"]), str(row["identity_value"]))
            for row in members
        }
        destination_rows = rows_by_keys(conn, keys)
        destination_merge_ids = sorted({
            str(row["merge_id"] or "") for row in destination_rows if row["merge_id"]
        })
        merge_id = destination_merge_ids[0] if destination_merge_ids else source_merge_id
        for stale_merge_id in destination_merge_ids[1:]:
            conn.execute(
                "UPDATE finding_remediation_merge_members SET merge_id = ? "
                "WHERE session_id = ? AND team_id = '' AND merge_id = ?",
                (merge_id, to_session_id, stale_merge_id),
            )
        conn.executemany(MEMBER_UPSERT_SQL, [
            (
                to_session_id,
                "",
                merge_id,
                row["affected_subject"],
                row["identity_kind"],
                row["identity_value"],
                row["vulnerability_id"],
                row["rule_identity"],
                (
                    to_session_id
                    if row["created_by_session_id"] == from_session_id
                    else row["created_by_session_id"]
                ),
                row["created_at"],
            )
            for row in members
        ])
    conn.execute(
        "DELETE FROM finding_remediation_merge_members WHERE session_id = ? AND team_id = ''",
        (from_session_id,),
    )
    return len(rows)
