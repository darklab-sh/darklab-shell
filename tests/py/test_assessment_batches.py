# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Focused contracts for bounded assessment-batch coordination."""

from __future__ import annotations

import pytest

from conftest import make_test_app
from core.database_access import get_db_connect
from core.migrations import MIGRATIONS
from core.migrations.v0075_assessment_batch_coordinator import MIGRATION
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_PREVIEW_PAGE_MAX_BYTES,
    BATCH_PREVIEW_PAGE_MAX_ITEMS,
    BATCH_PREVIEW_TTL_SECONDS,
)
from services.assessments.batch.policy import batch_chunk_sizes, normalize_batch_concurrency
from services.assessments.batch.rollup import derive_batch_progress


def test_assessment_batch_limits_chunking_and_progress_are_fixed():
    assert BATCH_PREVIEW_TTL_SECONDS == 900
    assert BATCH_PREVIEW_PAGE_MAX_ITEMS == 100
    assert BATCH_PREVIEW_PAGE_MAX_BYTES == 1024 * 1024
    assert batch_chunk_sizes(1) == (1,)
    assert batch_chunk_sizes(32) == (32,)
    assert batch_chunk_sizes(33) == (32, 1)
    assert batch_chunk_sizes(128) == (32, 32, 32, 32)
    assert batch_chunk_sizes(129) == (32, 32, 32, 32, 1)
    assert batch_chunk_sizes(512) == (32,) * 16
    with pytest.raises(AssessmentBatchError, match="between 1 and 512"):
        batch_chunk_sizes(513)

    concurrency = normalize_batch_concurrency()
    assert (concurrency.batch, concurrency.target, concurrency.owner, concurrency.instance) == (
        8, 1, 16, 32,
    )
    assert normalize_batch_concurrency(batch=8, target=1, owner=32, instance=64).instance == 64
    with pytest.raises(AssessmentBatchError, match="Target concurrency must be between 1 and 1"):
        normalize_batch_concurrency(target=2)
    with pytest.raises(AssessmentBatchError, match="Batch concurrency must be between 1 and 8"):
        normalize_batch_concurrency(batch=9)

    children = [
        {"status": "succeeded", "error_code": ""},
        {"status": "failed", "error_code": "child_failed"},
        {"status": "failed", "error_code": "feature_unavailable"},
        {"status": "pending", "error_code": ""},
        {"status": "failed", "error_code": "could_not_cancel"},
    ]
    progress = derive_batch_progress(children)
    assert progress.status == "running"
    assert (progress.succeeded, progress.failed, progress.unavailable) == (1, 1, 1)
    assert progress.could_not_cancel == 1
    assert derive_batch_progress(children, cancellation_requested=True).status == "canceling"
    settled = derive_batch_progress([
        {"status": "succeeded", "error_code": ""},
        {"status": "canceled", "error_code": "cancelled"},
    ], cancellation_requested=True)
    assert settled.status == "canceled"
    assert settled.settled == settled.total == 2


def test_assessment_batch_coordinator_migration_is_backend_neutral():
    make_test_app()
    assert MIGRATIONS[-1] is MIGRATION
    assert MIGRATION.version == "0075"
    assert any("details_json JSONB" in statement for statement in MIGRATION.postgres_statements or ())
    with get_db_connect()() as conn:
        parent_columns = {
            str(row["name"]): str(row["type"])
            for row in conn.execute("PRAGMA table_info(assessment_batches)").fetchall()
        }
        event_columns = {
            str(row["name"]): str(row["type"])
            for row in conn.execute("PRAGMA table_info(assessment_batch_events)").fetchall()
        }
        parent_foreign_keys = conn.execute(
            "PRAGMA foreign_key_list(assessment_batches)"
        ).fetchall()
        event_foreign_keys = conn.execute(
            "PRAGMA foreign_key_list(assessment_batch_events)"
        ).fetchall()
        indexes = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' "
                "AND name LIKE 'idx_assessment_batch%'"
            ).fetchall()
        }
    assert parent_columns["execution_id"] == "TEXT"
    assert parent_columns["item_count"] == "INTEGER"
    assert event_columns["details_json"] == "TEXT"
    assert {str(row["table"]) for row in parent_foreign_keys} == {
        "assessment_batches", "workflow_executions",
    }
    assert {str(row["table"]) for row in event_foreign_keys} == {"assessment_batches"}
    assert "idx_assessment_batches_assessment_created" in indexes
    assert "idx_assessment_batch_events_cursor" in indexes
