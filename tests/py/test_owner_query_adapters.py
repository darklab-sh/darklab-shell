# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from services.teams.contracts import TeamError
from services.teams.ownership_queries import (
    OwnerKeyShape,
    PersonalTeamRows,
    attribution_values,
    composite_owner_predicate,
    personal_only_owner_predicate,
    team_capable_owner_predicate,
    team_only_owner_predicate,
    token_keyed_owner_predicate,
)
from services.teams.scope import personal_owner_context, team_owner_context


REPO_ROOT = Path(__file__).resolve().parents[2]


def _mixed_owner_rows(conn):
    conn.execute(
        """
        CREATE TABLE owner_adapter_rows (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            session_token TEXT NOT NULL,
            team_id TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO owner_adapter_rows (id, session_id, session_token, team_id) VALUES (?, ?, ?, ?)",
        (
            ("owner-a-null", "tok_owner_a", "tok_owner_a", None),
            ("owner-a-empty", "tok_owner_a", "tok_owner_a", ""),
            ("owner-b-empty", "tok_owner_b", "tok_owner_b", ""),
            ("team-row", "tok_owner_a", "tok_owner_a", "team_red"),
        ),
    )


def _selected_ids(conn, predicate):
    rows = conn.execute(
        f"SELECT id FROM owner_adapter_rows WHERE {predicate.sql} ORDER BY id",  # nosec B608
        predicate.params,
    ).fetchall()
    return [row[0] for row in rows]


def _assert_mixed_owner_results(conn):
    owner_a = personal_owner_context("tok_owner_a")
    team = team_owner_context(
        "team_red",
        actor_member_id="tmem_owner",
        actor_session_id="tok_owner_a",
    )

    assert _selected_ids(conn, personal_only_owner_predicate(owner_a)) == [
        "owner-a-empty",
        "owner-a-null",
        "team-row",
    ]
    assert _selected_ids(
        conn,
        team_capable_owner_predicate(
            owner_a,
            personal_team_rows=PersonalTeamRows.NULL,
        ),
    ) == ["owner-a-null"]
    assert _selected_ids(
        conn,
        team_capable_owner_predicate(
            owner_a,
            personal_team_rows=PersonalTeamRows.EMPTY,
        ),
    ) == ["owner-a-empty"]
    assert _selected_ids(
        conn,
        team_capable_owner_predicate(
            owner_a,
            personal_team_rows=PersonalTeamRows.NULL_OR_EMPTY,
        ),
    ) == ["owner-a-empty", "owner-a-null"]
    assert _selected_ids(
        conn,
        team_capable_owner_predicate(
            owner_a,
            personal_team_rows=PersonalTeamRows.UNFILTERED,
        ),
    ) == ["owner-a-empty", "owner-a-null", "team-row"]
    assert _selected_ids(
        conn,
        team_capable_owner_predicate(
            team,
            personal_team_rows=PersonalTeamRows.NULL_OR_EMPTY,
        ),
    ) == ["team-row"]
    assert _selected_ids(conn, team_only_owner_predicate(team)) == ["team-row"]
    assert _selected_ids(
        conn,
        token_keyed_owner_predicate(
            owner_a,
            team_column="team_id",
            personal_team_rows=PersonalTeamRows.NULL_OR_EMPTY,
        ),
    ) == ["owner-a-empty", "owner-a-null"]
    assert _selected_ids(
        conn,
        token_keyed_owner_predicate(team, token_column="team_id"),
    ) == ["team-row"]


def test_owner_query_adapters_preserve_mixed_sqlite_result_sets():
    with sqlite3.connect(":memory:") as conn:
        _mixed_owner_rows(conn)
        _assert_mixed_owner_results(conn)


def test_composite_and_attribution_adapters_keep_roles_separate():
    owner = personal_owner_context("tok_owner_a")
    composite = composite_owner_predicate(
        owner,
        owner_key_shape=OwnerKeyShape.SESSION_TOKEN,
        key_values=(("name", "API_KEY"), ("revision", 3)),
    )
    assert composite.sql == "session_token = ? AND name = ? AND revision = ?"
    assert composite.params == ("tok_owner_a", "API_KEY", 3)

    team = team_owner_context(
        "team_red",
        actor_member_id="tmem_owner",
        actor_session_id="tok_owner_a",
    )
    assert attribution_values(team).session_id == "tok_owner_a"
    assert attribution_values(team).member_id == "tmem_owner"
    assert attribution_values(owner).session_id == "tok_owner_a"
    assert attribution_values(owner).member_id == ""


@pytest.mark.parametrize("identifier", ("team-id", "team_id; DROP TABLE runs", "runs.team.id", ""))
def test_owner_query_adapters_reject_unsafe_identifiers(identifier):
    owner = personal_owner_context("tok_owner_a")
    with pytest.raises(TeamError, match="safe SQL identifier"):
        personal_only_owner_predicate(owner, owner_column=identifier)


def test_owner_query_adapters_require_explicit_table_shape():
    owner = personal_owner_context("tok_owner_a")
    team = team_owner_context("team_red")
    with pytest.raises(TeamError, match="explicit personal-row representation"):
        team_capable_owner_predicate(owner, personal_team_rows="")  # type: ignore[arg-type]
    with pytest.raises(TeamError, match="explicit personal-row representation"):
        token_keyed_owner_predicate(owner, team_column="team_id")
    with pytest.raises(TeamError, match="Personal-only table"):
        personal_only_owner_predicate(team)
    with pytest.raises(TeamError, match="Team-only table"):
        team_only_owner_predicate(owner)
    with pytest.raises(TeamError, match="at least one additional key"):
        composite_owner_predicate(owner, key_values=())
    with pytest.raises(TeamError, match="valid owner key shape"):
        composite_owner_predicate(
            owner,
            key_values=(("name", "API_KEY"),),
            owner_key_shape="session_token",  # type: ignore[arg-type]
        )
    with pytest.raises(TeamError, match="duplicate key column"):
        composite_owner_predicate(owner, key_values=(("session_id", "other"),))


def test_checked_in_owner_query_inventory_matches_source():
    result = subprocess.run(
        [sys.executable, "scripts/development/owner_query_inventory.py", "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
