# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only bounded assessment-batch compiler coverage."""

from __future__ import annotations

from dataclasses import replace
import uuid

import pytest

from conftest import make_test_app
from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.base_action_catalog import ACTIONS
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.preview_builder import BatchPreviewBuilder
from services.assessments.batch.preview_classification import check_exclusion_reason
from services.assessments.batch.preview_compiler import compile_batch_preview
from services.assessments.batch.preview_estimate import estimate_batch_duration
from services.assessments.batch.preview_models import (
    BatchCheckMapping,
    BatchPreviewItem,
)
from services.assessments.batch.preview_storage import get_batch_preview_items
from services.assessments.batch.preview_selection import normalize_preview_selection
from services.assessments.probe_runtime import ProbePlanningRuntime
from services.assessments.storage import create_assessment_cycle
from services.nuclei.template_cache import NucleiTemplateCacheSnapshot
from services.projects.crud import create_project, delete_project
from services.projects.targets import add_project_target


@pytest.fixture
def batch_cycle(monkeypatch: pytest.MonkeyPatch):
    make_test_app()
    session_id = "batch-compiler-" + uuid.uuid4().hex
    project = create_project(session_id, {"name": "Batch compiler"})
    assert project is not None
    project_id = str(project["id"])
    target = add_project_target(
        session_id,
        project_id,
        {
            "type": "domain",
            "value": "batch.example.test",
            "source": "auto_command",
            "review_state": "confirmed",
        },
    )
    assert target is not None
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE project_links SET source = 'auto_command' WHERE project_id = ? "
            "AND entity_type = 'atlas_entity' AND entity_id = ?",
            (project_id, str(target["id"])),
        )
        conn.commit()
    cycle = create_assessment_cycle(session_id, project_id, "network")
    assessment_id = str(cycle["assessment"]["id"])
    runtime = ProbePlanningRuntime(
        available_features=frozenset(
            {*ACTIONS, "reviewed_nse_profiles", "managed_nuclei_templates"}
        ),
        intrusive_actions_enabled=True,
        template_snapshot=NucleiTemplateCacheSnapshot(
            "ready", "v10.4.7", "sha256:" + "1" * 64, 100
        ),
    )
    monkeypatch.setattr(
        "services.assessments.batch.preview_draft.probe_planning_runtime",
        lambda: runtime,
    )
    yield session_id, project_id, assessment_id, str(target["id"])
    with get_db_connect()() as conn:
        conn.execute(
            "DELETE FROM assessment_batch_previews WHERE assessment_id = ?",
            (assessment_id,),
        )
        conn.commit()
    delete_project(session_id, project_id)


def _duplicate_ping_check(assessment_id: str) -> None:
    with get_db_connect()() as conn:
        dialect = dialect_for_backend(get_db_backend())
        assessment = conn.execute(
            "SELECT profile_snapshot FROM project_assessments WHERE id = ?",
            (assessment_id,),
        ).fetchone()
        snapshot = dialect.decode_json_dict(assessment["profile_snapshot"])
        original = next(
            item for item in snapshot["checks"] if item["key"] == "host_reachability"
        )
        snapshot["checks"].append({**original, "key": "host_reachability_duplicate"})
        conn.execute(
            "UPDATE project_assessments SET profile_snapshot = ? WHERE id = ?",
            (dialect.json_param(snapshot), assessment_id),
        )
        conn.execute(
            "INSERT INTO project_assessment_checks "
            "(id, assessment_id, category, check_key, target_entity_id, target_type, "
            "target_value, target_value_hash, applicability, policy_level, state, "
            "state_source, state_reason, recommended_action_key, first_evidence_at, "
            "last_evidence_at, created_at, updated_at) "
            "SELECT ?, assessment_id, category, 'host_reachability_duplicate', target_entity_id, target_type, "
            "target_value, target_value_hash, applicability, policy_level, state, "
            "state_source, state_reason, recommended_action_key, first_evidence_at, "
            "last_evidence_at, created_at, updated_at "
            "FROM project_assessment_checks WHERE assessment_id = ? AND check_key = 'host_reachability'",
            ("chk-batch-duplicate-" + uuid.uuid4().hex, assessment_id),
        )
        conn.commit()


