# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persist run previews in the database and optional full output in files."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import gzip
import hashlib
import json
import logging
import os

from config import resolve_data_dir
from core.helpers import get_log_session_id
from services.runs.output_model import LineEvent, UnknownCollector, from_wire, line_event_from_legacy, to_legacy_wire, to_wire

DATA_DIR = resolve_data_dir()
RUN_OUTPUT_DIR = os.path.join(DATA_DIR, "run-output")
# Artifact wrapper version. This is separate from LINE_EVENT_SCHEMA_VERSION:
# artifacts can change their envelope without changing per-line event fields.
RUN_OUTPUT_ARTIFACT_FORMAT_VERSION = 1
log = logging.getLogger("shell")


def ensure_run_output_dir():
    os.makedirs(RUN_OUTPUT_DIR, exist_ok=True)


def artifact_rel_path_for_run(run_id: str) -> str:
    digest = hashlib.sha256(str(run_id).encode("utf-8")).hexdigest()
    return os.path.join(digest[:2], digest[:4], f"{run_id}.txt.gz")


@dataclass(frozen=True)
class RunOutputLoadResult:
    events: list[LineEvent]
    source: str
    truncated: bool
    fallback: bool = False

    @property
    def entries(self) -> list[dict[str, object]]:
        return [to_legacy_wire(event) for event in self.events]

    @property
    def partial(self) -> bool:
        return self.truncated or self.fallback


