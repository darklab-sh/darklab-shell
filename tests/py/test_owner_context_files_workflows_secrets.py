# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from identity_helpers import anonymous_session_id
from services.secrets.storage import _secret_scope_owner
from services.session.storage import _recent_values_owner
from services.teams.ownership_queries import workspace_keyed_owner_predicate
from services.teams.request_scope import RequestScope
from services.teams.scope import personal_owner_context, team_owner_context
from services.workflows.storage import _owner_where
from services.workflows.user_workflows import _workflow_owner_where
from services.workspace.metadata import _workspace_metadata_owner_where


REPO_ROOT = Path(__file__).resolve().parents[2]


def _mixed_storage_rows(conn: sqlite3.Connection) -> tuple[str, str]:
    owner_a = anonymous_session_id("files-workflows-secrets-owner-a")
    owner_b = anonymous_session_id("files-workflows-secrets-owner-b")
    conn.execute(
        "CREATE TABLE owner_storage_rows ("
        "id TEXT PRIMARY KEY, personal_workspace_id TEXT NOT NULL, session_token TEXT NOT NULL, "
        "team_id TEXT, kind TEXT NOT NULL)"
    )
    conn.executemany(
        "INSERT INTO owner_storage_rows (id, personal_workspace_id, session_token, team_id, kind) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            ("owner-a-null", owner_a, owner_a, None, "domain"),
            ("owner-a-empty", owner_a, owner_a, "", "domain"),
            ("owner-b-empty", owner_b, owner_b, "", "domain"),
            ("team-red", owner_b, "team-red", "team-red", "domain"),
            ("team-blue", owner_a, "team-blue", "team-blue", "domain"),
            ("team-red-flat-null", "team-red", "team-red", None, "domain"),
            ("team-red-flat-empty", "team-red", "team-red", "", "domain"),
            ("owner-a-other-kind", owner_a, owner_a, "", "ip"),
        ),
    )
    return owner_a, owner_b


def _selected_ids(
    conn: sqlite3.Connection,
    clause: str,
    params: tuple[object, ...] | list[object],
) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            f"SELECT id FROM owner_storage_rows WHERE {clause} ORDER BY id",  # nosec B608
            params,
        ).fetchall()
    ]


def test_files_workflows_and_secrets_preserve_mixed_sqlite_result_sets():
    with sqlite3.connect(":memory:") as conn:
        owner_a, _owner_b = _mixed_storage_rows(conn)

        workflow_sql, workflow_params = _owner_where(owner_a)
        assert _selected_ids(conn, workflow_sql, workflow_params) == [
            "owner-a-empty",
            "owner-a-null",
            "owner-a-other-kind",
        ]
        user_workflow_sql, user_workflow_params = _workflow_owner_where(owner_a)
        assert _selected_ids(conn, user_workflow_sql, user_workflow_params) == [
            "owner-a-empty",
            "owner-a-null",
            "owner-a-other-kind",
        ]

        workflow_team_sql, workflow_team_params = _owner_where(owner_a, team_id="team-red")
        assert _selected_ids(conn, workflow_team_sql, workflow_team_params) == ["team-red"]

        recent_owner = _recent_values_owner(owner_a, "", kind="domain")
        assert _selected_ids(conn, recent_owner.sql, recent_owner.params) == ["owner-a-empty"]

        personal_scope = RequestScope(personal_owner_context(owner_a))
        metadata_sql, metadata_params = _workspace_metadata_owner_where(personal_scope)
        assert _selected_ids(conn, metadata_sql, metadata_params) == [
            "owner-a-empty",
            "owner-a-null",
            "owner-a-other-kind",
        ]

        team_scope = RequestScope(
            team_owner_context("team-red", actor_session_id=owner_a),
            team_id="team-red",
        )
        metadata_team_sql, metadata_team_params = _workspace_metadata_owner_where(team_scope)
        assert _selected_ids(conn, metadata_team_sql, metadata_team_params) == [
            "team-red",
            "team-red-flat-empty",
            "team-red-flat-null",
        ]

        secret_owner = workspace_keyed_owner_predicate(
            _secret_scope_owner("team-red"),
            workspace_column="session_token",
        )
        assert _selected_ids(conn, secret_owner.sql, secret_owner.params) == [
            "team-red",
            "team-red-flat-empty",
            "team-red-flat-null",
        ]


def test_files_workflows_secrets_review_covers_every_baseline_site():
    review = json.loads(
        (
            REPO_ROOT
            / ".tooling"
            / "owner-query-reviews"
            / "files-workflows-secrets.json"
        ).read_text(encoding="utf-8")
    )
    paths = review["paths"]
    baseline = sum(int(item["baseline"]) for item in paths.values())
    adapted = sum(int(item["adapter"]) for item in paths.values())
    exceptions = sum(int(item["named_exception"]) for item in paths.values())
    assert baseline == review["baseline_site_count"] == 40
    assert adapted == 39
    assert exceptions == 1
    assert review["summary"] == {
        "equivalent_adapter": 39,
        "equivalent_named_exception": 1,
        "non_equivalent": 0,
    }

    inventory = [
        json.loads(line)
        for line in (
            REPO_ROOT / ".tooling" / "owner-query-inventory.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    remaining = [
        item
        for item in inventory
        if item.get("planned_branch")
        == "refactor/owner-context-files-workflows-secrets"
    ]
    assert len(remaining) == 1
    assert remaining[0]["conversion_classification"] == "equivalent"
    assert remaining[0]["reviewed_exception"].startswith(
        "named relational owner-correlation exception:"
    )