def _classification_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "state": "not_started",
        "state_source": "derived",
        "policy_level": "safe",
        "recommended_action_key": "command:ping",
        "check_key": "host_reachability",
        "applicability": "applicable",
        "unavailable_evidence_count": 0,
        "current_target_id": "ent-classification",
        "current_target_type": "domain",
        "current_target_value": "classification.example.test",
        "target_type": "domain",
        "target_value": "classification.example.test",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("row_overrides", "expected_reason"),
    (
        (
            {
                "check_key": "intrusive_template_validation",
                "policy_level": "intrusive",
                "recommended_action_key": "command:nuclei",
            },
            "intrusive",
        ),
        (
            {
                "check_key": "destructive_validation",
                "policy_level": "destructive",
                "recommended_action_key": "command:sqlmap",
            },
            "destructive",
        ),
        (
            {
                "check_key": "subdomain_takeover_confirmation",
                "policy_level": "standard",
                "recommended_action_key": "command:nuclei",
            },
            "takeover_confirmation",
        ),
        (
            {
                "check_key": "private_callback_validation",
                "policy_level": "standard",
                "recommended_action_key": "oast_private_callback",
            },
            "oast",
        ),
        (
            {
                "check_key": "api_schema_conformance",
                "policy_level": "standard",
                "recommended_action_key": "command:schemathesis",
            },
            "schemathesis",
        ),
        (
            {
                "check_key": "zap_active_scan",
                "policy_level": "standard",
                "recommended_action_key": "zap_active_scan",
            },
            "non_runnable",
        ),
    ),
)
def test_batch_classifier_explicitly_excludes_unsupported_action_families(
    row_overrides,
    expected_reason,
):
    row = _classification_row(**row_overrides)
    frozen = {
        "recommended_action": row["recommended_action_key"],
        "policy_level": row["policy_level"],
    }

    assert check_exclusion_reason(row, frozen) == expected_reason


def test_compiler_defaults_to_safe_deduplicates_and_explains_standard_work(batch_cycle):
    session_id, project_id, assessment_id, target_id = batch_cycle
    _duplicate_ping_check(assessment_id)

    preview = compile_batch_preview(session_id, project_id, assessment_id)
    summary = preview["summary"]
    assert preview["candidate_item_count"] == 3
    assert preview["selected_item_count"] == 2
    assert preview["potential_covered_check_count"] == 3
    assert summary["eligible_check_count"] == 4
    assert summary["standard_item_count"] == 1
    assert summary["standard_selected"] is False
    assert summary["chunk_sizes"] == [2]
    assert summary["selected_target_entity_ids"] == [target_id]
    assert summary["selected_categories"] == ["discovery"]
    assert summary["fan_out"] == 2
    assert summary["credential_classification"] == "none"
    assert summary["target_review_hints"] == [
        {
            "target_entity_id": target_id,
            "target_type": "domain",
            "target_value": "batch.example.test",
            "hints": [
                {
                    "code": "discovered_target",
                    "reason": (
                        "Discovered by auto_command; review whether this is intended "
                        "infrastructure or third-party scope."
                    ),
                }
            ],
        }
    ]
    page = get_batch_preview_items(session_id, str(preview["preview_id"]))
    standard = next(
        item for item in page["items"] if item["policy_level"] == "standard"
    )
    ping = next(item for item in page["items"] if item["action"]["id"] == "ping")
    assert standard["selected"] is False
    assert len(ping["check_mappings"]) == 2
    with get_db_connect()() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM assessment_batches "
                "WHERE assessment_id = ?",
                (assessment_id,),
            ).fetchone()["n"]
            == 0
        )
        assert conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"] >= 0


def test_compiler_requires_explicit_standard_selection_and_rejects_truncation(
    batch_cycle,
):
    session_id, project_id, assessment_id, target_id = batch_cycle
    preview = compile_batch_preview(
        session_id,
        project_id,
        assessment_id,
        {
            "include_standard": True,
            "target_entity_ids": [target_id],
            "categories": ["discovery"],
            "item_limit": 3,
            "max_parallel": 3,
        },
    )
    assert preview["selected_item_count"] == 3
    assert preview["summary"]["standard_selected"] is True
    assert preview["summary"]["requires_standard_confirmation"] is True
    assert preview["concurrency"]["batch"] == 3

    with pytest.raises(AssessmentBatchError) as oversized:
        compile_batch_preview(
            session_id,
            project_id,
            assessment_id,
            {"include_standard": True, "item_limit": 2},
        )
    assert oversized.value.code == "preview_item_limit_exceeded"
    assert oversized.value.details == {"selected_item_count": 3, "item_limit": 2}

    with pytest.raises(AssessmentBatchError) as unknown:
        compile_batch_preview(
            session_id, project_id, assessment_id, {"categories": ["missing"]}
        )
    assert unknown.value.code == "batch_selection_not_found"


