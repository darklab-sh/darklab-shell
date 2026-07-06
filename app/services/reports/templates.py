"""Config-backed report template catalog."""

from __future__ import annotations

from collections.abc import Mapping

from copy import deepcopy
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
from typing import Any

import config as _config
from services.projects.contracts import ProjectWorkspaceError
from services.projects.utils import trim_text as _trim_text

from .models import REPORT_SECTION_TYPES, normalize_report_sections


REPORT_TEMPLATE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
REPORT_TEMPLATE_MAX_TEMPLATES = 25
REPORT_TEMPLATE_LABEL_MAX_LEN = 80
REPORT_TEMPLATE_DESCRIPTION_MAX_LEN = 1000

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportTemplateCatalog:
    source_path: str
    templates: tuple[dict[str, Any], ...]


_CATALOG_CACHE: dict[str, object] = {
    "signature": None,
    "catalog": None,
}


def _conf_dir() -> Path:
    return Path(_config.APP_CONF_DIR) if _config.APP_CONF_DIR else Path(__file__).resolve().parents[2] / "conf"


def _bundled_conf_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "conf"


def default_report_templates_path() -> Path:
    return _bundled_conf_dir() / "report_templates.yaml"


def configured_report_templates_path(cfg: Mapping[str, Any] | None = None) -> Path:
    active_cfg = cfg or _config.CFG
    raw_path = str(active_cfg.get("report_templates_file") or "report_templates.yaml").strip()
    path = Path(raw_path or "report_templates.yaml")
    return path if path.is_absolute() else _conf_dir() / path


def _catalog_signature(path: Path) -> tuple[str, int | None, int | None]:
    normalized = os.path.abspath(path)
    try:
        stat = os.stat(normalized)
    except OSError:
        return (normalized, None, None)
    return (normalized, stat.st_mtime_ns, stat.st_size)


def _load_yaml_catalog(path: Path) -> dict:
    return _config._load_yaml_config_optional(path)


def normalize_report_template_entry(entry: object) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ProjectWorkspaceError("report template entries must be objects")
    template_id = str(entry.get("id") or "").strip().lower()
    if not REPORT_TEMPLATE_ID_RE.fullmatch(template_id):
        raise ProjectWorkspaceError("report template id must use lowercase letters, numbers, underscores, or hyphens")
    label = _trim_text(entry.get("label"), REPORT_TEMPLATE_LABEL_MAX_LEN) or template_id.replace("_", " ").title()
    description = _trim_text(entry.get("description"), REPORT_TEMPLATE_DESCRIPTION_MAX_LEN)
    sections = normalize_report_sections(entry.get("sections"))
    section_types = {section["type"] for section in sections}
    missing = [section_type for section_type in REPORT_SECTION_TYPES if section_type not in section_types]
    if missing:
        raise ProjectWorkspaceError(f"report template missing sections: {', '.join(missing)}")
    return {
        "id": template_id,
        "label": label,
        "description": description,
        "sections": sections,
    }


def normalize_report_template_catalog(data: object, *, source_path: str = "") -> ReportTemplateCatalog:
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("report template catalog must be an object")
    raw_templates = data.get("templates")
    if not isinstance(raw_templates, list):
        raise ProjectWorkspaceError("report template catalog must define a templates list")
    if len(raw_templates) > REPORT_TEMPLATE_MAX_TEMPLATES:
        raise ProjectWorkspaceError("report template catalog exceeds the configured template cap")
    templates = []
    seen_ids = set()
    for raw_entry in raw_templates:
        template = normalize_report_template_entry(raw_entry)
        template_id = str(template["id"])
        if template_id in seen_ids:
            raise ProjectWorkspaceError(f"duplicate report template id: {template_id}")
        seen_ids.add(template_id)
        templates.append(template)
    if not templates:
        raise ProjectWorkspaceError("report template catalog must define at least one template")
    return ReportTemplateCatalog(source_path=source_path, templates=tuple(templates))


def clear_report_template_catalog_cache() -> None:
    _CATALOG_CACHE["signature"] = None
    _CATALOG_CACHE["catalog"] = None


def load_report_template_catalog(cfg: Mapping[str, Any] | None = None) -> ReportTemplateCatalog:
    path = configured_report_templates_path(cfg)
    default_path = default_report_templates_path()
    signature = (
        _catalog_signature(path),
        _catalog_signature(default_path) if path != default_path else None,
    )
    cached = _CATALOG_CACHE.get("catalog")
    if _CATALOG_CACHE.get("signature") == signature and isinstance(cached, ReportTemplateCatalog):
        return cached

    data = _load_yaml_catalog(path)
    try:
        catalog = normalize_report_template_catalog(data, source_path=str(path))
    except ProjectWorkspaceError as exc:
        if path == default_path:
            raise
        log.warning(
            "REPORT_TEMPLATES_OVERRIDE_INVALID",
            extra={"path": str(path), "fallback_path": str(default_path), "error": str(exc)},
        )
        default_data = _load_yaml_catalog(default_path)
        catalog = normalize_report_template_catalog(default_data, source_path=str(default_path))

    _CATALOG_CACHE["signature"] = signature
    _CATALOG_CACHE["catalog"] = catalog
    return catalog


def list_report_templates(cfg: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    return [deepcopy(template) for template in load_report_template_catalog(cfg).templates]
