# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Focused contracts for bounded assessment-batch coordination."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

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
from services.assessments.batch.events import append_batch_event, list_batch_events
from services.assessments.batch.plan_policy import (
    batch_execution_key,
    evaluate_shared_batch,
    retest_group_key,
)
from services.assessments.batch.policy import (
    batch_chunk_sizes,
    normalize_batch_concurrency,
)
from services.assessments.batch.rollup import derive_batch_progress
from services.assessments.batch.storage import active_batch_count, create_batch_parent


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
    assert (
        concurrency.batch,
        concurrency.target,
        concurrency.owner,
        concurrency.instance,
    ) == (
        8,
        1,
        16,
        32,
    )
    assert (
        normalize_batch_concurrency(batch=8, target=1, owner=32, instance=64).instance
        == 64
    )
    with pytest.raises(
        AssessmentBatchError, match="Target concurrency must be between 1 and 1"
    ):
        normalize_batch_concurrency(target=2)
    with pytest.raises(
        AssessmentBatchError, match="Batch concurrency must be between 1 and 8"
    ):
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
    assert (
        derive_batch_progress(children, cancellation_requested=True).status
        == "canceling"
    )
    settled = derive_batch_progress(
        [
            {"status": "succeeded", "error_code": ""},
            {"status": "canceled", "error_code": "cancelled"},
        ],
        cancellation_requested=True,
    )
    assert settled.status == "canceled"
    assert settled.settled == settled.total == 2

    first_plan: dict[str, Any] = {
        "assessment_id": "asm-policy",
        "check_id": "chk-one",
        "profile_key": "network",
        "profile_version": "1.0",
        "action": {"key": "command:nmap", "id": "nmap"},
        "target": {
            "entity_id": "ent-policy",
            "type": "domain",
            "value": "policy.example",
        },
        "policy_level": "safe",
        "http_profile": {"role": "none", "id": "", "credential_use": "none"},
        "bounds": {
            "target_count": 1,
            "fan_out": 1,
            "request_limit": None,
            "time_limit_seconds": 600,
            "credential_use": "none",
        },
        "display_command": "nmap -sV --host-timeout 600s policy.example",
        "launchable": True,
        "unavailable_reason": "",
    }
    second_plan = {**first_plan, "check_id": "chk-two"}
    assert batch_execution_key(first_plan) == batch_execution_key(second_plan)
    assert retest_group_key(first_plan) != retest_group_key(second_plan)
    changed_bounds = deepcopy(second_plan)
    changed_bounds["bounds"]["time_limit_seconds"] = 300
    assert batch_execution_key(first_plan) != batch_execution_key(changed_bounds)
    changed_command = {**second_plan, "display_command": "nmap policy.example"}
    assert batch_execution_key(first_plan) != batch_execution_key(changed_command)

    decision = evaluate_shared_batch(
        [first_plan, second_plan],
        minimum_items=2,
        maximum_items=10,
        allowed_policy_levels={"safe"},
    )
    assert decision.allowed is True
    assert evaluate_shared_batch(
        [first_plan],
        minimum_items=2,
        maximum_items=10,
        allowed_policy_levels={"safe"},
    ).code == "too_few_items"
    standard_plan = {**second_plan, "policy_level": "standard"}
    assert evaluate_shared_batch(
        [first_plan, standard_plan],
        minimum_items=2,
        maximum_items=10,
        allowed_policy_levels={"safe"},
    ).code == "policy_excluded"
    credentialed_plan = deepcopy(second_plan)
    credentialed_plan["bounds"]["credential_use"] = "protected_http_profile"
    assert evaluate_shared_batch(
        [first_plan, credentialed_plan],
        minimum_items=2,
        maximum_items=10,
        allowed_policy_levels={"safe"},
    ).code == "credentialed"
    assert evaluate_shared_batch(
        [first_plan, changed_command],
        minimum_items=2,
        maximum_items=10,
        allowed_policy_levels={"safe"},
    ).code == "command_mismatch"
    excluded_plan = {
        **second_plan,
        "action": {"key": "command:schemathesis", "id": "schemathesis"},
    }
    assert evaluate_shared_batch(
        [first_plan, excluded_plan],
        minimum_items=2,
        maximum_items=10,
        allowed_policy_levels={"safe"},
        excluded_actions={"command:schemathesis"},
        require_exact_command=False,
    ).code == "action_excluded"


