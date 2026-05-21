"""Port/service watcher diff classifier for nmap-shaped output."""

from __future__ import annotations

import re
from typing import Any

from services.watchers.classifiers import register_classifier
from services.watchers.classifiers.common import command_root, normalized_lines
from services.watchers.models import DIFF_KIND_NONE, DIFF_KIND_SIGNAL, WatcherDiff

_PORT_RE = re.compile(r"^(?P<port>\d{1,5})/(?P<proto>tcp|udp)\s+(?P<state>\S+)(?:\s+(?P<service>\S+))?", re.I)


def applies_to(command_text: str, _run: dict[str, Any], _conn=None) -> bool:
    return command_root(command_text) == "nmap"


def _ports(run: dict[str, Any]) -> tuple[dict[str, dict[str, str]], bool]:
    lines, output_info = normalized_lines(run)
    ports: dict[str, dict[str, str]] = {}
    for line in lines:
        match = _PORT_RE.match(line)
        if not match:
            continue
        key = f"{match.group('port')}/{match.group('proto').lower()}"
        ports[key] = {
            "key": key,
            "port": match.group("port"),
            "proto": match.group("proto").lower(),
            "state": match.group("state").lower(),
            "service": (match.group("service") or "").lower(),
            "line": line,
        }
    return ports, bool(output_info.get("partial"))


@register_classifier("ports", applies_to=applies_to)
def diff(
    baseline_run: dict[str, Any],
    current_run: dict[str, Any],
    options: dict[str, bool] | None = None,
    _conn=None,
) -> WatcherDiff:
    left, left_partial = _ports(baseline_run)
    right, right_partial = _ports(current_run)
    added_keys = sorted(set(right) - set(left))
    removed_keys = sorted(set(left) - set(right))
    changed_keys = sorted(
        key for key in set(left) & set(right)
        if left[key]["state"] != right[key]["state"] or left[key]["service"] != right[key]["service"]
    )
    effective_removed = [] if bool((options or {}).get("suppress_removals")) else removed_keys
    summary = {
        "classifier": "ports",
        "added_port_count": len(added_keys),
        "removed_port_count": len(removed_keys),
        "changed_port_count": len(changed_keys),
        "suppressed_removed_port_count": len(removed_keys) - len(effective_removed),
        "added_ports": [right[key] for key in added_keys[:1000]],
        "removed_ports": [left[key] for key in effective_removed[:1000]],
        "changed_ports": [
            {"key": key, "before": left[key], "after": right[key]}
            for key in changed_keys[:1000]
        ],
    }
    truncated = left_partial or right_partial or len(added_keys) + len(effective_removed) + len(changed_keys) > 1000
    kind = DIFF_KIND_SIGNAL if added_keys or effective_removed or changed_keys else DIFF_KIND_NONE
    return WatcherDiff(summary=summary, kind=kind, truncated=truncated)
