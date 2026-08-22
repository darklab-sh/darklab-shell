# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Readable assessment lifecycle output for the headless CLI."""

from __future__ import annotations

from typing import Any

from ..errors import DarklabCliError
from ..formatting import print_payload, print_table


_ASSESSMENT_FIELDS = ("id", "status", "profile_key", "profile_version", "title")


def print_assessment_result(payload: Any, output_format: str) -> int:
    if output_format == "json":
        return print_payload(payload, "json")
    assessment = payload.get("assessment") if isinstance(payload, dict) else None
    if not isinstance(assessment, dict):
        raise DarklabCliError("assessment lifecycle response is invalid")
    print_table([assessment], _ASSESSMENT_FIELDS)
    return 0


def print_assessment_delete_preview(payload: Any, heading: str = "Assessment deletion preview:") -> None:
    raw_preview = payload.get("preview") if isinstance(payload, dict) else None
    if not isinstance(raw_preview, dict):
        raise DarklabCliError("assessment deletion preview response is invalid")
    preview: dict[str, Any] = raw_preview
    assessment = preview.get("assessment")
    if not isinstance(assessment, dict):
        raise DarklabCliError("assessment deletion preview is missing its assessment")
    print(heading)
    print_table([assessment], _ASSESSMENT_FIELDS)
    raw_counts = preview.get("will_delete")
    counts: dict[str, Any] = raw_counts if isinstance(raw_counts, dict) else {}
    count_rows = [
        {"record": key.replace("_", " "), "count": value}
        for key, value in counts.items()
        if key != "evidence_links_by_type"
    ]
    print("Assessment-owned records to delete:")
    print_table(count_rows, ("record", "count"))
    print(
        "Source records preserved: "
        f"{'yes' if not preview.get('source_records_deleted') else 'no'}"
    )
    if not preview.get("can_delete"):
        print("Deletion unavailable: archive this assessment first.")


def print_assessment_deleted(payload: Any, output_format: str) -> int:
    if output_format == "json":
        return print_payload(payload, "json")
    deleted = payload.get("deleted") if isinstance(payload, dict) else None
    if not isinstance(deleted, dict):
        raise DarklabCliError("assessment deletion response is invalid")
    print_assessment_delete_preview({"preview": deleted}, "Assessment deleted:")
    return 0


__all__ = [
    "print_assessment_delete_preview",
    "print_assessment_deleted",
    "print_assessment_result",
]