def test_compiler_explains_manual_evidence_and_changed_target_exclusions(batch_cycle):
    session_id, project_id, assessment_id, _target_id = batch_cycle
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE project_assessment_checks SET state = 'covered' "
            "WHERE assessment_id = ? AND check_key = 'dns_inventory'",
            (assessment_id,),
        )
        conn.execute(
            "UPDATE project_assessment_checks SET state = 'skipped', state_source = 'manual' "
            "WHERE assessment_id = ? AND check_key = 'service_discovery'",
            (assessment_id,),
        )
        conn.commit()
    preview = compile_batch_preview(session_id, project_id, assessment_id)
    assert preview["selected_item_count"] == 1
    assert preview["summary"]["reason_counts"] == {
        "already_covered": 1,
        "manual_excluded": 1,
    }

    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE project_links SET review_state = 'pending' WHERE project_id = ? "
            "AND entity_type = 'atlas_entity'",
            (project_id,),
        )
        conn.commit()
    with pytest.raises(AssessmentBatchError) as empty:
        compile_batch_preview(session_id, project_id, assessment_id)
    assert empty.value.code == "empty_batch_plan"
    assert empty.value.details["reason_counts"] == {
        "already_covered": 1,
        "manual_excluded": 1,
        "target_unavailable": 1,
    }


def _estimate_item(index: int) -> BatchPreviewItem:
    target_id = f"ent-estimate-{index % 4}"
    return BatchPreviewItem(
        execution_key="1" * 64,
        selected=True,
        policy_level="safe",
        action_key="command:ping",
        action_id="ping",
        target_entity_id=target_id,
        target_type="domain",
        target_value=f"host-{index % 4}.example",
        profile_identity={},
        bounds={},
        display_command="ping",
        public_plan_digest="2" * 64,
        public_plan={},
        duration_bound_seconds=10,
        mappings=(
            BatchCheckMapping(
                "asm", f"chk-{index}", "reachability", target_id, "3" * 64, "4" * 64
            ),
        ),
    )


def test_duration_estimate_preserves_the_32_item_chunk_boundary():
    base = tuple(_estimate_item(index) for index in range(33))
    at_limit = estimate_batch_duration(base[:32], parallel=8)
    over_limit = estimate_batch_duration(base, parallel=8)
    assert at_limit.chunk_sizes == (32,)
    assert over_limit.chunk_sizes == (32, 1)
    assert at_limit.minimum_seconds == 8
    assert over_limit.minimum_seconds == 9
    assert over_limit.maximum_seconds > at_limit.maximum_seconds

    unselected = tuple(replace(item, selected=False) for item in base[32:])
    assert estimate_batch_duration(
        (*base[:32], *unselected), parallel=8
    ).chunk_sizes == (32,)


def test_preview_selection_accepts_the_200_target_project_boundary_only():
    target_ids = [f"ent-boundary-{index:03d}" for index in range(200)]

    selection = normalize_preview_selection({"target_entity_ids": target_ids})

    assert selection.target_entity_ids == tuple(target_ids)
    with pytest.raises(AssessmentBatchError) as oversized:
        normalize_preview_selection(
            {"target_entity_ids": [*target_ids, "ent-boundary-200"]}
        )
    assert oversized.value.code == "invalid_batch_selection"


def test_preview_builder_rejects_only_after_the_50000_check_boundary():
    runtime = ProbePlanningRuntime(
        available_features=frozenset(),
        intrusive_actions_enabled=False,
        template_snapshot=NucleiTemplateCacheSnapshot("missing", "", "", 0),
    )
    builder = BatchPreviewBuilder(
        "prj-check-boundary",
        normalize_preview_selection(None),
        runtime,
        {"checks": []},
    )
    unavailable_row = {
        "target_entity_id": "ent-check-boundary",
        "category": "discovery",
        "check_key": "missing-frozen-check",
        "state": "not_started",
        "state_source": "",
        "policy_level": "safe",
        "recommended_action_key": "command:ping",
        "applicability": "applicable",
        "unavailable_evidence_count": 0,
    }

    for _index in range(50_000):
        builder.observe(unavailable_row)

    assert builder.check_count == 50_000
    with pytest.raises(AssessmentBatchError) as oversized:
        builder.observe(unavailable_row)
    assert oversized.value.code == "preview_check_limit_exceeded"
