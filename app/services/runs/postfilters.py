# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Run-output post-filter processors used by brokered command streams."""

from __future__ import annotations

from collections import deque
import json
import logging
import os
import re
from typing import Any, Mapping

import config as app_config
from services.commands.registry import command_root
from services.teams.scope import OwnerContext, personal_owner_context
from services.workspace.files import (
    WorkspaceDisabled,
    owner_workspace_dir,
)
from services.runs.output_sinks import SyntheticPostFilterProcessor as SyntheticPostFilterProcessor

log = logging.getLogger("shell")


class SyntheticPostFilterStageProcessor:
    """Apply one narrow app-native post-filter stage without enabling pipes."""

    def __init__(self, spec):
        self.spec = spec or {}
        self.kind = self.spec.get("kind")
        self._count = 0
        self._emitted = 0
        self._tail_buffer = deque(maxlen=int(self.spec.get("count", 0) or 0))
        self._grep_match = None
        self._line_buffer = []
        self._line_buffer_limit = max(0, int(app_config.CFG.get("max_output_lines", 0) or 0))
        self._line_buffer_dropped = 0

        if self.kind == "grep":
            pattern = self.spec["pattern"]
            flags = re.IGNORECASE if self.spec.get("ignore_case") else 0
            if self.spec.get("extended"):
                try:
                    compiled = re.compile(pattern, flags)
                except re.error as exc:
                    raise ValueError(f"Invalid synthetic grep regex: {exc}") from exc

                def _matches(line):
                    return bool(compiled.search(line))
            else:
                needle = pattern.lower() if self.spec.get("ignore_case") else pattern

                def _matches(line):
                    haystack = line.lower() if self.spec.get("ignore_case") else line
                    return needle in haystack

            if self.spec.get("invert_match"):
                self._grep_match = lambda line: not _matches(line)
            else:
                self._grep_match = _matches

    def process_output_line(self, line: str) -> list[str]:
        if not self.kind:
            return [line]

        normalized = str(line).rstrip("\n")
        if self.kind == "grep":
            return [line] if self._grep_match and self._grep_match(normalized) else []

        if self.kind == "head":
            if self._emitted >= int(self.spec.get("count", 0) or 0):
                return []
            self._emitted += 1
            return [line]

        if self.kind == "tail":
            self._tail_buffer.append(line)
            return []

        if self.kind == "wc_l":
            self._count += 1
            return []

        if self.kind in ("sort", "uniq", "jq"):
            if self._line_buffer_limit and len(self._line_buffer) >= self._line_buffer_limit:
                self._line_buffer_dropped += 1
                return []
            self._line_buffer.append(line)
            return []

        return [line]

    def finalize_output_lines(self) -> list[str]:
        def _buffer_truncation_notice() -> list[str]:
            if self._line_buffer_dropped <= 0:
                return []
            return [
                "[post-filter] output truncated to "
                f"{self._line_buffer_limit} lines before {self.kind}; "
                f"{self._line_buffer_dropped} later lines were skipped.\n"
            ]

        if self.kind == "tail":
            return list(self._tail_buffer)
        if self.kind == "wc_l":
            return [str(self._count)]

        if self.kind == "sort":
            numeric = self.spec.get("numeric", False)

            def _sort_key(ln):
                s = ln.rstrip("\n").lstrip()
                if numeric:
                    m = re.match(r'^[-+]?\d+\.?\d*', s)
                    return float(m.group(0)) if m else float("-inf")
                return s.lower()

            result = sorted(self._line_buffer, key=_sort_key, reverse=self.spec.get("reverse", False))
            if self.spec.get("unique"):
                seen: set = set()
                deduped = []
                for ln in result:
                    key = ln.rstrip("\n")
                    if key not in seen:
                        seen.add(key)
                        deduped.append(ln)
                result = deduped
            return [*_buffer_truncation_notice(), *result]

        if self.kind == "uniq":
            result = []
            prev = None
            if self.spec.get("count"):
                groups: list[tuple[int, str]] = []
                cnt = 0
                for ln in self._line_buffer:
                    n = ln.rstrip("\n")
                    if n == prev:
                        cnt += 1
                    else:
                        if prev is not None:
                            groups.append((cnt, prev))
                        prev = n
                        cnt = 1
                if prev is not None:
                    groups.append((cnt, prev))
                return [*_buffer_truncation_notice(), *[f"{c:7d} {ln}\n" for c, ln in groups]]
            for ln in self._line_buffer:
                n = ln.rstrip("\n")
                if n != prev:
                    result.append(ln)
                    prev = n
            return [*_buffer_truncation_notice(), *result]

        if self.kind == "jq":
            selector = self.spec.get("selector") if isinstance(self.spec, dict) else {}
            selector_op = selector.get("op", "") if isinstance(selector, dict) else ""
            if self._line_buffer_dropped > 0:
                log.warning("JQ_SELECTOR_CAP_HIT", extra={
                    "cap": "input_lines",
                    "limit": self._line_buffer_limit,
                    "dropped_count": self._line_buffer_dropped,
                    "selector_op": selector_op,
                })
                return ["[error] jq input exceeded the buffered line safety cap\n"]
            parsed = parse_jq_input_values(self._line_buffer)
            if isinstance(parsed, str):
                log.debug("JQ_SELECTOR_PARSE_FAILED", extra={
                    "selector_op": selector_op,
                    "input_line_count": len(self._line_buffer),
                    "error": parsed,
                })
                return [f"[error] {parsed}\n"]
            selected: list[Any] = []
            for value in parsed:
                selected.extend(select_jq_values(value, selector if isinstance(selector, dict) else {}))
                if len(selected) > 1000:
                    log.warning("JQ_SELECTOR_CAP_HIT", extra={
                        "cap": "output_lines",
                        "limit": 1000,
                        "selector_op": selector_op,
                    })
                    return ["[error] jq output exceeded the 1000-line safety cap\n"]
            output_lines: list[str] = []
            total_chars = 0
            for value in selected:
                rendered = format_jq_value(
                    value,
                    raw=bool(self.spec.get("raw")),
                    compact=bool(self.spec.get("compact")),
                )
                total_chars += len(rendered)
                if total_chars > 200000:
                    log.warning("JQ_SELECTOR_CAP_HIT", extra={
                        "cap": "output_bytes",
                        "limit": 200000,
                        "selector_op": selector_op,
                    })
                    return ["[error] jq output exceeded the 200 KB safety cap\n"]
                output_lines.extend(f"{line}\n" for line in rendered.split("\n"))
            log.debug("JQ_SELECTOR_STAGE_COMPLETED", extra={
                "selector_op": selector_op,
                "input_line_count": len(self._line_buffer),
                "selected_count": len(selected),
                "raw_output": bool(self.spec.get("raw")),
                "compact_output": bool(self.spec.get("compact")),
            })
            return output_lines

        return []


