# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded active-XSS observations from one app-reviewed Dalfox launch."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlsplit

from core.output_targets import tokenize_command
from services.intel.canonical import CanonicalizationError, canonical_url


DALFOX_XSS_PARSER_VERSION = "dalfox-jsonl-xss-v1"
DALFOX_XSS_JSON_MAX_LINE_BYTES = 32 * 1024
DALFOX_XSS_MAX_OBSERVATIONS = 64
_ALLOWED_LOCATIONS = frozenset({
    "Query", "Header", "Body", "JsonBody", "MultipartBody", "Path", "Fragment",
})
_RESULT_CONTRACTS = {
    "V": ("confirmed", "high", "dalfox_dom_execution"),
    "A": ("needs_runtime_confirmation", "medium", "dalfox_ast_analysis"),
    "R": ("reflected_unconfirmed", "low", "dalfox_reflection"),
}
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_OBSERVATION_ID_RE = re.compile(r"obs_[0-9a-f]{32}\Z")
_METHOD_RE = re.compile(r"[A-Z]{3,10}\Z")
_MESSAGE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
_PARAMETER_LOCATIONS = {
    "Body": "body",
    "Header": "header",
    "JsonBody": "json",
    "Query": "query",
}


@dataclass(frozen=True)
class ReviewedDalfoxXssContext:
    """Internal-only contract tying one active check to discovered parameter evidence."""

    target: str
    parameter: str
    location: str
    source_parameter_observation_id: str
    request_limit: int
    policy_level: str = "intrusive"

    def __post_init__(self) -> None:
        if (
            _url(self.target) != self.target
            or _parameter(self.parameter) != self.parameter
            or self.location not in _ALLOWED_LOCATIONS
            or not _OBSERVATION_ID_RE.fullmatch(self.source_parameter_observation_id)
            or not isinstance(self.request_limit, int)
            or isinstance(self.request_limit, bool)
            or not 1 <= self.request_limit <= 10_000
            or self.policy_level != "intrusive"
        ):
            raise ValueError("invalid reviewed Dalfox XSS context")


