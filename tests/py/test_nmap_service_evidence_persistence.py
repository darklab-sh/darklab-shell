# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json
import sqlite3

import pytest

from core.database_backend import DatabaseBackend
from core.migrations import MIGRATIONS
from core.migrations.runner import run_migrations
from services.assessments.nmap_service_evidence_persistence import (
    persist_nmap_xml_service_observations,
)


@pytest.fixture
def evidence_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn, MIGRATIONS, backend=DatabaseBackend.SQLITE)
    try:
        yield conn
    finally:
        conn.close()


def _seed_run(
    conn,
    run_id: str,
    *,
    session_id: str = "nmap-owner",
    team_id: str = "",
    command: str = "nmap -sV -oX scan.xml 192.0.2.10",
    exit_code: int = 0,
):
    conn.execute(
        "INSERT INTO runs (id, session_id, team_id, run_kind, command, started, finished, "
        "exit_code, output_preview) VALUES (?, ?, ?, 'external', ?, ?, ?, ?, '[]')",
        (
            run_id,
            session_id,
            team_id,
            command,
            "2026-08-09T00:00:00+00:00",
            "2026-08-09T00:01:00+00:00",
            exit_code,
        ),
    )


def _xml() -> str:
    return """<nmaprun version="7.95">
<host><address addr="192.0.2.10" addrtype="ipv4"/><ports>
<port protocol="tcp" portid="445"><state state="open"/><service name="microsoft-ds"/>
<script id="smb2-security-mode" output="free-form output is never stored">
<elem key="message_signing">disabled</elem></script>
</port></ports></host><runstats><finished time="1786233600"/></runstats></nmaprun>"""


def test_persistence_is_owner_scoped_idempotent_and_omits_free_form_output(evidence_db):
    _seed_run(evidence_db, "run-nmap-service")

    first = persist_nmap_xml_service_observations(
        evidence_db,
        "nmap-owner",
        _xml(),
        source_run_id="run-nmap-service",
        observed_at="2026-08-09T00:01:00+00:00",
    )
    repeated = persist_nmap_xml_service_observations(
        evidence_db,
        "nmap-owner",
        _xml(),
        source_run_id="run-nmap-service",
        observed_at="2026-08-09T00:01:00+00:00",
    )

    assert first == {
        "observation_count": 1,
        "created_count": 1,
        "skipped_count": 0,
        "truncated": False,
    }
    assert repeated == {
        "observation_count": 1,
        "created_count": 0,
        "skipped_count": 0,
        "truncated": False,
    }
    row = dict(evidence_db.execute("SELECT * FROM nmap_service_observations").fetchone())
    assert row["id"].startswith("obs_")
    assert row["session_id"] == "nmap-owner"
    assert row["team_id"] == ""
    assert row["run_id"] == "run-nmap-service"
    assert row["target"] == "192.0.2.10:445/tcp"
    assert row["evidence_kind"] == "smb_signing"
    assert row["classification"] == "informational"
    assert json.loads(row["fields_json"]) == [
        {"path": ["message_signing"], "value": "disabled"},
    ]
    assert "free-form output" not in str(row)


@pytest.mark.parametrize(
    ("owner", "team_id", "command", "exit_code"),
    [
        ("other-owner", "", "nmap -sV 192.0.2.10", 0),
        ("nmap-owner", "team-other", "nmap -sV 192.0.2.10", 0),
        ("nmap-owner", "", "httpx 192.0.2.10", 0),
        ("nmap-owner", "", "nmap -sV 192.0.2.10", 2),
    ],
)
def test_persistence_rejects_cross_owner_non_nmap_and_failed_sources(
    evidence_db,
    owner,
    team_id,
    command,
    exit_code,
):
    _seed_run(
        evidence_db,
        "run-rejected",
        command=command,
        exit_code=exit_code,
    )

    summary = persist_nmap_xml_service_observations(
        evidence_db,
        owner,
        _xml(),
        source_run_id="run-rejected",
        team_id=team_id,
        observed_at="2026-08-09T00:01:00+00:00",
    )

    assert summary["observation_count"] == 0
    assert evidence_db.execute(
        "SELECT COUNT(*) FROM nmap_service_observations",
    ).fetchone()[0] == 0


def test_persistence_rejects_conflicting_replay_for_the_same_observation(evidence_db):
    _seed_run(evidence_db, "run-conflict")
    persist_nmap_xml_service_observations(
        evidence_db,
        "nmap-owner",
        _xml(),
        source_run_id="run-conflict",
        observed_at="2026-08-09T00:01:00+00:00",
    )
    evidence_db.execute(
        "UPDATE nmap_service_observations SET evidence_kind = 'tampered'",
    )

    with pytest.raises(RuntimeError, match="identity conflict"):
        persist_nmap_xml_service_observations(
            evidence_db,
            "nmap-owner",
            _xml(),
            source_run_id="run-conflict",
            observed_at="2026-08-09T00:01:00+00:00",
        )


def test_persisted_observations_follow_the_source_run_lifecycle(evidence_db):
    _seed_run(evidence_db, "run-cascade")
    persist_nmap_xml_service_observations(
        evidence_db,
        "nmap-owner",
        _xml(),
        source_run_id="run-cascade",
        observed_at="2026-08-09T00:01:00+00:00",
    )

    evidence_db.execute("DELETE FROM runs WHERE id = ?", ("run-cascade",))

    assert evidence_db.execute(
        "SELECT COUNT(*) FROM nmap_service_observations",
    ).fetchone()[0] == 0
