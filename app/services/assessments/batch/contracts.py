# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Surface-neutral contracts for durable assessment batches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


BATCH_SCHEMA_VERSION = 1
BATCH_EVENT_SCHEMA_VERSION = 1
BATCH_PREVIEW_TTL_SECONDS = 15 * 60
BATCH_PREVIEW_PAGE_MAX_ITEMS = 100
BATCH_PREVIEW_PAGE_MAX_BYTES = 1024 * 1024
BATCH_PREVIEW_REQUEST_MAX_BYTES = 64 * 1024
BATCH_PREVIEW_BUILD_MAX_BYTES = 16 * 1024 * 1024
BATCH_PREVIEW_MAX_CHECK_ROWS = 50_000
BATCH_PREVIEW_MAX_TARGET_SELECTIONS = 200
BATCH_PREVIEW_MAX_CATEGORY_SELECTIONS = 64
BATCH_EVENT_DETAILS_MAX_BYTES = 4096
BATCH_DEFAULT_ITEM_LIMIT = 128
BATCH_HARD_ITEM_LIMIT = 512
BATCH_CHUNK_ITEM_LIMIT = 32
BATCH_MAX_CHECK_MAPPINGS_PER_ITEM = 256
BATCH_MAX_TOTAL_CHECK_MAPPINGS = 50_000
BATCH_MAX_ATTEMPTS = 4
BATCH_DEFAULT_MAX_ACTIVE_PER_OWNER = 3
BATCH_HARD_MAX_ACTIVE_PER_OWNER = 8
BATCH_DEFAULT_PARALLEL = 8
BATCH_HARD_PARALLEL = 8
BATCH_TARGET_PARALLEL = 1
BATCH_DEFAULT_OWNER_PARALLEL = 16
BATCH_HARD_OWNER_PARALLEL = 32
BATCH_DEFAULT_INSTANCE_PARALLEL = 32
BATCH_HARD_INSTANCE_PARALLEL = 64
BATCH_RETENTION_DAYS = 30
BATCH_ACTIVE_STATUSES = frozenset({"queued", "running", "canceling"})
BATCH_TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})
BATCH_ITEM_STATUSES = frozenset({
    "pending", "launching", "running", "succeeded", "failed", "skipped", "canceled",
})
BATCH_UNAVAILABLE_ERROR_CODES = frozenset({
    "feature_unavailable",
    "profile_unavailable",
    "scope_unavailable",
    "target_unavailable",
    "plan_changed",
    "policy_changed",
})
BATCH_COULD_NOT_CANCEL_ERROR_CODE = "could_not_cancel"
BATCH_VIEW_CAPABILITIES = frozenset()
BATCH_MUTATION_CAPABILITIES = frozenset({"run_commands"})


class AssessmentBatchError(ValueError):
    """A stable batch error shared by browser, API, and CLI adapters."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: Mapping[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = str(code)
        self.status_code = int(status_code)
        self.details = dict(details or {})


@dataclass(frozen=True)
class BatchConcurrency:
    """The four independent assessment-batch concurrency ceilings."""

    batch: int = BATCH_DEFAULT_PARALLEL
    target: int = BATCH_TARGET_PARALLEL
    owner: int = BATCH_DEFAULT_OWNER_PARALLEL
    instance: int = BATCH_DEFAULT_INSTANCE_PARALLEL


@dataclass(frozen=True)
class BatchProgress:
    """Derived public progress for one immutable set of batch items."""

    total: int
    pending: int
    launching: int
    running: int
    succeeded: int
    failed: int
    unavailable: int
    canceled: int
    could_not_cancel: int
    status: str

    @property
    def settled(self) -> int:
        return (
            self.succeeded
            + self.failed
            + self.unavailable
            + self.canceled
            + self.could_not_cancel
        )


__all__ = [
    "AssessmentBatchError",
    "BATCH_ACTIVE_STATUSES",
    "BATCH_CHUNK_ITEM_LIMIT",
    "BATCH_COULD_NOT_CANCEL_ERROR_CODE",
    "BATCH_DEFAULT_INSTANCE_PARALLEL",
    "BATCH_DEFAULT_ITEM_LIMIT",
    "BATCH_DEFAULT_MAX_ACTIVE_PER_OWNER",
    "BATCH_DEFAULT_OWNER_PARALLEL",
    "BATCH_DEFAULT_PARALLEL",
    "BATCH_EVENT_DETAILS_MAX_BYTES",
    "BATCH_EVENT_SCHEMA_VERSION",
    "BATCH_HARD_INSTANCE_PARALLEL",
    "BATCH_HARD_ITEM_LIMIT",
    "BATCH_HARD_MAX_ACTIVE_PER_OWNER",
    "BATCH_HARD_OWNER_PARALLEL",
    "BATCH_HARD_PARALLEL",
    "BATCH_ITEM_STATUSES",
    "BATCH_MAX_ATTEMPTS",
    "BATCH_MAX_CHECK_MAPPINGS_PER_ITEM",
    "BATCH_MAX_TOTAL_CHECK_MAPPINGS",
    "BATCH_MUTATION_CAPABILITIES",
    "BATCH_PREVIEW_PAGE_MAX_BYTES",
    "BATCH_PREVIEW_PAGE_MAX_ITEMS",
    "BATCH_PREVIEW_REQUEST_MAX_BYTES",
    "BATCH_PREVIEW_BUILD_MAX_BYTES",
    "BATCH_PREVIEW_MAX_CATEGORY_SELECTIONS",
    "BATCH_PREVIEW_MAX_CHECK_ROWS",
    "BATCH_PREVIEW_MAX_TARGET_SELECTIONS",
    "BATCH_PREVIEW_TTL_SECONDS",
    "BATCH_RETENTION_DAYS",
    "BATCH_SCHEMA_VERSION",
    "BATCH_TARGET_PARALLEL",
    "BATCH_TERMINAL_STATUSES",
    "BATCH_UNAVAILABLE_ERROR_CODES",
    "BATCH_VIEW_CAPABILITIES",
    "BatchConcurrency",
    "BatchProgress",
]