class DalfoxXssObservationState:
    """Normalize V/A/R rows only after an exact reviewed context and stream meta."""

    def __init__(
        self,
        command: str,
        source_run_id: str,
        context: ReviewedDalfoxXssContext | None,
    ) -> None:
        self.source_run_id = _text(source_run_id, 128)
        self.context = context if type(context) is ReviewedDalfoxXssContext else None
        self.tool_version = ""
        self.reported_finding_count = 0
        self._result_rows = 0
        self._seen: set[str] = set()
        self.enabled = (
            self.context is not None
            and _RUN_ID_RE.fullmatch(self.source_run_id) is not None
            and _active_command_matches(command, self.context)
        )

    def metadata(self, line: str) -> dict[str, dict[str, Any]]:
        """Return source metadata for one valid meta or finding row."""
        if not self.enabled:
            return {}
        record = _json_record(line)
        if not record:
            return {}
        meta = record.get("meta")
        if isinstance(meta, dict):
            return self._summary_metadata(meta)
        observation = self._finding_observation(record)
        if not observation:
            return {}
        return {"source_detail": {"dalfox_xss_observations": [observation]}}

    def _summary_metadata(self, meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
        context = self.context
        if context is None or self.tool_version or self._result_rows:
            return {}
        version = _text(meta.get("dalfox_version"), 64)
        targets = meta.get("targets")
        finding_count = meta.get("findings_count")
        total_requests = meta.get("total_requests")
        duration_ms = meta.get("scan_duration_ms")
        if (
            not version
            or not isinstance(targets, list)
            or len(targets) != 1
            or _url(targets[0]) != context.target
            or not _bounded_count(finding_count)
            or not _bounded_count(total_requests)
            or total_requests > context.request_limit
            or not _bounded_count(duration_ms)
        ):
            return {}
        self.tool_version = version
        self.reported_finding_count = finding_count
        return {"source_detail": {"dalfox_xss_scan": {
            "target": context.target,
            "parameter": context.parameter,
            "location": context.location,
            "source_parameter_observation_id": context.source_parameter_observation_id,
            "source_run_id": self.source_run_id,
            "tool_version": version,
            "parser_version": DALFOX_XSS_PARSER_VERSION,
            "policy_level": context.policy_level,
            "reported_finding_count": finding_count,
            "total_requests": total_requests,
            "scan_duration_ms": duration_ms,
            "truncated": finding_count > DALFOX_XSS_MAX_OBSERVATIONS,
        }}}

    def _finding_observation(self, record: dict[str, Any]) -> dict[str, Any] | None:
        context = self.context
        if context is None or not self.tool_version:
            return None
        result_type = _text(record.get("type"), 4)
        if result_type not in {*_RESULT_CONTRACTS, "I"}:
            return None
        if self._result_rows >= self.reported_finding_count:
            return None
        self._result_rows += 1
        if result_type == "I" or len(self._seen) >= DALFOX_XSS_MAX_OBSERVATIONS:
            return None
        if "request" in record or "response" in record:
            return None
        parameter = _parameter(record.get("param"))
        cwe_id = _cwe_id(record.get("cwe"))
        payload = _proof_text(record.get("payload"), 2048)
        evidence = _proof_text(record.get("evidence"), 4096)
        method = _text(record.get("method"), 10).upper()
        if (
            parameter != context.parameter
            or cwe_id != "CWE-79"
            or not payload
            or not evidence
            or not _METHOD_RE.fullmatch(method)
        ):
            return None
        validation_state, confidence, validation_method = _RESULT_CONTRACTS[result_type]
        proof_digest = _proof_digest(result_type, context, payload, evidence)
        observation_id = _observation_id(
            self.source_run_id,
            context.source_parameter_observation_id,
            result_type,
            proof_digest,
        )
        if observation_id in self._seen:
            return None
        self._seen.add(observation_id)
        observation: dict[str, Any] = {
            "observation_id": observation_id,
            "source_parameter_observation_id": context.source_parameter_observation_id,
            "target": context.target,
            "parameter": context.parameter,
            "location": context.location,
            "result_type": result_type,
            "validation_state": validation_state,
            "validation_method": validation_method,
            "confidence": confidence,
            "cwe_ids": [cwe_id],
            "method": method,
            "payload": payload,
            "evidence": evidence,
            "proof_digest": proof_digest,
            "source_run_id": self.source_run_id,
            "tool_version": self.tool_version,
            "parser_version": DALFOX_XSS_PARSER_VERSION,
            "policy_level": context.policy_level,
        }
        optional = {
            "type_description": _text(record.get("type_description"), 256),
            "inject_type": _text(record.get("inject_type"), 128),
            "message_id": _message_id(record.get("message_id")),
            "message": _text(record.get("message_str"), 512),
            "tool_severity": _severity(record.get("severity")),
        }
        observation.update({key: value for key, value in optional.items() if value})
        return observation


def _active_command_matches(command: str, context: ReviewedDalfoxXssContext) -> bool:
    tokens = tokenize_command(str(command or ""))
    if len(tokens) < 2 or tokens[0].casefold() != "dalfox":
        return False
    location = _PARAMETER_LOCATIONS.get(context.location, "")
    return (
        _url(tokens[1]) == context.target
        and _flag_value(tokens, "--format").casefold() == "jsonl"
        and _flag_value(tokens, "-p", "--param") == f"{context.parameter}:{location}"
        and bool(location)
        and "--skip-discovery" in tokens
        and "--skip-mining" in tokens
        and "--only-discovery" not in tokens
    )


def _flag_value(tokens: list[str], *names: str) -> str:
    for index, token in enumerate(tokens):
        for name in names:
            if token == name and index + 1 < len(tokens):
                return tokens[index + 1]
            if token.startswith(name + "="):
                return token.partition("=")[2]
    return ""


def _json_record(line: str) -> dict[str, Any] | None:
    raw = str(line or "").strip()
    if not raw.startswith("{") or len(raw.encode("utf-8")) > DALFOX_XSS_JSON_MAX_LINE_BYTES:
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


def _proof_text(value: Any, limit: int) -> str:
    text = str(value or "")
    if not text or len(text) > limit or any(ord(char) < 32 for char in text):
        return ""
    return text


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    return text if text and len(text) <= limit and not any(ord(char) < 32 for char in raw) else ""


def _bounded_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10_000_000


def _cwe_id(value: Any) -> str:
    normalized = _text(value, 32).upper()
    return "CWE-79" if normalized in {"79", "CWE-79"} else ""


def _message_id(value: Any) -> str:
    normalized = _text(value, 128)
    return normalized if _MESSAGE_ID_RE.fullmatch(normalized) else ""


def _severity(value: Any) -> str:
    normalized = _text(value, 16).casefold()
    return normalized if normalized in _SEVERITIES else ""


def _proof_digest(
    result_type: str,
    context: ReviewedDalfoxXssContext,
    payload: str,
    evidence: str,
) -> str:
    material = "\x1f".join((result_type, context.target, context.parameter, payload, evidence))
    return "sha256:" + hashlib.sha256(material.encode()).hexdigest()


def _observation_id(run_id: str, source_id: str, result_type: str, proof_digest: str) -> str:
    digest = hashlib.sha256(f"{run_id}\x1f{source_id}\x1f{result_type}\x1f{proof_digest}".encode()).hexdigest()
    return "obs_" + digest[:32]


__all__ = [
    "DALFOX_XSS_JSON_MAX_LINE_BYTES",
    "DALFOX_XSS_MAX_OBSERVATIONS",
    "DALFOX_XSS_PARSER_VERSION",
    "DalfoxXssObservationState",
    "ReviewedDalfoxXssContext",
]
