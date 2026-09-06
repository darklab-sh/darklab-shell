# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Command-specific state for streamed entity extraction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from core.output_dns_entities import DnsEntityState
from core.output_whois_entities import WhoisEntityState


class CommandEntityState(Protocol):
    def entities_for_line(self, text: str, source_line: int | None) -> list[dict[str, object]]: ...


def command_entity_state(
    root: str,
    command: str,
    target: str | None,
    extra_domain_suffixes: Sequence[str] = (),
) -> CommandEntityState | None:
    if root in {"dig", "nslookup"}:
        return DnsEntityState(command, extra_domain_suffixes)
    if root == "whois":
        return WhoisEntityState(target, extra_domain_suffixes)
    return None


__all__ = ["CommandEntityState", "command_entity_state"]
