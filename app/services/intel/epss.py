# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalization for the keyless FIRST EPSS CSV feed."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from services.intel.canonical import CanonicalizationError, canonical_cve

MAX_EPSS_ROWS = 2048


def normalize_epss_rows(raw: object) -> list[dict[str, Any]]:
    """Parse bounded EPSS CSV rows into canonical CVE risk records."""
    text = str(raw or "")
    if len(text.encode("utf-8")) > 2 * 1024 * 1024:
        return []
    rows: list[dict[str, Any]] = []
    feed = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for row in csv.DictReader(StringIO(feed)):
        if len(rows) >= MAX_EPSS_ROWS:
            break
        try:
            cve = canonical_cve(str(row.get("cve") or ""))
        except CanonicalizationError:
            continue
        if not cve:
            continue
        try:
            score = float(row.get("epss") or "")
            percentile = float(row.get("percentile") or "")
        except (TypeError, ValueError):
            continue
        if not 0 <= score <= 1 or not 0 <= percentile <= 1:
            continue
        rows.append({"cve": cve, "epss": score, "percentile": percentile, "date": str(row.get("date") or "")[:32]})
    return rows