class RunOutputCapture:
    def __init__(
        self,
        run_id: str,
        preview_limit: int,
        persist_full_output: bool,
        full_output_max_bytes: int,
        preview_max_bytes: int = 0,
    ):
        self.run_id = run_id
        self.preview_limit = max(0, int(preview_limit or 0))
        self.preview_max_bytes = max(0, int(preview_max_bytes or 0))
        self.persist_full_output = bool(persist_full_output)
        self.full_output_max_bytes = max(0, int(full_output_max_bytes or 0))
        self.preview_lines: deque[dict[str, object]] = deque()
        self.preview_line_bytes: deque[int] = deque()
        self.preview_bytes = 0
        self.preview_truncated = False
        self.output_line_count = 0
        self.full_output_available = False
        self.full_output_truncated = False
        self.full_output_bytes = 0
        self.artifact_rel_path: str | None = None
        self._artifact_file = None
        if self.persist_full_output:
            self.artifact_rel_path = artifact_rel_path_for_run(run_id)

    @staticmethod
    def _entry_storage_bytes(entry: dict[str, object]) -> int:
        # Match the SQLite preview serializer closely enough to keep the byte
        # cap conservative while avoiding re-serializing the whole preview.
        return len(json.dumps(entry).encode("utf-8")) + 2

    def _truncate_preview_entry(self, entry: dict[str, object]) -> dict[str, object]:
        if not self.preview_max_bytes:
            return dict(entry)
        preview_entry = dict(entry)
        if self._entry_storage_bytes(preview_entry) <= self.preview_max_bytes:
            return preview_entry
        original_text = str(preview_entry.get("text", ""))
        marker = " [preview line truncated]"
        low = 0
        high = len(original_text)
        best = ""
        while low <= high:
            mid = (low + high) // 2
            candidate = original_text[:mid] + marker
            preview_entry["text"] = candidate
            if self._entry_storage_bytes(preview_entry) <= self.preview_max_bytes:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1
        preview_entry["text"] = best or marker.strip()
        self.preview_truncated = True
        return preview_entry

    def _drop_oldest_preview_line(self) -> None:
        if not self.preview_lines:
            return
        self.preview_lines.popleft()
        if self.preview_line_bytes:
            self.preview_bytes = max(0, self.preview_bytes - self.preview_line_bytes.popleft())
        self.preview_truncated = True

    def _append_preview_entry(self, entry: dict[str, object]) -> None:
        preview_entry = self._truncate_preview_entry(entry)
        entry_bytes = self._entry_storage_bytes(preview_entry)
        if self.preview_limit > 0:
            while len(self.preview_lines) >= self.preview_limit:
                self._drop_oldest_preview_line()
        self.preview_lines.append(preview_entry)
        self.preview_line_bytes.append(entry_bytes)
        self.preview_bytes += entry_bytes
        if self.preview_max_bytes > 0:
            while self.preview_bytes > self.preview_max_bytes and len(self.preview_lines) > 1:
                self._drop_oldest_preview_line()

    @staticmethod
    def _jsonl_bytes(payload: dict[str, object]) -> int:
        return len((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))

    def _artifact_header(self) -> dict[str, object]:
        return {
            "v": RUN_OUTPUT_ARTIFACT_FORMAT_VERSION,
            "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_id": self.run_id,
        }

    def _ensure_artifact_file(self) -> bool:
        if self.full_output_truncated:
            return False
        if not self.persist_full_output or self._artifact_file:
            return bool(self._artifact_file)
        if not self.artifact_rel_path:
            self.artifact_rel_path = artifact_rel_path_for_run(self.run_id)
        header = self._artifact_header()
        header_bytes = self._jsonl_bytes(header)
        if self.full_output_max_bytes and header_bytes >= self.full_output_max_bytes:
            self.full_output_truncated = True
            log.warning("RUN_OUTPUT_ARTIFACT_TRUNCATED", extra={
                "run_id": self.run_id,
                "rel_path": self.artifact_rel_path,
                "artifact_bytes": self.full_output_bytes,
                "limit": self.full_output_max_bytes,
                "reason": "header_limit",
            })
            return False
        ensure_run_output_dir()
        artifact_path = get_artifact_path(self.artifact_rel_path)
        os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
        self._artifact_file = gzip.open(artifact_path, "wt", encoding="utf-8")
        self._artifact_file.write(json.dumps(header, separators=(",", ":")) + "\n")
        self.full_output_bytes += header_bytes
        log.info("RUN_OUTPUT_ARTIFACT_OPENED", extra={
            "run_id": self.run_id,
            "rel_path": self.artifact_rel_path,
            "format_version": RUN_OUTPUT_ARTIFACT_FORMAT_VERSION,
        })
        return True

    @staticmethod
    def _normalize_entities(entities: Sequence[Mapping[str, object]] | None) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        for entity in entities or []:
            if not isinstance(entity, Mapping):
                continue
            entity_type = str(entity.get("type", "")).strip()
            canonical_value = str(entity.get("canonical_value", "")).strip()
            if not entity_type or not canonical_value:
                continue
            item: dict[str, object] = {
                "type": entity_type,
                "value": str(entity.get("value", "")).strip() or canonical_value,
                "canonical_value": canonical_value,
                "confidence": str(entity.get("confidence", "")).strip() or "medium",
            }
            if isinstance(entity.get("source_line"), int):
                item["source_line"] = entity["source_line"]
            if isinstance(entity.get("start"), int) and isinstance(entity.get("end"), int):
                item["start"] = entity["start"]
                item["end"] = entity["end"]
            attributes = entity.get("attributes")
            if isinstance(attributes, Mapping):
                safe_attributes = {
                    str(key).strip(): value
                    for key, value in attributes.items()
                    if str(key).strip() and isinstance(value, (str, int, float, bool))
                }
                if safe_attributes:
                    item["attributes"] = safe_attributes
            normalized.append(item)
        return normalized

    def add_event(self, event: LineEvent):
        storage_event = replace(event, text=event.text.rstrip("\n"))
        entry = to_legacy_wire(storage_event)
        self.output_line_count += 1

        if observer := getattr(self, "_event_observer", None):
            observer(storage_event)
        self._append_preview_entry(entry)

        if not self.persist_full_output or not self._ensure_artifact_file():
            return
        artifact_file = self._artifact_file
        if artifact_file is None:
            return

        wire_entry = to_wire(storage_event)
        serialized = json.dumps(wire_entry, separators=(",", ":"))
        encoded = (serialized + "\n").encode("utf-8")
        if self.full_output_max_bytes and self.full_output_bytes + len(encoded) > self.full_output_max_bytes:
            self.full_output_truncated = True
            log.warning("RUN_OUTPUT_ARTIFACT_TRUNCATED", extra={
                "run_id": self.run_id,
                "rel_path": self.artifact_rel_path,
                "artifact_bytes": self.full_output_bytes,
                "limit": self.full_output_max_bytes,
                "reason": "line_limit",
            })
            self.close()
            return

        artifact_file.write(serialized + "\n")
        self.full_output_bytes += len(encoded)
        self.full_output_available = True

    def close(self):
        if self._artifact_file:
            self._artifact_file.close()
            self._artifact_file = None

    def finalize(self):
        self.close()
        finalized_rel_path = self.artifact_rel_path
        if not self.persist_full_output and not finalized_rel_path:
            return
        if not self.full_output_available and self.artifact_rel_path:
            delete_artifact_file(self.artifact_rel_path)
            self.artifact_rel_path = None
        log.info("RUN_OUTPUT_ARTIFACT_FINALIZED", extra={
            "run_id": self.run_id,
            "rel_path": finalized_rel_path,
            "artifact_bytes": self.full_output_bytes,
            "lines": self.output_line_count,
            "truncated": self.full_output_truncated,
            "available": self.full_output_available,
        })


def get_artifact_path(rel_path: str) -> str:
    return os.path.join(RUN_OUTPUT_DIR, rel_path)


def delete_artifact_file(rel_path: str | None):
    if not rel_path:
        return
    artifact_path = get_artifact_path(rel_path)
    try:
        os.remove(artifact_path)
    except FileNotFoundError:
        pass
    else:
        _remove_empty_artifact_parent_dirs(os.path.dirname(artifact_path))


def _remove_empty_artifact_parent_dirs(path: str) -> None:
    run_output_root = os.path.abspath(RUN_OUTPUT_DIR)
    current = os.path.abspath(path)
    while current != run_output_root and current.startswith(run_output_root + os.sep):
        try:
            os.rmdir(current)
        except OSError:
            return
        current = os.path.dirname(current)


