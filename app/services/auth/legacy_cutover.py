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


@dataclass(frozen=True)
class PostgresEvidence:
    run_count: int
    run_id_digest: str
    search_term: str = ""
    search_match_count: int = 0
    search_run_id_digest: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "run_count": self.run_count,
            "known_search_checked": bool(self.search_term),
            "known_search_matches": self.search_match_count,
        }


CutoverEvidence = FtsEvidence | PostgresEvidence


@dataclass(frozen=True)
class OtherLegacyDiscardPlan:
    """Private row identifiers stay in memory; only counts reach CLI output."""

    credentials: tuple[str, ...]
    run_ids: tuple[str, ...]
    snapshot_ids: tuple[str, ...]
    team_snapshot_ids: tuple[str, ...]
    team_recent_values: int
    member_ids: tuple[str, ...]
    rows_by_table: dict[str, int]

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "credentials": len(self.credentials),
            "owned_rows": sum(self.rows_by_table.values()),
            "owned_rows_by_table": self.rows_by_table,
            "team_snapshots": len(self.team_snapshot_ids),
            "team_recent_values": self.team_recent_values,
            "team_members": len(self.member_ids),
        }


_DISCARDABLE_OWNER_TABLES = (
    "runs", "snapshots", "recent_values", "session_preferences", "starred_commands",
)
_DISCARDABLE_RUN_REFERENCES = frozenset({
    ("run_output_artifacts", "run_id"),
    ("run_output_summary", "run_id"),
    ("run_output_summary_status", "run_id"),
})


def _postgres_reference_columns(conn: Any, suffix: str) -> tuple[tuple[str, str], ...]:
    rows = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND column_name LIKE ? "
        "ORDER BY table_name, column_name",
        (f"%{suffix}",),
    ).fetchall()
    columns = []
    for row in rows:
        table, column = str(row["table_name"]), str(row["column_name"])
        if not re.fullmatch(r"[a-z][a-z0-9_]*", table) or not re.fullmatch(r"[a-z][a-z0-9_]*", column):
            raise RuntimeError("unexpected database identifier during legacy discard")
        columns.append((table, column))
    return tuple(columns)


def _selected_owned_team_has_active_other_member(
    conn: Any, *, team_id: str, selected_hash: str, other_credential: str,
) -> bool:
    other_hash = hashlib.sha256(other_credential.encode("utf-8")).hexdigest()
    return conn.execute(
        "SELECT 1 FROM teams AS team "
        "JOIN team_members AS selected_member ON selected_member.team_id = team.id "
        "JOIN team_members AS other_member ON other_member.team_id = team.id "
        "WHERE team.id = ? AND team.status = 'active' "
        "AND selected_member.session_token_hash = ? "
        "AND selected_member.role = 'owner' AND selected_member.status = 'active' "
        "AND other_member.session_token_hash = ? AND other_member.status = 'active'",
        (team_id, selected_hash, other_hash),
    ).fetchone() is not None


