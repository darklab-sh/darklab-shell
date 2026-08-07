# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Workflow catalog loading and normalization helpers."""

from __future__ import annotations

import os
import re
import shlex
import logging
import yaml


WORKFLOW_INPUT_TYPES = {
    "text", "target", "domain", "host", "url", "port", "port_set",
    "path", "workspace_path", "wordlist",
}
WORKFLOW_INPUT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
WORKFLOW_TOKEN_RE = re.compile(r"{{\s*([a-z][a-z0-9_]*)\s*}}")
WORKFLOW_CAPTURE_SOURCES = {
    "first_nonempty_line", "first_line_containing", "entity", "json_pointer",
}
WORKFLOW_TERMINAL_DESTINATIONS = {"complete", "stop"}
log = logging.getLogger("shell")


def _local_overlay_path(path: str) -> str:
    root, ext = os.path.splitext(path)
    return f"{root}.local{ext}"


def _load_yaml_list(path: str) -> list:
    try:
        with open(path) as f:
            loaded = yaml.safe_load(f) or []
    except FileNotFoundError:
        return []
    except yaml.YAMLError as exc:
        log.warning("WORKFLOW_DEFINITION_REJECTED", extra={
            "source": "config",
            "reason": "invalid_yaml",
            "error_type": type(exc).__name__,
        })
        return []
    if not isinstance(loaded, list):
        log.warning("WORKFLOW_DEFINITION_REJECTED", extra={
            "source": "config",
            "reason": "root_not_list",
        })
        return []
    return loaded


def _load_yaml_list_with_local(path: str, *, local_path: str | None = None) -> list:
    merged = []
    merged.extend(_load_yaml_list(path))
    merged.extend(_load_yaml_list(local_path or _local_overlay_path(path)))
    return merged


def workflow_tokens(value: str) -> set[str]:
    return set(WORKFLOW_TOKEN_RE.findall(value or ""))


def render_workflow_text(value: str, inputs: dict[str, str]) -> str:
    return WORKFLOW_TOKEN_RE.sub(lambda match: inputs.get(match.group(1), ""), value or "")


def render_workflow_command(
    value: str,
    variables: dict[str, str],
    *,
    placeholders: dict[str, str] | None = None,
) -> str:
    """Render workflow variables as single shell-safe scalar arguments."""
    safe_placeholders = placeholders or {}
    return WORKFLOW_TOKEN_RE.sub(
        lambda match: (
            safe_placeholders[match.group(1)]
            if match.group(1) in safe_placeholders
            else shlex.quote(str(variables.get(match.group(1), "")))
        ),
        value or "",
    )


def normalize_workflow_inputs(raw_inputs):
    if not isinstance(raw_inputs, list):
        return []
    result = []
    seen_ids = set()
    for item in raw_inputs:
        if not isinstance(item, dict):
            continue
        input_id = str(item.get("id") or "").strip().lower()
        input_type = str(item.get("type") or "text").strip().lower()
        if (
            not input_id
            or input_id in seen_ids
            or not WORKFLOW_INPUT_ID_RE.fullmatch(input_id)
            or input_type not in WORKFLOW_INPUT_TYPES
        ):
            continue
        label = str(item.get("label") or input_id.replace("_", " ").title()).strip()
        placeholder = str(item.get("placeholder") or "").strip()
        default = str(item.get("default") or "").strip()
        help_text = str(item.get("help") or "").strip()
        normalized = {
            "id": input_id,
            "label": label or input_id.replace("_", " ").title(),
            "type": input_type,
            "required": bool(item.get("required", False)),
            "placeholder": placeholder,
            "default": default,
            "help": help_text,
        }
        if bool(item.get("sensitive", False)):
            normalized["sensitive"] = True
        result.append(normalized)
        seen_ids.add(input_id)
    return result


