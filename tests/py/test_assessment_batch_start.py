# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Confirmed-start contracts for immutable assessment-batch snapshots."""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest

from conftest import reusable_test_app
from core.database_access import get_db_connect
from services.assessments.base_action_catalog import ACTIONS
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.events import list_batch_events
from services.assessments.batch.preview_compiler import compile_batch_preview
from services.assessments.batch.preview_storage import get_batch_preview_items
from services.assessments.batch.retry_compiler import compile_batch_retry_preview
from services.assessments.batch.start import start_assessment_batch
from services.assessments.probe_runtime import ProbePlanningRuntime
from services.assessments.storage import create_assessment_cycle
from services.nuclei.template_cache import NucleiTemplateCacheSnapshot
from services.projects.crud import create_project, delete_project
from services.projects.targets import add_project_target


def _runtime() -> ProbePlanningRuntime:
    return ProbePlanningRuntime(
        available_features=frozenset(
            {*ACTIONS, "reviewed_nse_profiles", "managed_nuclei_templates"}
        ),
        intrusive_actions_enabled=True,
        template_snapshot=NucleiTemplateCacheSnapshot(
            "ready", "v10.4.7", "sha256:" + "1" * 64, 100
        ),
    )


@pytest.fixture
def batch_cycle(monkeypatch: pytest.MonkeyPatch):
    reusable_test_app(__name__)
    session_id = "tok_batch_start_" + uuid.uuid4().hex
    project = create_project(session_id, {"name": "Batch start Project"})
    assert project is not None
    project_id = str(project["id"])
    target = add_project_target(
        session_id,
        project_id,
        {
            "type": "domain",
            "value": "batch-start.example.test",
            "source": "user",
            "review_state": "confirmed",
        },
    )
    assert target is not None
    cycle = create_assessment_cycle(session_id, project_id, "network")
    assessment_id = str(cycle["assessment"]["id"])
    monkeypatch.setattr(
        "services.assessments.batch.preview_draft.probe_planning_runtime",
        _runtime,
    )
    monkeypatch.setattr(
        "services.assessments.batch.retry_draft.probe_planning_runtime",
        _runtime,
    )
    yield session_id, project_id, assessment_id
    with get_db_connect()() as conn:
        conn.execute(
            "DELETE FROM workflow_executions WHERE project_id = ?", (project_id,)
        )
        conn.execute(
            "DELETE FROM assessment_batch_previews WHERE project_id = ?", (project_id,)
        )
        conn.commit()
    delete_project(session_id, project_id)


def _start(
    session_id: str,
    project_id: str,
    assessment_id: str,
    preview: dict[str, object],
    **values: object,
) -> dict[str, object]:
    return start_assessment_batch(
        session_id,
        project_id,
        assessment_id,
        preview_id=str(preview["preview_id"]),
        plan_digest=preview["plan_digest"],
        confirmed=True,
        **cast(Any, values),
    )


