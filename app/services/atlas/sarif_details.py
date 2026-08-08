# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded, non-fetching SARIF provenance normalization."""

from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Any
from urllib.parse import unquote, urlsplit


SARIF_FINGERPRINT_LIMIT = 16
SARIF_LOCATION_LIMIT = 8
_MAX_LOCATION_CHARS = 1024
_MAX_REGION_VALUE = 10_000_000
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_./:%+-]{1,128}$")


def sarif_automation_details(run: dict[str, Any]) -> dict[str, str]:
    """Return bounded run automation identity without execution payloads."""
    from services.atlas.import_parser import _safe_text

    raw = run.get("automationDetails")
    automation = raw if isinstance(raw, dict) else {}
    return {
        key: value
        for key, value in (
            ("id", _safe_text(automation.get("id"), limit=256)),
            ("guid", _safe_text(automation.get("guid"), limit=128)),
            ("correlation_guid", _safe_text(automation.get("correlationGuid"), limit=128)),
        )
        if value
    }


def sarif_fingerprints(result: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Keep stable result fingerprints in deterministic bounded maps."""
    normalized: dict[str, dict[str, str]] = {}
    for source_key, output_key in (
        ("fingerprints", "fingerprints"),
        ("partialFingerprints", "partial_fingerprints"),
    ):
        raw = result.get(source_key)
        if not isinstance(raw, dict):
            continue
        values: dict[str, str] = {}
        for key in sorted(raw, key=lambda item: str(item)):
            name = _safe_identifier(key)
            value = _safe_value(raw.get(key))
            if name and value:
                values[name] = value
            if len(values) >= SARIF_FINGERPRINT_LIMIT:
                break
        if values:
            normalized[output_key] = values
    return normalized


def sarif_locations(
    result: dict[str, Any],
    artifacts: list[Any],
    state: Any,
    row_number: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Normalize safe web or repository-relative locations without resolving them."""
    raw_locations = result.get("locations")
    locations = raw_locations if isinstance(raw_locations, list) else []
    normalized: list[dict[str, Any]] = []
    rejected = 0
    truncated = len(locations) > SARIF_LOCATION_LIMIT
    for raw_location in locations[:SARIF_LOCATION_LIMIT]:
        physical = raw_location.get("physicalLocation") if isinstance(raw_location, dict) else None
        artifact = physical.get("artifactLocation") if isinstance(physical, dict) else None
        if not isinstance(artifact, dict):
            continue
        provenance = _artifact_provenance(artifact, artifacts)
        if not provenance:
            if artifact.get("uri") or artifact.get("index") is not None:
                rejected += 1
                state.warn(
                    row_number,
                    "unsafe_sarif_location",
                    "SARIF location used an unsafe or invalid artifact path.",
                    skipped=False,
                )
            continue
        region = _region(physical.get("region"))
        if region:
            provenance["region"] = region
        normalized.append(provenance)
    return normalized, rejected, truncated


def sarif_entity(locations: list[dict[str, Any]], row_number: int, state: Any):
    """Materialize only an explicit safe HTTP(S) location as an Atlas entity."""
    from services.atlas.import_parser import _entity_from_target

    for location in locations:
        if location.get("kind") == "web":
            return _entity_from_target(
                location["uri"], row_number, state, {"adapter": "sarif"}
            )
    return None


def sarif_location_summary(locations: list[dict[str, Any]]) -> str:
    """Render bounded safe locations for finding evidence."""
    from services.atlas.import_parser import _safe_multiline

    summaries = []
    for location in locations:
        text = str(location.get("uri") or "")
        region = location.get("region") if isinstance(location.get("region"), dict) else {}
        if region.get("start_line"):
            text += f":{region['start_line']}"
            if region.get("start_column"):
                text += f":{region['start_column']}"
        if text:
            summaries.append(text)
    return _safe_multiline("; ".join(summaries))


def safe_sarif_web_uri(value: Any) -> str:
    """Return one credential-free HTTP(S) URI or an empty string."""
    raw = str(value or "").strip()
    decoded = unquote(raw)
    if (
        not raw
        or len(raw) > _MAX_LOCATION_CHARS
        or _has_unsafe_text(raw)
        or _has_unsafe_text(decoded)
    ):
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return ""
    return raw


def _artifact_provenance(artifact: dict[str, Any], artifacts: list[Any]) -> dict[str, Any]:
    raw_uri = artifact.get("uri")
    index = _bounded_int(artifact.get("index"), minimum=0)
    resolved_from_index = False
    if not raw_uri and index is not None and index < len(artifacts):
        indexed = artifacts[index]
        location = indexed.get("location") if isinstance(indexed, dict) else None
        if isinstance(location, dict):
            raw_uri = location.get("uri")
            resolved_from_index = bool(raw_uri)
    normalized = _safe_artifact_uri(raw_uri)
    if not normalized:
        return {}
    uri, kind = normalized
    result: dict[str, Any] = {"uri": uri, "kind": kind}
    if index is not None:
        result["artifact_index"] = index
    if resolved_from_index:
        result["resolved_from_index"] = True
    uri_base_id = _safe_identifier(artifact.get("uriBaseId"))
    if uri_base_id:
        result["uri_base_id"] = uri_base_id
    return result


def _safe_artifact_uri(value: Any) -> tuple[str, str] | None:
    raw = str(value or "").strip()
    if not raw or len(raw) > _MAX_LOCATION_CHARS or _has_unsafe_text(raw):
        return None
    web_uri = safe_sarif_web_uri(raw)
    if web_uri:
        return web_uri, "web"
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    decoded = unquote(parsed.path)
    path = PurePosixPath(decoded)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or _has_unsafe_text(decoded)
        or path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or decoded.startswith("~")
    ):
        return None
    return raw, "relative"


def _region(value: Any) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    fields = (
        ("start_line", "startLine"),
        ("start_column", "startColumn"),
        ("end_line", "endLine"),
        ("end_column", "endColumn"),
    )
    return {
        output: number
        for output, source in fields
        if (number := _bounded_int(raw.get(source), minimum=1)) is not None
    }


def _bounded_int(value: Any, *, minimum: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= _MAX_REGION_VALUE else None


def _safe_identifier(value: Any) -> str:
    text = str(value or "").strip()
    return text if _SAFE_IDENTIFIER_RE.fullmatch(text) else ""


def _safe_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return text[:512] if text and not _has_unsafe_text(text) else ""


def _has_unsafe_text(value: str) -> bool:
    return "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value)


__all__ = [
    "SARIF_FINGERPRINT_LIMIT",
    "SARIF_LOCATION_LIMIT",
    "safe_sarif_web_uri",
    "sarif_automation_details",
    "sarif_entity",
    "sarif_fingerprints",
    "sarif_location_summary",
    "sarif_locations",
]
