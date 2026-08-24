# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded JSON readers shared by browser and API assessment-batch routes."""

from __future__ import annotations

import json

from flask import request

from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_PREVIEW_REQUEST_MAX_BYTES,
)
from services.assessments.batch.lifecycle_contracts import BATCH_MUTATION_REQUEST_MAX_BYTES


def _json_body(
    max_bytes: int,
    *,
    too_large_code: str,
    too_large_message: str,
    invalid_code: str,
    invalid_message: str,
) -> object | None:
    content_length = request.content_length
    if content_length is not None and content_length > max_bytes:
        raise AssessmentBatchError(too_large_code, too_large_message, status_code=413)
    payload = request.stream.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise AssessmentBatchError(too_large_code, too_large_message, status_code=413)
    if not payload:
        return None
    if not request.is_json:
        raise AssessmentBatchError(invalid_code, invalid_message)
    try:
        data = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssessmentBatchError(invalid_code, invalid_message) from exc
    if data is None:
        raise AssessmentBatchError(invalid_code, invalid_message)
    return data


def selection_body() -> dict[str, object]:
    data = _json_body(
        BATCH_PREVIEW_REQUEST_MAX_BYTES,
        too_large_code="batch_preview_request_too_large",
        too_large_message="Assessment batch preview request exceeds the 64 KiB limit.",
        invalid_code="invalid_batch_selection",
        invalid_message="Assessment batch selection must be valid JSON.",
    )
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise AssessmentBatchError(
            "invalid_batch_selection",
            "Assessment batch selection must be an object.",
        )
    return data


def mutation_body(*, optional: bool = False) -> object:
    data = _json_body(
        BATCH_MUTATION_REQUEST_MAX_BYTES,
        too_large_code="batch_mutation_request_too_large",
        too_large_message="Assessment batch request exceeds the 16 KiB limit.",
        invalid_code="invalid_batch_request",
        invalid_message="Assessment batch request must be valid JSON.",
    )
    if data is None and not optional:
        raise AssessmentBatchError(
            "invalid_batch_start",
            "Assessment batch start must be a JSON object.",
        )
    return data
