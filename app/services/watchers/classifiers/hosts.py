"""Host-list watcher diff classifier."""

from __future__ import annotations

from typing import Any

from services.watchers.classifiers import register_classifier
from services.watchers.classifiers.common import command_root, host_from_text, list_delta, normalized_lines
from services.watchers.models import DIFF_KIND_NONE, DIFF_KIND_SIGNAL, WatcherDiff

HOST_LIST_ROOTS = frozenset({"amass", "assetfinder", "dnsx", "httpx", "subfinder"})


def applies_to(command_text: str, _run: dict[str, Any], _conn=None) -> bool:
    return command_root(command_text) in HOST_LIST_ROOTS


def _hosts(run: dict[str, Any]) -> tuple[list[dict[str, str]], bool]:
    lines, output_info = normalized_lines(run)
    hosts = []
    seen = set()
    for line in lines:
        host = host_from_text(line)
        if not host or host in seen:
            continue
        seen.add(host)
        hosts.append({"key": host, "host": host, "line": line})
    return hosts, bool(output_info.get("partial"))


@register_classifier("hosts", applies_to=applies_to)
def diff(
    baseline_run: dict[str, Any],
    current_run: dict[str, Any],
    options: dict[str, bool] | None = None,
    _conn=None,
) -> WatcherDiff:
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
    return WatcherDiff(summary=summary, kind=kind, truncated=left_partial or right_partial or bool(delta["truncated"]))
