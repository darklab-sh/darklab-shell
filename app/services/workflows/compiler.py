# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Strict workflow definition compilation and typed input rendering."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from services.workflows.captures import MAX_CAPTURES_PER_STEP
from services.workflows.fanout_policy import normalize_fanout_policy

from services.workflows.catalog import (
    WORKFLOW_CAPTURE_SOURCES,
    WORKFLOW_INPUT_ID_RE,
    WORKFLOW_INPUT_TYPES,
    WORKFLOW_TERMINAL_DESTINATIONS,
    normalize_workflow_entry,
    render_workflow_command,
    workflow_tokens,
)

MAX_WORKFLOW_INPUT_VALUE_CHARS = 4096
_PORT_PART_RE = re.compile(r"^(\d{1,5})(?:-(\d{1,5}))?$")


class WorkflowDefinitionError(ValueError):
    """Raised when a workflow definition or execution input is invalid."""

    def __init__(self, message: str, *, field: str = "") -> None:
        super().__init__(message)
        self.field = field


def _raw_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise WorkflowDefinitionError(f"workflow {field} must be a list", field=field)
    return value


def _validate_graph(
    steps: list[dict[str, object]],
) -> tuple[dict[str, set[str]], list[str]]:
    step_ids = [str(step.get("id") or "") for step in steps]
    invalid_index = next(
        (index for index, step_id in enumerate(step_ids) if not WORKFLOW_INPUT_ID_RE.fullmatch(step_id)),
        None,
    )
    if invalid_index is not None:
        raise WorkflowDefinitionError(
            "workflow step ids must use lowercase letters, numbers, and underscores",
            field=f"steps.{invalid_index}.id",
        )
    if len(step_ids) != len(set(step_ids)):
        duplicate_index = next(
            index for index, step_id in enumerate(step_ids) if step_id in step_ids[:index]
        )
        raise WorkflowDefinitionError(
            "workflow step ids must be unique",
            field=f"steps.{duplicate_index}.id",
        )
    known = set(step_ids) | WORKFLOW_TERMINAL_DESTINATIONS
    edges: dict[str, set[str]] = {step_id: set() for step_id in step_ids}
    for index, step in enumerate(steps):
        next_value = step.get("next")
        if not isinstance(next_value, Mapping):
            if index + 1 < len(steps):
                edges[step_ids[index]].add(step_ids[index + 1])
            continue
        destinations = [next_value.get("success"), next_value.get("failure")]
        if not next_value.get("success") and index + 1 < len(steps):
            destinations.append(step_ids[index + 1])
        codes = next_value.get("codes")
        if isinstance(codes, Mapping):
            normalized_codes: dict[str, object] = {}
            for code, destination in codes.items():
                try:
                    normalized_code = str(int(str(code)))
                except ValueError as exc:
                    raise WorkflowDefinitionError(
                        f"invalid workflow exit code {code!r}",
                        field=f"steps.{index}.next.codes",
                    ) from exc
                if normalized_code in normalized_codes:
                    raise WorkflowDefinitionError(
                        "workflow exit codes must be unique",
                        field=f"steps.{index}.next.codes",
                    )
                normalized_codes[normalized_code] = destination
                destinations.append(destination)
            if isinstance(next_value, dict):
                next_value["codes"] = normalized_codes
        for destination in destinations:
            if not destination:
                continue
            destination_text = str(destination)
            if destination_text not in known:
                raise WorkflowDefinitionError(
                    f"workflow transition points to unknown step {destination_text!r}",
                    field=f"steps.{index}.next",
                )
            if destination_text in edges:
                edges[step_ids[index]].add(destination_text)

    visiting: set[str] = set()
    visited: set[str] = set()

    topological: list[str] = []

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise WorkflowDefinitionError("workflow transitions cannot contain cycles", field="steps")
        if step_id in visited:
            return
        visiting.add(step_id)
        for destination in edges[step_id]:
            visit(destination)
        visiting.remove(step_id)
        visited.add(step_id)
        topological.append(step_id)

    visit(step_ids[0])
    if visited != set(step_ids):
        missing = ", ".join(sorted(set(step_ids) - visited))
        raise WorkflowDefinitionError(f"workflow contains unreachable steps: {missing}", field="steps")
    topological.reverse()
    return edges, topological


