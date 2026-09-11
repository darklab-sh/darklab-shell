# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Safe inventory and conversion helpers for the one-time principal cutover."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import hashlib
import re
from pathlib import Path
from typing import Any

from core.database_backend import DatabaseBackend
from core.migrations.runner import applied_versions, apply_migration
from core.migrations.v0082_remove_legacy_session_identity import MIGRATION as REMOVAL_MIGRATION
from services.workspace.settings import session_workspace_name
from services.workspace.settings import workspace_settings

from .contracts import PrincipalBundle
from .ownership_cutover import PERSONAL_OWNER_TABLES
from .schema_guard import assert_post_cutover_schema
from .storage import create_principal_with_credential


SHARED_ANONYMOUS_STORAGE_KEY = f"sess_{hashlib.sha256(b'anonymous').hexdigest()[:32]}"
_SEARCH_TOKEN_RE = re.compile(r"[A-Za-z0-9]{3,}")


@dataclass(frozen=True)
class FtsEvidence:
    run_count: int
    indexed_count: int
    rowids: tuple[int, ...]
    search_term: str = ""
    search_rowids: tuple[int, ...] = ()

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "run_count": self.run_count,
            "indexed_count": self.indexed_count,
            "rowid_count": len(self.rowids),
            "known_search_checked": bool(self.search_term),
            "known_search_matches": len(self.search_rowids),
        }


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _count(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(_row_value(row, "count") if row is not None else 0)


def legacy_inventory(conn: Any, workspace_root: Path) -> dict[str, Any]:
    """Return counts and filesystem metadata without returning credential values."""
    token_count = _count(conn, "SELECT COUNT(*) AS count FROM session_tokens")
    used_token_count = _count(
        conn,
        "SELECT COUNT(*) AS count FROM session_tokens WHERE last_seen_at IS NOT NULL AND last_seen_at != ''",
    )
    owned_rows: dict[str, int] = {}
    for table_name in PERSONAL_OWNER_TABLES:
        owned_rows[table_name] = _count(
            conn,
            f"SELECT COUNT(*) AS count FROM {table_name} WHERE personal_workspace_id IN "  # nosec
            "(SELECT token FROM session_tokens)",
        )
    owned_rows["secrets"] = _count(
        conn,
        "SELECT COUNT(*) AS count FROM secrets WHERE owner_id IN (SELECT token FROM session_tokens)",
    )
    team_rows = _count(
        conn,
        "SELECT COUNT(*) AS count FROM team_members "
        "WHERE principal_id IS NULL OR principal_id = ''",
    )
    shared_path = workspace_root.resolve(strict=False) / SHARED_ANONYMOUS_STORAGE_KEY
    shared_exists = shared_path.exists() or shared_path.is_symlink()
    shared_entries = 0
    shared_bytes = 0
    if shared_exists and shared_path.is_dir() and not shared_path.is_symlink():
        for child in shared_path.rglob("*"):
            shared_entries += 1
            if child.is_file() and not child.is_symlink():
                shared_bytes += child.stat().st_size
    return {
        "legacy_credentials": token_count,
        "legacy_credentials_seen": used_token_count,
        "legacy_owned_rows": sum(owned_rows.values()),
        "legacy_owned_rows_by_table": owned_rows,
        "team_members_without_principal": team_rows,
        "shared_anonymous_workspace": {
            "exists": shared_exists,
            "entry_count": shared_entries,
            "bytes": shared_bytes,
        },
    }


def _known_search(conn: Any) -> tuple[str, tuple[int, ...]]:
    rows = conn.execute(
        "SELECT rowid, command, output_search_text FROM runs ORDER BY rowid LIMIT 100"
    ).fetchall()
    for row in rows:
        text = f"{_row_value(row, 'command', 1) or ''} {_row_value(row, 'output_search_text', 2) or ''}"
        for match in _SEARCH_TOKEN_RE.finditer(text):
            term = match.group(0)
            matched = conn.execute(
                "SELECT rowid FROM runs_fts WHERE runs_fts MATCH ? ORDER BY rowid",
                (term,),
            ).fetchall()
            rowids = tuple(int(_row_value(item, "rowid")) for item in matched)
            if int(_row_value(row, "rowid")) in rowids:
                return term, rowids
    return "", ()


def verify_runs_fts(conn: Any) -> FtsEvidence:
    """Check the external-content index without reconstructing the runs table."""
    conn.execute("INSERT INTO runs_fts(runs_fts) VALUES('integrity-check')")
    integrity = str(_row_value(conn.execute("PRAGMA integrity_check").fetchone(), "integrity_check"))
    if integrity.lower() != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    rowids = tuple(
        int(_row_value(row, "rowid"))
        for row in conn.execute("SELECT rowid FROM runs ORDER BY rowid").fetchall()
    )
    run_count = len(rowids)
    indexed_count = _count(conn, "SELECT COUNT(*) AS count FROM runs_fts")
    if indexed_count != run_count:
        raise RuntimeError("runs_fts row count does not match runs")
    term, search_rowids = _known_search(conn)
    return FtsEvidence(run_count, indexed_count, rowids, term, search_rowids)


def convert_selected_owner(
    conn: Any,
    *,
    selected_credential: str,
    workspace_root: Path,
    credential_label: str = "Migrated operator access",
) -> tuple[PrincipalBundle, FtsEvidence]:
    """Convert the sole selected legacy owner in the caller's transaction."""
    if "0082" in applied_versions(conn):
        raise RuntimeError("principal cutover has already completed")
    selected = str(selected_credential or "").strip()
    row = conn.execute(
        "SELECT last_seen_at FROM session_tokens WHERE token = ?",
        (selected,),
    ).fetchone()
    if row is None:
        raise RuntimeError("selected credential was not found")

    for table_name in PERSONAL_OWNER_TABLES:
        other = _count(
            conn,
            f"SELECT COUNT(*) AS count FROM {table_name} WHERE personal_workspace_id IN "  # nosec
            "(SELECT token FROM session_tokens WHERE token != ?)",
            (selected,),
        )
        if other:
            raise RuntimeError(f"{table_name} contains data owned by another legacy credential")
    other_secrets = _count(
        conn,
        "SELECT COUNT(*) AS count FROM secrets WHERE owner_id IN "
        "(SELECT token FROM session_tokens WHERE token != ?)",
        (selected,),
    )
    if other_secrets:
        raise RuntimeError("secrets contains data owned by another legacy credential")

    selected_hash = hashlib.sha256(selected.encode("utf-8")).hexdigest()
    other_members = _count(
        conn,
        "SELECT COUNT(*) AS count FROM team_members WHERE "
        "(principal_id IS NULL OR principal_id = '') AND session_token_hash != ?",
        (selected_hash,),
    )
    if other_members:
        raise RuntimeError("a team membership belongs to another legacy credential")

    shared_path = workspace_root.resolve(strict=False) / SHARED_ANONYMOUS_STORAGE_KEY
    if shared_path.is_symlink() or (shared_path.is_dir() and any(shared_path.iterdir())):
        raise RuntimeError("the shared-anonymous workspace needs an explicit disposition first")

    storage_key = session_workspace_name(selected)
    before = verify_runs_fts(conn)
    bundle = create_principal_with_credential(
        cutover_owner_id=selected,
        cutover_storage_key=storage_key,
        credential_label=credential_label,
        settings=replace(workspace_settings(), root=workspace_root),
        conn=conn,
    )
    conn.execute(
        "UPDATE team_members SET principal_id = ?, joined_by_credential_id = COALESCE(joined_by_credential_id, ?) "
        "WHERE session_token_hash = ?",
        (bundle.principal.id, bundle.credential.metadata.id, selected_hash),
    )
    conn.execute(
        "UPDATE teams SET created_by_principal_id = COALESCE(created_by_principal_id, ?), "
        "created_by_credential_id = COALESCE(created_by_credential_id, ?) "
        "WHERE created_by_session_token_hash = ?",
        (bundle.principal.id, bundle.credential.metadata.id, selected_hash),
    )
    conn.execute("DELETE FROM session_tokens")
    apply_migration(conn, REMOVAL_MIGRATION, backend=DatabaseBackend.SQLITE, commit=False)
    after = verify_runs_fts(conn)
    if after.rowids != before.rowids:
        raise RuntimeError("runs rowids changed during principal cutover")
    if after.search_term != before.search_term or after.search_rowids != before.search_rowids:
        raise RuntimeError("runs_fts known-substring results changed during principal cutover")
    assert_post_cutover_schema(conn, DatabaseBackend.SQLITE, enabled=True)
    return bundle, after


__all__ = [
    "FtsEvidence",
    "SHARED_ANONYMOUS_STORAGE_KEY",
    "convert_selected_owner",
    "legacy_inventory",
    "verify_runs_fts",
]