def parse_jq_input_values(lines: list[str]) -> list[Any] | str:
    non_empty = [str(line).strip() for line in lines if str(line).strip()]
    if not non_empty:
        return []
    jsonl_values: list[Any] = []
    for line in non_empty:
        try:
            jsonl_values.append(json.loads(line))
        except json.JSONDecodeError:
            break
    else:
        return jsonl_values
    try:
        return [json.loads("\n".join(non_empty))]
    except json.JSONDecodeError:
        return "jq expected JSON or JSONL input"


def jq_path_value(value: Any, path: list[str]) -> Any:
    current = value
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def jq_path_exists(value: Any, path: list[str]) -> bool:
    current = value
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def select_jq_values(value: Any, selector: dict[str, Any]) -> list[Any]:
    op = str(selector.get("op") or "")
    path = [str(part) for part in selector.get("path", []) or []]
    if op == "identity":
        return [value]
    if op == "field":
        return [jq_path_value(value, path)] if jq_path_exists(value, path) else []
    if op == "iterate":
        target = jq_path_value(value, path) if path else value
        return list(target) if isinstance(target, list) else []
    if op == "filter_has":
        return [value] if jq_path_exists(value, path) else []
    if op == "filter_eq":
        haystack = jq_filter_text(jq_path_value(value, path) if jq_path_exists(value, path) else "")
        return [value] if haystack == str(selector.get("value", "")) else []
    if op == "filter_contains":
        haystack = jq_filter_text(jq_path_value(value, path) if jq_path_exists(value, path) else "")
        return [value] if str(selector.get("value", "")) in haystack else []
    return []


def jq_filter_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def format_jq_value(value: Any, *, raw: bool, compact: bool) -> str:
    if raw and (value is None or isinstance(value, str | int | float | bool)):
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
    if compact:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(value, ensure_ascii=False, indent=2)


class WorkspacePathOutputFilter:
    """Display absolute owner-workspace paths as user-facing workspace paths."""

    def __init__(self, session_id: str, cfg: Mapping[str, Any], *, owner_context: OwnerContext | None = None):
        self.prefix = ""
        self.pattern = None
        if not session_id or not cfg.get("workspace_enabled"):
            return
        try:
            owner = owner_context or personal_owner_context(session_id)
            self.prefix = str(owner_workspace_dir(owner, cfg).resolve(strict=False)).rstrip(os.sep)
        except (WorkspaceDisabled, OSError):
            self.prefix = ""
        if self.prefix:
            self.pattern = re.compile(re.escape(self.prefix) + r"(/[\w@%+=:,./-]*)?")

    def process_output_line(self, line: str) -> str:
        if not self.pattern:
            return line

        def _replace(match):
            suffix = str(match.group(1) or "").lstrip("/")
            return f"/{suffix}" if suffix else "/"

        return self.pattern.sub(_replace, line)


class TruffleHogOutputFilter:
    _SECRET_FIELDS = {"Raw", "RawV2"}

    def __init__(self, command: str):
        self.enabled = command_root(command) == "trufflehog"

    def process_output_line(self, line: str) -> str:
        if not self.enabled:
            return line
        suffix = "\n" if str(line).endswith("\n") else ""
        try:
            parsed = json.loads(str(line).rstrip("\n"))
        except (TypeError, ValueError):
            return line
        if not isinstance(parsed, dict):
            return line
        redacted = False
        for secret_field in self._SECRET_FIELDS:
            if secret_field in parsed and parsed[secret_field] not in ("", None):
                parsed[secret_field] = "[redacted]"
                redacted = True
        if not redacted:
            return line
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":")) + suffix
