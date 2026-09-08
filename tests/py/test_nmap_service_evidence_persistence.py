# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json
import sqlite3

import pytest

from identity_helpers import anonymous_session_id
from core.database_backend import DatabaseBackend
from core.migrations import MIGRATIONS
from core.migrations.runner import run_migrations
from services.assessments.nmap_service_evidence_persistence import (
    persist_nmap_xml_service_observations,
)
from services.assessments.nmap_service_evidence_read import (
    nmap_service_evidence_for_run_on_conn,
)


_NMAP_OWNER = anonymous_session_id("nmap-owner")
_OTHER_OWNER = anonymous_session_id("other-owner")
_TEAM_MEMBER_A = anonymous_session_id("team-member-a")
_TEAM_MEMBER_B = anonymous_session_id("team-member-b")
_TEAM_MEMBER_C = anonymous_session_id("team-member-c")


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
    session_id: str = _NMAP_OWNER,
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
        _NMAP_OWNER,
        _xml(),
        source_run_id="run-nmap-service",
        observed_at="2026-08-09T00:01:00+00:00",
    )
    repeated = persist_nmap_xml_service_observations(
        evidence_db,
        _NMAP_OWNER,
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
    assert row["session_id"] == _NMAP_OWNER
    assert row["team_id"] == ""
    assert row["run_id"] == "run-nmap-service"
    assert row["target"] == "192.0.2.10:445/tcp"
    assert row["evidence_kind"] == "smb_signing"
    assert row["classification"] == "informational"
    assert json.loads(row["fields_json"]) == [
        {"path": ["message_signing"], "value": "disabled"},
    ]
    assert "free-form output" not in str(row)

    page = nmap_service_evidence_for_run_on_conn(
        evidence_db,
        _NMAP_OWNER,
        "run-nmap-service",
        limit=1,
    )
    assert page == {
        "observations": [{
            "id": row["id"],
            "run_id": "run-nmap-service",
            "target": "192.0.2.10:445/tcp",
            "service": "microsoft-ds",
            "script_id": "smb2-security-mode",
            "evidence_kind": "smb_signing",
            "classification": "informational",
            "tool_version": "7.95",
            "parser_version": "nmap-xml-service-evidence-v2",
            "fields": [{"path": ["message_signing"], "value": "disabled"}],
            "fields_truncated": False,
            "collection_truncated": False,
            "observed_at": "2026-08-09T00:01:00+00:00",
            "created_at": "2026-08-09T00:01:00+00:00",
        }],
        "total": 1,
        "limit": 1,
        "offset": 0,
        "has_more": False,
    }
    assert nmap_service_evidence_for_run_on_conn(
        evidence_db, _OTHER_OWNER, "run-nmap-service",
    ) is None

    _seed_run(
        evidence_db,
        "run-nmap-team",
        session_id=_TEAM_MEMBER_A,
        team_id="team-nmap",
    )
    team_summary = persist_nmap_xml_service_observations(
        evidence_db,
        _TEAM_MEMBER_B,
        _xml(),
        source_run_id="run-nmap-team",
        team_id="team-nmap",
        observed_at="2026-08-09T00:01:00+00:00",
    )
    team_page = nmap_service_evidence_for_run_on_conn(
        evidence_db,
        _TEAM_MEMBER_C,
        "run-nmap-team",
        team_id="team-nmap",
    )
    assert team_summary["created_count"] == 1
    assert team_page is not None and team_page["total"] == 1
    assert nmap_service_evidence_for_run_on_conn(
        evidence_db, _TEAM_MEMBER_A, "run-nmap-team",
    ) is None
    assert nmap_service_evidence_for_run_on_conn(
        evidence_db, _TEAM_MEMBER_A, "run-nmap-team", team_id="other-team",
    ) is None


@pytest.mark.parametrize(
    ("owner", "team_id", "command", "exit_code"),
    [
        (_OTHER_OWNER, "", "nmap -sV 192.0.2.10", 0),
        (_NMAP_OWNER, "team-other", "nmap -sV 192.0.2.10", 0),
        (_NMAP_OWNER, "", "httpx 192.0.2.10", 0),
        (_NMAP_OWNER, "", "nmap -sV 192.0.2.10", 2),
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
        _NMAP_OWNER,
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
            _NMAP_OWNER,
            _xml(),
            source_run_id="run-conflict",
            observed_at="2026-08-09T00:01:00+00:00",
        )


def test_persisted_observations_follow_the_source_run_lifecycle(evidence_db):
    _seed_run(evidence_db, "run-cascade")
    persist_nmap_xml_service_observations(
        evidence_db,
        _NMAP_OWNER,
        _xml(),
        source_run_id="run-cascade",
        observed_at="2026-08-09T00:01:00+00:00",
    )

    evidence_db.execute("DELETE FROM runs WHERE id = ?", ("run-cascade",))

    assert evidence_db.execute(
        "SELECT COUNT(*) FROM nmap_service_observations",
    ).fetchone()[0] == 0
