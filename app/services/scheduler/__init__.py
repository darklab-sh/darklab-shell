"""Scheduled and recurring run helpers."""

from __future__ import annotations

from config import resolve_effective_cfg


def scheduler_cfg() -> dict:
    cfg = resolve_effective_cfg().get("scheduler", {})
    return cfg if isinstance(cfg, dict) else {}
