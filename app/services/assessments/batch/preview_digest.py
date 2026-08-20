# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Streaming digest for complete assessment-batch preview snapshots."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from services.assessments.batch.contracts import BATCH_SCHEMA_VERSION
from services.assessments.batch.preview_models import BatchPreviewDraft


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def batch_preview_digest(draft: BatchPreviewDraft) -> str:
    """Hash the header and every stable-ordered item without one large payload."""
    digest = hashlib.sha256()
    header = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "project_id": draft.project_id,
        "assessment_id": draft.assessment_id,
        "source_batch_id": draft.source_batch_id,
        "profile_key": draft.profile_key,
        "profile_version": draft.profile_version,
        "selection": dict(draft.selection),
        "summary": dict(draft.summary),
        "concurrency": {
            "batch": draft.concurrency.batch,
            "target": draft.concurrency.target,
            "owner": draft.concurrency.owner,
            "instance": draft.concurrency.instance,
        },
        "item_count": len(draft.items),
    }
    digest.update(_canonical(header))
    for item_index, item in enumerate(draft.items):
        mappings = [
            {
                "assessment_id": mapping.assessment_id,
                "check_id": mapping.check_id,
                "check_key": mapping.check_key,
                "target_entity_id": mapping.target_entity_id,
                "coverage_key": mapping.coverage_key,
                "frozen_check_digest": mapping.frozen_check_digest,
            }
            for mapping in item.mappings
        ]
        digest.update(b"\n")
        digest.update(
            _canonical(
                {
                    "item_index": item_index,
                    "execution_key": item.execution_key,
                    "selected": item.selected,
                    "policy_level": item.policy_level,
                    "action_key": item.action_key,
                    "action_id": item.action_id,
                    "target": {
                        "entity_id": item.target_entity_id,
                        "type": item.target_type,
                        "value": item.target_value,
                    },
                    "profile_identity": dict(item.profile_identity),
                    "bounds": dict(item.bounds),
                    "display_command": item.display_command,
                    "public_plan_digest": item.public_plan_digest,
                    "public_plan": dict(item.public_plan),
                    "duration_bound_seconds": item.duration_bound_seconds,
                    "mappings": mappings,
                }
            )
        )
    return digest.hexdigest()

__all__ = ["batch_preview_digest"]
