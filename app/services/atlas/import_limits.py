"""Atlas import limit configuration and safe workflow errors."""

from __future__ import annotations

import logging
from typing import Any

from config import resolve_effective_cfg
from services.atlas.import_helpers import safe_label as _safe_label
from services.atlas.import_parser import ImportParserLimits

log = logging.getLogger("shell")

DRAFT_TTL_MINUTES = 30
PREVIEW_SAMPLE_LIMIT = 20
WARNING_SAMPLE_LIMIT = 50
DEFAULT_MAX_UPLOAD_MB = 10
DEFAULT_MAX_ROWS = 5000
DEFAULT_MAX_FINDINGS = 5000
DEFAULT_MAX_WARNINGS = 100
DEFAULT_MAX_XML_ELEMENTS = 100000
_INVALID_CFG_LIMIT_WARNED: set[str] = set()


class AtlasImportError(ValueError):
    """Safe import workflow error intended for JSON responses."""

    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def cfg_limit(key: str, default: int) -> int:
    raw_value = resolve_effective_cfg().get(key, default)
    invalid = False
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
        invalid = True
    if value <= 0:
        value = default
        invalid = True
    if invalid and key not in _INVALID_CFG_LIMIT_WARNED:
        _INVALID_CFG_LIMIT_WARNED.add(key)
        log.warning("ATLAS_IMPORT_CONFIG_LIMIT_INVALID", extra={
            "key": key,
            "default": default,
            "configured_type": type(raw_value).__name__[:64],
            "configured_value": _safe_label(raw_value, 120),
        })
    return value


def draft_ttl_minutes() -> int:
    return cfg_limit("atlas_import_draft_ttl_minutes", DRAFT_TTL_MINUTES)


def preview_sample_limit() -> int:
    return cfg_limit("atlas_import_preview_sample_limit", PREVIEW_SAMPLE_LIMIT)


def warning_sample_limit() -> int:
    return cfg_limit("atlas_import_warning_sample_limit", WARNING_SAMPLE_LIMIT)


def parser_limits() -> ImportParserLimits:
    return ImportParserLimits(
        max_upload_bytes=cfg_limit("atlas_import_max_upload_mb", DEFAULT_MAX_UPLOAD_MB) * 1024 * 1024,
        max_rows=cfg_limit("atlas_import_max_rows", DEFAULT_MAX_ROWS),
        max_warnings=cfg_limit("atlas_import_max_warnings", DEFAULT_MAX_WARNINGS),
        max_xml_elements=cfg_limit("atlas_import_max_xml_elements", DEFAULT_MAX_XML_ELEMENTS),
    )


def raise_import_limit_rejected(
    *,
    limit_key: str,
    configured_limit: int,
    actual_count: int,
    stage: str,
    draft_id: str = "",
    format_id: str = "",
    team_id: str = "",
    message: str,
) -> None:
    log.warning("ATLAS_IMPORT_LIMIT_REJECTED", extra={
        "limit_key": limit_key,
        "configured_limit": configured_limit,
        "actual_count": actual_count,
        "draft_id": draft_id,
        "format_id": format_id,
        "team_id": team_id,
        "stage": stage,
    })
    raise AtlasImportError("import_limit_exceeded", message)


def enforce_import_limits(
    counts: dict[str, Any],
    normalized_rows: dict[str, Any],
    *,
    stage: str,
    draft_id: str = "",
    format_id: str = "",
    team_id: str = "",
) -> None:
    rows = int(counts.get("rows") or 0)
    raw_findings = normalized_rows.get("findings")
    raw_warnings = normalized_rows.get("warnings")
    findings = raw_findings if isinstance(raw_findings, list) else []
    warnings = raw_warnings if isinstance(raw_warnings, list) else []
    max_rows = cfg_limit("atlas_import_max_rows", DEFAULT_MAX_ROWS)
    max_findings = cfg_limit("atlas_import_max_findings", DEFAULT_MAX_FINDINGS)
    max_warnings = cfg_limit("atlas_import_max_warnings", DEFAULT_MAX_WARNINGS)
    if rows > max_rows:
        raise_import_limit_rejected(
            limit_key="atlas_import_max_rows",
            configured_limit=max_rows,
            actual_count=rows,
            draft_id=draft_id,
            format_id=format_id,
            team_id=team_id,
            stage=stage,
            message=f"Import row count exceeds the configured limit ({max_rows}).",
        )
    if len(findings) > max_findings:
        raise_import_limit_rejected(
            limit_key="atlas_import_max_findings",
            configured_limit=max_findings,
            actual_count=len(findings),
            draft_id=draft_id,
            format_id=format_id,
            team_id=team_id,
            stage=stage,
            message=f"Import finding count exceeds the configured limit ({max_findings}).",
        )
    if len(warnings) > max_warnings:
        raise_import_limit_rejected(
            limit_key="atlas_import_max_warnings",
            configured_limit=max_warnings,
            actual_count=len(warnings),
            draft_id=draft_id,
            format_id=format_id,
            team_id=team_id,
            stage=stage,
            message=f"Import warning count exceeds the configured limit ({max_warnings}).",
        )
