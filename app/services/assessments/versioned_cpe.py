# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact CPE 2.3 normalization shared by structured evidence parsers."""

from __future__ import annotations

import re
from typing import Any

from services.assessments.cpe_applicability import normalize_observed_cpe


_CPE_COMPONENT_RE = re.compile(r"^[a-z0-9._-]{1,128}$", re.I)


def normalize_versioned_cpe(value: Any) -> str:
    """Return one exact versioned CPE 2.3 identifier or an empty string."""
    raw = str(value or "").strip()
    if normalize_observed_cpe(raw) is not None:
        return raw
    if not raw.startswith("cpe:/"):
        return ""
    components = raw[5:].split(":")
    if not 4 <= len(components) <= 7 or components[0] not in {"a", "h", "o"}:
        return ""
    if any(not _CPE_COMPONENT_RE.fullmatch(component) for component in components[:4]):
        return ""
    if any(component and not _CPE_COMPONENT_RE.fullmatch(component) for component in components[4:]):
        return ""
    legacy = components + ["*"] * (7 - len(components))
    fields = [*legacy, "*", "*", "*", "*"]
    candidate = "cpe:2.3:" + ":".join(component or "*" for component in fields)
    return candidate if normalize_observed_cpe(candidate) is not None else ""


__all__ = ["normalize_versioned_cpe"]
