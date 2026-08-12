# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Strict bounded parsing for the pinned Schemathesis NDJSON event stream."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import re
from typing import Any
from urllib.parse import urlsplit

from services.assessments.schemathesis_command import (
    SCHEMATHESIS_MAX_EXAMPLES_PER_OPERATION,
    SCHEMATHESIS_MAX_FAILURES,
    SCHEMATHESIS_TIME_LIMIT_SECONDS,
)
from services.assessments.schemathesis_report_contracts import (
    SCHEMATHESIS_REPORT_TOOL_VERSION,
    SchemathesisFailureExample,
    SchemathesisOperationEvidence,
    SchemathesisReport,
    SchemathesisReportError,
)
from services.assessments.schemathesis_report_decode import (
    SCHEMATHESIS_REPORT_MAX_LINE_BYTES,
    SCHEMATHESIS_REPORT_MAX_LINES,
    decode_schemathesis_events,
)
from services.assessments.schemathesis_schema import ReviewedOpenApiSchema


SCHEMATHESIS_REPORT_MAX_BYTES = 8 * 1024 * 1024
SCHEMATHESIS_REPORT_MAX_CASES_PER_OPERATION = (
    SCHEMATHESIS_MAX_EXAMPLES_PER_OPERATION * 2
)
_MAX_FAILURE_MESSAGE_BYTES = 64 * 1024
_MAX_PARAMETER_NAMES = 32
_MAX_PARAMETER_NAME_LENGTH = 128
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_PROFILE_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_VERSION_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,31}")
_FAILURE_TYPE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,79}")
_READ_METHODS = frozenset({"GET", "HEAD"})
_CHECK_PRESENTATION = {
    "not_a_server_error": ("Server error", "high"),
    "status_code_conformance": ("Undocumented response status", "low"),
    "content_type_conformance": ("Undocumented response content type", "low"),
    "response_schema_conformance": ("Response violates schema", "medium"),
    "negative_data_rejection": ("API accepted schema-violating request", "medium"),
}
_SCENARIO_STATUSES = frozenset({"success", "failure", "error", "interrupted", "skip"})
_STATUS_PRIORITY = {"skip": 0, "success": 1, "failure": 2, "error": 3, "interrupted": 4}
_STOP_REASONS = frozenset({"completed", "failure_limit", "max_time", "interrupted"})


def parse_schemathesis_ndjson(
    raw: bytes,
    schema: ReviewedOpenApiSchema,
    *,
    profile_key: str,
    profile_version: str,
) -> SchemathesisReport:
    """Parse one complete pinned report without retaining generated values or bodies."""
    _validate_inputs(raw, schema, profile_key, profile_version)
    events = decode_schemathesis_events(raw)
    if events[0][0] != "Initialize" or events[-1][0] != "EngineFinished":
        raise _error(
            "incomplete_report", "Schemathesis report boundaries are incomplete."
        )
    initialize = events[0][1]
    seed = initialize.get("seed")
    if (
        initialize.get("schemathesis_version") != SCHEMATHESIS_REPORT_TOOL_VERSION
        or type(seed) is not int
        or seed != 1
    ):
        raise _error(
            "unsupported_report_version",
            "Schemathesis report provenance doesn't match the pinned runtime.",
        )
    terminal = events[-1][1]
    stop_reason = str(terminal.get("stop_reason") or "")
    running_time = _bounded_running_time(terminal.get("running_time"))
    if stop_reason not in _STOP_REASONS:
        raise _error(
            "invalid_stop_reason", "Schemathesis report has an invalid stop reason."
        )

    accumulators: dict[str, _OperationAccumulator] = {}
    seen_case_ids: set[str] = set()
    fatal = False
    interrupted = False
    for event_name, payload in events[1:-1]:
        fatal = fatal or event_name == "FatalError"
        interrupted = interrupted or event_name == "Interrupted"
        if event_name != "ScenarioFinished":
            continue
        _merge_scenario(payload, schema, accumulators, seen_case_ids)
    operations = tuple(accumulators[key].result() for key in sorted(accumulators))
    missing = tuple(
        operation for operation in schema.operations if operation not in accumulators
    )
    failure_count = sum(item.failure_count for item in operations)
    if failure_count > SCHEMATHESIS_MAX_FAILURES:
        raise _error(
            "failure_limit_exceeded",
            "Schemathesis report exceeds the reviewed distinct-failure limit.",
        )
    if stop_reason == "failure_limit" and failure_count == 0:
        raise _error(
            "invalid_stop_reason",
            "Schemathesis failure-limit completion requires reviewed failures.",
        )
    return SchemathesisReport(
        tool_version=SCHEMATHESIS_REPORT_TOOL_VERSION,
        profile_key=str(profile_key),
        profile_version=str(profile_version),
        schema_artifact_id=schema.source_artifact_id,
        schema_sha256=schema.source_sha256,
        schema_version=schema.schema_version,
        seed=1,
        stop_reason=stop_reason,
        running_time_seconds=running_time,
        complete=stop_reason in {"completed", "failure_limit"}
        and not fatal
        and not interrupted,
        expected_operation_count=schema.operation_count,
        observed_operation_count=len(operations),
        case_count=sum(item.case_count for item in operations),
        failure_count=failure_count,
        missing_operations=missing,
        operations=operations,
    )


