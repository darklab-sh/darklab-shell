# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Adapters from shared diff classifiers to run-comparison derived groups."""

from __future__ import annotations

import shlex
from typing import Any

from core.output_signals import extract_target


DERIVED_CHANGE_LIMIT = 1000


def _command_root(run: dict[str, Any]) -> str:
    command = str(run.get("command") or "").strip()
    if not command:
        return ""
    try:
        return shlex.split(command)[0].lower()
    except ValueError:
        return command.split()[0].lower() if command.split() else ""


def _prepared_run(run: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        **run,
        "_comparison_entries": entries,
        "_comparison_output_info": {
            "partial": bool(run.get("preview_truncated") or run.get("full_output_truncated")),
        },
    }


def _line_indexes(entries: list[dict[str, Any]]) -> dict[int, int]:
    indexes = {}
    for compare_index, entry in enumerate(entries):
        line_index = entry.get("line_index")
        if isinstance(line_index, int) and not isinstance(line_index, bool) and line_index not in indexes:
            indexes[line_index] = compare_index
    return indexes


def _with_line_pointer(item: dict[str, Any], indexes: dict[int, int], side: str) -> dict[str, Any]:
    enriched = dict(item)
    line_index = enriched.get("line_index")
    if isinstance(line_index, int) and not isinstance(line_index, bool) and line_index in indexes:
        enriched["compare_line_index"] = indexes[line_index]
        enriched["compare_side"] = side
    return enriched


def _same_root_applies(classifier, left_run: dict[str, Any], right_run: dict[str, Any]) -> bool:
    left_root = _command_root(left_run)
    right_root = _command_root(right_run)
    return bool(
        left_root
        and left_root == right_root
        and classifier.applies_to(str(left_run.get("command") or ""), left_run)
        and classifier.applies_to(str(right_run.get("command") or ""), right_run)
    )


def _target_metadata(left_run: dict[str, Any], right_run: dict[str, Any], fallback: str):
    def command_target(run: dict[str, Any]) -> str:
        command = str(run.get("command") or "")
        target = str(extract_target(command) or "")
        if target:
            return target
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        for flag in ("-d", "--domain", "-domain"):
            if flag in tokens:
                index = tokens.index(flag) + 1
                return str(tokens[index]) if index < len(tokens) else ""
        return ""

    left_target = command_target(left_run)
    right_target = command_target(right_run)
    ambiguous = bool(left_target and right_target and left_target != right_target)
    target = "" if ambiguous else right_target or left_target
    return target, target or ("multiple targets" if ambiguous else fallback), ambiguous


def _host_group(
    left_run: dict[str, Any],
    right_run: dict[str, Any],
    left_entries: list[dict[str, Any]],
    right_entries: list[dict[str, Any]],
) -> dict[str, Any] | None:
    from services.diff.classifiers import hosts  # noqa: PLC0415

    if not _same_root_applies(hosts, left_run, right_run):
        return None
    result = hosts.diff(
        _prepared_run(left_run, left_entries),
        _prepared_run(right_run, right_entries), None, None,
    )
    summary = result.summary
    if (
        not int(summary.get("added_host_count") or 0)
        and not int(summary.get("removed_host_count") or 0)
        and not result.truncated
    ):
        return None
    target, display_target, target_ambiguous = _target_metadata(left_run, right_run, "hosts")
    left_indexes = _line_indexes(left_entries)
    right_indexes = _line_indexes(right_entries)
    added = [
        _with_line_pointer(item, right_indexes, "right")
        for item in summary.get("added_hosts", [])[:DERIVED_CHANGE_LIMIT]
    ]
    removed = [
        _with_line_pointer(item, left_indexes, "left")
        for item in summary.get("removed_hosts", [])[:DERIVED_CHANGE_LIMIT]
    ]
    return {
        "id": "discovered_hosts",
        "kind": "hosts",
        "classifier": "hosts",
        "title": "Discovered hosts",
        "command_root": _command_root(right_run),
        "target": target,
        "display_target": display_target,
        "target_ambiguous": target_ambiguous,
        "note": "Host results may be incomplete." if result.truncated else "",
        "added": added,
        "removed": removed,
        "changed": [],
        "added_count": int(summary.get("added_host_count") or 0),
        "removed_count": int(summary.get("removed_host_count") or 0),
        "changed_count": 0,
        "truncated": bool(result.truncated),
    }


def _tls_group(
    left_run: dict[str, Any],
    right_run: dict[str, Any],
    left_entries: list[dict[str, Any]],
    right_entries: list[dict[str, Any]],
) -> dict[str, Any] | None:
    from services.diff.classifiers import tls  # noqa: PLC0415

    if not _same_root_applies(tls, left_run, right_run):
        return None
    result = tls.diff(
        _prepared_run(left_run, left_entries),
        _prepared_run(right_run, right_entries), None, None,
    )
    changed_rows = result.summary.get("changed_tls_fields", [])
    if not changed_rows and not result.truncated:
        return None
    target, display_target, target_ambiguous = _target_metadata(
        left_run,
        right_run,
        "TLS certificate",
    )
    changed = [
        {
            "key": str(item.get("field") or ""),
            "before": {"field": item.get("field"), "value": item.get("before", "")},
            "after": {"field": item.get("field"), "value": item.get("after", "")},
        }
        for item in changed_rows[:DERIVED_CHANGE_LIMIT]
    ]
    return {
        "id": "tls_certificate",
        "kind": "tls",
        "classifier": "tls",
        "title": "TLS certificate",
        "command_root": _command_root(right_run),
        "target": target,
        "display_target": display_target,
        "target_ambiguous": target_ambiguous,
        "note": "TLS results may be incomplete." if result.truncated else "",
        "added": [],
        "removed": [],
        "changed": changed,
        "added_count": 0,
        "removed_count": 0,
        "changed_count": int(result.summary.get("changed_tls_field_count") or 0),
        "truncated": bool(result.truncated),
    }


def compare_additional_derived_groups(
    left_run: dict[str, Any],
    right_run: dict[str, Any],
    left_entries: list[dict[str, Any]],
    right_entries: list[dict[str, Any]],
    *,
    skip_hosts: bool = False,
) -> list[dict[str, Any]]:
    groups = []
    if not skip_hosts:
        host_group = _host_group(left_run, right_run, left_entries, right_entries)
        if host_group is not None:
            groups.append(host_group)
    tls_group = _tls_group(left_run, right_run, left_entries, right_entries)
    if tls_group is not None:
        groups.append(tls_group)
    return groups
