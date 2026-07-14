# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Host-list diff classifier."""

from __future__ import annotations

from typing import Any

from services.diff.classifiers import register_classifier
from services.diff.classifiers.common import command_root, host_from_text, list_delta, normalized_line_records
from services.diff.models import DIFF_KIND_NONE, DIFF_KIND_SIGNAL, DiffResult

HOST_LIST_ROOTS = frozenset({"amass", "assetfinder", "dnsx", "httpx", "subfinder"})


def applies_to(command_text: str, _run: dict[str, Any], _conn=None) -> bool:
    return command_root(command_text) in HOST_LIST_ROOTS


def _hosts(run: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    records, output_info = normalized_line_records(run)
    hosts = []
    seen = set()
    for record in records:
        line = str(record.get("line") or "")
        host = host_from_text(line)
        if not host or host in seen:
            continue
        seen.add(host)
        item: dict[str, Any] = {"key": host, "host": host, "line": line}
        line_index = record.get("line_index")
        if isinstance(line_index, int) and not isinstance(line_index, bool):
            item["line_index"] = line_index
        hosts.append(item)
    return hosts, bool(output_info.get("partial"))


@register_classifier("hosts", applies_to=applies_to)
def diff(
    baseline_run: dict[str, Any],
    current_run: dict[str, Any],
    options: dict[str, bool] | None = None,
    _conn=None,
) -> DiffResult:
    left, left_partial = _hosts(baseline_run)
    right, right_partial = _hosts(current_run)
    delta = list_delta(left, right)
    effective_removed_count = 0 if bool((options or {}).get("suppress_removals")) else int(delta["removed_count"])
    summary = {
        "classifier": "hosts",
        "added_host_count": int(delta["added_count"]),
        "removed_host_count": int(delta["removed_count"]),
        "suppressed_removed_host_count": int(delta["removed_count"]) - effective_removed_count,
        "unchanged_host_count": int(delta["unchanged_count"]),
        "added_hosts": delta["added"],
        "removed_hosts": delta["removed"] if effective_removed_count else [],
    }
    kind = DIFF_KIND_SIGNAL if int(delta["added_count"]) or effective_removed_count else DIFF_KIND_NONE
    return DiffResult(summary=summary, kind=kind, truncated=left_partial or right_partial or bool(delta["truncated"]))