class _OperationAccumulator:
    def __init__(self, operation: str):
        self.operation = operation
        self.method, self.path = operation.split(" ", 1)
        self.status = "skip"
        self.case_count = 0
        self.status_codes: set[int] = set()
        self.failures: dict[str, SchemathesisFailureExample] = {}

    def merge_status(self, status: str) -> None:
        if _STATUS_PRIORITY[status] > _STATUS_PRIORITY[self.status]:
            self.status = status

    def add_failure(self, failure: SchemathesisFailureExample) -> None:
        self.failures.setdefault(failure.fingerprint, failure)
        if len(self.failures) > SCHEMATHESIS_MAX_FAILURES:
            raise _error(
                "failure_limit_exceeded",
                "Schemathesis report exceeds the reviewed distinct-failure limit.",
            )

    def result(self) -> SchemathesisOperationEvidence:
        failures = tuple(self.failures[key] for key in sorted(self.failures))
        return SchemathesisOperationEvidence(
            operation=self.operation,
            method=self.method,
            path=self.path,
            status=self.status,
            case_count=self.case_count,
            failure_count=len(failures),
            response_statuses=tuple(sorted(self.status_codes)),
            failures=failures,
        )


def _validate_inputs(
    raw: Any,
    schema: Any,
    profile_key: Any,
    profile_version: Any,
) -> None:
    if type(schema) is not ReviewedOpenApiSchema:
        raise _error(
            "schema_review_required",
            "Schemathesis report requires one reviewed schema.",
        )
    if (
        not isinstance(raw, bytes)
        or not raw
        or len(raw) > SCHEMATHESIS_REPORT_MAX_BYTES
    ):
        raise _error(
            "invalid_report_size",
            "Schemathesis report is empty or exceeds the 8 MiB parsing limit.",
        )
    if (
        not isinstance(profile_key, str)
        or not isinstance(profile_version, str)
        or not _PROFILE_RE.fullmatch(profile_key)
        or not _VERSION_RE.fullmatch(profile_version)
    ):
        raise _error(
            "invalid_profile_provenance", "Schemathesis profile provenance is invalid."
        )


def _merge_scenario(
    payload: Mapping[str, Any],
    schema: ReviewedOpenApiSchema,
    accumulators: dict[str, _OperationAccumulator],
    seen_case_ids: set[str],
) -> None:
    if payload.get("phase") != "Fuzzing":
        raise _error(
            "invalid_scenario_phase",
            "Schemathesis report contains an unexpected phase.",
        )
    status = str(payload.get("status") or "")
    if status not in _SCENARIO_STATUSES or not isinstance(
        payload.get("is_final"), bool
    ):
        raise _error(
            "invalid_scenario_status", "Schemathesis scenario status is invalid."
        )
    recorder = payload.get("recorder")
    if not isinstance(recorder, Mapping):
        raise _error(
            "invalid_scenario_recorder", "Schemathesis scenario recorder is invalid."
        )
    operation = str(recorder.get("label") or "")
    if operation not in schema.operations:
        raise _error(
            "operation_out_of_scope",
            "Schemathesis report contains an unreviewed operation.",
        )
    accumulator = accumulators.setdefault(operation, _OperationAccumulator(operation))
    accumulator.merge_status(status)
    cases = _mapping_field(recorder, "cases")
    checks = _mapping_field(recorder, "checks")
    interactions = _mapping_field(recorder, "interactions")
    if status in {"success", "failure"} and not cases:
        raise _error(
            "missing_scenario_cases",
            "Schemathesis completed scenario omits generated cases.",
        )
    if set(checks) - set(cases) or set(interactions) - set(cases):
        raise _error(
            "orphan_report_record", "Schemathesis report contains orphan case evidence."
        )
    failed_check_count = 0
    for case_id, case_node in cases.items():
        case = _review_case(case_id, case_node, operation, seen_case_ids)
        accumulator.case_count += 1
        if accumulator.case_count > SCHEMATHESIS_REPORT_MAX_CASES_PER_OPERATION:
            raise _error(
                "case_limit_exceeded",
                "Schemathesis report exceeds the reviewed per-operation case limit.",
            )
        interaction = _review_interaction(interactions.get(case_id), case, schema)
        if status in {"success", "failure"} and interaction is None:
            raise _error(
                "missing_case_interaction",
                "Schemathesis report omits a completed case interaction.",
            )
        if interaction is not None:
            accumulator.status_codes.add(interaction)
        case_checks = checks.get(case_id)
        if status in {"success", "failure"} and not isinstance(case_checks, list):
            raise _error(
                "missing_case_checks", "Schemathesis report omits case check results."
            )
        if case_checks is None:
            continue
        failed_check_count += _review_checks(
            case_checks,
            case,
            operation,
            interaction,
            accumulator,
            require_complete=status in {"success", "failure"},
        )
    if (status == "success" and failed_check_count) or (
        status == "failure" and not failed_check_count
    ):
        raise _error(
            "scenario_result_mismatch",
            "Schemathesis scenario status doesn't match its check results.",
        )


