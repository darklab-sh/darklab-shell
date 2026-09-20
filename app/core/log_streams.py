# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Console stream routing without application configuration or startup imports."""

import logging
import sys


class _SeverityFilter(logging.Filter):
    def __init__(self, *, warnings: bool) -> None:
        super().__init__()
        self.warnings = warnings

    def filter(self, record: logging.LogRecord) -> bool:
        return (record.levelno >= logging.WARNING) == self.warnings


def console_handlers(formatter: logging.Formatter) -> list[logging.StreamHandler]:
    """Return disjoint stdout/stderr handlers; the logger controls verbosity."""
    handlers = []
    for stream, warnings in ((sys.stdout, False), (sys.stderr, True)):
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        handler.addFilter(_SeverityFilter(warnings=warnings))
        handlers.append(handler)
    return handlers
