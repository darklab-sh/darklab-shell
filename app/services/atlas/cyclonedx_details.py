# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded CycloneDX component, dependency, and VEX provenance."""

from __future__ import annotations

from datetime import datetime
from collections.abc import Iterator
from typing import Any
from urllib.parse import unquote, urlsplit


CYCLONEDX_AFFECT_LIMIT = 16
CYCLONEDX_DEPENDENCY_LIMIT = 64
CYCLONEDX_REFERENCE_LIMIT = 16
_TEXT_LIMIT = 4096


def document_provenance(document: dict[str, Any], spec_version: str) -> dict[str, Any]:
    """Return bounded BOM identity shared by every imported evidence record."""
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    tool = _first_tool(metadata.get("tools"))
    return _compact({
        "spec_version": spec_version,
        "serial_number": _text(document.get("serialNumber"), 256),
        "bom_version": _integer(document.get("version"), minimum=1),
        "observed_at": _timestamp(metadata.get("timestamp")),
        "tool_name": _text(tool.get("name"), 128),
        "tool_vendor": _text(tool.get("vendor"), 128),
        "tool_version": _text(tool.get("version"), 128),
    })


def component_records(
    document: dict[str, Any],
    state: Any,
    evidence: list[Any],
    provenance: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Append typed component evidence and return a bounded BOM-reference map."""
    from services.atlas.import_types import ImportEvidence

    components = _component_tree(document.get("components"))
    indexed: dict[str, dict[str, Any]] = {}
    for raw, parent_ref in components:
        row_number = state.next_row()
        component = normalize_component(raw)
        bom_ref = str(component.get("bom_ref") or "")
        if not bom_ref:
            state.warn(
                row_number,
                "missing_cyclonedx_component_ref",
                "CycloneDX component is missing a bounded BOM reference.",
            )
            continue
        if bom_ref in indexed:
            state.warn(
                row_number,
                "duplicate_cyclonedx_component_ref",
                "CycloneDX component repeated an earlier BOM reference.",
            )
            continue
        if parent_ref:
            component["parent_ref"] = parent_ref
        indexed[bom_ref] = component
        evidence.append(ImportEvidence(
            row_number=row_number,
            evidence_type="cyclonedx_component",
            subject_key=bom_ref,
            label=_component_label(component),
            external_id=bom_ref,
            observed_at=str(provenance.get("observed_at") or ""),
            source_detail={**provenance, **component},
        ))
    return indexed


def dependency_records(
    document: dict[str, Any],
    components: dict[str, dict[str, Any]],
    state: Any,
    evidence: list[Any],
    provenance: dict[str, Any],
) -> None:
    """Append bounded dependency-edge evidence without inventing components."""
    from services.atlas.import_types import ImportEvidence

    raw_dependencies = document.get("dependencies")
    dependencies = raw_dependencies if isinstance(raw_dependencies, list) else []
    for raw in dependencies:
        row_number = state.next_row()
        dependency = raw if isinstance(raw, dict) else {}
        component_ref = _text(dependency.get("ref"), 512)
        raw_depends_on = dependency.get("dependsOn")
        depends_on_values = raw_depends_on if isinstance(raw_depends_on, list) else []
        depends_on = _bounded_unique(depends_on_values, CYCLONEDX_DEPENDENCY_LIMIT, 512)
        if not component_ref or component_ref not in components:
            state.warn(
                row_number,
                "unknown_cyclonedx_dependency_ref",
                "CycloneDX dependency references an unknown component.",
            )
            continue
        known = [item for item in depends_on if item in components]
        unknown_count = len(depends_on) - len(known)
        if unknown_count:
            state.warn(
                row_number,
                "unknown_cyclonedx_dependency_target",
                "CycloneDX dependency includes unknown component references.",
                skipped=False,
            )
        evidence.append(ImportEvidence(
            row_number=row_number,
            evidence_type="cyclonedx_dependency",
            subject_key=component_ref,
            label=f"{_component_label(components[component_ref])} dependencies",
            external_id=component_ref,
            observed_at=str(provenance.get("observed_at") or ""),
            source_detail={
                **provenance,
                "component_ref": component_ref,
                "depends_on": known,
                "dependency_count": len(known),
                "unknown_dependency_count": unknown_count,
                "dependencies_truncated": len(depends_on_values) > CYCLONEDX_DEPENDENCY_LIMIT,
            },
        ))


def vulnerability_detail(
    vulnerability: dict[str, Any],
    components: dict[str, dict[str, Any]],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Normalize one included vulnerability and its VEX disposition."""
    analysis = vulnerability.get("analysis") if isinstance(vulnerability.get("analysis"), dict) else {}
    raw_affects = vulnerability.get("affects")
    affects = raw_affects if isinstance(raw_affects, list) else []
    component_refs = _bounded_unique(
        [item.get("ref") for item in affects if isinstance(item, dict)],
        CYCLONEDX_AFFECT_LIMIT,
        512,
    )
    component_details = [components[ref] for ref in component_refs if ref in components]
    raw_state = _text(analysis.get("state"), 64).casefold()
    return {
        **provenance,
        "analysis": _compact({
            "state": raw_state,
            "category": vex_category(raw_state),
            "justification": _text(analysis.get("justification"), 128),
            "responses": _bounded_unique(analysis.get("response"), 16, 128),
            "detail": _text(analysis.get("detail"), _TEXT_LIMIT),
            "first_issued": _text(analysis.get("firstIssued"), 64),
            "last_updated": _text(analysis.get("lastUpdated"), 64),
        }),
        "components": component_details,
        "component_refs": component_refs,
        "unknown_component_ref_count": len(component_refs) - len(component_details),
        "affects_truncated": len(affects) > CYCLONEDX_AFFECT_LIMIT,
        "references": safe_references(vulnerability.get("references")),
    }


def normalize_component(value: Any) -> dict[str, Any]:
    """Return one safe, typed component identity."""
    component = value if isinstance(value, dict) else {}
    return _compact({
        "bom_ref": _text(component.get("bom-ref"), 512),
        "component_type": _text(component.get("type"), 64),
        "group": _text(component.get("group"), 256),
        "name": _text(component.get("name"), 256),
        "version": _text(component.get("version"), 128),
        "scope": _text(component.get("scope"), 64),
        "purl": _text(component.get("purl"), 1024),
        "cpe": _text(component.get("cpe"), 1024),
    })


def safe_references(value: Any) -> list[str]:
    """Keep bounded credential-free HTTP(S) vulnerability references."""
    references = value if isinstance(value, list) else []
    safe: list[str] = []
    for item in references:
        raw = item.get("url") if isinstance(item, dict) else ""
        uri = _safe_web_uri(raw)
        if uri and uri not in safe:
            safe.append(uri)
        if len(safe) >= CYCLONEDX_REFERENCE_LIMIT:
            break
    return safe


def vex_category(state: str) -> str:
    """Map CycloneDX analysis states to the app's non-mutating review categories."""
    if state in {"not_affected", "false_positive"}:
        return "not_affected"
    if state in {"resolved", "resolved_with_pedigree"}:
        return "resolved"
    if state == "in_triage":
        return "under_investigation"
    if state == "exploitable" or not state:
        return "affected"
    return "under_investigation"


def _component_label(component: dict[str, Any]) -> str:
    name = str(component.get("name") or component.get("bom_ref") or "component")
    version = str(component.get("version") or "")
    return f"{name} {version}".strip()


def _first_tool(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, dict)), {})
    if isinstance(value, dict):
        components = value.get("components")
        if isinstance(components, list):
            return next((item for item in components if isinstance(item, dict)), {})
    return {}


