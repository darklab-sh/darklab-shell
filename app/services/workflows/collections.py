# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded collection captures used by assessment workflow fan-out."""

from __future__ import annotations

import json
from collections.abc import Mapping

from services.runs.output_model import LineEvent
from services.workflows.captures import (
    MAX_CAPTURES_PER_STEP,
    MAX_CAPTURE_VALUE_BYTES,
    _IGNORED_ROLES,
    _json_pointer_value,
)

MAX_CAPTURE_ITEMS = 32
MAX_COLLECTION_TOTAL_BYTES = 8192


def _allowed(event: LineEvent) -> bool:
    return (
        event.kind.value != "notice"
        and event.role not in _IGNORED_ROLES
        and event.noise_kind is None
        and bool(event.text.strip())
    )


def _clean(value: object) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    if isinstance(value, bool):
        value = "true" if value else "false"
    text = str(value).strip()
    if not text or any(ord(char) < 32 and char != "\t" for char in text):
        return None
    if len(text.encode("utf-8")) > MAX_CAPTURE_VALUE_BYTES:
        return None
    return text


class WorkflowCollectionAccumulator:
    """Collect bounded, deduplicated values from normalized workflow output."""

    def __init__(self, captures: object):
        rules = captures if isinstance(captures, list) else []
        self.rules = [
            dict(rule) for rule in rules[:MAX_CAPTURES_PER_STEP]
            if isinstance(rule, Mapping)
            and str(rule.get("kind") or rule.get("mode") or "").lower() == "collection"
        ]
        self.values: dict[str, list[str]] = {}
        self.errors: list[str] = []
        self._json_attempted: set[str] = set()

    def _rule(self, name: str) -> Mapping[str, object]:
        return next((rule for rule in self.rules if str(rule.get("name") or "") == name), {})

    def _save(self, name: str, value: object) -> None:
        text = _clean(value)
        if text is None:
            return
        values = self.values.setdefault(name, [])
        if text in values:
            return
        raw_limit = self._rule(name).get("item_limit")
        if not isinstance(raw_limit, (str, bytes, bytearray, int, float, type(None))):
            raw_limit = None
        try:
            limit = int(raw_limit or MAX_CAPTURE_ITEMS)
        except (TypeError, ValueError):
            limit = MAX_CAPTURE_ITEMS
        limit = min(max(limit, 1), MAX_CAPTURE_ITEMS)
        if len(values) >= limit:
            return
        total = sum(len(item.encode("utf-8")) for items in self.values.values() for item in items)
        if total + len(text.encode("utf-8")) > MAX_COLLECTION_TOTAL_BYTES:
            if "workflow collection captures exceed the execution limit" not in self.errors:
                self.errors.append("workflow collection captures exceed the execution limit")
            return
        values.append(text)

    def observe(self, event: LineEvent) -> None:
        for rule in self.rules:
            name = str(rule.get("name") or "")
            source = str(rule.get("source") or "")
            if not name or len(self.values.get(name, [])) >= MAX_CAPTURE_ITEMS:
                continue
            if source == "entity":
                entity_type = str(rule.get("entity_type") or "")
                for entity in event.entities:
                    if not entity_type or entity.type == entity_type:
                        self._save(name, entity.canonical_value or entity.value)
                continue
            if not _allowed(event):
                continue
            text = event.text.strip()
            if source == "first_nonempty_line":
                self._save(name, text)
            elif source == "first_line_containing" and str(rule.get("contains") or "") in text:
                self._save(name, text)
            elif source == "json_pointer" and name not in self._json_attempted:
                try:
                    payload = json.loads(text)
                    value = _json_pointer_value(payload, str(rule.get("pointer") or ""))
                except (TypeError, ValueError, IndexError, KeyError):
                    continue
                self._json_attempted.add(name)
                if isinstance(value, list):
                    for item in value:
                        self._save(name, item)

    def result(self) -> tuple[dict[str, list[str]], str]:
        missing = [
            str(rule.get("name") or "") for rule in self.rules
            if rule.get("required") and not self.values.get(str(rule.get("name") or ""))
        ]
        problems = [*self.errors]
        if missing:
            problems.append("required collection captures were not found: " + ", ".join(missing))
        return {name: list(values) for name, values in self.values.items()}, "; ".join(problems)
