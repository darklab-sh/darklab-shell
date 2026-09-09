# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from identity_helpers import anonymous_session_id
from services.teams.ownership_queries import (
    PersonalTeamRows,
    composite_owner_predicate,
    personal_only_owner_predicate,
    team_capable_owner_predicate,
    team_only_owner_predicate,
)
from services.teams.scope import personal_owner_context, team_owner_context


REPO_ROOT = Path(__file__).resolve().parents[2]


def _mixed_remaining_rows(conn: sqlite3.Connection) -> tuple[str, str]:
    owner_a = anonymous_session_id("remaining-surfaces-owner-a")
    owner_b = anonymous_session_id("remaining-surfaces-owner-b")
    conn.execute(
        "CREATE TABLE owner_remaining_rows ("
        "id TEXT PRIMARY KEY, personal_workspace_id TEXT NOT NULL, team_id TEXT, run_id TEXT NOT NULL)"
    )
    conn.executemany(
        "INSERT INTO owner_remaining_rows (id, personal_workspace_id, team_id, run_id) VALUES (?, ?, ?, ?)",
        (
            ("owner-a-null", owner_a, None, "run-one"),
            ("owner-a-empty", owner_a, "", "run-one"),
            ("owner-a-other-run", owner_a, "", "run-two"),
            ("owner-b-empty", owner_b, "", "run-one"),
            ("team-red", owner_b, "team-red", "run-one"),
            ("team-blue", owner_a, "team-blue", "run-one"),
        ),
    )
    return owner_a, owner_b


def _selected_ids(conn: sqlite3.Connection, predicate) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            f"SELECT id FROM owner_remaining_rows WHERE {predicate.sql} ORDER BY id",  # nosec B608
            predicate.params,
        ).fetchall()
    ]


def _assert_remaining_surface_results(conn: sqlite3.Connection) -> None:
    owner_a, _owner_b = _mixed_remaining_rows(conn)
    personal = personal_owner_context(owner_a)
    team = team_owner_context("team-red", actor_session_id=owner_a)

    assert _selected_ids(conn, personal_only_owner_predicate(personal)) == [
        "owner-a-empty",
        "owner-a-null",
        "owner-a-other-run",
        "team-blue",
    ]
    assert _selected_ids(
        conn,
        composite_owner_predicate(personal, key_values=(("run_id", "run-one"),)),
    ) == ["owner-a-empty", "owner-a-null", "team-blue"]
    assert _selected_ids(
        conn,
        team_capable_owner_predicate(
            personal,
            personal_team_rows=PersonalTeamRows.NULL_OR_EMPTY,
        ),
    ) == ["owner-a-empty", "owner-a-null", "owner-a-other-run"]
    assert _selected_ids(
        conn,
        team_capable_owner_predicate(
            team,
            personal_team_rows=PersonalTeamRows.NULL_OR_EMPTY,
        ),
    ) == ["team-red"]
    assert _selected_ids(conn, team_only_owner_predicate(team)) == ["team-red"]


def test_remaining_surface_adapters_preserve_mixed_sqlite_result_sets():
    with sqlite3.connect(":memory:") as conn:
        _assert_remaining_surface_results(conn)


def test_remaining_surface_review_covers_every_baseline_site():
    review = json.loads(
        (
            REPO_ROOT
            / ".tooling"
            / "owner-query-reviews"
            / "remaining-surfaces.json"
        ).read_text(encoding="utf-8")
    )
    paths = review["paths"]
    baseline = sum(int(item["baseline"]) for item in paths.values())
    adapted = sum(int(item["adapter"]) for item in paths.values())
    exceptions = sum(int(item["named_exception"]) for item in paths.values())
    assert baseline == review["baseline_site_count"] == 52
    assert adapted == 34
    assert exceptions == 18
    assert review["summary"] == {
        "equivalent_adapter": 34,
        "equivalent_named_exception": 18,
        "non_equivalent": 0,
    }

    inventory = [
        json.loads(line)
        for line in (
            REPO_ROOT / ".tooling" / "owner-query-inventory.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    sites = [item for item in inventory if item.get("kind") == "site"]
    metadata = next(item for item in inventory if item.get("kind") == "metadata")
    assert all(item["conversion_classification"] != "unclassified" for item in sites)
    remaining = [
        item
        for item in sites
        if item.get("planned_branch")
        == "refactor/owner-context-remaining-surfaces"
    ]
    assert len(remaining) == metadata["summary"]["by_branch"][
        "refactor/owner-context-remaining-surfaces"
    ]
    assert {item["conversion_classification"] for item in remaining} == {
        "equivalent",
        "principal-foundation",
    }
    assert all(item["reviewed_exception"] != "temporary Phase 3A direct predicate" for item in remaining)
