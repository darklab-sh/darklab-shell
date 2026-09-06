# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Target-aware entity extraction for WHOIS output."""

from __future__ import annotations

from collections.abc import Sequence
import re

from core.output_entities import (
    _add_entity,
    _domain_candidate_has_allowed_suffix,
    _is_public_ip,
)
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip


class WhoisEntityState:
    """Emit one validated command target and ignore registry response metadata."""

    def __init__(self, target: str | None, extra_domain_suffixes: Sequence[str] = ()) -> None:
        self.target = str(target or "").strip().rstrip(".")
        self.extra_domain_suffixes = tuple(extra_domain_suffixes)
        self.entity_type, self.canonical_value = self._canonical_target()
        self.emitted = False

    def entities_for_line(self, text: str, source_line: int | None) -> list[dict[str, object]]:
        stripped = str(text or "").strip()
        if self.emitted or not stripped or not self.entity_type:
            return []
        self.emitted = True
        match = re.search(re.escape(self.target), stripped, re.I) if self.target else None
        entities: list[dict[str, object]] = []
        _add_entity(
            entities,
            set(),
            entity_type=self.entity_type,
            value=self.target,
            canonical_value=self.canonical_value,
            source_line=source_line,
            start=match.start() if match else None,
            end=match.end() if match else None,
        )
        return entities

    def _canonical_target(self) -> tuple[str, str]:
        try:
            canonical = canonical_ip(self.target)
        except CanonicalizationError:
            canonical = ""
        if canonical:
            return ("ip", canonical) if _is_public_ip(canonical) else ("", "")
        try:
            canonical = canonical_domain(self.target)
        except CanonicalizationError:
            return "", ""
        if not _domain_candidate_has_allowed_suffix(canonical, self.extra_domain_suffixes):
            return "", ""
        return "domain", canonical


__all__ = ["WhoisEntityState"]
