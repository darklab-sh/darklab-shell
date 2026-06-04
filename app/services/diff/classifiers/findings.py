"""Structured finding diff classifier."""

from __future__ import annotations

from typing import Any

from services.diff.classifiers import register_classifier
from services.diff.classifiers.common import list_delta
from services.diff.models import DIFF_KIND_NONE, DIFF_KIND_SIGNAL, DiffResult


def applies_to(_command_text: str, run: dict[str, Any], conn=None) -> bool:
    if conn is None:
        return False
    run_id = str(run.get("id") or "")
    session_id = str(run.get("session_id") or "")
    if not run_id or not session_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM findings f JOIN findings_occurrences fo ON fo.finding_id = f.id "
        "WHERE f.session_id = ? AND fo.run_id = ? LIMIT 1",
        (session_id, run_id),
    ).fetchone()
    return row is not None


def _items(conn, run: dict[str, Any]) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT f.id, f.signature_hash, f.fingerprint, f.title, f.raw_line, f.severity, fo.line_number "
        "FROM findings f JOIN findings_occurrences fo ON fo.finding_id = f.id "
        "WHERE f.session_id = ? AND fo.run_id = ? "
        "ORDER BY fo.line_number ASC, f.id ASC",
        (str(run.get("session_id") or ""), str(run.get("id") or "")),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["key"] = str(item.get("signature_hash") or item.get("fingerprint") or item.get("id") or "")
        items.append({
            "key": item["key"],
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "severity": str(item.get("severity") or ""),
            "line_number": item.get("line_number"),
            "raw_line": str(item.get("raw_line") or ""),
        })
    return items


@register_classifier("findings", applies_to=applies_to)
def diff(
    baseline_run: dict[str, Any],
    current_run: dict[str, Any],
    options: dict[str, bool] | None = None,
    conn=None,
) -> DiffResult:
    if conn is None:
        return DiffResult(summary={"classifier": "findings", "error": "missing connection"}, kind=DIFF_KIND_NONE)
    delta = list_delta(_items(conn, baseline_run), _items(conn, current_run))
    effective_removed_count = 0 if bool((options or {}).get("suppress_removals")) else int(delta["removed_count"])
    summary = {
        "classifier": "findings",
        "added_finding_count": int(delta["added_count"]),
        "removed_finding_count": int(delta["removed_count"]),
        "suppressed_removed_finding_count": int(delta["removed_count"]) - effective_removed_count,
        "unchanged_finding_count": int(delta["unchanged_count"]),
        "added_findings": delta["added"],
        "removed_findings": delta["removed"] if effective_removed_count else [],
    }
    kind = DIFF_KIND_SIGNAL if int(delta["added_count"]) or effective_removed_count else DIFF_KIND_NONE
    return DiffResult(summary=summary, kind=kind, truncated=bool(delta["truncated"]))

