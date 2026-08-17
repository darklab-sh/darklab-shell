# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Public request contracts for assessment-batch lifecycle mutations."""

from __future__ import annotations

from collections.abc import Mapping

from services.assessments.batch.contracts import AssessmentBatchError


BATCH_MUTATION_REQUEST_MAX_BYTES = 16 * 1024
_START_FIELDS = frozenset(
    {"confirmed", "plan_digest", "preview_id", "standard_confirmed", "tab_id"}
)


def _bounded_text(value: object, *, field: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum:
        raise AssessmentBatchError(
            "invalid_batch_start",
            f"{field} is required and must be at most {maximum} characters.",
        )
    return text


def normalize_batch_start_request(value: object) -> dict[str, object]:
    """Return one strict, bounded confirmation request."""
    if not isinstance(value, Mapping):
        raise AssessmentBatchError(
            "invalid_batch_start", "Assessment batch start must be a JSON object."
        )
    unsupported = sorted(str(field) for field in set(value) - _START_FIELDS)
    if unsupported:
        raise AssessmentBatchError(
            "invalid_batch_start",
            "Assessment batch start contains unsupported fields.",
            details={"fields": unsupported},
        )
    if value.get("confirmed") is not True:
        raise AssessmentBatchError(
            "batch_confirmation_required",
            "Starting an assessment batch requires explicit confirmation.",
            status_code=409,
        )
    standard_confirmed = value.get("standard_confirmed", False)
    if not isinstance(standard_confirmed, bool):
        raise AssessmentBatchError(
            "invalid_batch_start", "standard_confirmed must be true or false."
        )
    tab_id = str(value.get("tab_id") or "").strip()
    if len(tab_id) > 128:
        raise AssessmentBatchError(
            "invalid_batch_start", "tab_id must be at most 128 characters."
        )
    return {
        "preview_id": _bounded_text(
            value.get("preview_id"), field="preview_id", maximum=64
        ),
        "plan_digest": _bounded_text(
            value.get("plan_digest"), field="plan_digest", maximum=64
        ),
        "confirmed": True,
        "standard_confirmed": standard_confirmed,
        "tab_id": tab_id,
    }


def normalize_batch_cancel_request(value: object) -> None:
    """Require an empty JSON object when a cancellation body is present."""
    if value is None:
        return
    if not isinstance(value, Mapping) or value:
        raise AssessmentBatchError(
            "invalid_batch_cancel",
            "Assessment batch cancellation accepts only an empty JSON object.",
        )


__all__ = [
    "BATCH_MUTATION_REQUEST_MAX_BYTES",
    "normalize_batch_cancel_request",
    "normalize_batch_start_request",
]
