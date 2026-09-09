# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from identity_helpers import anonymous_session_id
from services.history import snapshots
from services.history.api_queries import project_owner_clause, run_owner_clause
from services.runs import persistence


REPO_ROOT = Path(__file__).resolve().parents[2]


def _mixed_history_rows(conn: sqlite3.Connection) -> tuple[str, str]:
    owner_a = anonymous_session_id("history-owner-a")
    owner_b = anonymous_session_id("history-owner-b")
    conn.execute(
        "CREATE TABLE owner_history_rows (id TEXT PRIMARY KEY, personal_workspace_id TEXT NOT NULL, team_id TEXT)"
    )
    conn.executemany(
        "INSERT INTO owner_history_rows (id, personal_workspace_id, team_id) VALUES (?, ?, ?)",
        (
            ("owner-a-null", owner_a, None),
            ("owner-a-empty", owner_a, ""),
            ("owner-b-empty", owner_b, ""),
            ("team-red", owner_b, "team-red"),
            ("team-blue", owner_a, "team-blue"),
        ),
    )
    return owner_a, owner_b


def _selected_ids(conn: sqlite3.Connection, clause: str, params: list[str], *, alias: str) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            f"SELECT {alias}.id FROM owner_history_rows {alias} WHERE {clause} ORDER BY {alias}.id",  # nosec B608
            params,
        ).fetchall()
    ]


def test_history_run_and_project_clauses_preserve_mixed_sqlite_result_sets():
    with sqlite3.connect(":memory:") as conn:
        owner_a, _owner_b = _mixed_history_rows(conn)

        run_sql, run_params = run_owner_clause(owner_a, "", alias="r")
        assert _selected_ids(conn, run_sql, run_params, alias="r") == [
            "owner-a-empty",
            "owner-a-null",
        ]
        run_team_sql, run_team_params = run_owner_clause(owner_a, "team-red", alias="r")
        assert _selected_ids(conn, run_team_sql, run_team_params, alias="r") == ["team-red"]

        project_sql, project_params = project_owner_clause(owner_a, "", alias="p")
        assert _selected_ids(conn, project_sql, project_params, alias="p") == [
            "owner-a-empty",
            "owner-a-null",
        ]
        project_team_sql, project_team_params = project_owner_clause(owner_a, "team-red", alias="p")
        assert _selected_ids(conn, project_team_sql, project_team_params, alias="p") == ["team-red"]


def test_run_visibility_preserves_empty_team_personal_semantics(monkeypatch):
    owner_a = anonymous_session_id("visibility-owner-a")
    owner_b = anonymous_session_id("visibility-owner-b")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE runs (id TEXT PRIMARY KEY, personal_workspace_id TEXT NOT NULL, team_id TEXT)"
    )
    conn.executemany(
        "INSERT INTO runs (id, personal_workspace_id, team_id) VALUES (?, ?, ?)",
        (
            ("owner-a-null", owner_a, None),
            ("owner-a-empty", owner_a, ""),
            ("owner-b-empty", owner_b, ""),
            ("team-red", owner_b, "team-red"),
        ),
    )
    monkeypatch.setattr(persistence, "get_db_connect", lambda: lambda: conn)

    assert persistence.run_scope_visibility_from_db("owner-a-empty", owner_a) == (True, False, "")
    assert persistence.run_scope_visibility_from_db("owner-a-null", owner_a) == (False, True, "")
    assert persistence.run_scope_visibility_from_db("team-red", owner_a, "team-red") == (True, False, "")
    assert persistence.run_scope_visibility_from_db("team-red", owner_a, "team-blue") == (
        False,
        True,
        "team-red",
    )
    conn.close()


def test_snapshot_bulk_mutation_preserves_unfiltered_session_semantics(monkeypatch):
    owner_a = anonymous_session_id("snapshot-owner-a")
    owner_b = anonymous_session_id("snapshot-owner-b")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE snapshots (id TEXT PRIMARY KEY, personal_workspace_id TEXT NOT NULL, team_id TEXT)"
    )
    conn.executemany(
        "INSERT INTO snapshots (id, personal_workspace_id, team_id) VALUES (?, ?, ?)",
        (
            ("owner-a-null", owner_a, None),
            ("owner-a-empty", owner_a, ""),
            ("owner-b-empty", owner_b, ""),
            ("team-red", owner_a, "team-red"),
        ),
    )
    metadata_deletes: list[list[str]] = []
    monkeypatch.setattr(snapshots, "get_db_connect", lambda: lambda: conn)
    monkeypatch.setattr(snapshots, "delete_snapshot_metadata", lambda _conn, ids: metadata_deletes.append(ids))
    monkeypatch.setattr(snapshots, "record_event", lambda *_args, **_kwargs: None)

    def result_factory(counts, snapshot_id, status, **_kwargs):
        counts[status] += 1
        return {"snapshot_id": snapshot_id, "status": status}

    counts, results = snapshots.bulk_delete_snapshots(
        session_id=owner_a,
        snapshot_ids=["owner-a-null", "owner-a-empty", "owner-b-empty", "team-red"],
        result_factory=result_factory,
        audit_fields={},
    )

    assert counts == {"deleted": 3, "not_found": 1, "rejected": 0}
    assert [result["status"] for result in results] == ["deleted", "deleted", "not_found", "deleted"]
    assert metadata_deletes == [["owner-a-null", "owner-a-empty", "team-red"]]
    assert [row[0] for row in conn.execute("SELECT id FROM snapshots ORDER BY id")] == ["owner-b-empty"]
    conn.close()


def test_history_run_inventory_review_covers_every_foundation_site():
    review = json.loads(
        (REPO_ROOT / ".tooling" / "owner-query-reviews" / "history-runs.json").read_text(encoding="utf-8")
    )
    classifications = review["classifications"]
    assert sum(int(item["site_count"]) for item in classifications) == review["baseline_site_count"] == 28
    assert {item["classification"] for item in classifications} == {"equivalent"}
    assert review["summary"] == {
        "equivalent_adapter": 22,
        "equivalent_named_exception": 6,
        "non_equivalent": 0,
    }

    inventory = [
        json.loads(line)
        for line in (REPO_ROOT / ".tooling" / "owner-query-inventory.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    remaining = [
        item
        for item in inventory
        if item.get("planned_branch") == "refactor/owner-context-history-runs"
    ]
    assert len(remaining) == 6
    assert {item["conversion_classification"] for item in remaining} == {"equivalent"}
    assert all(item["reviewed_exception"].startswith("named relational owner-correlation exception:") for item in remaining)