def _component_tree(value: Any) -> Iterator[tuple[dict[str, Any], str]]:
    pending = [(item, "") for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    index = 0
    while index < len(pending):
        component, parent_ref = pending[index]
        index += 1
        yield component, parent_ref
        bom_ref = _text(component.get("bom-ref"), 512)
        children = component.get("components")
        if isinstance(children, list):
            pending.extend((child, bom_ref) for child in children if isinstance(child, dict))


def _bounded_unique(value: Any, limit: int, text_limit: int) -> list[str]:
    values = value if isinstance(value, list) else []
    result: list[str] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            continue
        text = _text(item, text_limit)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _timestamp(value: Any) -> str:
    timestamp = _text(value, 64)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return timestamp if parsed.tzinfo is not None else ""


def _safe_web_uri(value: Any) -> str:
    uri = str(value or "").strip()
    decoded = unquote(uri)
    if not uri or len(uri) > 2048 or _unsafe(uri) or _unsafe(decoded):
        return ""
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return ""
    return uri


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    return text[:limit] if text and not _unsafe(raw) else ""


def _integer(value: Any, *, minimum: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= 10_000_000 else None


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {})}


def _unsafe(value: str) -> bool:
    return "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value)


__all__ = [
    "component_records",
    "dependency_records",
    "document_provenance",
    "safe_references",
    "vex_category",
    "vulnerability_detail",
]
