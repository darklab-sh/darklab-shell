# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared diff data models and constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DIFF_KIND_SIGNAL = "signal"
DIFF_KIND_TEXTUAL = "textual"
DIFF_KIND_NONE = "none"
DIFF_KINDS = frozenset({DIFF_KIND_SIGNAL, DIFF_KIND_TEXTUAL, DIFF_KIND_NONE})


@dataclass(frozen=True)
class DiffResult:
    summary: dict[str, Any]
    kind: str
    truncated: bool = False


WatcherDiff = DiffResult

