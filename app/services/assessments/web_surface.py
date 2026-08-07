# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Safe metadata normalization for HTTPx screenshot artifacts."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit


def normalize_httpx_screenshot(record: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return bounded screenshot metadata, never captured markup or unsafe paths."""
    item = record if isinstance(record, dict) else {}
    url = _safe_url(item.get("url") or item.get("input"))
    artifact = _safe_artifact_path(item.get("screenshot") or item.get("screenshot_path"))
    if not url or not artifact:
        return None
    technologies = item.get("technologies") or item.get("tech") or []
    if isinstance(technologies, str):
        technologies = [technologies]
    technologies = [_text(value, 128) for value in technologies if _text(value, 128)][:32]
    status = item.get("status_code") or item.get("status-code")
    try:
        status_code = int(status) if status is not None else None
    except (TypeError, ValueError):
        status_code = None
    return {
        "url": url,
        "artifact_path": artifact,
        "status_code": status_code if status_code is None or 100 <= status_code <= 599 else None,
        "title": _text(item.get("title"), 512),
        "technologies": technologies,
        "captured_at": _text(item.get("timestamp") or item.get("captured_at"), 64),
        "visual_hash": _text(item.get("hash") or item.get("visual_hash"), 128),
        "source_run_id": _text(item.get("run_id"), 128),
        "profile_role": _text(item.get("profile_role"), 64),
    }


def _safe_url(value: Any) -> str:
    url = _text(value, 2048)
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or "@" in parsed.netloc:
        return ""
    return url


def _safe_artifact_path(value: Any) -> str:
    path = _text(value, 512).replace("\\", "/")
    candidate = PurePosixPath(path)
    if not path or candidate.is_absolute() or ".." in candidate.parts or path.startswith("/"):
        return ""
    return str(candidate)


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


__all__ = ["normalize_httpx_screenshot"]