def _validate_capture_paths(
    steps: list[dict[str, object]],
    input_ids: set[str],
    collection_names: set[str],
    edges: Mapping[str, set[str]],
    topological: list[str],
) -> None:
    steps_by_id = {str(step.get("id") or ""): step for step in steps}
    predecessors: dict[str, set[str]] = {step_id: set() for step_id in steps_by_id}
    for source, destinations in edges.items():
        for destination in destinations:
            predecessors[destination].add(source)

    available_after: dict[str, set[str]] = {}
    for step_id in topological:
        incoming = predecessors[step_id]
        if incoming:
            available_before = set.intersection(*(available_after[source] for source in incoming))
        else:
            available_before = set(input_ids)
        step = steps_by_id[step_id]
        used = workflow_tokens(str(step.get("cmd") or "")) | workflow_tokens(
            str(step.get("note") or "")
        )
        step_index = steps.index(step)
        raw_for_each = step.get("for_each")
        if isinstance(raw_for_each, Mapping):
            collection_name = str(raw_for_each.get("collection") or "")
            if collection_name not in collection_names:
                raise WorkflowDefinitionError(
                    "workflow for_each source must name a collection capture",
                    field=f"steps.{step_index}.for_each.collection",
                )
            if collection_name not in available_before:
                raise WorkflowDefinitionError(
                    "workflow for_each source is not available on every path",
                    field=f"steps.{step_index}.for_each.collection",
                )
            if collection_name not in workflow_tokens(str(step.get("cmd") or "")):
                raise WorkflowDefinitionError(
                    "workflow for_each collection must be referenced by the step command",
                    field=f"steps.{step_index}.cmd",
                )
            extra_collections = (used & collection_names) - {collection_name}
            if extra_collections:
                raise WorkflowDefinitionError(
                    "workflow fan-out steps can reference only their selected collection",
                    field=f"steps.{step_index}.cmd",
                )
        elif used & collection_names:
            raise WorkflowDefinitionError(
                "workflow collection variables require a for_each step",
                field=f"steps.{step_index}.for_each",
            )
        unavailable = used - available_before
        if unavailable:
            missing = ", ".join(sorted(unavailable))
            raise WorkflowDefinitionError(
                f"workflow step {step_id!r} uses variables not available on every path: {missing}",
                field=f"steps.{step_index}.cmd",
            )
        raw_captures = step.get("captures")
        capture_items = raw_captures if isinstance(raw_captures, list) else []
        captures = {
            str(capture.get("name") or "")
            for capture in capture_items
            if isinstance(capture, Mapping)
        }
        available_after[step_id] = available_before | captures


