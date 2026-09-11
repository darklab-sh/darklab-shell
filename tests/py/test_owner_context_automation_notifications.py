# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from services.connectors.oast_correlations import _owner_predicate as oast_owner_predicate
from services.connectors.zap_jobs import _owner_predicate as zap_owner_predicate
from services.notifications.channels_store import _owner_where as notification_owner_where
from services.scheduler.service import _owner_schedule_clause
from services.watchers.models import Watcher
from services.watchers.service import (
    _owner_watcher_clause,
    _project_owner_clause,
    _watcher_run_owner_clause,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _mixed_automation_rows(conn: sqlite3.Connection) -> tuple[str, str]:
    owner_a = "wsp_" + "a" * 32
    owner_b = "wsp_" + "b" * 32
    conn.execute(
        "CREATE TABLE owner_automation_rows ("
        "id TEXT PRIMARY KEY, personal_workspace_id TEXT NOT NULL, session_token TEXT NOT NULL, "
        "team_id TEXT, state TEXT NOT NULL, enabled INTEGER NOT NULL)"
    )
    conn.executemany(
        "INSERT INTO owner_automation_rows "
        "(id, personal_workspace_id, session_token, team_id, state, enabled) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            ("owner-a-null", owner_a, owner_a, None, "ok", 1),
            ("owner-a-empty", owner_a, owner_a, "", "ok", 1),
            ("owner-b-empty", owner_b, owner_b, "", "ok", 1),
            ("team-red", owner_b, owner_b, "team-red", "ok", 1),
            ("team-blue", owner_a, owner_a, "team-blue", "ok", 1),
        ),
    )
    return owner_a, owner_b


def _selected_ids(
    conn: sqlite3.Connection,
    clause: str,
    params: tuple[object, ...],
) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            f"SELECT id FROM owner_automation_rows WHERE {clause} ORDER BY id",  # nosec B608
            params,
        ).fetchall()
    ]


def _watcher(owner: str, *, team_id: str = "") -> Watcher:
    return Watcher(
        id="watcher",
        session_token=owner,
        team_id=team_id,
        project_id="",
        label="",
        command_text="echo test",
        schedule_id="schedule",
        baseline_run_id="",
        last_run_id="",
        last_diff_summary={},
        state="ok",
        state_reason="",
        last_error="",
        options={},
        policy={},
        consecutive_no_change=0,
        consecutive_changed=0,
        consecutive_failures=0,
        created="",
        updated="",
    )


def test_automation_notification_clauses_preserve_mixed_sqlite_result_sets():
    with sqlite3.connect(":memory:") as conn:
        owner_a, _owner_b = _mixed_automation_rows(conn)

        for owner_factory in (oast_owner_predicate, zap_owner_predicate):
            personal_sql, personal_params = owner_factory(owner_a, "")
            assert _selected_ids(conn, personal_sql, personal_params) == ["owner-a-empty"]
            team_sql, team_params = owner_factory(owner_a, "team-red")
            assert _selected_ids(conn, team_sql, team_params) == ["team-red"]

        null_or_empty_factories = (
            notification_owner_where,
            _owner_schedule_clause,
            _owner_watcher_clause,
            _project_owner_clause,
        )
        for owner_factory in null_or_empty_factories:
            personal_sql, personal_params = owner_factory(owner_a, "")
            assert _selected_ids(conn, personal_sql, personal_params) == [
                "owner-a-empty",
                "owner-a-null",
            ]
            team_sql, team_params = owner_factory(owner_a, "team-red")
            assert _selected_ids(conn, team_sql, team_params) == ["team-red"]

        personal_run_sql, personal_run_params = _watcher_run_owner_clause(
            _watcher(owner_a),
            table_alias="",
        )
        assert _selected_ids(conn, personal_run_sql, personal_run_params) == [
            "owner-a-empty",
            "owner-a-null",
        ]
        team_run_sql, team_run_params = _watcher_run_owner_clause(
            _watcher(owner_a, team_id="team-red"),
            table_alias="",
        )
        assert _selected_ids(conn, team_run_sql, team_run_params) == ["team-red"]


def test_automation_notifications_review_covers_every_baseline_site():
    review = json.loads(
        (
            REPO_ROOT
            / ".tooling"
            / "owner-query-reviews"
            / "automation-notifications.json"
        ).read_text(encoding="utf-8")
    )
    paths = review["paths"]
    baseline = sum(int(item["baseline"]) for item in paths.values())
    adapted = sum(int(item["adapter"]) for item in paths.values())
    exceptions = sum(int(item["named_exception"]) for item in paths.values())
    assert baseline == review["baseline_site_count"] == 28
    assert adapted == 27
    assert exceptions == 1
    assert review["summary"] == {
        "equivalent_adapter": 27,
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
        == "refactor/owner-context-automation-notifications"
    ]
    assert len(remaining) == 1
    assert remaining[0]["conversion_classification"] == "equivalent"
    assert remaining[0]["reviewed_exception"].startswith(
        "named relational owner-correlation exception:"
    )
