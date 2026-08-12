# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Frozen-check and digest helpers for Assessment action plans."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend


def frozen_check(row: Any) -> Mapping[str, Any] | None:
    """Return the exact frozen definition for a persisted check row."""
    snapshot = dialect_for_backend(get_db_backend()).decode_json_dict(
        row["profile_snapshot"]
    )
    check_key = str(row["check_key"] or "")
    for item in snapshot.get("checks", []):
        if isinstance(item, Mapping) and str(item.get("key") or "") == check_key:
            return item
    return None


def digest_plan(payload: Mapping[str, Any]) -> str:
    """Return the stable digest used for launch and reservation confirmation."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["digest_plan", "frozen_check"]
