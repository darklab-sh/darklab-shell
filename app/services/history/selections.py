# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Resolve complete run selections for History bulk actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from hashlib import sha256

from core.database_access import get_db_connect
from core.database_backend import SQLiteOperationalError
from core.helpers import get_log_session_id
from services.history.queries import build_fts_query, history_run_filter_clause
from services.history.run_metadata import history_column_exists
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL

log = logging.getLogger("shell")


@dataclass(frozen=True)
class HistoryRunSelection:
    run_ids: list[str]
    non_starred_run_ids: list[str]

    @property
    def total_count(self) -> int:
        return len(self.run_ids)

    @property
    def non_starred_count(self) -> int:
        return len(self.non_starred_run_ids)


def matching_history_runs(
    *,
    session_id: str,
    owner_scope,
    query: str,
    structured_filters,
    command_root: str,
    exit_code_filter: str,
    date_range: str,
    type_filter: str,
    project_id: str,
    starred_only: bool,
    scope: str,
) -> HistoryRunSelection:
    if type_filter == "snapshots":
        return HistoryRunSelection(run_ids=[], non_starred_run_ids=[])
    run_kind = {
        "runs_builtin": RUN_KIND_BUILTIN,
        "runs_external": RUN_KIND_EXTERNAL,
    }.get(type_filter, "all")

    def _query(conn, *, force_like=False):
        run_sql, run_params, _fts_q = history_run_filter_clause(
            conn=conn,
            session_id=session_id,
            owner_scope=owner_scope,
            query=query,
            structured_filters=structured_filters,
            command_root=command_root,
            exit_code_filter=exit_code_filter,
            date_range=date_range,
            project_id=project_id,
            starred_only=starred_only,
            run_kind=run_kind,
            scope=scope,
            has_run_kind_column=history_column_exists(conn, "runs", "run_kind"),
            force_like=force_like,
        )
        return conn.execute(
            "SELECT r.id, EXISTS ("  # nosec
            "SELECT 1 FROM starred_commands sc "
            "WHERE sc.session_id = r.session_id AND sc.command = r.command"
            ") AS starred"
            + run_sql
            + " ORDER BY r.started DESC, r.id DESC",
            run_params,
        ).fetchall()

    with get_db_connect()() as conn:
        try:
            rows = _query(conn)
        except SQLiteOperationalError as exc:
            if not query or not build_fts_query(query):
                raise
            log.warning("HISTORY_DELETE_FILTER_FALLBACK", extra={
                "session": get_log_session_id(session_id),
                "query_len": len(query),
                "query_hash": sha256(query.encode("utf-8")).hexdigest()[:16],
                "reason": "missing_fts" if "runs_fts" in str(exc).lower() else "fts_error",
                "error_type": type(exc).__name__,
            })
            rows = _query(conn, force_like=True)
    run_ids = [str(row["id"]) for row in rows]
    return HistoryRunSelection(
        run_ids=run_ids,
        non_starred_run_ids=[str(row["id"]) for row in rows if not bool(row["starred"])],
    )
