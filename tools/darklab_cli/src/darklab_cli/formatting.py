# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable text and JSON formatting helpers for darklab CLI commands."""

from __future__ import annotations

import json
from typing import Any

from .client import print_json


def print_payload(payload: Any, output_format: str) -> int:
    if output_format == "json":
        print_json(payload)
        return 0
    if isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}: {_format_table_value(value)}")
        return 0
    print(payload)
    return 0


def print_collection(
    payload: dict[str, Any],
    key: str,
    output_format: str,
    *,
    fields: tuple[str, ...],
    reverse: bool = False,
) -> int:
    items = payload.get(key) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []
    if reverse:
        items = list(reversed(items))
    if output_format == "json":
        if isinstance(payload, dict):
            payload = {**payload, key: items}
        print_json(payload)
        return 0
    if output_format == "ndjson":
        for item in items:
            print(json.dumps(item, sort_keys=True))
        return 0
    print_table([item for item in items if isinstance(item, dict)], fields)
    return 0


def print_table(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    if not rows:
        print("No results.")
        return
    headers = tuple(_field_header(field) for field in fields)
    rendered_rows = [[_format_table_value(row.get(field)) for field in fields] for row in rows]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rendered_rows))
        for index in range(len(fields))
    ]
    print("  ".join(headers[index].ljust(widths[index]) for index in range(len(headers))))
    print("  ".join("-" * width for width in widths))
    for row in rendered_rows:
        print("  ".join(row[index].ljust(widths[index]) for index in range(len(fields))))


def _field_header(field: str) -> str:
    aliases = {"byte_size": "BYTES",
        "canonical_value": "VALUE",
        "display_name": "NAME",
        "exit_code": "EXIT",
        "occurrence_count": "OCCURRENCES",
        "run_kind": "KIND",
    }
    return aliases.get(field, field.replace("_", " ").upper())


def _format_table_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


__all__ = ["print_collection", "print_payload", "print_table"]