def test_assessment_batch_storage_events_and_migration_are_backend_neutral():
    make_test_app()
    assert MIGRATIONS[-1] is MIGRATION
    assert MIGRATION.version == "0075"
    assert any(
        "details_json JSONB" in statement
        for statement in MIGRATION.postgres_statements or ()
    )
    timestamp = "2026-08-17 12:00:00"
    session_id = "batch-storage-owner"
    project_id = "prj-batch-storage"
    assessment_id = "asm-batch-storage"
    with get_db_connect()() as conn:
        parent_columns = {
            str(row["name"]): str(row["type"])
            for row in conn.execute("PRAGMA table_info(assessment_batches)").fetchall()
        }
        event_columns = {
            str(row["name"]): str(row["type"])
            for row in conn.execute(
                "PRAGMA table_info(assessment_batch_events)"
            ).fetchall()
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
        conn.execute(
            "INSERT INTO projects "
            "(id, session_id, name, slug, created, updated) VALUES (?, ?, ?, ?, ?, ?)",
            (
                project_id,
                session_id,
                "Batch storage",
                "batch-storage",
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            "INSERT INTO project_assessments "
            "(id, session_id, project_id, title, profile_key, profile_version, "
            "status, started_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'network', '1.0', 'active', ?, ?, ?)",
            (
                assessment_id,
                session_id,
                project_id,
                "Batch storage",
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
    assert parent_columns["execution_id"] == "TEXT"
    assert parent_columns["item_count"] == "INTEGER"
    assert event_columns["details_json"] == "TEXT"
    assert {str(row["table"]) for row in parent_foreign_keys} == {
        "assessment_batches",
        "workflow_executions",
    }
    assert {str(row["table"]) for row in event_foreign_keys} == {"assessment_batches"}
    assert "idx_assessment_batches_assessment_created" in indexes
    assert "idx_assessment_batch_events_cursor" in indexes

    parent = create_batch_parent(
        session_id=session_id,
        team_id="",
        project_id=project_id,
        assessment_id=assessment_id,
        preview_id="prv_batch_storage",
        preview_digest="a" * 64,
        item_count=33,
    )
    batch_id = str(parent["batch_id"])
    assert batch_id.startswith("abx_")
    assert parent["status"] == "queued"
    assert parent["item_count"] == 33
    assert parent["chunk_count"] == 2
    assert parent["progress"] == {
        "total": 33,
        "pending": 33,
        "launching": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "unavailable": 0,
        "canceled": 0,
        "could_not_cancel": 0,
        "status": "queued",
        "settled": 0,
    }
    assert active_batch_count(session_id) == 1

    events = list_batch_events(session_id, batch_id)
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert [event["event_type"] for event in events] == [
        "parent_created",
        "chunk_initialized",
        "chunk_initialized",
    ]
    assert events[-1]["details"] == {"item_count": 1}
    assert list_batch_events("another-owner", batch_id) == []
    assert [
        event["sequence"]
        for event in list_batch_events(
            session_id,
            batch_id,
            after_sequence=1,
            limit=1,
        )
    ] == [2]
    with pytest.raises(AssessmentBatchError, match="unsupported fields"):
        append_batch_event(
            batch_id,
            "item_failed",
            details={"private_values": 1},
        )
    with pytest.raises(AssessmentBatchError, match="status is invalid"):
        append_batch_event(batch_id, "item_claimed", status="unknown_status")
    assert len(list_batch_events(session_id, batch_id)) == 3

    with pytest.raises(
        AssessmentBatchError, match="Active assessment batch limit reached"
    ):
        create_batch_parent(
            session_id=session_id,
            team_id="",
            project_id=project_id,
            assessment_id=assessment_id,
            preview_id="prv_batch_storage_second",
            preview_digest="b" * 64,
            item_count=1,
            max_active=1,
        )
    with get_db_connect()() as conn:
        chunk_rows = conn.execute(
            "SELECT step_id, step_index, status FROM workflow_execution_steps "
            "WHERE execution_id = ? ORDER BY step_index",
            (batch_id,),
        ).fetchall()
        child_counts = conn.execute(
            "SELECT step_id, COUNT(*) AS n FROM workflow_execution_children "
            "WHERE execution_id = ? GROUP BY step_id ORDER BY step_id",
            (batch_id,),
        ).fetchall()
        execution_count = conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_executions "
            "WHERE session_id = ? AND execution_kind = 'assessment_batch'",
            (session_id,),
        ).fetchone()
    assert [
        (row["step_id"], row["step_index"], row["status"]) for row in chunk_rows
    ] == [
        ("chunk_0001", 0, "pending"),
        ("chunk_0002", 1, "pending"),
    ]
    assert [(row["step_id"], row["n"]) for row in child_counts] == [
        ("chunk_0001", 32),
        ("chunk_0002", 1),
    ]
    assert execution_count["n"] == 1

    with get_db_connect()() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM workflow_executions WHERE id = ?", (batch_id,))
        conn.commit()
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM assessment_batches WHERE execution_id = ?",
                (batch_id,),
            ).fetchone()["n"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM assessment_batch_events WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()["n"]
            == 0
        )