def plan_other_legacy_discard(
    conn: Any, *, selected_credential: str, reviewed_team_snapshot_ids: tuple[str, ...] = (),
    expected_team_recent_values: int | None = None,
) -> OtherLegacyDiscardPlan:
    """Fail closed unless the other owners have only the reviewed disposable shape."""
    if _database_backend(conn) != DatabaseBackend.POSTGRES:
        raise RuntimeError("development legacy discard supports Postgres only")
    selected = str(selected_credential or "").strip()
    if conn.execute("SELECT 1 FROM session_tokens WHERE token = ?", (selected,)).fetchone() is None:
        raise RuntimeError("selected credential was not found")
    credentials = tuple(
        str(row["token"])
        for row in conn.execute(
            "SELECT token FROM session_tokens WHERE token != ? ORDER BY token", (selected,)
        ).fetchall()
    )
    if not credentials:
        raise RuntimeError("there are no other legacy credentials to discard")

    rows_by_table = {
        table: _count(
            conn,
            f"SELECT COUNT(*) AS count FROM {table} WHERE personal_workspace_id IN "  # nosec
            "(SELECT token FROM session_tokens WHERE token != ?)",
            (selected,),
        )
        for table in PERSONAL_OWNER_TABLES
    }
    rows_by_table["secrets"] = _count(
        conn,
        "SELECT COUNT(*) AS count FROM secrets WHERE owner_id IN "
        "(SELECT token FROM session_tokens WHERE token != ?)",
        (selected,),
    )
    unexpected = [
        table for table, count in rows_by_table.items()
        if count and table not in _DISCARDABLE_OWNER_TABLES
    ]
    if unexpected:
        raise RuntimeError("other legacy owners have unsupported data in: " + ", ".join(unexpected))
    if _count(
        conn,
        "SELECT COUNT(*) AS count FROM runs WHERE (team_id IS NULL OR team_id != '') "
        "AND personal_workspace_id IN (SELECT token FROM session_tokens WHERE token != ?)",
        (selected,),
    ):
        raise RuntimeError("other legacy runs include Team data")

    selected_hash = hashlib.sha256(selected.encode("utf-8")).hexdigest()
    if _count(
        conn,
        "SELECT COUNT(*) AS count FROM recent_values WHERE team_id IS NULL "
        "AND personal_workspace_id IN (SELECT token FROM session_tokens WHERE token != ?)",
        (selected,),
    ):
        raise RuntimeError("other legacy recent_values have an unknown Team scope")
    team_recent_rows = conn.execute(
        "SELECT team_id, personal_workspace_id FROM recent_values "
        "WHERE team_id != '' AND personal_workspace_id IN "
        "(SELECT token FROM session_tokens WHERE token != ?)",
        (selected,),
    ).fetchall()
    team_recent_count = len(team_recent_rows)
    if expected_team_recent_values is not None and expected_team_recent_values < 0:
        raise RuntimeError("reviewed Team recent-value count must not be negative")
    if team_recent_count != (expected_team_recent_values or 0):
        raise RuntimeError("other legacy recent_values include Team data; review and confirm their exact count")
    team_recent_owners = {
        (str(row["team_id"]), str(row["personal_workspace_id"]))
        for row in team_recent_rows
    }
    for team_id, other_credential in team_recent_owners:
        if not _selected_owned_team_has_active_other_member(
            conn,
            team_id=team_id,
            selected_hash=selected_hash,
            other_credential=other_credential,
        ):
            raise RuntimeError("reviewed Team recent values have no active selected owner and test membership")

    # A Team snapshot may be discarded only when the operator named its exact
    # ID and both its author and the selected operator belong to that Team.
    # Keep NULL scope fail-closed; it is not an explicitly reviewed Team ID.
    if _count(
        conn,
        "SELECT COUNT(*) AS count FROM snapshots WHERE team_id IS NULL "
        "AND personal_workspace_id IN (SELECT token FROM session_tokens WHERE token != ?)",
        (selected,),
    ):
        raise RuntimeError("other legacy snapshots have an unknown Team scope")
    team_snapshots = conn.execute(
        "SELECT id, team_id, personal_workspace_id FROM snapshots "
        "WHERE team_id != '' AND personal_workspace_id IN "
        "(SELECT token FROM session_tokens WHERE token != ?) ORDER BY id",
        (selected,),
    ).fetchall()
    reviewed_ids = tuple(str(snapshot_id).strip() for snapshot_id in reviewed_team_snapshot_ids)
    if not all(reviewed_ids) or len(set(reviewed_ids)) != len(reviewed_ids):
        raise RuntimeError("reviewed Team snapshot IDs must be nonempty and unique")
    team_snapshot_ids = tuple(str(row["id"]) for row in team_snapshots)
    if set(team_snapshot_ids) != set(reviewed_ids):
        raise RuntimeError("other legacy snapshots include Team data; review and name every Team snapshot ID")
    for row in team_snapshots:
        if not _selected_owned_team_has_active_other_member(
            conn,
            team_id=str(row["team_id"]),
            selected_hash=selected_hash,
            other_credential=str(row["personal_workspace_id"]),
        ):
            raise RuntimeError("reviewed Team snapshot has no active selected owner and author membership")

    for entity_type, owner_table in (("run", "runs"), ("snapshot", "snapshots")):
        for link_table in ("project_links", "entity_labels", "entity_notes"):
            if _count(
                conn,
                f"SELECT COUNT(*) AS count FROM {link_table} AS linked "  # nosec
                f"JOIN {owner_table} AS owned ON owned.id = linked.entity_id "
                "WHERE linked.entity_type = ? AND owned.personal_workspace_id IN "
                "(SELECT token FROM session_tokens WHERE token != ?)",
                (entity_type, selected),
            ):
                raise RuntimeError(f"other legacy {entity_type} is referenced by {link_table}")
    if _count(
        conn,
        "SELECT COUNT(*) AS count FROM finding_version_inference_sources AS linked "
        "JOIN runs AS owned ON owned.id = linked.source_id "
        "WHERE linked.source_kind = 'run' AND owned.personal_workspace_id IN "
        "(SELECT token FROM session_tokens WHERE token != ?)",
        (selected,),
    ):
        raise RuntimeError("other legacy run is referenced by finding_version_inference_sources")
    if _count(
        conn,
        "SELECT COUNT(*) AS count FROM finding_evidence_links AS linked "
        "JOIN runs AS owned ON owned.id = linked.evidence_id "
        "WHERE linked.evidence_type IN ('run', 'run_line', 'retest_run') "
        "AND owned.personal_workspace_id IN "
        "(SELECT token FROM session_tokens WHERE token != ?)",
        (selected,),
    ):
        raise RuntimeError("other legacy run is referenced by finding_evidence_links")

    run_ids = tuple(
        str(row["id"])
        for row in conn.execute(
            "SELECT id FROM runs WHERE personal_workspace_id IN "
            "(SELECT token FROM session_tokens WHERE token != ?) ORDER BY id",
            (selected,),
        ).fetchall()
    )
    snapshot_ids = tuple(
        str(row["id"])
        for row in conn.execute(
            "SELECT id FROM snapshots WHERE personal_workspace_id IN "
            "(SELECT token FROM session_tokens WHERE token != ?) ORDER BY id",
            (selected,),
        ).fetchall()
    )
    # Run metadata handled by delete_run_artifacts is safe to remove. Every
    # other run reference needs a deliberate disposition before a test run goes.
    for table, column in _postgres_reference_columns(conn, "run_id"):
        if (table, column) in _DISCARDABLE_RUN_REFERENCES:
            continue
        if _count(
            conn,
            f"SELECT COUNT(*) AS count FROM {table} AS linked "  # nosec
            f"JOIN runs AS old_run ON old_run.id = linked.{column} "
            "WHERE old_run.personal_workspace_id IN "
            "(SELECT token FROM session_tokens WHERE token != ?)",
            (selected,),
        ):
            raise RuntimeError(f"other legacy runs are referenced by {table}.{column}")

    other_hashes = {hashlib.sha256(token.encode("utf-8")).hexdigest() for token in credentials}
    for other_hash in other_hashes:
        if conn.execute(
            "SELECT 1 FROM team_members WHERE session_token_hash = ? "
            "AND principal_id IS NOT NULL AND principal_id != ''",
            (other_hash,),
        ).fetchone() is not None:
            raise RuntimeError("an other legacy Team member already has a principal")
    members = conn.execute(
        "SELECT id, team_id, role, status, session_token_hash FROM team_members "
        "WHERE (principal_id IS NULL OR principal_id = '') "
        "AND session_token_hash != ? ORDER BY id",
        (selected_hash,),
    ).fetchall()
    for row in members:
        if row["session_token_hash"] not in other_hashes:
            raise RuntimeError("a legacy Team member cannot be matched to an other credential")
        if row["role"] == "owner":
            raise RuntimeError("an other legacy credential owns a Team")
        if conn.execute(
            "SELECT 1 FROM team_members WHERE team_id = ? AND session_token_hash = ? "
            "AND role = 'owner' AND status = 'active'",
            (row["team_id"], selected_hash),
        ).fetchone() is None:
            raise RuntimeError("an other legacy Team member has no selected active Team owner")
    if _count(
        conn,
        "SELECT COUNT(*) AS count FROM teams WHERE "
        "(created_by_principal_id IS NULL OR created_by_principal_id = '') "
        "AND created_by_session_token_hash != '' AND created_by_session_token_hash != ?",
        (selected_hash,),
    ):
        raise RuntimeError("an other legacy credential created a Team")
    member_ids = tuple(str(row["id"]) for row in members)
    if member_ids:
        placeholders = ",".join("?" for _ in member_ids)
        for table, column in _postgres_reference_columns(conn, "member_id"):
            if _count(
                conn,
                f"SELECT COUNT(*) AS count FROM {table} "  # nosec
                f"WHERE {column} IN ({placeholders})",
                member_ids,
            ):
                raise RuntimeError(f"other legacy Team members are referenced by {table}.{column}")

    return OtherLegacyDiscardPlan(
        credentials, run_ids, snapshot_ids, team_snapshot_ids, team_recent_count, member_ids, rows_by_table,
    )