def compile_workflow_definition(entry: object, *, require_workflow_id: bool = False) -> dict[str, object]:
    if not isinstance(entry, dict):
        raise WorkflowDefinitionError("workflow payload must be an object", field="workflow")
    if "version" in entry and str(entry.get("version") or "").strip() not in {"1", "2", "3"}:
        raise WorkflowDefinitionError("unsupported workflow version", field="version")
    raw_inputs = _raw_list(entry.get("inputs") or [], "inputs")
    raw_steps = _raw_list(entry.get("steps"), "steps")
    raw_version = str(entry.get("version") or "").strip()
    version = int(raw_version) if raw_version in {"1", "2", "3"} else 1
    normalized_for_each: dict[int, dict[str, object]] = {}
    for step_index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict) or "for_each" not in raw_step:
            continue
        if version < 3:
            raise WorkflowDefinitionError(
                "workflow for_each steps require version 3",
                field=f"steps.{step_index}.for_each",
            )
        raw_for_each = raw_step.get("for_each")
        if not isinstance(raw_for_each, dict):
            raise WorkflowDefinitionError(
                "workflow for_each must be an object",
                field=f"steps.{step_index}.for_each",
            )
        collection_name = str(raw_for_each.get("collection") or "").strip().lower()
        if not WORKFLOW_INPUT_ID_RE.fullmatch(collection_name):
            raise WorkflowDefinitionError(
                "workflow for_each collection must use lowercase letters, numbers, and underscores",
                field=f"steps.{step_index}.for_each.collection",
            )
        try:
            policy = normalize_fanout_policy(raw_for_each)
        except ValueError as exc:
            raise WorkflowDefinitionError(
                str(exc),
                field=f"steps.{step_index}.for_each",
            ) from exc
        normalized_for_each[step_index] = {
            "collection": collection_name,
            "failure_mode": policy.failure_mode,
            "retries": policy.retries,
            "max_parallel": policy.max_parallel,
            "max_failures": policy.max_failures,
        }
    declared_raw = {
        str(item.get("id") or "").strip().lower()
        for item in raw_inputs
        if isinstance(item, dict)
    }
    raw_capture_names: set[str] = set()
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            continue
        for capture in raw_step.get("captures") or []:
            if isinstance(capture, dict):
                raw_capture_names.add(str(capture.get("name") or "").strip().lower())
    declared_raw.update(raw_capture_names)
    used_raw = set()
    for raw_step in raw_steps:
        if isinstance(raw_step, dict):
            used_raw.update(workflow_tokens(str(raw_step.get("cmd") or "")))
            used_raw.update(workflow_tokens(str(raw_step.get("note") or "")))
    undeclared_raw = used_raw - declared_raw
    if undeclared_raw:
        missing = ", ".join(sorted(undeclared_raw))
        error_field = "steps"
        for index, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, dict):
                continue
            if workflow_tokens(str(raw_step.get("cmd") or "")) & undeclared_raw:
                error_field = f"steps.{index}.cmd"
                break
            if workflow_tokens(str(raw_step.get("note") or "")) & undeclared_raw:
                error_field = f"steps.{index}.note"
                break
        raise WorkflowDefinitionError(
            f"workflow uses undeclared variables: {missing}",
            field=error_field,
        )
    normalized = normalize_workflow_entry(entry)
    if not normalized:
        raise WorkflowDefinitionError(
            "workflow title and at least one valid step are required",
            field="workflow",
        )
    inputs = normalized.get("inputs")
    steps = normalized.get("steps")
    if not isinstance(inputs, list) or len(inputs) != len(raw_inputs):
        raise WorkflowDefinitionError(
            "workflow inputs contain invalid or duplicate definitions",
            field="inputs",
        )
    if not isinstance(steps, list) or len(steps) != len(raw_steps):
        raise WorkflowDefinitionError(
            "workflow steps contain invalid variables, captures, or commands",
            field="steps",
        )

    workflow_id = str(entry.get("id") or "").strip().lower()
    if version >= 2 and require_workflow_id and not workflow_id:
        raise WorkflowDefinitionError(f"version {version} operator workflows require a stable id", field="id")
    if version >= 2 and workflow_id and not WORKFLOW_INPUT_ID_RE.fullmatch(workflow_id):
        raise WorkflowDefinitionError(
            "workflow ids must use lowercase letters, numbers, and underscores",
            field="id",
        )
    if version == 1 and any(
        isinstance(step, dict) and (step.get("captures") or step.get("next") or step.get("id"))
        for step in raw_steps
    ):
        raise WorkflowDefinitionError(
        "workflow step ids, captures, and transitions require version 2",
            field="version",
        )
    normalized["version"] = version
    for index, step in enumerate(steps):
        if isinstance(step, dict):
            step.setdefault("id", f"step_{index + 1}")
            if index in normalized_for_each:
                step["for_each"] = normalized_for_each[index]

    declared = {str(item.get("id")) for item in inputs if isinstance(item, dict)}
    capture_names: set[str] = set()
    collection_names: set[str] = set()
    for step_index, (raw_step, step) in enumerate(zip(raw_steps, steps, strict=True)):
        if not isinstance(raw_step, dict) or not isinstance(step, dict):
            raise WorkflowDefinitionError(
                "workflow steps must be objects",
                field=f"steps.{step_index}",
            )
        raw_captures = raw_step.get("captures") or []
        if len(raw_captures) > MAX_CAPTURES_PER_STEP:
            raise WorkflowDefinitionError(
                f"workflow steps can define at most {MAX_CAPTURES_PER_STEP} captures",
                field=f"steps.{step_index}.captures",
            )
        normalized_captures = step.get("captures") or []
        if not isinstance(raw_captures, list) or len(raw_captures) != len(normalized_captures):
            raise WorkflowDefinitionError(
                "workflow captures contain invalid or duplicate definitions",
                field=f"steps.{step_index}.captures",
            )
        for capture in normalized_captures:
            if not isinstance(capture, dict):
                continue
            name = str(capture.get("name") or "")
            source = str(capture.get("source") or "")
            if name in declared or name in capture_names:
                raise WorkflowDefinitionError(f"workflow variable {name!r} is declared more than once")
            if source not in WORKFLOW_CAPTURE_SOURCES:
                raise WorkflowDefinitionError(f"unsupported workflow capture source {source!r}")
            if source == "first_line_containing" and not str(capture.get("contains") or ""):
                raise WorkflowDefinitionError(f"workflow capture {name!r} requires contains")
            if source == "entity" and not str(capture.get("entity_type") or ""):
                raise WorkflowDefinitionError(f"workflow capture {name!r} requires entity_type")
            if source == "json_pointer" and not str(capture.get("pointer") or "").startswith("/"):
                raise WorkflowDefinitionError(f"workflow capture {name!r} requires a JSON Pointer")
            capture_kind = str(capture.get("kind") or capture.get("mode") or "").strip().lower()
            if capture_kind:
                if capture_kind != "collection":
                    raise WorkflowDefinitionError(f"unsupported workflow capture kind {capture_kind!r}")
                if version < 3:
                    raise WorkflowDefinitionError(
                        "collection captures require workflow version 3",
                        field=f"steps.{step_index}.captures",
                    )
                try:
                    item_limit = int(capture.get("item_limit") or 32)
                except (TypeError, ValueError) as exc:
                    raise WorkflowDefinitionError("collection item_limit must be an integer") from exc
                if not 1 <= item_limit <= 32:
                    raise WorkflowDefinitionError("collection item_limit must be between 1 and 32")
                collection_names.add(name)
            capture_names.add(name)

    for item in inputs:
        if isinstance(item, dict) and item.get("type") == "path":
            item["type"] = "workspace_path"
    edges, topological = _validate_graph(steps)
    _validate_capture_paths(steps, declared, collection_names, edges, topological)
    if version == 1:
        for step in steps:
            if isinstance(step, dict):
                step.pop("id", None)
    return normalized


