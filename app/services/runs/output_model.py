"""Typed run-output line events.

The helpers here define the compatibility contract used by the run-output
migration: legacy ``cls`` strings keep working, while new code can reason over
separate semantic ``kind`` and structural ``role`` fields.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any


LINE_EVENT_SCHEMA_VERSION = 1

UnknownCollector = Callable[[str, str], None]


class LineKind(str, Enum):
    info = "info"
    notice = "notice"
    warn = "warn"
    error = "error"

    @classmethod
    def from_legacy_cls(cls, value: object) -> "LineKind":
        for token in _legacy_cls_tokens(value):
            kind = _LEGACY_KIND_BY_CLS.get(token)
            if kind is not None:
                return kind
        return cls.info


class LineRole(str, Enum):
    body = "body"
    prompt_echo = "prompt-echo"
    section_header = "section-header"
    kv = "kv"
    help_row = "help-row"
    pty_marker = "pty-marker"
    progress = "progress"
    status_line = "status-line"
    success = "success"
    denied = "denied"
    exit_ok = "exit-ok"
    exit_fail = "exit-fail"

    @classmethod
    def from_legacy_cls(cls, value: object) -> "LineRole":
        for token in _legacy_cls_tokens(value):
            role = _LEGACY_ROLE_BY_CLS.get(token)
            if role is not None:
                return role
        return cls.body


class LineSignal(str, Enum):
    findings = "findings"
    warnings = "warnings"
    errors = "errors"
    summaries = "summaries"


LINE_KIND_VALUES = tuple(kind.value for kind in LineKind)
LINE_ROLE_VALUES = tuple(role.value for role in LineRole)
LINE_SIGNAL_VALUES = tuple(signal.value for signal in LineSignal)


_LEGACY_KIND_BY_CLS = {
    "": LineKind.info,
    "output": LineKind.info,
    "out": LineKind.info,
    "cmd": LineKind.info,
    "notice": LineKind.notice,
    "builtin-note": LineKind.notice,
    "welcome-output": LineKind.notice,
    "warn": LineKind.warn,
    "warning": LineKind.warn,
    "error": LineKind.error,
}

_LEGACY_ROLE_BY_CLS = {
    "": LineRole.body,
    "output": LineRole.body,
    "out": LineRole.body,
    "notice": LineRole.body,
    "warn": LineRole.body,
    "warning": LineRole.body,
    "error": LineRole.body,
    "builtin-note": LineRole.body,
    "builtin-spacer": LineRole.body,
    "welcome-output": LineRole.body,
    "cmd": LineRole.prompt_echo,
    "prompt-echo": LineRole.prompt_echo,
    "builtin-section": LineRole.section_header,
    "builtin-kv": LineRole.kv,
    "builtin-help-row": LineRole.help_row,
    "builtin-faq-q": LineRole.help_row,
    "builtin-faq-a": LineRole.help_row,
    "pty-marker": LineRole.pty_marker,
    "progress": LineRole.progress,
    "status-line": LineRole.status_line,
    "builtin-success": LineRole.success,
    "denied": LineRole.denied,
    "exit-ok": LineRole.exit_ok,
    "exit-fail": LineRole.exit_fail,
}

_KIND_LEGACY_CLS = {
    LineKind.info: "",
    LineKind.notice: "notice",
    LineKind.warn: "warn",
    LineKind.error: "error",
}

_ROLE_LEGACY_CLS = {
    LineRole.body: "",
    LineRole.prompt_echo: "prompt-echo",
    LineRole.section_header: "builtin-section",
    LineRole.kv: "builtin-kv",
    LineRole.help_row: "builtin-help-row",
    LineRole.pty_marker: "pty-marker",
    LineRole.progress: "progress",
    LineRole.status_line: "status-line",
    LineRole.success: "builtin-success",
    LineRole.denied: "denied",
    LineRole.exit_ok: "exit-ok",
    LineRole.exit_fail: "exit-fail",
}


@dataclass(frozen=True)
class LineEntity:
    type: str
    value: str
    canonical_value: str
    confidence: str
    source_line: int | None = None
    start: int | None = None
    end: int | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, object]) -> "LineEntity | None":
        entity_type = str(payload.get("type", "")).strip()
        canonical_value = str(payload.get("canonical_value", "")).strip()
        if not entity_type or not canonical_value:
            return None
        value = str(payload.get("value", "")).strip() or canonical_value
        confidence = str(payload.get("confidence", "")).strip() or "medium"
        start = _optional_int(payload.get("start"))
        end = _optional_int(payload.get("end"))
        if start is None or end is None:
            start = None
            end = None
        return cls(
            type=entity_type,
            value=value,
            canonical_value=canonical_value,
            confidence=confidence,
            source_line=_optional_int(payload.get("source_line")),
            start=start,
            end=end,
        )

    def to_wire(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": self.type,
            "value": self.value,
            "canonical_value": self.canonical_value,
            "confidence": self.confidence,
        }
        if self.source_line is not None:
            payload["source_line"] = self.source_line
        if self.start is not None:
            payload["start"] = self.start
        if self.end is not None:
            payload["end"] = self.end
        return payload


@dataclass(frozen=True)
class LineEvent:
    text: str
    kind: LineKind = LineKind.info
    role: LineRole = LineRole.body
    legacy_cls: str = ""
    ts_clock: str = ""
    ts_elapsed: str = ""
    signals: tuple[LineSignal, ...] = ()
    line_index: int | None = None
    command_root: str = ""
    target: str = ""
    entities: tuple[LineEntity, ...] = ()


def to_wire(event: LineEvent) -> dict[str, object]:
    payload = _legacy_payload(event)
    payload["v"] = LINE_EVENT_SCHEMA_VERSION
    payload["kind"] = event.kind.value
    payload["role"] = event.role.value
    return payload


def to_legacy_wire(event: LineEvent) -> dict[str, object]:
    return _legacy_payload(event)


def to_legacy_entry(event: LineEvent, *, include_timestamps: bool = True) -> dict[str, object]:
    return _legacy_payload(event, include_timestamps=include_timestamps)


def to_legacy_output_event(event: LineEvent, *, include_timestamps: bool = False) -> dict[str, object]:
    return {"type": "output", **_legacy_payload(event, include_timestamps=include_timestamps)}


def line_event_from_legacy(
    text: object,
    cls: object = "",
    *,
    kind: LineKind | str | None = None,
    role: LineRole | str | None = None,
    ts_clock: object = "",
    ts_elapsed: object = "",
    signals: Sequence[object] | None = None,
    line_index: object = None,
    command_root: object = "",
    target: object = "",
    entities: Sequence[Mapping[str, object]] | None = None,
) -> LineEvent:
    legacy_cls = str(cls or "")
    return LineEvent(
        text=str(text),
        kind=_coerce_kind(kind, legacy_cls),
        role=_coerce_role(role, legacy_cls),
        legacy_cls=legacy_cls,
        ts_clock=str(ts_clock or ""),
        ts_elapsed=str(ts_elapsed or ""),
        signals=_signals_from_wire(signals, None),
        line_index=_optional_int(line_index),
        command_root=str(command_root or ""),
        target=str(target or ""),
        entities=_entities_from_wire(entities),
    )


def from_wire(payload: Mapping[str, object], unknown_collector: UnknownCollector | None = None) -> LineEvent:
    """Decode a wire payload, falling back to legacy-safe defaults.

    Unknown kind, role, and signal values fall back to info/body/dropped. Callers
    that need telemetry should pass ``unknown_collector`` and throttle warnings
    at the artifact-load or stream level.
    """
    cls_value = payload.get("cls", "")
    kind = _enum_from_wire(LineKind, payload.get("kind"), LineKind.from_legacy_cls(cls_value), "kind", unknown_collector)
    role = _enum_from_wire(LineRole, payload.get("role"), LineRole.from_legacy_cls(cls_value), "role", unknown_collector)
    return LineEvent(
        text=str(payload.get("text", "")),
        kind=kind,
        role=role,
        legacy_cls=str(cls_value or ""),
        ts_clock=str(payload.get("tsC", "")),
        ts_elapsed=str(payload.get("tsE", "")),
        signals=_signals_from_wire(payload.get("signals"), unknown_collector),
        line_index=_optional_int(payload.get("line_index")),
        command_root=str(payload.get("command_root", "") or ""),
        target=str(payload.get("target", "") or ""),
        entities=_entities_from_wire(payload.get("entities")),
    )


def event_search_text(event: LineEvent) -> str:
    return event.text


def legacy_cls_for_event(event: LineEvent) -> str:
    """Return the compatibility class string for legacy readers.

    Events decoded from older payloads keep their original ``cls`` so
    round-trips preserve compatibility. New producers should leave
    ``legacy_cls`` empty and let this function choose the canonical class.
    If kind and role are both non-default, the legacy class prefers role;
    the explicit ``kind`` field carries severity.
    """
    if event.legacy_cls:
        return event.legacy_cls
    if event.role != LineRole.body:
        return _ROLE_LEGACY_CLS[event.role]
    return _KIND_LEGACY_CLS[event.kind]


def _legacy_payload(event: LineEvent, *, include_timestamps: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "text": event.text,
        "cls": legacy_cls_for_event(event),
    }
    # Route and storage compatibility paths keep timestamp keys even when a
    # line has no timestamp, matching the old RunOutputCapture payload shape.
    if include_timestamps or event.ts_clock:
        payload["tsC"] = event.ts_clock
    if include_timestamps or event.ts_elapsed:
        payload["tsE"] = event.ts_elapsed
    if event.signals:
        payload["signals"] = [signal.value for signal in event.signals]
    if event.line_index is not None:
        payload["line_index"] = event.line_index
    if event.command_root:
        payload["command_root"] = event.command_root
    if event.target:
        payload["target"] = event.target
    if event.entities:
        payload["entities"] = [entity.to_wire() for entity in event.entities]
    return payload


def _legacy_cls_tokens(value: object) -> tuple[str, ...]:
    if value is None:
        return ("",)
    text = str(value or "").strip()
    if not text:
        return ("",)
    return tuple(token for token in text.split() if token)


def _enum_from_wire(
    enum_cls: type[LineKind] | type[LineRole],
    value: object,
    default: LineKind | LineRole,
    family: str,
    unknown_collector: UnknownCollector | None,
) -> Any:
    if value is None or value == "":
        return default
    try:
        return enum_cls(str(value))
    except ValueError:
        if unknown_collector is not None:
            unknown_collector(family, str(value))
        return default


def _coerce_kind(value: LineKind | str | None, legacy_cls: str) -> LineKind:
    if isinstance(value, LineKind):
        return value
    if value is None or value == "":
        return LineKind.from_legacy_cls(legacy_cls)
    try:
        return LineKind(str(value))
    except ValueError:
        return LineKind.from_legacy_cls(legacy_cls)


def _coerce_role(value: LineRole | str | None, legacy_cls: str) -> LineRole:
    if isinstance(value, LineRole):
        return value
    if value is None or value == "":
        return LineRole.from_legacy_cls(legacy_cls)
    try:
        return LineRole(str(value))
    except ValueError:
        return LineRole.from_legacy_cls(legacy_cls)


def _signals_from_wire(value: object, unknown_collector: UnknownCollector | None) -> tuple[LineSignal, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    signals: list[LineSignal] = []
    for item in value:
        if isinstance(item, LineSignal):
            signals.append(item)
            continue
        try:
            signals.append(LineSignal(str(item)))
        except ValueError:
            if unknown_collector is not None:
                unknown_collector("signal", str(item))
    return tuple(signals)


def _entities_from_wire(value: object) -> tuple[LineEntity, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    entities: list[LineEntity] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        entity = LineEntity.from_wire(item)
        if entity is not None:
            entities.append(entity)
    return tuple(entities)


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


__all__ = [
    "LINE_EVENT_SCHEMA_VERSION",
    "LINE_KIND_VALUES",
    "LINE_ROLE_VALUES",
    "LINE_SIGNAL_VALUES",
    "LineEntity",
    "LineEvent",
    "LineKind",
    "LineRole",
    "LineSignal",
    "UnknownCollector",
    "event_search_text",
    "from_wire",
    "legacy_cls_for_event",
    "line_event_from_legacy",
    "to_legacy_entry",
    "to_legacy_output_event",
    "to_legacy_wire",
    "to_wire",
]
