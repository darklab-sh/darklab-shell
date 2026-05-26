"""Scheduled and recurring run helpers."""

from __future__ import annotations

from config import CFG


def scheduler_cfg() -> dict:
    cfg = CFG.get("scheduler", {})
    return cfg if isinstance(cfg, dict) else {}
