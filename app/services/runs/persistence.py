# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Run persistence helpers owned by the service layer."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.storage.transactions import run_transaction

_T = TypeVar("_T")


def run_persistence_transaction(callback: Callable[[Any], _T]) -> _T:
    return run_transaction(callback)


def insert_run_row(
    conn: Any,
    *,
    run_id: str,
    session_id: str,
    team_id: str,
    run_kind: str,
    owner_tab_id: str,
    command: str,
    started: str,
    finished: str,
    exit_code: int,
    output_preview: str,
    preview_truncated: object,
    output_line_count: int,
    full_output_available: object,
    full_output_truncated: object,
    output_search_text: str,
) -> None:
    dialect = dialect_for_backend(get_db_backend())
    conn.execute(
        "INSERT INTO runs "
        "("
        "id, session_id, team_id, run_kind, owner_tab_id, command, started, finished, exit_code, output, output_preview, "
        "preview_truncated, output_line_count, full_output_available, full_output_truncated, "
        "output_search_text"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            session_id,
            team_id,
            run_kind,
            owner_tab_id,
            command,
            started,
            finished,
            exit_code,
            None,
            output_preview,
            dialect.boolean_param(preview_truncated),
            int(output_line_count or 0),
            dialect.boolean_param(full_output_available),
            dialect.boolean_param(full_output_truncated),
            output_search_text,
        ),
    )


def upsert_run_output_artifact(
    conn: Any,
    *,
    run_id: str,
    rel_path: str,
    compression: str,
    byte_size: int,
    line_count: int,
    truncated: object,
    created: str,
) -> None:
    dialect = dialect_for_backend(get_db_backend())
    params = (
        run_id,
        rel_path,
        compression,
        int(byte_size or 0),
        int(line_count or 0),
        dialect.boolean_param(truncated),
        created,
    )
    if get_db_backend() == DatabaseBackend.POSTGRES:
        conn.execute(
            "INSERT INTO run_output_artifacts "
            "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET "
            "rel_path = excluded.rel_path, "
            "compression = excluded.compression, "
            "byte_size = excluded.byte_size, "
            "line_count = excluded.line_count, "
            "truncated = excluded.truncated, "
            "created = excluded.created",
            params,
        )
        return
    conn.execute(
        "INSERT OR REPLACE INTO run_output_artifacts "
        "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        params,
    )


def run_finalize_savepoint(conn: Any, name: str, callback: Callable[[], _T]) -> _T:
    savepoint = f"run_finalize_{name}"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        result = callback()
    except Exception:
        try:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        finally:
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise
    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    return result


def scan_target_observation_count(conn: Any, run_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM scan_target_observations WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return 0
    try:
        return int(row["count"] or 0)
    except (KeyError, TypeError, IndexError):
        return int(row[0] or 0)


def run_scope_visibility_from_db(run_id: str, session_id: str, team_id: str = "") -> tuple[bool, bool, str]:
    with get_db_connect()() as conn:
        if team_id:
            row = conn.execute(
                "SELECT 1 FROM runs WHERE id = ? AND team_id = ?",
                (run_id, team_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM runs WHERE id = ? AND session_id = ? AND team_id = ''",
                (run_id, session_id),
            ).fetchone()
        db_match = row is not None
        other_scope_row = None
        if not db_match:
            other_scope_row = conn.execute(
                "SELECT team_id FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        return (
            db_match,
            other_scope_row is not None,
            str(other_scope_row["team_id"] or "") if other_scope_row else "",
        )
