# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Server-owned assessment-batch preview storage contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest

from conftest import make_test_app
from core.database_access import get_db_connect
from services.assessments.action_plan_payload import digest_plan
from services.assessments.batch.contracts import AssessmentBatchError, BatchConcurrency
from services.assessments.batch.preview_digest import batch_preview_digest
from services.assessments.batch.preview_models import (
    BatchCheckMapping,
    BatchPreviewDraft,
    BatchPreviewItem,
)
from services.assessments.batch.preview_storage import (
    get_batch_preview_items,
    store_batch_preview,
)
from services.assessments.probe_plan_digest import probe_plan_digest


def _preview_item(index: int) -> BatchPreviewItem:
    target_id = f"ent-preview-{index:03d}"
    target_value = f"host-{index:03d}.example"
    command = f"ping -c 4 -W 2 {target_value}"
    bounds = {
        "target_count": 1,
        "fan_out": 1,
        "request_limit": 4,
        "time_limit_seconds": 10,
        "credential_use": "none",
        "summary": "Four probes against one approved host.",
    }
    plan: dict[str, object] = {
        "schema_version": 1,
        "digest_version": 1,
        "project_id": "prj-preview-storage",
        "action": {"id": "ping", "revision": "1", "mode": "reachability"},
        "target": {"entity_id": target_id, "type": "domain", "value": target_value},
        "profile": {},
        "http_profile": {"id": "", "revision": "", "credential_use": "none"},
        "policy_level": "safe",
        "required_features": ["ping"],
        "feature_gates": [],
        "scope": {
            "kind": "project_target",
            "project_id": "prj-preview-storage",
            "target_count": 1,
            "fan_out": 1,
        },
        "bounds": bounds,
        "display_command": command,
        "expected_evidence": ["run"],
        "availability": {"available": True, "code": "", "reason": ""},
        "launchable": True,
        "unavailable_reason": "",
        "requires_confirmation": True,
    }
    plan["plan_digest"] = probe_plan_digest(plan)
    return BatchPreviewItem(
        execution_key=digest_plan({"execution": index}),
        selected=True,
        policy_level="safe",
        action_key="command:ping",
        action_id="ping",
        target_entity_id=target_id,
        target_type="domain",
        target_value=target_value,
        profile_identity={},
        bounds=bounds,
        display_command=command,
        public_plan_digest=str(plan["plan_digest"]),
        public_plan=plan,
        duration_bound_seconds=10,
        mappings=(
            BatchCheckMapping(
                assessment_id="asm-preview-storage",
                check_id=f"chk-preview-{index:03d}",
                check_key=f"check-{index:03d}",
                target_entity_id=target_id,
                coverage_key=digest_plan({"coverage": index}),
                frozen_check_digest=digest_plan({"check": index}),
            ),
        ),
    )


def test_assessment_batch_previews_are_atomic_paged_current_and_owner_scoped():
    make_test_app()
    created_at = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    timestamp = "2026-08-17 12:00:00"
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO projects "
            "(id, session_id, name, slug, created, updated) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "prj-preview-storage",
                "preview-storage-owner",
                "Preview storage",
                "preview-storage",
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            "INSERT INTO project_assessments "
            "(id, session_id, project_id, title, profile_key, profile_version, status, "
            "started_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'network', '1.0', 'active', ?, ?, ?)",
            (
                "asm-preview-storage",
                "preview-storage-owner",
                "prj-preview-storage",
                "Preview storage",
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()

    items = tuple(_preview_item(index) for index in range(101))
    draft = BatchPreviewDraft(
        session_id="preview-storage-owner",
        team_id="",
        project_id="prj-preview-storage",
        assessment_id="asm-preview-storage",
        source_batch_id="",
        profile_key="network",
        profile_version="1.0",
        selection={"include_standard": False, "item_limit": 128},
        summary={
            "unavailable_check_count": 2,
            "skipped_check_count": 3,
            "estimated_min_seconds": 20,
            "estimated_max_seconds": 160,
        },
        concurrency=BatchConcurrency(),
        items=items,
    )
    preview = store_batch_preview(draft, current_time=created_at)
    assert preview["plan_digest"] == batch_preview_digest(draft)
    assert preview["candidate_item_count"] == 101
    assert preview["selected_item_count"] == 101
    assert preview["potential_covered_check_count"] == 101

    first = cast(
        dict[str, Any],
        get_batch_preview_items(
            "preview-storage-owner",
            str(preview["preview_id"]),
            current_time=created_at,
        ),
    )
    assert len(first["items"]) == 100
    assert first["next_cursor"] == 100
    assert first["items"][0]["check_mappings"][0]["check_id"] == "chk-preview-000"
    second = cast(
        dict[str, Any],
        get_batch_preview_items(
            "preview-storage-owner",
            str(preview["preview_id"]),
            cursor=int(first["next_cursor"]),
            current_time=created_at,
        ),
    )
    assert [item["item_index"] for item in second["items"]] == [100]
    assert second["next_cursor"] is None

    with get_db_connect()() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM assessment_batches "
                "WHERE assessment_id = ?",
                ("asm-preview-storage",),
            ).fetchone()["n"]
            == 0
        )
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM assessment_batch_previews"
        ).fetchone()["n"]
    with pytest.raises(AssessmentBatchError, match="preview item is invalid"):
        store_batch_preview(
            replace(
                draft,
                items=(
                    replace(
                        items[0],
                        public_plan={**items[0].public_plan, "launchable": False},
                    ),
                ),
            ),
            current_time=created_at,
        )
    with get_db_connect()() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM assessment_batch_previews"
            ).fetchone()["n"]
            == before
        )

    with pytest.raises(AssessmentBatchError) as out_of_scope:
        get_batch_preview_items(
            "another-owner", str(preview["preview_id"]), current_time=created_at
        )
    assert out_of_scope.value.code == "preview_not_found"
    with pytest.raises(AssessmentBatchError) as expired:
        get_batch_preview_items(
            "preview-storage-owner",
            str(preview["preview_id"]),
            current_time=created_at + timedelta(seconds=15 * 60 + 1),
        )
    assert expired.value.code == "preview_expired"

    replacement = store_batch_preview(
        draft,
        current_time=created_at + timedelta(seconds=15 * 60 + 1),
    )
    assert replacement["preview_id"] != preview["preview_id"]
    with pytest.raises(AssessmentBatchError) as cleaned:
        get_batch_preview_items(
            "preview-storage-owner",
            str(preview["preview_id"]),
            current_time=created_at + timedelta(seconds=15 * 60 + 1),
        )
    assert cleaned.value.code == "preview_not_found"
