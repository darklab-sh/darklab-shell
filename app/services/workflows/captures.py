# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded capture selectors for normalized workflow step output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from services.runs.output_model import LineEvent, LineKind, LineRole


MAX_CAPTURES_PER_STEP = 8
MAX_CAPTURE_VALUE_BYTES = 2048
MAX_CAPTURE_TOTAL_BYTES = 8192
_IGNORED_ROLES = {
    LineRole.prompt_echo,
    LineRole.progress,
    LineRole.status_line,
    LineRole.pty_marker,
    LineRole.exit_ok,
    LineRole.exit_fail,
}


def _json_pointer_value(payload: object, pointer: str) -> object:
    if pointer == "":
        return payload
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must start with /")
    current = payload
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not part.isdigit():
                raise KeyError(part)
            current = current[int(part)]
        elif isinstance(current, Mapping):
            current = current[part]
        else:
            raise KeyError(part)
    return current


def _scalar_text(value: object) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


class WorkflowCaptureAccumulator:
    """Collect at most one bounded scalar for each configured selector."""

    def __init__(self, captures: object):
        rules = captures if isinstance(captures, list) else []
        self.rules = [dict(rule) for rule in rules[:MAX_CAPTURES_PER_STEP] if isinstance(rule, Mapping)]
        self.values: dict[str, str] = {}
        self.errors: list[str] = []
        self._json_attempted: set[str] = set()

    @staticmethod
    def _line_allowed(event: LineEvent) -> bool:
        return (
            event.kind != LineKind.notice
            and event.role not in _IGNORED_ROLES
            and event.noise_kind is None
            and bool(event.text.strip())
        )

    def _save(self, name: str, value: str | None) -> None:
        if not value or name in self.values:
            return
        if any(ord(character) < 32 and character != "\t" for character in value):
            self.errors.append(f"capture {name} contains control characters")
            return
        encoded = value.encode("utf-8")
        if len(encoded) > MAX_CAPTURE_VALUE_BYTES:
            self.errors.append(f"capture {name} exceeds the value limit")
            return
        total = sum(len(item.encode("utf-8")) for item in self.values.values()) + len(encoded)
        if total > MAX_CAPTURE_TOTAL_BYTES:
            self.errors.append("workflow captures exceed the execution limit")
            return
        self.values[name] = value

    def observe(self, event: LineEvent) -> None:
        for rule in self.rules:
            name = str(rule.get("name") or "")
            if not name or name in self.values:
                continue
            source = str(rule.get("source") or "")
            if source == "entity":
                entity_type = str(rule.get("entity_type") or "")
                for entity in event.entities:
                    if not entity_type or entity.type == entity_type:
                        self._save(name, entity.canonical_value or entity.value)
                        break
                continue
            if not self._line_allowed(event):
                continue
            text = event.text.strip()
            if source == "first_nonempty_line":
                self._save(name, text)
            elif source == "first_line_containing":
                literal = str(rule.get("contains") or "")
                if literal and literal in text:
                    self._save(name, text)
            elif source == "json_pointer" and name not in self._json_attempted:
                try:
                    payload = json.loads(text)
                except (TypeError, ValueError):
                    continue
                self._json_attempted.add(name)
                try:
                    value = _scalar_text(_json_pointer_value(payload, str(rule.get("pointer") or "")))
                except (IndexError, KeyError, TypeError, ValueError):
                    continue
                self._save(name, value)

    def result(self) -> tuple[dict[str, str], str]:
        missing = [
            str(rule.get("name") or "")
            for rule in self.rules
            if rule.get("required") and str(rule.get("name") or "") not in self.values
        ]
        problems = [*self.errors]
        if missing:
            problems.append("required captures were not found: " + ", ".join(missing))
        return dict(self.values), "; ".join(problems)
