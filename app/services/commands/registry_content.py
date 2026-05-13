"""App content loaders used by the command/content registry."""

from __future__ import annotations

import os
from typing import TypedDict
import yaml

import config as app_config


class TourPayload(TypedDict):
    version: int
    chapters: list[dict[str, object]]


_TOUR_ALLOWED_REQUIRES = {"workspace_enabled", "interactive_pty_enabled"}
_TOUR_REQUIRED_STRING_FIELDS = ("id", "title", "summary")
_TOUR_OPTIONAL_STRING_FIELDS = ("sample", "illustration")


def _local_overlay_path(path: str) -> str:
    root, ext = os.path.splitext(path)
    return f"{root}.local{ext}"


def _load_yaml_list(path: str) -> list:
    try:
        with open(path) as f:
            loaded = yaml.safe_load(f) or []
    except (FileNotFoundError, yaml.YAMLError):
        return []
    return loaded if isinstance(loaded, list) else []


def _load_yaml_list_with_local(path: str) -> list:
    merged = []
    merged.extend(_load_yaml_list(path))
    merged.extend(_load_yaml_list(_local_overlay_path(path)))
    return merged


def load_welcome(path: str) -> list[dict[str, object]]:
    """Read welcome.yaml and return startup blocks for the welcome typeout."""
    data = _load_yaml_list_with_local(path)
    return [
        {
            "cmd": str(item.get("cmd", "")).strip(),
            "out": str(item.get("out", "")).rstrip() if item.get("out") else "",
            "group": str(item.get("group", "")).strip().lower() if item.get("group") else "",
            "featured": bool(item.get("featured", False)),
        }
        for item in data
        if isinstance(item, dict) and item.get("cmd")
    ]


def _tour_config(cfg=None):
    return app_config.CFG if cfg is None else cfg


def _tour_error(message):
    return ValueError(f"Invalid tour.yaml: {message}")


def _read_tour_payload(path: str):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise _tour_error("top-level value must be a mapping")
    return loaded


def _tour_requires_values(raw, index):
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = raw
    else:
        raise _tour_error(f"chapter {index} requires must be a string or list of strings")
    normalized = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise _tour_error(f"chapter {index} requires must contain non-empty strings")
        key = value.strip()
        if key not in _TOUR_ALLOWED_REQUIRES:
            raise _tour_error(f"chapter {index} has unknown requires key {key!r}")
        normalized.append(key)
    return normalized


def _normalize_tour_chapter(raw, index):
    if not isinstance(raw, dict):
        raise _tour_error(f"chapter {index} must be a mapping")
    chapter = {}
    for field_name in _TOUR_REQUIRED_STRING_FIELDS:
        value = raw.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise _tour_error(f"chapter {index} missing required {field_name!r}")
        chapter[field_name] = value.strip()
    for field_name in _TOUR_OPTIONAL_STRING_FIELDS:
        value = raw.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise _tour_error(f"chapter {index} {field_name!r} must be a string")
        stripped = value.strip()
        if stripped:
            chapter[field_name] = stripped
    requires = _tour_requires_values(raw.get("requires"), index)
    if len(requires) == 1:
        chapter["requires"] = requires[0]
    elif len(requires) > 1:
        chapter["requires"] = requires
    return chapter


def _tour_chapter_requires(chapter):
    requires = chapter.get("requires")
    if not requires:
        return []
    if isinstance(requires, str):
        return [requires]
    return [str(value) for value in requires]


def _tour_chapter_enabled(chapter, cfg=None, mobile=False):
    if mobile and chapter.get("id") == "interactive_pty":
        return False
    active_cfg = _tour_config(cfg)
    return all(bool(active_cfg.get(key, False)) for key in _tour_chapter_requires(chapter))


def load_tour(path: str, cfg=None, *, mobile: bool = False) -> TourPayload:
    """Read tour.yaml and return the visible onboarding tour chapters."""
    payload = _read_tour_payload(path)
    if payload is None:
        return {"version": 0, "chapters": []}
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise _tour_error("version must be a positive integer")
    raw_chapters = payload.get("chapters")
    if not isinstance(raw_chapters, list):
        raise _tour_error("chapters must be a list")
    chapters = [
        _normalize_tour_chapter(item, index)
        for index, item in enumerate(raw_chapters, start=1)
    ]
    active_cfg = _tour_config(cfg)
    if not bool(active_cfg.get("tour_enabled", True)):
        return {"version": version, "chapters": []}
    return {
        "version": version,
        "chapters": [
            chapter for chapter in chapters
            if _tour_chapter_enabled(chapter, active_cfg, mobile=mobile)
        ],
    }


def load_ascii_art(path: str) -> str:
    """Read banner art as plain text, preferring a local overlay."""
    local_path = _local_overlay_path(path)
    if os.path.exists(local_path):
        with open(local_path) as f:
            return f.read().rstrip()
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        return f.read().rstrip()


def _hint_category_enabled(category, cfg=None):
    active_cfg = app_config.CFG if cfg is None else cfg
    normalized = str(category or "general").strip().lower()
    if normalized in ("", "general"):
        return True
    if normalized == "workspace":
        return bool(active_cfg.get("workspace_enabled", False))
    if normalized in {"interactive_pty", "pty"}:
        return bool(active_cfg.get("interactive_pty_enabled", False))
    return True


def load_scoped_hints(path: str, cfg=None) -> list[str]:
    hints = []
    seen = set()
    for candidate in (path, _local_overlay_path(path)):
        if not os.path.exists(candidate):
            continue
        category = "general"
        with open(candidate) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    category = line[1:-1].strip().lower() or "general"
                    continue
                if _hint_category_enabled(category, cfg) and line not in seen:
                    hints.append(line)
                    seen.add(line)
    return hints