def load_full_output_lines(rel_path: str) -> list[str]:
    return [event.text for event in load_full_output_events(rel_path)]


def load_full_output_events(rel_path: str, unknown_collector: UnknownCollector | None = None) -> list[LineEvent]:
    raw_rows: list[str] = []
    with gzip.open(get_artifact_path(rel_path), "rt", encoding="utf-8") as f:
        events: list[LineEvent] = []
        for index, raw_row in enumerate(f):
            row = raw_row.rstrip("\r\n")
            raw_rows.append(row)
            try:
                item = json.loads(row)
            except json.JSONDecodeError as exc:
                log.warning("RUN_OUTPUT_ARTIFACT_PARSE_FALLBACK", extra={
                    "rel_path": rel_path,
                    "row_index": index,
                    "reason": "json_decode",
                    "error": str(exc),
                })
                raw_rows.extend(rest.rstrip("\r\n") for rest in f)
                return [line_event_from_legacy(line) for line in raw_rows]
            if index == 0 and _is_artifact_header(item):
                continue
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                log.warning("RUN_OUTPUT_ARTIFACT_PARSE_FALLBACK", extra={
                    "rel_path": rel_path,
                    "row_index": index,
                    "reason": "invalid_row",
                    "error": type(item).__name__,
                })
                raw_rows.extend(rest.rstrip("\r\n") for rest in f)
                return [line_event_from_legacy(line) for line in raw_rows]
            events.append(from_wire(item, unknown_collector))
    return events


def _is_artifact_header(item: object) -> bool:
    # A text field disambiguates line-event rows that may carry incidental
    # header-shaped metadata from the artifact wrapper header.
    return (
        isinstance(item, dict)
        and item.get("v") == RUN_OUTPUT_ARTIFACT_FORMAT_VERSION
        and isinstance(item.get("created"), str)
        and isinstance(item.get("run_id"), str)
        and "text" not in item
    )


def load_full_output_entries(rel_path: str) -> list[dict[str, object]]:
    return [to_legacy_wire(event) for event in load_full_output_events(rel_path)]


def preview_output_events_from_run(
    run: Mapping[str, object],
    unknown_collector: UnknownCollector | None = None,
) -> list[LineEvent]:
    raw = run.get("output_preview")
    if raw is None:
        raw = run.get("output")
    loaded = json.loads(str(raw)) if raw else []
    if loaded and isinstance(loaded[0], str):
        return [line_event_from_legacy(line) for line in loaded]
    events: list[LineEvent] = []
    for item in loaded:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            events.append(from_wire(item, unknown_collector))
        elif isinstance(item, str):
            events.append(line_event_from_legacy(item))
    return events


def preview_output_entries_from_run(run: Mapping[str, object]) -> list[dict[str, object]]:
    return [to_legacy_wire(event) for event in preview_output_events_from_run(run)]


def load_run_output_events_for_run(
    run: Mapping[str, object],
    *,
    prefer_full: bool = True,
    log_event: str = "FULL_OUTPUT_LOAD_FAILED",
    failure_log_extra: Mapping[str, object] | None = None,
) -> RunOutputLoadResult:
    unknown_collector = unknown_line_event_collector({
        "run_id": str(run.get("id") or ""),
        "session": get_log_session_id(str(run.get("session_id") or "")),
    })
    if prefer_full and run.get("full_output_available") and run.get("rel_path"):
        rel_path = str(run.get("rel_path") or "")
        try:
            return RunOutputLoadResult(
                events=load_full_output_events(rel_path, unknown_collector),
                source="full",
                truncated=bool(run.get("full_output_truncated")),
            )
        except (OSError, EOFError, UnicodeError, json.JSONDecodeError) as exc:
            log_extra: dict[str, object] = {
                "run_id": str(run.get("id") or ""),
                "reason": type(exc).__name__,
            }
            default_log_extra = {
                "session": get_log_session_id(str(run.get("session_id") or "")),
                "rel_path": rel_path,
            }
            log_extra.update(default_log_extra if failure_log_extra is None else failure_log_extra)
            log.warning(log_event, extra=log_extra)
    return RunOutputLoadResult(
        events=preview_output_events_from_run(run, unknown_collector),
        source="preview",
        truncated=bool(run.get("preview_truncated")),
        fallback=bool(prefer_full and run.get("full_output_available") and run.get("rel_path")),
    )


def load_run_output_entries_for_run(
    run: Mapping[str, object],
    *,
    prefer_full: bool = True,
    log_event: str = "FULL_OUTPUT_LOAD_FAILED",
) -> RunOutputLoadResult:
    return load_run_output_events_for_run(run, prefer_full=prefer_full, log_event=log_event)


def unknown_line_event_collector(base_extra: Mapping[str, object]) -> UnknownCollector:
    seen: set[tuple[str, str]] = set()

    def collect(family: str, value: str) -> None:
        key = (family, value)
        if key in seen:
            return
        seen.add(key)
        log.warning("LINE_EVENT_UNKNOWN_VALUE", extra={**base_extra, "family": family, "value": value})

    return collect