def normalize_workflow_entry(entry):
    if not isinstance(entry, dict):
        return None
    title = str(entry.get("title") or "").strip()
    description = str(entry.get("description") or "").strip()
    steps = entry.get("steps") or []
    if not title or not isinstance(steps, list):
        return None
    inputs = normalize_workflow_inputs(entry.get("inputs") or [])
    declared_ids = {item["id"] for item in inputs}
    raw_version = str(entry.get("version") or "").strip()
    version = int(raw_version) if raw_version in {"1", "2", "3"} else 1
    clean_steps = []
    capture_names = set()
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        cmd = str(step.get("cmd") or "").strip()
        note = str(step.get("note") or "").strip()
        if not cmd:
            continue
        captures = []
        pending_capture_names = set()
        for raw_capture in step.get("captures") or []:
            if not isinstance(raw_capture, dict):
                continue
            name = str(raw_capture.get("name") or "").strip().lower()
            source = str(raw_capture.get("source") or "").strip().lower()
            if (
                not WORKFLOW_INPUT_ID_RE.fullmatch(name)
                or name in declared_ids
                or name in capture_names
                or name in pending_capture_names
                or source not in WORKFLOW_CAPTURE_SOURCES
            ):
                continue
            capture = {
                "name": name,
                "source": source,
                "required": bool(raw_capture.get("required", False)),
            }
            capture_kind = str(raw_capture.get("kind") or raw_capture.get("mode") or "").strip().lower()
            if capture_kind == "collection":
                capture["kind"] = "collection"
                try:
                    capture["item_limit"] = int(raw_capture.get("item_limit") or 32)
                except (TypeError, ValueError):
                    capture["item_limit"] = 0
            for field in ("contains", "entity_type", "pointer"):
                field_value = str(raw_capture.get(field) or "").strip()
                if field_value:
                    capture[field] = field_value
            captures.append(capture)
            pending_capture_names.add(name)
        tokens = workflow_tokens(cmd) | workflow_tokens(note)
        all_v2_captures = {
            str(capture.get("name") or "").strip().lower()
            for candidate in steps
            if isinstance(candidate, dict)
            for capture in candidate.get("captures") or []
            if isinstance(capture, dict)
        } if version == 2 else set()
        if tokens and not tokens.issubset(declared_ids | capture_names | all_v2_captures):
            continue
        clean_step: dict[str, object] = {
            "cmd": cmd,
            "note": note,
        }
        if version >= 2:
            clean_step["id"] = str(step.get("id") or f"step_{index + 1}").strip().lower()
        if version >= 2 and captures:
            clean_step["captures"] = captures
            capture_names.update(pending_capture_names)
        raw_next = step.get("next")
        if version >= 2 and isinstance(raw_next, dict):
            next_value: dict[str, object] = {}
            for outcome in ("success", "failure"):
                destination = str(raw_next.get(outcome) or "").strip().lower()
                if destination:
                    next_value[outcome] = destination
            raw_codes = raw_next.get("codes")
            if isinstance(raw_codes, dict):
                codes = {
                    str(code).strip(): str(destination).strip().lower()
                    for code, destination in raw_codes.items()
                    if str(code).strip() and str(destination).strip()
                }
                if codes:
                    next_value["codes"] = codes
            if next_value:
                clean_step["next"] = next_value
        clean_steps.append(clean_step)
    if not clean_steps:
        return None
    normalized = {
        "title": title,
        "description": description,
        "inputs": inputs,
        "steps": clean_steps,
    }
    if version >= 2:
        normalized["version"] = version
    workflow_id = str(entry.get("id") or "").strip().lower()
    if workflow_id:
        normalized["id"] = workflow_id
    feature_required = entry.get("feature_required") or entry.get("requires_feature") or entry.get("feature")
    if feature_required:
        if isinstance(feature_required, (list, tuple, set)):
            normalized["feature_required"] = [
                str(value).strip().lower() for value in feature_required if str(value).strip()
            ]
        else:
            normalized["feature_required"] = str(feature_required).strip().lower()
    return normalized


def load_workflows(path: str, *, local_path: str | None = None) -> list[dict[str, object]]:
    """Read workflows.yaml and return a list of normalized workflow dicts."""
    data = _load_yaml_list_with_local(path, local_path=local_path)
    if not data:
        return []
    result = []
    for index, entry in enumerate(data):
        normalized = None
        if isinstance(entry, dict) and "version" in entry:
            try:
                from services.workflows.compiler import compile_workflow_definition  # noqa: PLC0415

                if str(entry.get("version") or "").strip() != "2":
                    raise ValueError("unsupported workflow version")
                normalized = compile_workflow_definition(entry, require_workflow_id=True)
            except ValueError as exc:
                log.warning("WORKFLOW_DEFINITION_REJECTED", extra={
                    "source": "config",
                    "entry_index": index,
                    "reason": str(exc)[:200],
                })
        else:
            normalized = normalize_workflow_entry(entry)
        if normalized:
            result.append(normalized)
    return result


def workflow_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(title or "").strip().lower()).strip("-")
    return slug or "workflow"


def workflow_with_catalog_metadata(entry, source, index):
    item = dict(entry)
    item["source"] = source
    item.setdefault("id", f"{source}:{workflow_slug(item.get('title', 'workflow'))}-{index + 1}")
    return item
