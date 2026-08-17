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
from core.migrations.v0075_assessment_batch_coordinator import (
    MIGRATION as COORDINATOR_MIGRATION,
)
from core.migrations.v0076_assessment_batch_items import MIGRATION as ITEM_MIGRATION
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
        {"status": "skipped", "error_code": "failure_limit"},
        {"status": "failed", "error_code": "could_not_cancel"},
    ]
    progress = derive_batch_progress(children)
    assert progress.status == "running"
    assert (progress.succeeded, progress.failed, progress.unavailable) == (1, 1, 1)
    assert progress.could_not_cancel == 1
    assert progress.skipped == 1
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
    assert MIGRATIONS[-2] is COORDINATOR_MIGRATION
    assert MIGRATIONS[-1] is ITEM_MIGRATION
    assert ITEM_MIGRATION.version == "0076"
    assert any(
        "details_json JSONB" in statement
        for statement in COORDINATOR_MIGRATION.postgres_statements or ()
    )
    assert any(
        "public_plan_json JSONB" in statement
        for statement in ITEM_MIGRATION.postgres_statements or ()
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
        preview_columns = {
            str(row["name"]): str(row["type"])
            for row in conn.execute(
                "PRAGMA table_info(assessment_batch_previews)"
            ).fetchall()
        }
        preview_item_columns = {
            str(row["name"]): str(row["type"])
            for row in conn.execute(
                "PRAGMA table_info(assessment_batch_preview_items)"
            ).fetchall()
        }
        item_columns = {
            str(row["name"]): str(row["type"])
            for row in conn.execute(
                "PRAGMA table_info(assessment_batch_items)"
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
    assert preview_columns["summary_json"] == "TEXT"
    assert preview_columns["selected_item_count"] == "INTEGER"
    assert preview_item_columns["public_plan_json"] == "TEXT"
    assert item_columns["child_ordinal"] == "INTEGER"
    assert {str(row["table"]) for row in parent_foreign_keys} == {
        "assessment_batches",
        "workflow_executions",
    }
    assert {str(row["table"]) for row in event_foreign_keys} == {"assessment_batches"}
    assert "idx_assessment_batches_assessment_created" in indexes
    assert "idx_assessment_batch_events_cursor" in indexes
    assert "idx_assessment_batch_previews_personal_expiry" in indexes
    assert "idx_assessment_batch_items_child" in indexes

    preview_id = "abp_batch_storage"
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO assessment_batch_previews "
            "(id, session_id, project_id, assessment_id, profile_key, profile_version, "
            "selection_json, summary_json, plan_digest, candidate_item_count, "
            "selected_item_count, mapping_count, safe_item_count, standard_item_count, "
            "max_parallel, max_owner_parallel, max_instance_parallel, expires_at, created) "
            "VALUES (?, ?, ?, ?, 'network', '1.0', '{}', '{}', ?, 2, 1, 2, 1, 1, "
            "8, 16, 32, ?, ?)",
            (preview_id, session_id, project_id, assessment_id, "b" * 64, timestamp, timestamp),
        )
        for item_index, selected, policy_level, execution_key in (
            (0, 1, "safe", "c" * 64),
            (1, 0, "standard", "d" * 64),
        ):
            conn.execute(
                "INSERT INTO assessment_batch_preview_items "
                "(preview_id, item_index, execution_key, selected, policy_level, "
                "action_key, action_id, target_entity_id, target_type, target_value, "
                "profile_identity_json, bounds_json, display_command, public_plan_digest, "
                "public_plan_json, duration_bound_seconds, created) "
                "VALUES (?, ?, ?, ?, ?, 'command:nmap', 'nmap', 'ent-batch-storage', "
                "'domain', 'batch.example', '{}', '{}', 'nmap batch.example', ?, '{}', 600, ?)",
                (
                    preview_id,
                    item_index,
                    execution_key,
                    selected,
                    policy_level,
                    execution_key,
                    timestamp,
                ),
            )
            conn.execute(
                "INSERT INTO assessment_batch_preview_item_checks "
                "(preview_id, item_index, mapping_index, assessment_id, check_id, check_key, "
                "target_entity_id, coverage_key, frozen_check_digest, created) "
                "VALUES (?, ?, 0, ?, ?, ?, 'ent-batch-storage', ?, ?, ?)",
                (
                    preview_id,
                    item_index,
                    assessment_id,
                    f"chk-batch-{item_index}",
                    f"check-{item_index}",
                    execution_key,
                    "e" * 64,
                    timestamp,
                ),
            )
        conn.commit()

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
        "skipped": 0,
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
        conn.execute(
            "INSERT INTO assessment_batch_items "
            "(batch_id, item_index, step_id, child_ordinal, source_preview_id, execution_key, "
            "policy_level, action_key, action_id, target_entity_id, target_type, target_value, "
            "profile_identity_json, bounds_json, display_command, public_plan_digest, "
            "public_plan_json, duration_bound_seconds, created) "
            "VALUES (?, 0, 'chunk_0001', 0, ?, ?, 'safe', 'command:nmap', 'nmap', "
            "'ent-batch-storage', 'domain', 'batch.example', '{}', '{}', "
            "'nmap batch.example', ?, '{}', 600, ?)",
            (batch_id, preview_id, "c" * 64, "c" * 64, timestamp),
        )
        conn.execute(
            "INSERT INTO assessment_batch_item_checks "
            "(batch_id, item_index, mapping_index, assessment_id, check_id, check_key, "
            "target_entity_id, coverage_key, frozen_check_digest, created) "
            "VALUES (?, 0, 0, ?, 'chk-batch-0', 'check-0', 'ent-batch-storage', ?, ?, ?)",
            (batch_id, assessment_id, "c" * 64, "e" * 64, timestamp),
        )
        conn.commit()

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
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM assessment_batch_items WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM assessment_batch_item_checks WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()["n"] == 0
        conn.execute("DELETE FROM assessment_batch_previews WHERE id = ?", (preview_id,))
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM assessment_batch_preview_items WHERE preview_id = ?",
            (preview_id,),
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM assessment_batch_preview_item_checks WHERE preview_id = ?",
            (preview_id,),
        ).fetchone()["n"] == 0
