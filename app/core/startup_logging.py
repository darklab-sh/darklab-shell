# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Capture configuration logs until the runtime logging pipeline is ready."""

from __future__ import annotations

import json
import logging
import socket
import sys
import time
from typing import Any

_FATAL_FIELDS = ("phase", "source", "key", "error")
_GELF_LEVEL_ERROR = 3
_OPENSEARCH_METADATA_FIELDS = frozenset({
    "_field_names",
    "_id",
    "_ignored",
    "_index",
    "_meta",
    "_primary_term",
    "_routing",
    "_seq_no",
    "_source",
    "_version",
})


def gelf_additional_field_name(key: str, value: object = None) -> str:
    """Return a GELF field name with a stable OpenSearch mapping."""
    if key == "status":
        return "_http_status" if isinstance(value, int) and not isinstance(value, bool) else "_event_status"
    if key == "http_status" and value is not None and (
        not isinstance(value, int) or isinstance(value, bool)
    ):
        return "_event_http_status"
    field_name = f"_{key}"
    if field_name in _OPENSEARCH_METADATA_FIELDS:
        return f"_event_{key}"
    return field_name


def gelf_additional_field(key: str, value: object) -> tuple[str, object]:
    """Return one GELF additional field with a mapping-safe value type."""
    field_name = gelf_additional_field_name(key, value)
    if key == "status" and field_name == "_event_status" and value is not None:
        return field_name, str(value)
    if key == "http_status" and field_name == "_event_http_status":
        return field_name, str(value)
    if key.endswith("_status") and key != "http_status" and value is not None:
        return field_name, str(value)
    return field_name, value


def _safe_log_value(value: object, limit: int = 240) -> str:
    normalized = "".join(
        character if character.isprintable() and character not in "\r\n" else "?"
        for character in str(value)
    )
    return normalized[:limit]


class ConfigStartupLogger:
    """Buffer config records without attaching a handler before runtime bootstrap."""

    def __init__(self, logger: logging.Logger, *, app_version: str, active: bool) -> None:
        self._logger = logger
        self._active = active
        self.records: list[logging.LogRecord] = []
        self.app_name = "darklab_shell"
        self.app_version = app_version
        self.log_format = "text"

    def set_fallback_config(self, *, log_format: object, app_name: object, app_version: str) -> None:
        candidate_format = log_format.strip().lower() if isinstance(log_format, str) else ""
        if candidate_format in {"text", "gelf"}:
            self.log_format = candidate_format
        if isinstance(app_name, str) and app_name.strip():
            self.app_name = _safe_log_value(app_name.strip(), 64)
        self.app_version = _safe_log_value(app_version, 32)

    def debug(self, msg: object, *args: object, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: object, *args: object, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: object, *args: object, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: object, *args: object, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def _log(self, level: int, msg: object, *args: object, **kwargs: Any) -> None:
        if not self._active:
            self._logger.log(level, msg, *args, **kwargs)
            return
        extra = kwargs.pop("extra", None)
        exc_info = kwargs.pop("exc_info", None)
        stack_info = kwargs.pop("stack_info", None)
        kwargs.pop("stacklevel", None)
        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise TypeError(f"Unexpected logging arguments: {unexpected}")
        if exc_info is True:
            exc_info = sys.exc_info()
        record = self._logger.makeRecord(
            self._logger.name,
            level,
            "",
            0,
            msg,
            args,
            exc_info,
            extra=extra,
            sinfo=stack_info,
        )
        if record.getMessage() == "CONFIG_LOAD_FAILED":
            self._emit_fatal_fallback(record)
            return
        self.records.append(record)

    def drain(self) -> list[logging.LogRecord]:
        records = list(self.records)
        self.records.clear()
        self._active = False
        return records

    def _emit_fatal_fallback(self, record: logging.LogRecord) -> None:
        fields = {
            key: _safe_log_value(getattr(record, key, ""))
            for key in _FATAL_FIELDS
        }
        try:
            if self.log_format == "gelf":
                additional_fields: dict[str, object] = {}
                for key, value in fields.items():
                    field_name, field_value = gelf_additional_field(key, value)
                    if key == "status" and field_name in additional_fields:
                        continue
                    additional_fields[field_name] = field_value
                payload = {
                    "version": "1.1",
                    "host": socket.getfqdn(),
                    "short_message": "CONFIG_LOAD_FAILED",
                    "timestamp": record.created,
                    "level": _GELF_LEVEL_ERROR,
                    "_app": self.app_name,
                    "_app_version": self.app_version,
                    "_logger": record.name,
                    **additional_fields,
                }
                line = json.dumps(payload, separators=(",", ":"), default=str)
            else:
                timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created))
                extras = "  ".join(
                    f"{key}={value!r}" if " " in value or value == "" else f"{key}={value}"
                    for key, value in fields.items()
                )
                line = f"{timestamp} [ERROR] CONFIG_LOAD_FAILED  {extras}"
            sys.stderr.write(f"{line}\n")
            sys.stderr.flush()
        except Exception:  # pragma: no cover - diagnostics must not replace the config error
            pass


_CONFIG_STARTUP_LOGGERS: dict[str, ConfigStartupLogger] = {}


def install_config_log_buffer(
    logger: logging.Logger,
    *,
    app_version: str,
) -> ConfigStartupLogger:
    """Return a config logger that buffers until a direct pipeline is configured."""
    active = not bool(logger.handlers)
    startup_logger = ConfigStartupLogger(
        logger,
        app_version=app_version,
        active=active,
    )
    if active:
        _CONFIG_STARTUP_LOGGERS[logger.name] = startup_logger
    return startup_logger


def configure_config_log_fallback(
    logger: ConfigStartupLogger,
    *,
    log_format: object,
    app_name: object,
    app_version: str,
) -> None:
    """Update the fatal fallback after a valid overlay selects its output format."""
    logger.set_fallback_config(
        log_format=log_format,
        app_name=app_name,
        app_version=app_version,
    )


def drain_config_log_records(logger: logging.Logger) -> list[logging.LogRecord]:
    """Deactivate the startup logger and return its records for one-time replay."""
    startup_logger = _CONFIG_STARTUP_LOGGERS.pop(logger.name, None)
    return startup_logger.drain() if startup_logger is not None else []
