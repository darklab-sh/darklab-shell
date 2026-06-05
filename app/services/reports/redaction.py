"""Report redaction helpers."""

from __future__ import annotations

from services.projects.packages import package_redaction_rules

from .models import normalize_report_export_prefs


def report_redaction_rules(export_prefs: dict | None, *, cfg=None):
    prefs = normalize_report_export_prefs(export_prefs or {})
    return package_redaction_rules(prefs["redaction_mode"], cfg=cfg)