def _review_case(
    case_id: Any,
    node: Any,
    operation: str,
    seen_case_ids: set[str],
) -> dict[str, Any]:
    if (
        not isinstance(case_id, str)
        or not _ID_RE.fullmatch(case_id)
        or case_id in seen_case_ids
    ):
        raise _error(
            "invalid_case_identity", "Schemathesis report case identity is invalid."
        )
    seen_case_ids.add(case_id)
    value = node.get("value") if isinstance(node, Mapping) else None
    if not isinstance(value, dict) or value.get("id") != case_id:
        raise _error(
            "invalid_case_record", "Schemathesis report case record is invalid."
        )
    method = str(value.get("method") or "").upper()
    path = str(value.get("path") or "")
    if method not in _READ_METHODS or f"{method} {path}" != operation:
        raise _error(
            "case_operation_mismatch", "Schemathesis case doesn't match its operation."
        )
    meta = value.get("meta")
    generation = meta.get("generation") if isinstance(meta, Mapping) else None
    phase = meta.get("phase") if isinstance(meta, Mapping) else None
    if (
        not isinstance(generation, Mapping)
        or generation.get("mode") != "negative"
        or not isinstance(phase, Mapping)
        or phase.get("name") != "fuzzing"
    ):
        raise _error(
            "case_generation_mismatch",
            "Schemathesis case wasn't generated in reviewed mode.",
        )
    return value


def _review_interaction(
    value: Any,
    case: Mapping[str, Any],
    schema: ReviewedOpenApiSchema,
) -> int | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _error("invalid_interaction", "Schemathesis interaction is invalid.")
    request = value.get("request")
    if (
        not isinstance(request, Mapping)
        or str(request.get("method") or "").upper() != case["method"]
    ):
        raise _error(
            "invalid_interaction_request", "Schemathesis request metadata is invalid."
        )
    uri = urlsplit(str(request.get("uri") or ""))
    base = urlsplit(schema.base_url)
    base_path = base.path.rstrip("/")
    operation_path = str(case["path"])
    if (
        uri.scheme != base.scheme
        or uri.netloc != base.netloc
        or (
            base_path
            and uri.path != base_path
            and not uri.path.startswith(base_path + "/")
        )
        or not _operation_path_matches(uri.path, base_path, operation_path)
        or uri.fragment
    ):
        raise _error(
            "interaction_out_of_scope",
            "Schemathesis interaction left the reviewed API scope.",
        )
    response = value.get("response")
    if response is None:
        return None
    status = response.get("status_code") if isinstance(response, Mapping) else None
    if (
        not isinstance(status, int)
        or isinstance(status, bool)
        or not 100 <= status <= 599
    ):
        raise _error(
            "invalid_response_status", "Schemathesis response status is invalid."
        )
    return status


def _review_checks(
    values: list[Any],
    case: Mapping[str, Any],
    operation: str,
    response_status: int | None,
    accumulator: _OperationAccumulator,
    *,
    require_complete: bool,
) -> int:
    names: set[str] = set()
    failure_count = 0
    for value in values:
        if not isinstance(value, Mapping):
            raise _error(
                "invalid_check_record", "Schemathesis check record is invalid."
            )
        name = str(value.get("name") or "")
        status = str(value.get("status") or "")
        if (
            name not in _CHECK_PRESENTATION
            or name in names
            or status not in {"success", "failure"}
        ):
            raise _error(
                "invalid_check_record", "Schemathesis check record is invalid."
            )
        names.add(name)
        failure_info = value.get("failure_info")
        if status == "success":
            if failure_info is not None:
                raise _error(
                    "invalid_success_record",
                    "Successful Schemathesis check has failure data.",
                )
            continue
        failure = (
            failure_info.get("failure") if isinstance(failure_info, Mapping) else None
        )
        if not isinstance(failure, Mapping):
            raise _error(
                "missing_failure_record",
                "Failed Schemathesis check omits failure data.",
            )
        failure_count += 1
        accumulator.add_failure(
            _failure_example(name, failure, case, operation, response_status)
        )
    if require_complete and names != set(_CHECK_PRESENTATION):
        raise _error(
            "incomplete_check_set",
            "Schemathesis case doesn't contain the reviewed checks.",
        )
    return failure_count


