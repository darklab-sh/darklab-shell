# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact private path arguments for a reviewed Schemathesis command."""

from pathlib import Path
import shlex
from typing import Any, cast


_CONFIG_FILE = "schemathesis.toml"
_REPORT_FILE = "events.ndjson"
_SCHEMA_FILE = "schema.json"


def schemathesis_runtime_path_args(
    schema_path: Any,
    config_path: Any,
    report_path: Any,
) -> tuple[str, str, str] | None:
    """Return quoted paths only when all files share one private run directory."""
    if schema_path is None and config_path is None and report_path is None:
        return "[protected-schema]", "[protected-config]", "[protected-report]"
    try:
        schema_file = Path(cast(Any, schema_path))
        config_file = Path(cast(Any, config_path))
        report_file = Path(cast(Any, report_path))
    except TypeError:
        return None
    parent = schema_file.parent
    if (
        not schema_file.is_absolute()
        or not config_file.is_absolute()
        or not report_file.is_absolute()
        or config_file.parent != parent
        or report_file.parent != parent
        or not parent.name.startswith("run-")
        or parent.parent.name != "private-http-runs"
        or schema_file.name != _SCHEMA_FILE
        or config_file.name != _CONFIG_FILE
        or report_file.name != _REPORT_FILE
    ):
        return None
    return cast(tuple[str, str, str], tuple(shlex.quote(str(path)) for path in (schema_file, config_file, report_file)))


__all__ = ["schemathesis_runtime_path_args"]