def test_confirmed_start_copies_every_selected_item_and_mapping_once(batch_cycle):
    session_id, project_id, assessment_id = batch_cycle
    preview = compile_batch_preview(session_id, project_id, assessment_id)
    with get_db_connect()() as conn:
        initial_run_count = int(
            conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
        )

    with pytest.raises(AssessmentBatchError) as missing_confirmation:
        start_assessment_batch(
            session_id,
            project_id,
            assessment_id,
            preview_id=str(preview["preview_id"]),
            plan_digest=preview["plan_digest"],
            confirmed=False,
        )
    assert missing_confirmation.value.code == "batch_confirmation_required"
    with pytest.raises(AssessmentBatchError) as wrong_digest:
        start_assessment_batch(
            session_id,
            project_id,
            assessment_id,
            preview_id=str(preview["preview_id"]),
            plan_digest="f" * 64,
            confirmed=True,
        )
    assert wrong_digest.value.code == "batch_confirmation_mismatch"

    batch = _start(
        session_id,
        project_id,
        assessment_id,
        preview,
        owner_client_id="browser-client",
        owner_tab_id="assessment-tab",
        max_active=1,
    )
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE assessment_batch_previews SET expires_at = ? WHERE id = ?",
            ("2000-01-01 00:00:00", preview["preview_id"]),
        )
        conn.execute(
            "UPDATE project_assessment_checks SET state = 'skipped', "
            "state_source = 'manual' WHERE assessment_id = ? AND policy_level = 'safe'",
            (assessment_id,),
        )
        conn.commit()
    replay = _start(
        session_id,
        project_id,
        assessment_id,
        preview,
        owner_client_id="browser-client",
        owner_tab_id="assessment-tab",
        max_active=1,
    )

    assert replay["batch_id"] == batch["batch_id"]
    assert batch["item_count"] == preview["selected_item_count"] == 2
    assert batch["chunk_count"] == 1
    with get_db_connect()() as conn:
        preview_items = conn.execute(
            "SELECT item_index, display_command, public_plan_json FROM "
            "assessment_batch_preview_items WHERE preview_id = ? AND selected = ? "
            "ORDER BY item_index",
            (preview["preview_id"], True),
        ).fetchall()
        items = conn.execute(
            "SELECT item_index, step_id, child_ordinal, display_command, "
            "public_plan_json FROM assessment_batch_items WHERE batch_id = ? "
            "ORDER BY item_index",
            (batch["batch_id"],),
        ).fetchall()
        mapping_count = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM assessment_batch_item_checks "
                "WHERE batch_id = ?",
                (batch["batch_id"],),
            ).fetchone()["n"]
        )
        child_count = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM workflow_execution_children "
                "WHERE execution_id = ?",
                (batch["batch_id"],),
            ).fetchone()["n"]
        )
        parent_count = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM workflow_executions "
                "WHERE execution_kind = 'assessment_batch' AND project_id = ?",
                (project_id,),
            ).fetchone()["n"]
        )
        run_count = int(conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"])
        claimed = conn.execute(
            "SELECT started_execution_id FROM assessment_batch_previews WHERE id = ?",
            (preview["preview_id"],),
        ).fetchone()
    assert [row["display_command"] for row in items] == [
        row["display_command"] for row in preview_items
    ]
    assert [row["public_plan_json"] for row in items] == [
        row["public_plan_json"] for row in preview_items
    ]
    assert [(row["step_id"], row["child_ordinal"]) for row in items] == [
        ("chunk_0001", 0),
        ("chunk_0001", 1),
    ]
    assert mapping_count == preview["potential_covered_check_count"]
    assert child_count == len(items) == 2
    assert parent_count == 1
    assert run_count == initial_run_count
    assert claimed["started_execution_id"] == batch["batch_id"]


def test_standard_items_need_a_separate_confirmation(batch_cycle):
    session_id, project_id, assessment_id = batch_cycle
    preview = compile_batch_preview(
        session_id,
        project_id,
        assessment_id,
        {"include_standard": True, "item_limit": 3},
    )

    with pytest.raises(AssessmentBatchError) as missing_standard:
        _start(session_id, project_id, assessment_id, preview)
    assert missing_standard.value.code == "standard_confirmation_required"
    batch = _start(
        session_id,
        project_id,
        assessment_id,
        preview,
        standard_confirmed=True,
    )
    assert batch["item_count"] == preview["selected_item_count"] == 3


def test_start_rejects_scope_drift_and_rolls_back_partial_materialization(batch_cycle):
    session_id, project_id, assessment_id = batch_cycle
    stale_preview = compile_batch_preview(session_id, project_id, assessment_id)
    with get_db_connect()() as conn:
        check = conn.execute(
            "SELECT id FROM project_assessment_checks "
            "WHERE assessment_id = ? AND policy_level = 'safe' ORDER BY id LIMIT 1",
            (assessment_id,),
        ).fetchone()
        assert check is not None
        conn.execute(
            "UPDATE project_assessment_checks SET state = 'skipped', "
            "state_source = 'manual', state_reason = 'Operator excluded' "
            "WHERE id = ?",
            (check["id"],),
        )
        conn.commit()
    with pytest.raises(AssessmentBatchError) as stale:
        _start(session_id, project_id, assessment_id, stale_preview)
    assert stale.value.code == "batch_preview_stale"

    current_preview = compile_batch_preview(session_id, project_id, assessment_id)
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE assessment_batch_preview_items SET selected = ? "
            "WHERE preview_id = ? AND selected = ? AND item_index = ("
            "SELECT MIN(item_index) FROM assessment_batch_preview_items "
            "WHERE preview_id = ? AND selected = ?)",
            (False, current_preview["preview_id"], True, current_preview["preview_id"], True),
        )
        conn.commit()
    with pytest.raises(AssessmentBatchError) as partial:
        _start(session_id, project_id, assessment_id, current_preview)
    assert partial.value.code == "batch_preview_stale"
    with get_db_connect()() as conn:
        parent_count = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM workflow_executions "
                "WHERE execution_kind = 'assessment_batch' AND project_id = ?",
                (project_id,),
            ).fetchone()["n"]
        )
        claimed = conn.execute(
            "SELECT started_execution_id FROM assessment_batch_previews WHERE id = ?",
            (current_preview["preview_id"],),
        ).fetchone()
    assert parent_count == 0
    assert claimed["started_execution_id"] == ""


