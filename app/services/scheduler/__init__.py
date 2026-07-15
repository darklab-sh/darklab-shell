# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scheduled and recurring run helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from config import resolve_effective_cfg


def scheduler_cfg() -> Mapping[str, Any]:
    cfg = resolve_effective_cfg().get("scheduler", {})
    return cfg if isinstance(cfg, Mapping) else {}
