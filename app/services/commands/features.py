"""Shared feature gates for command discovery and autocomplete."""

from __future__ import annotations

from typing import Any, Mapping

import config as app_config
from services.commands.raw_packets import RAW_PACKET_TOOLS, raw_packet_scanning_active


def feature_enabled(feature: object, cfg: Mapping[str, Any] | None = None) -> bool:
    normalized = str(feature or "").strip().lower()
    if not normalized:
        return True
    active_cfg = app_config.CFG if cfg is None else cfg
    if normalized == "tour":
        return bool(active_cfg.get("tour_enabled", True))
    if normalized == "workspace":
        return bool(active_cfg.get("workspace_enabled", False))
    if normalized in {"interactive_pty", "pty"}:
        return bool(active_cfg.get("interactive_pty_enabled", False))
    if normalized == "raw_packet_scanning":
        return raw_packet_scanning_active(active_cfg, tool="nmap")
    prefix = "raw_packet_scanning_"
    if normalized.startswith(prefix) and normalized.removeprefix(prefix) in RAW_PACKET_TOOLS:
        return raw_packet_scanning_active(active_cfg, tool=normalized.removeprefix(prefix))
    return True


def suggestion_required_features(item: object) -> list[str]:
    if not isinstance(item, dict):
        return []
    feature_required = item.get("feature_required") or item.get("requires_feature") or item.get("feature")
    if isinstance(feature_required, (list, tuple, set)):
        required = [str(value).strip().lower() for value in feature_required if str(value).strip()]
    else:
        feature = str(feature_required or "").strip().lower()
        required = [feature] if feature else []
    interactive = item.get("interactive")
    if interactive is True or (isinstance(interactive, str) and interactive.strip().lower() in {"1", "true", "yes", "on"}):
        required.append("interactive_pty")
    return list(dict.fromkeys(required))


def suggestion_enabled_for_features(item: object, cfg: Mapping[str, Any] | None = None) -> bool:
    return all(feature_enabled(feature, cfg) for feature in suggestion_required_features(item))
