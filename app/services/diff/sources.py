# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Owner-scoped file and completed-run sources for terminal diffs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from core.database_access import get_db_connect
from services.runs.comparison import compare_entries_for_diff
from services.teams.scope import OwnerContext, shared_owner_predicate
from services.workspace.files import read_owner_workspace_text_file


DiffSourceKind = Literal["file", "run"]
FILE_DIFF_MAX_LINES = 5_000
FILE_DIFF_MAX_BYTES = 500_000


class DiffSourceError(ValueError):
    """A requested diff source can't be resolved safely."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DiffSource:
    kind: DiffSourceKind
    reference: str
    label: str
    text: str
    partial: bool = False


def _diff_line_count(text: str) -> int:
    if not text:
        return 0
    line_breaks = text.count("\n") + text.count("\r") - text.count("\r\n")
    return line_breaks + (0 if text.endswith(("\n", "\r")) else 1)


def _source_spec(reference: str) -> tuple[DiffSourceKind, str]:
    normalized = str(reference or "").strip()
    if normalized.startswith("run:"):
        value = normalized.removeprefix("run:").strip()
        if not value:
            raise DiffSourceError("run: requires a run id")
        return "run", value
    if normalized.startswith("file:"):
        value = normalized.removeprefix("file:").strip()
        if not value:
            raise DiffSourceError("file: requires a file path")
        return "file", value
    if not normalized:
        raise DiffSourceError("diff sources can't be empty")
    return "file", normalized


def _run_rows_for_ids(owner: OwnerContext, run_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not run_ids:
        return {}
    scope_sql, scope_params = shared_owner_predicate(
        owner,
        team_column="runs.team_id",
        session_column="runs.session_id",
    )
    placeholders = ", ".join("?" for _item in run_ids)
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT runs.*, art.rel_path "  # nosec
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE " + scope_sql + " AND runs.finished IS NOT NULL "
            "AND runs.id IN (" + placeholders + ")",
            (*scope_params, *run_ids),
        ).fetchall()
    return {str(row["id"]): dict(row) for row in rows}


def _latest_run_rows_for_tab(owner: OwnerContext, tab_id: str) -> list[dict[str, Any]]:
    normalized_tab_id = str(tab_id or "").strip()
    if not normalized_tab_id:
        raise DiffSourceError("diff --last requires an active terminal tab")
    scope_sql, scope_params = shared_owner_predicate(
        owner,
        team_column="runs.team_id",
        session_column="runs.session_id",
    )
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT runs.*, art.rel_path "  # nosec
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE " + scope_sql + " AND runs.owner_tab_id = ? "
            "AND runs.finished IS NOT NULL "
            "ORDER BY runs.started DESC, runs.id DESC LIMIT 2",
            (*scope_params, normalized_tab_id),
        ).fetchall()
    if len(rows) < 2:
        raise DiffSourceError("diff --last requires two completed runs in this tab", status_code=404)
    return [dict(row) for row in reversed(rows)]


def _run_label(run: Mapping[str, Any]) -> str:
    run_id = str(run.get("id") or "")
    started = str(run.get("started") or "").strip()
    command = " ".join(str(run.get("command") or "").split())
    if len(command) > 96:
        command = command[:93] + "..."
    details = " · ".join(item for item in (started, command) if item)
    return f"run:{run_id}" + (f" [{details}]" if details else "")


def _run_source(run: Mapping[str, Any]) -> DiffSource:
    run_id = str(run.get("id") or "")
    entries, output_info = compare_entries_for_diff(run)
    lines = [str(entry.get("text") or "") for entry in entries]
    text = "\n".join(lines)
    if lines:
        text += "\n"
    return DiffSource(
        kind="run",
        reference=f"run:{run_id}",
        label=_run_label(run),
        text=text,
        partial=bool(output_info.get("partial")),
    )


def _file_source(
    owner: OwnerContext,
    path: str,
    cfg: Mapping[str, Any] | None,
) -> DiffSource:
    text = read_owner_workspace_text_file(owner, path, cfg)
    byte_count = len(text.encode("utf-8"))
    reference = f"file:{path}"
    if byte_count > FILE_DIFF_MAX_BYTES:
        raise DiffSourceError(
            f"{reference} exceeds the file diff limit of {FILE_DIFF_MAX_BYTES:,} bytes",
            status_code=413,
        )
    line_count = _diff_line_count(text)
    if line_count > FILE_DIFF_MAX_LINES:
        raise DiffSourceError(
            f"{reference} exceeds the file diff limit of {FILE_DIFF_MAX_LINES:,} lines",
            status_code=413,
        )
    return DiffSource(
        kind="file",
        reference=reference,
        label=path,
        text=text,
    )


def resolve_diff_sources(
    owner: OwnerContext,
    *,
    left_reference: str = "",
    right_reference: str = "",
    use_last: bool = False,
    tab_id: str = "",
    cfg: Mapping[str, Any] | None = None,
) -> tuple[DiffSource, DiffSource]:
    """Resolve an explicit source pair or the latest two runs in one tab."""

    if use_last:
        left_run, right_run = _latest_run_rows_for_tab(owner, tab_id)
        return _run_source(left_run), _run_source(right_run)

    left_kind, left_value = _source_spec(left_reference)
    right_kind, right_value = _source_spec(right_reference)
    run_ids = [
        value
        for kind, value in ((left_kind, left_value), (right_kind, right_value))
        if kind == "run"
    ]
    run_rows = _run_rows_for_ids(owner, run_ids)

    def resolve(kind: DiffSourceKind, value: str) -> DiffSource:
        if kind == "file":
            return _file_source(owner, value, cfg)
        run = run_rows.get(value)
        if not run:
            raise DiffSourceError(f"completed run was not found: run:{value}", status_code=404)
        return _run_source(run)

    return resolve(left_kind, left_value), resolve(right_kind, right_value)


def diff_source_notice(source: DiffSource) -> str:
    if source.kind == "run" and source.partial:
        return f"diff: {source.reference} output is partial or exceeded comparison limits"
    return ""
