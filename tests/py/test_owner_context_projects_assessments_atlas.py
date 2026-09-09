# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from identity_helpers import anonymous_session_id
from services.atlas.scope import metadata_owner_params, metadata_owner_sql
from services.projects.overview import _run_owner_clause
from services.projects.scope import personal_owner_where, shared_owner_where


REPO_ROOT = Path(__file__).resolve().parents[2]


def _mixed_project_rows(conn: sqlite3.Connection) -> tuple[str, str]:
    owner_a = anonymous_session_id("project-owner-a")
    owner_b = anonymous_session_id("project-owner-b")
    conn.execute(
        "CREATE TABLE owner_project_rows (id TEXT PRIMARY KEY, personal_workspace_id TEXT NOT NULL, team_id TEXT)"
    )
    conn.executemany(
        "INSERT INTO owner_project_rows (id, personal_workspace_id, team_id) VALUES (?, ?, ?)",
        (
            ("owner-a-null", owner_a, None),
            ("owner-a-empty", owner_a, ""),
            ("owner-b-empty", owner_b, ""),
            ("team-red", owner_b, "team-red"),
            ("team-blue", owner_a, "team-blue"),
            ("team-red-metadata-null", "team-red", None),
            ("team-red-metadata-empty", "team-red", ""),
        ),
    )
    return owner_a, owner_b


def _selected_ids(
    conn: sqlite3.Connection,
    clause: str,
    params: tuple[str, ...] | list[str],
) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            f"SELECT id FROM owner_project_rows WHERE {clause} ORDER BY id",  # nosec B608
            params,
        ).fetchall()
    ]


def test_project_and_atlas_owner_clauses_preserve_mixed_sqlite_result_sets():
    with sqlite3.connect(":memory:") as conn:
        owner_a, _owner_b = _mixed_project_rows(conn)

        personal_sql, personal_params = shared_owner_where(owner_a)
        assert _selected_ids(conn, personal_sql, personal_params) == ["owner-a-empty"]

        team_sql, team_params = shared_owner_where(owner_a, team_id="team-red")
        assert _selected_ids(conn, team_sql, team_params) == ["team-red"]

        run_sql, run_params = _run_owner_clause(owner_a, "", alias="")
        assert _selected_ids(conn, run_sql, run_params) == ["owner-a-empty"]

        unfiltered_sql, unfiltered_params = personal_owner_where(owner_a)
        assert _selected_ids(conn, unfiltered_sql, unfiltered_params) == [
            "owner-a-empty",
            "owner-a-null",
            "team-blue",
        ]

        metadata_personal_sql = metadata_owner_sql("", "")
        assert _selected_ids(
            conn,
            metadata_personal_sql,
            metadata_owner_params(owner_a),
        ) == ["owner-a-empty"]

        metadata_team_sql = metadata_owner_sql("", "team-red")
        assert _selected_ids(
            conn,
            metadata_team_sql,
            metadata_owner_params(owner_a, "team-red"),
        ) == [
            "team-red",
            "team-red-metadata-empty",
            "team-red-metadata-null",
        ]


def test_project_assessment_atlas_review_covers_every_baseline_site():
    review = json.loads(
        (
            REPO_ROOT
            / ".tooling"
            / "owner-query-reviews"
            / "projects-assessments-atlas.json"
        ).read_text(encoding="utf-8")
    )
    paths = review["paths"]
    baseline = sum(int(item["baseline"]) for item in paths.values())
    adapted = sum(int(item["adapter"]) for item in paths.values())
    exceptions = sum(int(item["named_exception"]) for item in paths.values())
    assert baseline == review["baseline_site_count"] == 156
    assert adapted == 116
    assert exceptions == 40
    assert review["summary"] == {
        "equivalent_adapter": 116,
        "equivalent_named_exception": 40,
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
        == "refactor/owner-context-projects-assessments-atlas"
    ]
    assert len(remaining) == 40
    assert {item["conversion_classification"] for item in remaining} == {"equivalent"}
    assert all(
        item["reviewed_exception"].startswith(
            "named relational owner-correlation exception:"
        )
        for item in remaining
    )
