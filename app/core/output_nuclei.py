# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Structured Nuclei output metadata with trusted takeover context."""

from __future__ import annotations

import json
from typing import Any

from services.assessments.nuclei_takeover_observations import (
    ReviewedNucleiTakeoverTemplate,
    nuclei_takeover_json_metadata,
)
from services.nuclei.provenance import nuclei_source_detail, nuclei_template_provenance


NUCLEI_JSON_MAX_LINE_BYTES = 131_072


def nuclei_output_metadata(
    command: str,
    line_text: str,
    *,
    source_run_id: str = "",
    takeover_template: ReviewedNucleiTakeoverTemplate | None = None,
) -> dict[str, object]:
    """Return provenance for every line and bounded confirmation evidence for JSON."""
    row = _json_row(line_text)
    provenance = nuclei_template_provenance(command)
    metadata: dict[str, object] = {}
    if provenance:
        metadata["template_provenance"] = provenance
    source_detail = nuclei_source_detail(command, line_text=line_text, row=row)
    takeover = nuclei_takeover_json_metadata(
        row,
        source_run_id=source_run_id,
        template=takeover_template,
    )
    source_detail.update(takeover)
    if source_detail:
        metadata["source_detail"] = source_detail
    return metadata


def _json_row(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text.startswith("{") or len(text.encode("utf-8")) > NUCLEI_JSON_MAX_LINE_BYTES:
        return None
    try:
        row = json.loads(text)
    except json.JSONDecodeError:
        return None
    return row if isinstance(row, dict) else None


__all__ = ["NUCLEI_JSON_MAX_LINE_BYTES", "nuclei_output_metadata"]
