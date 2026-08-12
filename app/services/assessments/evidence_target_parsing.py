# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Privacy-safe command-target parsing for assessment evidence."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping
import logging
import re
from typing import TypeVar

from core.output_targets import extract_target
from services.metrics_lazy import app_metrics

_TARGET_PARSER = "command_registry"
_ROOT_RE = re.compile(r"[^a-z0-9_.:-]+")

Identity = TypeVar("Identity", bound=Hashable)
log = logging.getLogger("shell")


def _normalized_root(value: object) -> str:
    basename = str(value or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return (_ROOT_RE.sub("_", basename).strip("._:-") or "unknown")[:80]


def command_identities(
    command: str,
    command_target_inputs_fn: Callable[[str], list[dict[str, str]]],
    canonical_identity_fn: Callable[[object, object], Identity | None],
    *,
    run_id: str,
    root: str,
) -> set[Identity]:
    """Return parsed identities and report bounded parser/fallback outcomes."""
    identities: set[Identity] = set()
    safe_root = _normalized_root(root)
    parse_error: Exception | None = None
    try:
        inputs = command_target_inputs_fn(command)
    except Exception as exc:
        parse_error = exc
        inputs = []
    for item in inputs if isinstance(inputs, list) else []:
        if not isinstance(item, Mapping) or str(item.get("target_list_file") or "") == "1":
            continue
        identity = canonical_identity_fn(item.get("value"), item.get("value_type"))
        if identity is not None:
            identities.add(identity)
    parsed_count = len(identities)
    if not identities:
        fallback = extract_target(command)
        for value in str(fallback or "").split(","):
            identity = canonical_identity_fn(value, "target")
            if identity is not None:
                identities.add(identity)
    outcome = "parsed" if parsed_count else ("fallback_error" if parse_error else "fallback_empty")
    if parse_error is not None:
        log.warning("PROJECT_ASSESSMENT_TARGET_PARSE_FALLBACK", extra={
            "run_id": run_id,
            "command_root": safe_root,
            "parser": _TARGET_PARSER,
            "error_class": type(parse_error).__name__,
        })
    log.debug("PROJECT_ASSESSMENT_TARGET_PARSE_RESULT", extra={
        "run_id": run_id,
        "command_root": safe_root,
        "parser": _TARGET_PARSER,
        "outcome": outcome,
        "parsed_identity_count": parsed_count,
        "fallback_identity_count": len(identities) if not parsed_count else 0,
    })
    app_metrics.record_assessment_parser_result(_TARGET_PARSER, outcome)
    return identities


__all__ = ["command_identities"]