def _operation_path_matches(actual: str, base_path: str, operation_path: str) -> bool:
    expected = f"{base_path}{operation_path}" or "/"
    pattern_parts: list[str] = []
    cursor = 0
    for match in re.finditer(r"\{[^/{}]+\}", expected):
        pattern_parts.append(re.escape(expected[cursor : match.start()]))
        pattern_parts.append(r"[^/]+")
        cursor = match.end()
    pattern_parts.append(re.escape(expected[cursor:]))
    return re.fullmatch("".join(pattern_parts), actual) is not None


def _failure_example(
    check_name: str,
    failure: Mapping[str, Any],
    case: Mapping[str, Any],
    operation: str,
    response_status: int | None,
) -> SchemathesisFailureExample:
    failure_type = str(failure.get("type") or "")
    message = str(failure.get("message") or "")
    if (
        not _FAILURE_TYPE_RE.fullmatch(failure_type)
        or not message
        or len(message.encode("utf-8")) > _MAX_FAILURE_MESSAGE_BYTES
        or any(character in message for character in ("\x00", "\r"))
    ):
        raise _error(
            "invalid_failure_detail", "Schemathesis failure detail is invalid."
        )
    method, path = operation.split(" ", 1)
    parameter_names, media_type = _request_shape(case)
    example_digest = _digest_json(case)
    message_digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    title, severity = _CHECK_PRESENTATION[check_name]
    fingerprint = hashlib.sha256(
        "\x1f".join(
            (
                operation,
                check_name,
                failure_type,
                str(response_status or ""),
                message_digest,
            )
        ).encode()
    ).hexdigest()
    return SchemathesisFailureExample(
        fingerprint=fingerprint,
        operation=operation,
        method=method,
        path=path,
        check_name=check_name,
        failure_type=failure_type,
        title=title,
        severity=severity,
        response_status=response_status,
        parameter_names=parameter_names,
        body_media_type=media_type,
        example_digest=example_digest,
        message_digest=message_digest,
    )


def _request_shape(case: Mapping[str, Any]) -> tuple[tuple[str, ...], str]:
    names: list[str] = []
    for field, prefix in (("path_parameters", "path"), ("query", "query")):
        values = case.get(field, {})
        if not isinstance(values, Mapping):
            raise _error(
                "invalid_case_parameters", "Schemathesis case parameters are invalid."
            )
        names.extend(f"{prefix}:{key}" for key in values)
    body = case.get("body")
    if body is not None:
        if isinstance(body, Mapping):
            names.extend(f"body:{key}" for key in body if key != "$base64")
        names.append("body")
    normalized = tuple(sorted(set(str(name) for name in names)))
    if len(normalized) > _MAX_PARAMETER_NAMES or any(
        not name
        or len(name) > _MAX_PARAMETER_NAME_LENGTH
        or any(ord(char) < 32 for char in name)
        for name in normalized
    ):
        raise _error(
            "case_parameter_limit_exceeded",
            "Schemathesis case has too many parameters.",
        )
    media_type = str(case.get("media_type") or "")
    if len(media_type) > 128 or any(ord(character) < 32 for character in media_type):
        raise _error(
            "invalid_case_media_type", "Schemathesis case media type is invalid."
        )
    return normalized, media_type


def _mapping_field(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    field = value.get(key, {})
    if not isinstance(field, Mapping):
        raise _error(
            "invalid_scenario_recorder", "Schemathesis scenario recorder is invalid."
        )
    return field


def _bounded_running_time(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _error(
            "invalid_running_time", "Schemathesis report running time is invalid."
        )
    result = float(value)
    if (
        not math.isfinite(result)
        or result < 0
        or result > SCHEMATHESIS_TIME_LIMIT_SECONDS + 30
    ):
        raise _error(
            "invalid_running_time", "Schemathesis report running time is invalid."
        )
    return result


def _digest_json(value: Any) -> str:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise _error(
            "invalid_case_record", "Schemathesis report case record is invalid."
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _error(code: str, message: str) -> SchemathesisReportError:
    return SchemathesisReportError(code, message)


__all__ = [
    "SCHEMATHESIS_REPORT_MAX_BYTES",
    "SCHEMATHESIS_REPORT_MAX_CASES_PER_OPERATION",
    "SCHEMATHESIS_REPORT_MAX_LINE_BYTES",
    "SCHEMATHESIS_REPORT_MAX_LINES",
    "parse_schemathesis_ndjson",
]
