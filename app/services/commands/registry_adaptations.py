"""Shared normalization and gating helpers for declarative runtime adaptations."""

from __future__ import annotations

import re
from typing import Any, Mapping

from services.commands.raw_packets import raw_packet_scanning_active


_INJECT_BOOL_FIELDS = (
    "requires_workspace",
    "requires_raw_packets",
    "unless_raw_packets",
    "requires_restricted_cidrs",
)


def copy_inject_conditions(source: Mapping[str, Any], target: dict[str, object]) -> None:
    for field in _INJECT_BOOL_FIELDS:
        if source.get(field):
            target[field] = True


def copy_environment_conditions(source: Mapping[str, Any], target: dict[str, object]) -> None:
    if source.get("requires_raw_packets"):
        target["requires_raw_packets"] = True
    unless_any = [str(token).strip() for token in source.get("unless_any", []) or [] if str(token).strip()]
    if unless_any:
        target["unless_any"] = unless_any


def inject_merge_key(item: Mapping[str, Any]) -> tuple[object, ...]:
    return (
        tuple(item.get("flags", []) or []),
        item.get("position"),
        tuple(item.get("unless_any", []) or []),
        tuple(item.get("unless_any_regex", []) or []),
        *(bool(item.get(field)) for field in _INJECT_BOOL_FIELDS[1:]),
    )


def environment_merge_key(item: Mapping[str, Any]) -> tuple[object, ...]:
    return (
        item.get("name"),
        item.get("value"),
        item.get("managed_directory_flag"),
        bool(item.get("requires_raw_packets")),
        tuple(item.get("unless_any", []) or []),
    )


def runtime_injection_blocked(tokens: list[str], inject: Mapping[str, Any]) -> bool:
    unless_any = [str(item) for item in inject.get("unless_any", []) or [] if str(item)]
    if any(
        token == blocker or token.startswith(f"{blocker}=")
        for blocker in unless_any
        for token in tokens[1:]
    ):
        return True
    for raw_pattern in inject.get("unless_any_regex", []) or []:
        try:
            if any(re.search(str(raw_pattern), token) for token in tokens[1:]):
                return True
        except re.error:
            continue
    return False


def runtime_adaptation_enabled(
    adaptation: Mapping[str, object],
    cfg: Mapping[str, Any],
    *,
    tool: str,
    workspace_ready: bool = False,
) -> bool:
    if adaptation.get("requires_workspace") and not workspace_ready:
        return False
    if adaptation.get("requires_restricted_cidrs") and not cfg.get("restricted_command_input_cidrs"):
        return False
    if adaptation.get("requires_raw_packets") or adaptation.get("unless_raw_packets"):
        raw_active = raw_packet_scanning_active(cfg, tool=tool)
        if adaptation.get("requires_raw_packets") and not raw_active:
            return False
        if adaptation.get("unless_raw_packets") and raw_active:
            return False
    return True
