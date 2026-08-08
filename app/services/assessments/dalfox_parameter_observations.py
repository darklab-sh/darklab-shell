# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded parameter observations from reviewed Dalfox discovery JSONL."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit

from core.output_targets import tokenize_command
from services.intel.canonical import CanonicalizationError, canonical_url


DALFOX_DISCOVERY_PARSER_VERSION = "dalfox-jsonl-discovery-v1"
DALFOX_JSON_MAX_LINE_BYTES = 32 * 1024
DALFOX_MAX_PARAMETER_OBSERVATIONS = 256
_ALLOWED_LOCATIONS = frozenset({
    "Query", "Header", "Body", "JsonBody", "MultipartBody", "Path", "Fragment",
})


class DalfoxParameterObservationState:
    """Normalize one trusted discovery stream while bounding and deduplicating rows."""

    def __init__(self, command: str, source_run_id: str) -> None:
        self.command = str(command or "")
        self.source_run_id = _text(source_run_id, 128)
        self.target = _discovery_target(self.command)
        self.tool_version = ""
        self._seen: set[str] = set()

    def metadata(self, line: str) -> dict[str, dict[str, Any]]:
        """Return durable source metadata for one valid Dalfox JSONL row."""
        record = _json_record(line)
        if not record or not self.source_run_id or not self.target:
            return {}
        meta = record.get("meta")
        if isinstance(meta, dict):
            return self._summary_metadata(meta)
        observation = self._parameter_observation(record)
        if not observation:
            return {}
        return {"source_detail": {"parameter_observations": [observation]}}

    def _summary_metadata(self, meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
        mode = _text(meta.get("mode"), 32)
        version = _text(meta.get("dalfox_version"), 64)
        discovered = meta.get("params_discovered")
        if mode != "only_discovery" or not version or not _bounded_count(discovered):
            return {}
        self.tool_version = version
        return {"source_detail": {"parameter_discovery": {
            "target": self.target,
            "mode": mode,
            "reported_parameter_count": discovered,
            "source_run_id": self.source_run_id,
            "tool_version": version,
            "parser_version": DALFOX_DISCOVERY_PARSER_VERSION,
            "truncated": discovered > DALFOX_MAX_PARAMETER_OBSERVATIONS,
        }}}

    def _parameter_observation(self, record: dict[str, Any]) -> dict[str, str] | None:
        if not self.tool_version or len(self._seen) >= DALFOX_MAX_PARAMETER_OBSERVATIONS:
            return None
        target = _url(record.get("url"))
        parameter = _parameter(record.get("param"))
        location = _text(record.get("location"), 32)
        if target != self.target or not parameter or location not in _ALLOWED_LOCATIONS:
            return None
        observation_id = _observation_id(self.source_run_id, target, location, parameter)
        if observation_id in self._seen:
            return None
        self._seen.add(observation_id)
        return {
            "observation_id": observation_id,
            "target": target,
            "parameter": parameter,
            "location": location,
            "source_run_id": self.source_run_id,
            "tool_version": self.tool_version,
            "parser_version": DALFOX_DISCOVERY_PARSER_VERSION,
        }


def _discovery_target(command: str) -> str:
    tokens = tokenize_command(command)
    if len(tokens) < 2 or tokens[0].casefold() != "dalfox":
        return ""
    if (
        "--only-discovery" not in tokens
        or "--skip-mining-dict" not in tokens
        or "--skip-discovery" in tokens
    ):
        return ""
    output_format = _flag_value(tokens, "--format")
    return _url(tokens[1]) if output_format.casefold() == "jsonl" else ""


def _flag_value(tokens: list[str], name: str) -> str:
    for index, token in enumerate(tokens):
        if token == name and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith(name + "="):
            return token.partition("=")[2]
    return ""


def _json_record(line: str) -> dict[str, Any] | None:
    raw = str(line or "").strip()
    if not raw.startswith("{") or len(raw.encode("utf-8")) > DALFOX_JSON_MAX_LINE_BYTES:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _url(value: Any) -> str:
    raw = _text(value, 2048)
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if not raw or parsed.username or parsed.password:
        return ""
    try:
        return canonical_url(raw)
    except CanonicalizationError:
        return ""


def _parameter(value: Any) -> str:
    raw = str(value or "")
    parameter = raw.strip()
    if not parameter or len(parameter) > 256 or any(ord(char) < 32 for char in raw):
        return ""
    return parameter


def _bounded_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 1_000_000


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    return text if text and len(text) <= limit and not any(ord(char) < 32 for char in raw) else ""


def _observation_id(run_id: str, target: str, location: str, parameter: str) -> str:
    digest = hashlib.sha256(f"{run_id}\x1f{target}\x1f{location}\x1f{parameter}".encode()).hexdigest()
    return "obs_" + digest[:32]


__all__ = [
    "DALFOX_DISCOVERY_PARSER_VERSION",
    "DALFOX_JSON_MAX_LINE_BYTES",
    "DALFOX_MAX_PARAMETER_OBSERVATIONS",
    "DalfoxParameterObservationState",
]
