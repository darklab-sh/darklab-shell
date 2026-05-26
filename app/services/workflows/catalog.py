"""Workflow catalog loading and normalization helpers."""

from __future__ import annotations

import os
import re
import yaml


WORKFLOW_INPUT_TYPES = {"domain", "host", "url", "port", "path"}
WORKFLOW_INPUT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
WORKFLOW_TOKEN_RE = re.compile(r"{{\s*([a-z][a-z0-9_]*)\s*}}")


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


def workflow_tokens(value: str) -> set[str]:
    return set(WORKFLOW_TOKEN_RE.findall(value or ""))


def render_workflow_text(value: str, inputs: dict[str, str]) -> str:
    return WORKFLOW_TOKEN_RE.sub(lambda match: inputs.get(match.group(1), ""), value or "")


def normalize_workflow_inputs(raw_inputs):
    if not isinstance(raw_inputs, list):
        return []
    result = []
    seen_ids = set()
    for item in raw_inputs:
        if not isinstance(item, dict):
            continue
        input_id = str(item.get("id") or "").strip().lower()
        input_type = str(item.get("type") or "").strip().lower()
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
    clean_steps = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        cmd = str(step.get("cmd") or "").strip()
        note = str(step.get("note") or "").strip()
        if not cmd:
            continue
        tokens = workflow_tokens(cmd) | workflow_tokens(note)
        if tokens and not tokens.issubset(declared_ids):
            continue
        clean_steps.append({"cmd": cmd, "note": note})
    if not clean_steps:
        return None
    normalized = {
        "title": title,
        "description": description,
        "inputs": inputs,
        "steps": clean_steps,
    }
    feature_required = entry.get("feature_required") or entry.get("requires_feature") or entry.get("feature")
    if feature_required:
        if isinstance(feature_required, (list, tuple, set)):
            normalized["feature_required"] = [
                str(value).strip().lower() for value in feature_required if str(value).strip()
            ]
        else:
            normalized["feature_required"] = str(feature_required).strip().lower()
    return normalized


def load_workflows(path: str) -> list[dict[str, object]]:
    """Read workflows.yaml and return a list of normalized workflow dicts."""
    data = _load_yaml_list_with_local(path)
    if not data:
        return []
    result = []
    for entry in data:
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