def _settle_source_with_one_failure(batch_id: str) -> tuple[str, str]:
    with get_db_connect()() as conn:
        items = conn.execute(
            "SELECT item.item_index, item.step_id, item.child_ordinal, mapping.check_id "
            "FROM assessment_batch_items item JOIN assessment_batch_item_checks mapping "
            "ON mapping.batch_id = item.batch_id AND mapping.item_index = item.item_index "
            "WHERE item.batch_id = ? ORDER BY item.item_index, mapping.mapping_index",
            (batch_id,),
        ).fetchall()
        item_checks: dict[int, list[str]] = {}
        item_children: dict[int, tuple[str, int]] = {}
        for row in items:
            index = int(row["item_index"])
            item_checks.setdefault(index, []).append(str(row["check_id"]))
            item_children[index] = (str(row["step_id"]), int(row["child_ordinal"]))
        assert len(item_children) == 2
        succeeded_index, failed_index = sorted(item_children)
        for index, status, error_code in (
            (succeeded_index, "succeeded", ""),
            (failed_index, "failed", "feature_unavailable"),
        ):
            step_id, ordinal = item_children[index]
            conn.execute(
                "UPDATE workflow_execution_children SET status = ?, error_code = ? "
                "WHERE execution_id = ? AND step_id = ? AND ordinal = ? AND attempt = 1",
                (status, error_code, batch_id, step_id, ordinal),
            )
        conn.execute(
            "UPDATE workflow_executions SET status = 'failed' WHERE id = ?",
            (batch_id,),
        )
        conn.commit()
    return item_checks[succeeded_index][0], item_checks[failed_index][0]


def test_retry_preview_rebuilds_only_failed_work_and_creates_immutable_lineage(
    batch_cycle,
):
    session_id, project_id, assessment_id = batch_cycle
    source_preview = compile_batch_preview(session_id, project_id, assessment_id)
    source = _start(session_id, project_id, assessment_id, source_preview)
    source_id = str(source["batch_id"])
    succeeded_check_id, failed_check_id = _settle_source_with_one_failure(source_id)

    retry_preview = cast(
        dict[str, Any],
        compile_batch_retry_preview(
            session_id,
            project_id,
            assessment_id,
            source_id,
        ),
    )
    assert retry_preview["source_batch_id"] == source_id
    assert retry_preview["selected_item_count"] == 1
    assert retry_preview["summary"]["source_item_count"] == 2
    assert retry_preview["summary"]["source_succeeded_item_count"] == 1
    assert retry_preview["summary"]["source_retry_eligible_item_count"] == 1
    retry_items = cast(
        dict[str, Any],
        get_batch_preview_items(session_id, str(retry_preview["preview_id"])),
    )["items"]
    retry_check_ids = {
        mapping["check_id"]
        for item in retry_items
        for mapping in item["check_mappings"]
    }
    assert retry_check_ids == {failed_check_id}
    assert succeeded_check_id not in retry_check_ids

    with pytest.raises(AssessmentBatchError) as wrong_surface:
        _start(session_id, project_id, assessment_id, retry_preview)
    assert wrong_surface.value.code == "batch_confirmation_mismatch"

    retry = _start(
        session_id,
        project_id,
        assessment_id,
        retry_preview,
        source_batch_id=source_id,
    )
    assert retry["batch_id"] != source_id
    assert retry["source_batch_id"] == source_id
    replay = _start(
        session_id,
        project_id,
        assessment_id,
        retry_preview,
        source_batch_id=source_id,
    )
    assert replay["batch_id"] == retry["batch_id"]
    source_events = list_batch_events(session_id, source_id)
    retry_created = [
        event for event in source_events if event["event_type"] == "retry_created"
    ]
    assert len(retry_created) == 1
    assert retry_created[0]["source_batch_id"] == source_id
    assert retry_created[0]["retry_batch_id"] == retry["batch_id"]
    with get_db_connect()() as conn:
        statuses = conn.execute(
            "SELECT status FROM workflow_execution_children WHERE execution_id = ? "
            "ORDER BY step_id, ordinal, attempt",
            (source_id,),
        ).fetchall()
    assert [str(row["status"]) for row in statuses] == ["succeeded", "failed"]


def test_retry_preview_can_explain_nothing_currently_retryable(batch_cycle):
    session_id, project_id, assessment_id = batch_cycle
    source_preview = compile_batch_preview(session_id, project_id, assessment_id)
    source = _start(session_id, project_id, assessment_id, source_preview)
    source_id = str(source["batch_id"])
    _succeeded_check_id, failed_check_id = _settle_source_with_one_failure(source_id)
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE project_assessment_checks SET state = 'covered' WHERE id = ?",
            (failed_check_id,),
        )
        conn.commit()

    retry_preview = cast(
        dict[str, Any],
        compile_batch_retry_preview(
            session_id,
            project_id,
            assessment_id,
            source_id,
        ),
    )
    assert retry_preview["candidate_item_count"] == 0
    assert retry_preview["selected_item_count"] == 0
    assert retry_preview["summary"]["reason_counts"] == {"already_covered": 1}
    assert retry_preview["summary"]["chunk_sizes"] == []
    with pytest.raises(AssessmentBatchError) as empty:
        _start(
            session_id,
            project_id,
            assessment_id,
            retry_preview,
            source_batch_id=source_id,
        )
    assert empty.value.code == "empty_batch_retry"