def compile_execution_definition(entry: object) -> dict[str, object]:
    """Compile a definition and give legacy steps stable snapshot-local ids."""
    normalized = compile_workflow_definition(entry)
    raw_steps = normalized.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    for index, step in enumerate(steps):
        if isinstance(step, dict):
            step.setdefault("id", f"step_{index + 1}")
    return normalized


def _validate_port_set(value: str) -> str:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise WorkflowDefinitionError("port value is required")
    normalized = []
    for part in parts:
        match = _PORT_PART_RE.fullmatch(part)
        if not match:
            raise WorkflowDefinitionError(f"invalid port or range {part!r}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if not 1 <= start <= end <= 65535:
            raise WorkflowDefinitionError(f"port or range is outside 1-65535: {part!r}")
        normalized.append(str(start) if start == end else f"{start}-{end}")
    return ",".join(normalized)


def normalize_workflow_input_value(input_definition: Mapping[str, object], value: object) -> str:
    input_type = str(input_definition.get("type") or "text").lower()
    if input_type not in WORKFLOW_INPUT_TYPES:
        raise WorkflowDefinitionError(f"unsupported workflow input type {input_type!r}")
    text = str(value if value is not None else "").strip()
    if len(text) > MAX_WORKFLOW_INPUT_VALUE_CHARS:
        raise WorkflowDefinitionError("workflow input is too long")
    if any(ord(character) < 32 and character not in "\t" for character in text):
        raise WorkflowDefinitionError("workflow input contains control characters")
    if not text:
        if input_definition.get("required"):
            raise WorkflowDefinitionError(f"workflow input {input_definition.get('id')!r} is required")
        return ""
    if input_type == "port":
        normalized = _validate_port_set(text)
        if "," in normalized or "-" in normalized:
            raise WorkflowDefinitionError("a single port is required")
        return normalized
    if input_type == "port_set":
        return _validate_port_set(text)
    if input_type in {"host", "domain"}:
        try:
            return str(ipaddress.ip_address(text)) if input_type == "host" else _normalize_domain(text)
        except ValueError:
            return _normalize_domain(text)
    if input_type == "url":
        parsed = urlsplit(text)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise WorkflowDefinitionError("workflow URL must use http or https")
        return text
    if input_type == "target":
        try:
            return str(ipaddress.ip_address(text))
        except ValueError:
            try:
                return str(ipaddress.ip_network(text, strict=False))
            except ValueError:
                return _normalize_domain(text)
    if input_type in {"path", "workspace_path", "wordlist"}:
        path = PurePosixPath(text)
        if input_type == "wordlist" and text.startswith("/usr/share/wordlists/"):
            if ".." in path.parts:
                raise WorkflowDefinitionError("workflow wordlist path is invalid")
            return str(path)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise WorkflowDefinitionError("workflow path must stay inside Files")
        return str(path)
    return text


def _normalize_domain(value: str) -> str:
    domain = value.rstrip(".").lower()
    if len(domain) > 253 or not domain:
        raise WorkflowDefinitionError("invalid domain value")
    labels = domain.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not re.fullmatch(r"[a-z0-9-]+", label)
        for label in labels
    ):
        raise WorkflowDefinitionError("invalid domain value")
    return domain


