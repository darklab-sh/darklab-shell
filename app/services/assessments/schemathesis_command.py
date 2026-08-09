# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded Schemathesis command derived from a reviewed local schema."""

from __future__ import annotations

import shlex
from typing import Any

from services.assessments.command_plan_contracts import CommandPlan
from services.assessments.schemathesis_command_paths import (
    schemathesis_runtime_path_args,
)
from services.assessments.schemathesis_schema import (
    ReviewedOpenApiSchema,
    SchemathesisSchemaError,
    review_local_openapi_json,
)


SCHEMATHESIS_MAX_EXAMPLES_PER_OPERATION = 10
SCHEMATHESIS_MAX_FAILURES = 10
SCHEMATHESIS_RATE_LIMIT = "2/s"
SCHEMATHESIS_REQUEST_TIMEOUT_SECONDS = 10
SCHEMATHESIS_TIME_LIMIT_SECONDS = 300
SCHEMATHESIS_WORKERS = 1
def reviewed_schemathesis_command_plan(
    schema: ReviewedOpenApiSchema,
    *,
    schema_path: Any = None,
    config_path: Any = None,
    report_path: Any = None,
) -> CommandPlan | None:
    """Return a fixed read-only negative-testing plan for one reviewed schema."""
    reviewed = _rereview(schema)
    if reviewed is None:
        return None
    paths = schemathesis_runtime_path_args(schema_path, config_path, report_path)
    if paths is None:
        return None
    schema_arg, config_arg, report_arg = paths
    base_url = shlex.quote(reviewed.base_url)
    request_limit = reviewed.operation_count * SCHEMATHESIS_MAX_EXAMPLES_PER_OPERATION
    command = (
        f"schemathesis --config-file {config_arg} run {schema_arg} "
        f"--url {base_url} --workers {SCHEMATHESIS_WORKERS} "
        "--phases fuzzing --include-method GET --include-method HEAD "
        "--checks not_a_server_error,status_code_conformance,content_type_conformance,"
        "response_schema_conformance,negative_data_rejection "
        f"--max-failures {SCHEMATHESIS_MAX_FAILURES} --exclude-deprecated "
        f"--rate-limit {SCHEMATHESIS_RATE_LIMIT} --max-redirects 0 "
        f"--request-timeout {SCHEMATHESIS_REQUEST_TIMEOUT_SECONDS} --request-retries 0 "
        f"--report ndjson --report-ndjson-path {report_arg} "
        "--output-sanitize true --output-truncate true --mode negative "
        f"--max-examples {SCHEMATHESIS_MAX_EXAMPLES_PER_OPERATION} --seed 1 "
        "--generation-database none --generation-deterministic --no-color"
    )
    return CommandPlan(
        command,
        f"One reviewed local OpenAPI artifact, {reviewed.operation_count} GET/HEAD "
        f"operations, at most {SCHEMATHESIS_MAX_EXAMPLES_PER_OPERATION} negative examples "
        f"per operation, {SCHEMATHESIS_RATE_LIMIT}, one worker, no redirects or retries, "
        "and a private sanitized NDJSON report.",
        request_limit,
        SCHEMATHESIS_TIME_LIMIT_SECONDS,
        "none",
    )


def reviewed_schemathesis_command_matches(
    command: Any,
    schema: ReviewedOpenApiSchema,
    *,
    schema_path: Any = None,
    config_path: Any = None,
    report_path: Any = None,
) -> bool:
    """Return whether a command exactly matches the app-owned schema plan."""
    expected = reviewed_schemathesis_command_plan(
        schema,
        schema_path=schema_path,
        config_path=config_path,
        report_path=report_path,
    )
    return expected is not None and str(command or "") == expected.command


def _rereview(schema: Any) -> ReviewedOpenApiSchema | None:
    if type(schema) is not ReviewedOpenApiSchema:
        return None
    try:
        reviewed = review_local_openapi_json(
            schema.content,
            source_artifact_id=schema.source_artifact_id,
            base_url=schema.base_url,
        )
    except SchemathesisSchemaError:
        return None
    return reviewed if reviewed == schema else None


__all__ = [
    "SCHEMATHESIS_MAX_EXAMPLES_PER_OPERATION",
    "SCHEMATHESIS_MAX_FAILURES",
    "SCHEMATHESIS_RATE_LIMIT",
    "SCHEMATHESIS_REQUEST_TIMEOUT_SECONDS",
    "SCHEMATHESIS_TIME_LIMIT_SECONDS",
    "SCHEMATHESIS_WORKERS",
    "reviewed_schemathesis_command_matches",
    "reviewed_schemathesis_command_plan",
]
