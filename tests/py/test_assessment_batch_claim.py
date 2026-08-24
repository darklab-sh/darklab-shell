# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fair, authoritative claim contracts for assessment-batch children."""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest

from conftest import make_test_app
from core.database_access import get_db_connect
from services.assessments.batch.claim import claim_next_batch_item
from services.assessments.batch.contracts import BatchConcurrency
from services.assessments.batch.event_page import get_batch_event_page
from services.assessments.batch.storage import create_batch_parent


def _batch_events(session_id: str, batch_id: str) -> list[dict[str, object]]:
    events = get_batch_event_page(session_id, batch_id)["events"]
    assert isinstance(events, list)
    return [event for event in events if isinstance(event, dict)]


@pytest.fixture
def batch_factory():
    make_test_app()
    project_ids: list[str] = []

    def create(
        session_id: str,
        target_ids: list[str],
        *,
        concurrency: BatchConcurrency,
    ) -> dict[str, object]:
        suffix = uuid.uuid4().hex
        project_id = "prj_claim_" + suffix[:16]
        assessment_id = "asm_claim_" + suffix[:20]
        project_ids.append(project_id)
        timestamp = "2026-08-17 12:00:00"
        with get_db_connect()() as conn:
            conn.execute(
                "INSERT INTO projects (id, session_id, name, slug, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    session_id,
                    "Claim test",
                    "claim-" + suffix[:12],
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                "INSERT INTO project_assessments "
                "(id, session_id, project_id, title, profile_key, profile_version, "
                "status, started_at, created_at, updated_at) "
                "VALUES (?, ?, ?, 'Claim test', 'network', '1.0', 'active', ?, ?, ?)",
                (
                    assessment_id,
                    session_id,
                    project_id,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        parent = create_batch_parent(
            session_id=session_id,
            team_id="",
            project_id=project_id,
            assessment_id=assessment_id,
            preview_id="abp_" + suffix[:24],
            preview_digest=suffix * 2,
            item_count=len(target_ids),
            concurrency=concurrency,
            max_active=8,
        )
        batch_id = str(parent["batch_id"])
        with get_db_connect()() as conn:
            for index, target_id in enumerate(target_ids):
                step_id = f"chunk_{index // 32 + 1:04d}"
                execution_key = f"{index + 1:064x}"
                conn.execute(
                    "INSERT INTO assessment_batch_items "
                    "(batch_id, item_index, step_id, child_ordinal, source_preview_id, "
                    "execution_key, policy_level, action_key, action_id, target_entity_id, "
                    "target_type, target_value, profile_identity_json, bounds_json, "
                    "display_command, public_plan_digest, public_plan_json, "
                    "duration_bound_seconds, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'safe', 'command:ping', 'ping', ?, "
                    "'domain', ?, '{}', '{}', ?, ?, '{}', 30, ?)",
                    (
                        batch_id,
                        index,
                        step_id,
                        index % 32,
                        "abp_" + suffix[:24],
                        execution_key,
                        target_id,
                        f"{target_id}.example.test",
                        f"ping -c 4 {target_id}.example.test",
                        execution_key,
                        timestamp,
                    ),
                )
            conn.commit()
        return {**parent, "project_id": project_id, "assessment_id": assessment_id}

    yield create
    with get_db_connect()() as conn:
        for project_id in project_ids:
            conn.execute(
                "DELETE FROM workflow_executions WHERE project_id = ?", (project_id,)
            )
            conn.execute(
                "DELETE FROM project_assessments WHERE project_id = ?", (project_id,)
            )
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()


def test_claim_skips_busy_targets_and_records_authoritative_events(batch_factory):
    with get_db_connect()() as conn:
        initial_run_count = int(
            conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
        )
    batch = batch_factory(
        "batch-claim-owner",
        ["ent-target-a", "ent-target-a", "ent-target-b", "ent-target-b"],
        concurrency=BatchConcurrency(batch=8, target=1, owner=16, instance=32),
    )
    batch_id = str(batch["batch_id"])

    first = claim_next_batch_item(batch_id)
    second = claim_next_batch_item(batch_id)
    third = claim_next_batch_item(batch_id)

    assert (first["status"], first["item_index"]) == ("claimed", 0)
    assert (second["status"], second["item_index"]) == ("claimed", 2)
    assert third == {"status": "deferred", "reason_code": "target_parallel_limit"}
    first_item = cast(dict[str, Any], first["item"])
    second_item = cast(dict[str, Any], second["item"])
    assert first_item["target"]["entity_id"] == "ent-target-a"
    assert second_item["target"]["entity_id"] == "ent-target-b"
    with get_db_connect()() as conn:
        execution = conn.execute(
            "SELECT status FROM workflow_executions WHERE id = ?", (batch_id,)
        ).fetchone()
        step = conn.execute(
            "SELECT status, fanout_checkpoint FROM workflow_execution_steps "
            "WHERE execution_id = ? AND step_id = 'chunk_0001'",
            (batch_id,),
        ).fetchone()
        active = conn.execute(
            "SELECT ordinal, status FROM workflow_execution_children "
            "WHERE execution_id = ? AND status = 'launching' ORDER BY ordinal",
            (batch_id,),
        ).fetchall()
        run_count = int(conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"])
    assert execution["status"] == "running"
    assert step["status"] == "launching"
    assert [(row["ordinal"], row["status"]) for row in active] == [
        (0, "launching"),
        (2, "launching"),
    ]
    assert run_count == initial_run_count
    events = _batch_events("batch-claim-owner", batch_id)
    assert [event["event_type"] for event in events[-4:]] == [
        "parent_status_changed",
        "chunk_status_changed",
        "item_claimed",
        "item_claimed",
    ]
    assert [event["item_ordinal"] for event in events[-2:]] == [0, 2]


def test_claim_enforces_batch_and_owner_limits(batch_factory):
    batch_limited = batch_factory(
        "batch-limit-owner",
        ["ent-batch-a", "ent-batch-b"],
        concurrency=BatchConcurrency(batch=1, target=1, owner=16, instance=32),
    )
    assert claim_next_batch_item(str(batch_limited["batch_id"]))["status"] == "claimed"
    assert claim_next_batch_item(str(batch_limited["batch_id"])) == {
        "status": "deferred",
        "reason_code": "batch_parallel_limit",
    }

    first_owner_batch = batch_factory(
        "shared-limit-owner",
        ["ent-owner-a"],
        concurrency=BatchConcurrency(batch=8, target=1, owner=1, instance=32),
    )
    second_owner_batch = batch_factory(
        "shared-limit-owner",
        ["ent-owner-b"],
        concurrency=BatchConcurrency(batch=8, target=1, owner=8, instance=32),
    )
    assert claim_next_batch_item(str(first_owner_batch["batch_id"]))["status"] == "claimed"
    assert claim_next_batch_item(str(second_owner_batch["batch_id"])) == {
        "status": "deferred",
        "reason_code": "owner_parallel_limit",
    }


def test_claim_enforces_the_most_restrictive_instance_limit(batch_factory):
    first = batch_factory(
        "instance-owner-one",
        ["ent-instance-a"],
        concurrency=BatchConcurrency(batch=8, target=1, owner=32, instance=1),
    )
    second = batch_factory(
        "instance-owner-two",
        ["ent-instance-b"],
        concurrency=BatchConcurrency(batch=8, target=1, owner=32, instance=64),
    )

    assert claim_next_batch_item(str(first["batch_id"]))["status"] == "claimed"
    assert claim_next_batch_item(str(second["batch_id"])) == {
        "status": "deferred",
        "reason_code": "instance_parallel_limit",
    }