def resolve_workflow_inputs(definition: Mapping[str, object], provided: Mapping[str, object]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    known = set()
    raw_inputs = definition.get("inputs")
    for item in raw_inputs if isinstance(raw_inputs, list) else []:
        if not isinstance(item, Mapping):
            continue
        input_id = str(item.get("id") or "")
        known.add(input_id)
        raw_value = provided.get(input_id, item.get("default", ""))
        resolved[input_id] = normalize_workflow_input_value(item, raw_value)
    unknown = sorted(str(key) for key in provided if str(key) not in known)
    if unknown:
        raise WorkflowDefinitionError(f"unknown workflow inputs: {', '.join(unknown)}")
    return resolved


def render_step_command(step: Mapping[str, object], variables: Mapping[str, str]) -> str:
    missing = workflow_tokens(str(step.get("cmd") or "")) - set(variables)
    if missing:
        raise WorkflowDefinitionError(
            f"workflow step is missing variables: {', '.join(sorted(missing))}"
        )
    command = render_workflow_command(str(step.get("cmd") or ""), dict(variables)).strip()
    if not command:
        raise WorkflowDefinitionError("workflow step rendered an empty command")
    return command


def render_step_display_command(
    step: Mapping[str, object],
    definition: Mapping[str, object],
    variables: Mapping[str, str],
) -> str:
    """Render a value-safe command for run metadata, logs, and history."""
    missing = workflow_tokens(str(step.get("cmd") or "")) - set(variables)
    if missing:
        raise WorkflowDefinitionError(
            f"workflow step is missing variables: {', '.join(sorted(missing))}"
        )
    raw_inputs = definition.get("inputs")
    inputs = (
        [item for item in raw_inputs if isinstance(item, Mapping)]
        if isinstance(raw_inputs, list)
        else []
    )
    input_names = {str(item.get("id") or "") for item in inputs}
    placeholders = {
        str(item.get("id") or ""): "[redacted]"
        for item in inputs
        if item.get("sensitive") and item.get("id")
    }
    placeholders.update(
        {
            name: f"[captured:{name}]"
            for name in variables
            if name not in input_names
        }
    )
    command = render_workflow_command(
        str(step.get("cmd") or ""),
        dict(variables),
        placeholders=placeholders,
    ).strip()
    if not command:
        raise WorkflowDefinitionError("workflow step rendered an empty command")
    return command


def workflow_private_values(
    definition: Mapping[str, object],
    variables: Mapping[str, str],
) -> tuple[str, ...]:
    """Return sensitive inputs and capture values that metadata must not expose."""
    raw_inputs = definition.get("inputs")
    inputs = (
        [item for item in raw_inputs if isinstance(item, Mapping)]
        if isinstance(raw_inputs, list)
        else []
    )
    input_names = {str(item.get("id") or "") for item in inputs}
    private_names = {
        str(item.get("id") or "")
        for item in inputs
        if item.get("sensitive") and item.get("id")
    }
    private_names.update(name for name in variables if name not in input_names)
    return tuple(
        str(variables[name])
        for name in sorted(private_names)
        if name in variables and str(variables[name])
    )


def definition_json(definition: Mapping[str, object]) -> str:
    return json.dumps(definition, separators=(",", ":"), sort_keys=True)
