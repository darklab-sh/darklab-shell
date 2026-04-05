"""
Centralized logging configuration for shell.darklab.sh.

Two output formats, controlled by CFG['log_format']:
  text  — human-readable key=value lines (default, good for Docker stdout)
  gelf  — newline-delimited GELF 1.1 JSON for Graylog / GELF-capable back-ends

Log level is controlled by CFG['log_level'] (default: INFO).
Structured context is passed via Python's logging extra={} mechanism — extra
fields appear as _field_name in GELF output and as key=value pairs in text mode.

Call configure_logging(cfg) once, before importing any local module that may
emit log records at import time (e.g. process.py, which attempts a Redis
connection and logs the result during module initialisation).
"""

import json
import logging
import socket

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# All attributes that logging.LogRecord populates by default.
# Anything in record.__dict__ that is NOT in this set and does NOT start
# with "_" is treated as a caller-supplied structured extra field.
_STDLIB_ATTRS = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "taskName", "thread", "threadName",
})

# GELF syslog severity mapping
_GELF_LEVEL = {
    logging.DEBUG:    7,
    logging.INFO:     6,
    logging.WARNING:  4,
    logging.ERROR:    3,
    logging.CRITICAL: 2,
}

_HOSTNAME = socket.getfqdn()


def _extra_fields(record: logging.LogRecord) -> dict:
    """Return caller-supplied extra fields from a LogRecord, sorted by key.
    Excludes standard LogRecord attributes and private underscore-prefixed keys."""
    return {
        k: v for k, v in sorted(record.__dict__.items())
        if k not in _STDLIB_ATTRS and not k.startswith("_")
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

class GELFFormatter(logging.Formatter):
    """
    Emits one compact GELF 1.1 JSON object per record (newline-delimited).

    short_message carries the bare event name (e.g. "RUN_START"); all
    structured context lives in _-prefixed GELF additional fields so that
    Graylog / OpenSearch can index and filter on individual values without
    parsing the message string.
    """

    def __init__(self, app_name: str = "shell.darklab.sh") -> None:
        super().__init__()
        self._app_name = app_name

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        payload: dict = {
            "version":       "1.1",
            "host":          _HOSTNAME,
            "short_message": record.message,
            "timestamp":     record.created,
            "level":         _GELF_LEVEL.get(record.levelno, 7),
            "_app":          self._app_name,
            "_logger":       record.name,
        }
        if record.exc_info:
            payload["full_message"] = self.formatException(record.exc_info)
        for key, val in _extra_fields(record).items():
            payload[f"_{key}"] = val
        return json.dumps(payload, separators=(",", ":"), default=str)


class _TextFormatter(logging.Formatter):
    """
    Human-readable single-line format with structured extras appended:

        2026-04-02T10:00:00Z [INFO ] RUN_START  cmd='nmap 8.8.8.8'  ip=1.2.3.4  run_id=abc123

    Extra fields are sorted alphabetically for deterministic output.
    String values that contain spaces are repr()-quoted.
    Exception tracebacks are appended on subsequent lines.
    """

    _LEVEL_LABELS = {
        logging.DEBUG:    "DEBUG",
        logging.INFO:     "INFO ",
        logging.WARNING:  "WARN ",
        logging.ERROR:    "ERROR",
        logging.CRITICAL: "CRIT ",
    }

    def format(self, record: logging.LogRecord) -> str:
        import time
        ts    = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created))
        level = self._LEVEL_LABELS.get(record.levelno, record.levelname[:5].ljust(5))
        msg   = record.getMessage()
        line  = f"{ts} [{level}] {msg}"

        extras = _extra_fields(record)
        if extras:
            pairs = "  ".join(
                f"{k}={v!r}" if isinstance(v, str) and (" " in v or v == "") else f"{k}={v}"
                for k, v in extras.items()
            )
            line = f"{line}  {pairs}"

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line = f"{line}\n{record.exc_text}"

        return line


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure_logging(cfg: dict) -> None:
    """
    Apply level and format from cfg to the 'shell' logger.

    Must be called before any local module import that emits log records,
    specifically before 'from process import ...' in app.py.
    """
    level_name = str(cfg.get("log_level", "INFO")).upper()
    level      = getattr(logging, level_name, logging.INFO)
    fmt_name   = str(cfg.get("log_format", "text")).lower()
    app_name   = str(cfg.get("app_name", "shell.darklab.sh"))

    formatter: logging.Formatter = (
        GELFFormatter(app_name) if fmt_name == "gelf" else _TextFormatter()
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)  # handler accepts all; the logger level gates first

    logger = logging.getLogger("shell")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False  # do not forward to root — this is the complete pipeline

    # Suppress Werkzeug's built-in request lines; we cover request logging
    # via before_request / after_request hooks in app.py instead.
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    logger.info("LOGGING_CONFIGURED", extra={"level": level_name, "format": fmt_name})