def discard_other_legacy_owners(conn: Any, plan: OtherLegacyDiscardPlan) -> None:
    """Remove reviewed test-owned database rows without touching filesystem data."""
    from core.database import delete_run_artifacts, delete_snapshot_metadata  # noqa: PLC0415

    for offset in range(0, len(plan.run_ids), 250):
        run_ids = plan.run_ids[offset:offset + 250]
        delete_run_artifacts(conn, run_ids, delete_files=False)
    for offset in range(0, len(plan.snapshot_ids), 250):
        snapshot_ids = plan.snapshot_ids[offset:offset + 250]
        delete_snapshot_metadata(conn, snapshot_ids, delete_files=False)
    for table in _DISCARDABLE_OWNER_TABLES:
        cursor = conn.execute(
            f"DELETE FROM {table} WHERE personal_workspace_id IN "  # nosec
            "(SELECT token FROM session_tokens WHERE token IN ("
            + ",".join("?" for _ in plan.credentials) + "))",
            plan.credentials,
        )
        if cursor.rowcount != plan.rows_by_table[table]:
            raise RuntimeError(f"discarded {table} row count changed during conversion")
    for member_id in plan.member_ids:
        conn.execute("DELETE FROM team_members WHERE id = ?", (member_id,))


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


def _database_backend(conn: Any) -> DatabaseBackend:
    explicit = getattr(conn, "database_backend", None)
    if explicit is not None:
        return DatabaseBackend(explicit)
    return DatabaseBackend.SQLITE


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
    team_creator_rows = _count(
        conn,
        "SELECT COUNT(*) AS count FROM teams WHERE "
        "(created_by_principal_id IS NULL OR created_by_principal_id = '') "
        "AND created_by_session_token_hash != ''",
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
        "database_backend": _database_backend(conn).value,
        "legacy_credentials": token_count,
        "legacy_credentials_seen": used_token_count,
        "legacy_owned_rows": sum(owned_rows.values()),
        "legacy_owned_rows_by_table": owned_rows,
        "team_members_without_principal": team_rows,
        "teams_without_creator_principal": team_creator_rows,
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


def _postgres_id_evidence(rows: Any) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        value = str(_row_value(row, "id")).encode("utf-8")
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
        count += 1
    return count, digest.hexdigest()


def _known_postgres_search(conn: Any) -> tuple[str, int, str]:
    rows = conn.execute(
        "SELECT id, command, output_search_text FROM runs ORDER BY id LIMIT 100"
    ).fetchall()
    for row in rows:
        text = f"{_row_value(row, 'command', 1) or ''} {_row_value(row, 'output_search_text', 2) or ''}"
        for match in _SEARCH_TOKEN_RE.finditer(text):
            term = match.group(0).lower()
            pattern = f"%{term}%"
            matched = conn.execute(
                "SELECT id FROM runs WHERE command ILIKE ? "
                "OR output_search_text ILIKE ? ORDER BY id",
                (pattern, pattern),
            )
            match_count, match_digest = _postgres_id_evidence(matched)
            if match_count:
                return term, match_count, match_digest
    return "", 0, ""


def verify_postgres_runs(conn: Any) -> PostgresEvidence:
    """Capture safe row and search evidence around a Postgres cutover."""
    run_count, run_id_digest = _postgres_id_evidence(
        conn.execute("SELECT id FROM runs ORDER BY id")
    )
    term, search_match_count, search_run_id_digest = _known_postgres_search(conn)
    return PostgresEvidence(
        run_count,
        run_id_digest,
        term,
        search_match_count,
        search_run_id_digest,
    )


def _cutover_evidence(conn: Any, backend: DatabaseBackend) -> CutoverEvidence:
    if backend == DatabaseBackend.POSTGRES:
        return verify_postgres_runs(conn)
    return verify_runs_fts(conn)


def convert_selected_owner(
    conn: Any,
    *,
    selected_credential: str,
    workspace_root: Path,
    credential_label: str = "Migrated operator access",
) -> tuple[PrincipalBundle, CutoverEvidence]:
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
    other_team_creators = _count(
        conn,
        "SELECT COUNT(*) AS count FROM teams WHERE "
        "(created_by_principal_id IS NULL OR created_by_principal_id = '') "
        "AND created_by_session_token_hash != '' "
        "AND created_by_session_token_hash != ?",
        (selected_hash,),
    )
    if other_team_creators:
        raise RuntimeError("a Team creator belongs to another legacy credential")

    shared_path = workspace_root.resolve(strict=False) / SHARED_ANONYMOUS_STORAGE_KEY
    if shared_path.is_symlink() or (shared_path.is_dir() and any(shared_path.iterdir())):
        raise RuntimeError("the shared-anonymous workspace needs an explicit disposition first")

    backend = _database_backend(conn)
    storage_key = session_workspace_name(selected)
    before = _cutover_evidence(conn, backend)
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
    apply_migration(conn, REMOVAL_MIGRATION, backend=backend, commit=False)
    after = _cutover_evidence(conn, backend)
    if isinstance(before, FtsEvidence) and isinstance(after, FtsEvidence):
        if after.rowids != before.rowids:
            raise RuntimeError("runs rowids changed during principal cutover")
        if after.search_term != before.search_term or after.search_rowids != before.search_rowids:
            raise RuntimeError("runs_fts known-substring results changed during principal cutover")
    elif isinstance(before, PostgresEvidence) and isinstance(after, PostgresEvidence):
        if after.run_count != before.run_count or after.run_id_digest != before.run_id_digest:
            raise RuntimeError("Postgres runs changed during principal cutover")
        if (
            after.search_term != before.search_term
            or after.search_match_count != before.search_match_count
            or after.search_run_id_digest != before.search_run_id_digest
        ):
            raise RuntimeError("Postgres known-substring results changed during principal cutover")
    else:
        raise RuntimeError("database backend changed during principal cutover")
    assert_post_cutover_schema(conn, backend, enabled=True)
    return bundle, after


__all__ = [
    "FtsEvidence",
    "PostgresEvidence",
    "SHARED_ANONYMOUS_STORAGE_KEY",
    "convert_selected_owner",
    "legacy_inventory",
    "verify_runs_fts",
]
