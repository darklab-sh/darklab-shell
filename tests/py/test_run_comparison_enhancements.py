# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Focused regression coverage for run-comparison metadata and adapters."""

from __future__ import annotations

import json
import sqlite3
import uuid

import pytest

from core.database_backend import DatabaseBackend
from core.database import DB_PATH
from core.migrations.runner import apply_migration, ensure_migration_table
from core.migrations.v0044_finding_occurrence_comparison import MIGRATION
from services.runs.comparison_derived import compare_additional_derived_groups
from services.runs.comparison_findings import (
    compare_finding_items,
    finding_compare_key,
    finding_comparison_key,
    run_finding_compare_items,
)
from services.projects.findings import record_run_findings
from services.teams.request_scope import RequestScope
from services.teams.scope import personal_owner_context, team_owner_context
from conftest import make_test_app


def _comparison_key(text: str) -> str:
    return finding_comparison_key(
        tool_root="scanner",
        kind="finding",
        subject_key="domain:darklab.sh",
        text=text,
    )


@pytest.mark.parametrize(("before", "after"), (
    ("[high] TLS certificate expires soon", "[critical] TLS certificate expires soon"),
    ("severity: medium exposed service", "severity: high exposed service"),
    ("low severity weak cipher", "high severity weak cipher"),
    ("TruffleHog verified AWS key", "TruffleHog unknown AWS key"),
    ("|_ CVE-2026-0001 7.5 https://vulners.com/cve/CVE-2026-0001", "|_ CVE-2026-0001 9.8 https://vulners.com/cve/CVE-2026-0001"),
    (
        "Nmap Vulners: CVE-2026-0001 affects https on darklab.sh:443 "
        "(CVSS score 7.5, severity high); public exploit references: CVE-2026-0001",
        "Nmap Vulners: CVE-2026-0001 affects https on darklab.sh:443 "
        "(CVSS score 9.8, severity critical); public exploit references: CVE-2026-0001",
    ),
))
def test_finding_comparison_key_ignores_supported_severity_tokens(before, after):
    assert _comparison_key(before) == _comparison_key(after)
    assert finding_comparison_key(
        tool_root="scanner",
        kind="finding",
        subject_key=f"unscoped:scanner:{before}",
        text=before,
    ) == finding_comparison_key(
        tool_root="scanner",
        kind="finding",
        subject_key=f"unscoped:scanner:{after}",
        text=after,
    )


def test_changed_findings_pair_exact_severities_before_remaining_duplicates():
    left = [
        {"comparison_key": "shared", "key": "shared", "id": "left-low", "severity": "low"},
        {"comparison_key": "shared", "key": "shared", "id": "left-high", "severity": "high"},
    ]
    right = [
        {"comparison_key": "shared", "key": "shared", "id": "right-high", "severity": "high"},
        {"comparison_key": "shared", "key": "shared", "id": "right-critical", "severity": "critical"},
    ]

    result = compare_finding_items(left, right)

    assert result["unchanged_count"] == 1
    assert result["added"] == []
    assert result["removed"] == []
    assert result["changed"] == [{
        "key": "shared",
        "before": left[0],
        "after": right[1],
        "changed_fields": ["severity"],
    }]

    duplicate_left = [
        {"comparison_key": "duplicate", "key": "duplicate", "id": f"left-{index}", "severity": "low"}
        for index in range(1000)
    ]
    duplicate_right = [
        {"comparison_key": "duplicate", "key": "duplicate", "id": f"right-{index}", "severity": "high"}
        for index in range(1000)
    ]
    duplicate_result = compare_finding_items(duplicate_left, duplicate_right)
    assert len(duplicate_result["changed"]) == 1000
    assert duplicate_result["added"] == duplicate_result["removed"] == []


def test_findings_without_comparison_keys_keep_generic_add_remove_behavior():
    unchanged = {"comparison_key": "", "key": "", "id": "same", "severity": "low"}
    removed = {"comparison_key": "", "key": "", "id": "removed", "severity": "low"}
    added = {"comparison_key": "", "key": "", "id": "added", "severity": "high"}

    result = compare_finding_items([unchanged, removed], [unchanged, added])

    assert result["unchanged_count"] == 1
    assert result["changed"] == []
    assert result["removed"] == [removed]
    assert result["added"] == [added]


def _legacy_finding_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE runs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE findings (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            line_number INTEGER,
            scope TEXT NOT NULL DEFAULT 'finding',
            review_state TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT '',
            tool_root TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'finding',
            subject_key TEXT NOT NULL DEFAULT '',
            signature_hash TEXT NOT NULL DEFAULT '',
            first_run_id TEXT NOT NULL DEFAULT '',
            last_run_id TEXT NOT NULL DEFAULT '',
            first_seen_at TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT NOT NULL DEFAULT '',
            occurrence_count INTEGER NOT NULL DEFAULT 0,
            fingerprint TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new',
            title TEXT NOT NULL DEFAULT '',
            raw_line TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL
        );
        CREATE TABLE findings_occurrences (
            finding_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            line_number INTEGER NOT NULL DEFAULT 0,
            snippet TEXT NOT NULL DEFAULT '',
            seen_at TEXT NOT NULL,
            PRIMARY KEY (finding_id, run_id, line_number)
        );
    """)


def test_occurrence_migration_backfills_and_trigger_snapshots_comparison_metadata():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _legacy_finding_schema(conn)
    conn.execute(
        "INSERT INTO runs (id, session_id) VALUES ('run-old', 'session-a')"
    )
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, run_id, line_number, severity, tool_root, kind, subject_key, raw_line, created) "
        "VALUES ('finding-old', 'session-a', '', 2, 'high', 'scanner', 'finding', "
        "'domain:darklab.sh', '[high] exposed service', '2026-07-13T10:00:00Z')"
    )
    conn.execute(
        "INSERT INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at) "
        "VALUES ('finding-old', 'run-old', 2, '[high] exposed service', '2026-07-13T10:00:00Z')"
    )
    ensure_migration_table(conn, backend=DatabaseBackend.SQLITE)

    apply_migration(conn, MIGRATION, backend=DatabaseBackend.SQLITE)

    backfilled = conn.execute(
        "SELECT observed_severity, comparison_key FROM findings_occurrences WHERE finding_id = 'finding-old'"
    ).fetchone()
    assert backfilled["observed_severity"] == "high"
    assert finding_compare_key(backfilled) == _comparison_key("[high] exposed service")

    conn.execute(
        "INSERT INTO runs (id, session_id) VALUES ('run-new', 'session-a')"
    )
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, run_id, line_number, severity, tool_root, kind, subject_key, raw_line, created) "
        "VALUES ('finding-new', 'session-a', 'run-new', 4, 'critical', 'scanner', 'finding', "
        "'domain:darklab.sh', '[critical] exposed service', '2026-07-13T11:00:00Z')"
    )
    triggered = conn.execute(
        "SELECT observed_severity, comparison_key FROM findings_occurrences WHERE finding_id = 'finding-new'"
    ).fetchone()
    assert triggered["observed_severity"] == "critical"
    assert finding_compare_key(triggered) == _comparison_key("[critical] exposed service")
    conn.close()


def test_finding_compare_loader_applies_owner_scope_to_run_and_finding():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _legacy_finding_schema(conn)
    ensure_migration_table(conn, backend=DatabaseBackend.SQLITE)
    apply_migration(conn, MIGRATION, backend=DatabaseBackend.SQLITE)
    for run_id, session_id, team_id in (
        ("personal-run", "session-a", ""),
        ("team-run", "session-b", "team-a"),
    ):
        conn.execute(
            "INSERT INTO runs (id, session_id, team_id) VALUES (?, ?, ?)",
            (run_id, session_id, team_id),
        )
        conn.execute(
            "INSERT INTO findings "
            "(id, session_id, team_id, run_id, line_number, severity, tool_root, kind, subject_key, raw_line, created) "
            "VALUES (?, ?, ?, ?, 0, 'high', 'scanner', 'finding', 'domain:darklab.sh', "
            "'[high] exposed service', '2026-07-13T10:00:00Z')",
            (f"finding-{run_id}", session_id, team_id, run_id),
        )

    personal_scope = RequestScope(personal_owner_context("session-a"))
    team_scope = RequestScope(
        team_owner_context("team-a", actor_session_id="session-b"),
        team_id="team-a",
    )
    personal_items, personal_total, _ = run_finding_compare_items(conn, personal_scope, "personal-run")
    hidden_items, hidden_total, _ = run_finding_compare_items(conn, personal_scope, "team-run")
    team_items, team_total, _ = run_finding_compare_items(conn, team_scope, "team-run")

    assert personal_total == 1 and len(personal_items) == 1
    assert hidden_total == 0 and hidden_items == []
    assert team_total == 1 and len(team_items) == 1
    conn.close()


def test_host_and_tls_adapters_use_same_root_and_loaded_entries():
    for root in ("subfinder", "amass"):
        host_groups = compare_additional_derived_groups(
            {"command": f"{root} -d darklab.sh"},
            {"command": f"{root} -d darklab.sh"},
            [{"text": "old.darklab.sh", "line_index": 2}],
            [{"text": "new.darklab.sh", "line_index": 3}],
        )
        assert host_groups[0]["id"] == "discovered_hosts"
        assert host_groups[0]["target"] == "darklab.sh"
        assert host_groups[0]["added"][0]["host"] == "new.darklab.sh"
        assert host_groups[0]["added"][0]["compare_line_index"] == 0

    ambiguous_hosts = compare_additional_derived_groups(
        {"command": "subfinder -d old.darklab.sh", "preview_truncated": True},
        {"command": "subfinder -d new.darklab.sh"},
        [{"text": "api.old.darklab.sh", "line_index": 2}],
        [{"text": "api.new.darklab.sh", "line_index": 3}],
    )[0]
    assert ambiguous_hosts["target"] == ""
    assert ambiguous_hosts["display_target"] == "multiple targets"
    assert ambiguous_hosts["target_ambiguous"] is True
    assert ambiguous_hosts["truncated"] is True
    assert ambiguous_hosts["note"] == "Host results may be incomplete."

    capped_hosts = compare_additional_derived_groups(
        {"command": "subfinder -d darklab.sh"},
        {"command": "subfinder -d darklab.sh"},
        [],
        [{"text": f"host-{index}.darklab.sh", "line_index": index} for index in range(1001)],
    )[0]
    assert capped_hosts["added_count"] == 1001
    assert len(capped_hosts["added"]) == 1000
    assert capped_hosts["truncated"] is True

    assert compare_additional_derived_groups(
        {"command": "httpx -u https://darklab.sh"},
        {"command": "httpx -u https://darklab.sh"},
        [{"text": "https://old.darklab.sh"}],
        [{"text": "https://new.darklab.sh"}],
        skip_hosts=True,
    ) == []

    tls_groups = compare_additional_derived_groups(
        {"command": "openssl s_client -connect darklab.sh:443", "full_output_truncated": True},
        {"command": "openssl s_client -connect darklab.sh:443"},
        [
            {"text": "subject=CN=old.darklab.sh"},
            {"text": "issuer=CN=Old CA"},
            {"text": "notBefore=Jul 01 00:00:00 2026 GMT"},
            {"text": "notAfter=Aug 01 00:00:00 2026 GMT"},
            {"text": "SHA256 Fingerprint=AA:BB"},
            {"text": "Verify return code: 10 (certificate has expired)"},
            {"text": "X509v3 Subject Alternative Name:"},
            {"text": "DNS:old.darklab.sh,"},
            {"text": "DNS:www.darklab.sh"},
        ],
        [
            {"text": "subject=CN=darklab.sh"},
            {"text": "issuer=CN=New CA"},
            {"text": "notBefore=Jul 02 00:00:00 2026 GMT"},
            {"text": "notAfter=Sep 01 00:00:00 2026 GMT"},
            {"text": "SHA256 Fingerprint=CC:DD"},
            {"text": "Verify return code: 0 (ok)"},
            {"text": "X509v3 Subject Alternative Name:"},
            {"text": "DNS:api.darklab.sh,"},
            {"text": "DNS:darklab.sh"},
        ],
    )
    assert tls_groups[0]["id"] == "tls_certificate"
    assert tls_groups[0]["target"] == "darklab.sh:443"
    assert {item["key"] for item in tls_groups[0]["changed"]} == {
        "issuer",
        "not_after",
        "not_before",
        "sha256_fingerprint",
        "subject",
        "subject_alt_names",
        "verify_return_code",
    }
    assert tls_groups[0]["changed_count"] == 7
    assert tls_groups[0]["truncated"] is True
    assert tls_groups[0]["note"] == "TLS results may be incomplete."

    assert compare_additional_derived_groups(
        {"command": "subfinder -d darklab.sh"},
        {"command": "amass enum -d darklab.sh"},
        [{"text": "old.darklab.sh"}],
        [{"text": "new.darklab.sh"}],
    ) == []

    session_id = f"compare-derived-{uuid.uuid4().hex[:8]}"
    left_id = f"run-derived-left-{uuid.uuid4().hex[:8]}"
    right_id = f"run-derived-right-{uuid.uuid4().hex[:8]}"
    client = make_test_app().test_client()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany(
                "INSERT INTO runs "
                "(id, session_id, run_kind, command, started, finished, exit_code, output_preview, "
                "output_line_count) VALUES (?, ?, 'external', 'subfinder -d darklab.sh', ?, ?, 0, ?, 1)",
                [
                    (
                        left_id,
                        session_id,
                        "2026-07-13T10:00:00Z",
                        "2026-07-13T10:00:01Z",
                        json.dumps([{"text": "old.darklab.sh", "line_index": 0}]),
                    ),
                    (
                        right_id,
                        session_id,
                        "2026-07-13T11:00:00Z",
                        "2026-07-13T11:00:01Z",
                        json.dumps([{"text": "new.darklab.sh", "line_index": 0}]),
                    ),
                ],
            )
            conn.commit()

        response = client.get(
            f"/history/compare?left={left_id}&right={right_id}",
            headers={"X-Session-ID": session_id},
        )
        assert response.status_code == 200
        route_group = response.get_json()["derived_changes"]["groups"][0]
        assert route_group["id"] == "discovered_hosts"
        assert route_group["added"][0]["host"] == "new.darklab.sh"
        assert route_group["removed"][0]["host"] == "old.darklab.sh"
    finally:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany("DELETE FROM runs WHERE id = ?", [(left_id,), (right_id,)])
            conn.commit()


def test_compare_route_reports_severity_change_anchors_and_conditional_workflow_provenance():
    session_id = f"compare-enhancements-{uuid.uuid4().hex[:8]}"
    left_id = f"run-left-{uuid.uuid4().hex[:8]}"
    right_id = f"run-right-{uuid.uuid4().hex[:8]}"
    finding_ids = []
    execution_id = f"wfx-{uuid.uuid4().hex[:8]}"
    left_entries = [
        {"text": "[low] exposed service", "line_index": 0, "signals": ["findings"]},
        {"text": "severity: medium weak configuration", "line_index": 1, "signals": ["findings"]},
        {"text": "low severity weak cipher", "line_index": 2, "signals": ["findings"]},
        {"text": "TruffleHog unknown AWS key", "line_index": 3, "signals": ["findings"]},
    ]
    right_entries = [
        {"text": "[high] exposed service", "line_index": 0, "signals": ["findings"]},
        {"text": "severity: high weak configuration", "line_index": 1, "signals": ["findings"]},
        {"text": "high severity weak cipher", "line_index": 2, "signals": ["findings"]},
        {"text": "TruffleHog verified AWS key", "line_index": 3, "signals": ["findings"]},
    ]
    client = make_test_app().test_client()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            conn.executemany(
                "INSERT INTO runs "
                "(id, session_id, run_kind, command, started, finished, exit_code, output_preview, output_line_count) "
                "VALUES (?, ?, 'external', 'scanner darklab.sh', ?, ?, 0, ?, ?)",
                [
                    (
                        left_id, session_id, "2026-07-13T10:00:00Z", "2026-07-13T10:00:01Z",
                        json.dumps(left_entries), len(left_entries),
                    ),
                    (
                        right_id, session_id, "2026-07-13T11:00:00Z", "2026-07-13T11:00:01Z",
                        json.dumps(right_entries), len(right_entries),
                    ),
                ],
            )
            left_findings = record_run_findings(conn, session_id, left_id, left_entries)
            right_findings = record_run_findings(conn, session_id, right_id, right_entries)
            repeated_right_findings = record_run_findings(conn, session_id, right_id, right_entries)
            assert [item["id"] for item in repeated_right_findings] == [
                item["id"] for item in right_findings
            ]
            finding_ids.extend(item["id"] for item in (*left_findings, *right_findings))
            occurrence_snapshots = conn.execute(
                "SELECT observed_severity, comparison_key FROM findings_occurrences "
                "WHERE run_id = ? ORDER BY line_number",
                (right_id,),
            ).fetchall()
            assert [str(row["observed_severity"]) for row in occurrence_snapshots] == [
                "high",
                "high",
                "high",
                "high",
            ]
            assert all(str(row["comparison_key"]).startswith("raw:scanner\x1f") for row in occurrence_snapshots)
            subjects = {
                str(row["subject_key"])
                for row in conn.execute(
                    "SELECT subject_key FROM findings WHERE id IN ("
                    + ",".join("?" for _finding_id in finding_ids)
                    + ")",
                    finding_ids,
                ).fetchall()
            }
            assert subjects == {
                "unscoped:scanner:[<severity>] exposed service",
                "unscoped:scanner:severity: <severity> weak configuration",
                "unscoped:scanner:<severity> severity weak cipher",
                "unscoped:scanner:trufflehog <verification> aws key",
            }
            conn.execute(
                "INSERT INTO workflow_executions "
                "(id, session_id, workflow_id, workflow_source, title, status, current_step_id, created, updated) "
                "VALUES (?, ?, 'workflow-1', 'user', 'External review', 'completed', 'scan', "
                "'2026-07-13T10:00:00Z', '2026-07-13T10:00:01Z')",
                (execution_id, session_id),
            )
            conn.execute(
                "INSERT INTO workflow_execution_steps "
                "(id, execution_id, step_id, step_index, run_id, status, exit_code, created, started, finished) "
                "VALUES (?, ?, 'scan', 0, ?, 'completed', 0, '2026-07-13T10:00:00Z', "
                "'2026-07-13T10:00:00Z', '2026-07-13T10:00:01Z')",
                (f"wfs-{uuid.uuid4().hex[:8]}", execution_id, left_id),
            )
            conn.execute(
                "INSERT INTO workflow_execution_steps "
                "(id, execution_id, step_id, step_index, run_id, status, exit_code, created, started, finished) "
                "VALUES (?, ?, 'verify', 1, ?, 'completed', 0, '2026-07-13T10:00:02Z', "
                "'2026-07-13T10:00:02Z', '2026-07-13T10:00:03Z')",
                (f"wfs-{uuid.uuid4().hex[:8]}", execution_id, right_id),
            )
            conn.commit()

        response = client.get(
            f"/history/compare?left={left_id}&right={right_id}",
            headers={"X-Session-ID": session_id},
        )
        payload = response.get_json()

        assert response.status_code == 200
        assert payload["left_run_id"] == left_id
        assert payload["right_run_id"] == right_id
        assert payload["left"]["workflow_execution_id"] == execution_id
        assert payload["left"]["workflow_step_id"] == "scan"
        assert payload["right"]["workflow_execution_id"] == execution_id
        assert payload["right"]["workflow_step_id"] == "verify"
        assert payload["left"]["workflow_execution"]["workflow_id"] == "workflow-1"
        assert payload["right"]["workflow_execution"]["workflow_id"] == "workflow-1"
        assert payload["objects"]["findings"]["added"] == []
        assert payload["objects"]["findings"]["removed"] == []
        changed = payload["objects"]["findings"]["changed"]
        assert len(changed) == 4
        assert all(item["changed_fields"] == ["severity"] for item in changed)
        changed_by_line = {item["before"]["raw_line"]: item for item in changed}
        bracketed = changed_by_line["[low] exposed service"]
        assert bracketed["before"]["severity"] == "low"
        assert bracketed["before"]["compare_line_index"] == 0
        assert bracketed["after"]["severity"] == "high"
        assert bracketed["after"]["compare_line_index"] == 0

        reversed_response = client.get(
            f"/history/compare?left={right_id}&right={left_id}",
            headers={"X-Session-ID": session_id},
        )
        reversed_payload = reversed_response.get_json()
        assert reversed_response.status_code == 200
        assert reversed_payload["left_run_id"] == right_id
        assert reversed_payload["right_run_id"] == left_id
        reversed_changed = {
            item["before"]["raw_line"]: item
            for item in reversed_payload["objects"]["findings"]["changed"]
        }
        assert reversed_changed["[high] exposed service"]["before"]["severity"] == "high"
        assert reversed_changed["[high] exposed service"]["after"]["severity"] == "low"
    finally:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM workflow_execution_steps WHERE execution_id = ?", (execution_id,))
            conn.execute("DELETE FROM workflow_executions WHERE id = ?", (execution_id,))
            conn.executemany("DELETE FROM findings WHERE id = ?", [(finding_id,) for finding_id in finding_ids])
            conn.executemany("DELETE FROM runs WHERE id = ?", [(left_id,), (right_id,)])
            conn.commit()


def test_compare_routes_resolve_real_team_scope_without_leaking_subordinate_rows():
    from services.teams.storage import add_team_member, create_team, soft_remove_team_member

    personal_session = f"compare-personal-{uuid.uuid4().hex[:8]}"
    owner_session = f"tok_compare-owner-{uuid.uuid4().hex[:8]}"
    team_session = f"tok_compare-operator-{uuid.uuid4().hex[:8]}"
    left_id = f"run-team-left-{uuid.uuid4().hex[:8]}"
    right_id = f"run-team-right-{uuid.uuid4().hex[:8]}"
    hidden_personal_run_id = f"run-personal-hidden-{uuid.uuid4().hex[:8]}"
    hidden_team_run_id = f"run-team-hidden-{uuid.uuid4().hex[:8]}"
    project_id = f"project-team-{uuid.uuid4().hex[:8]}"
    valid_execution_id = f"wfx-team-{uuid.uuid4().hex[:8]}"
    hidden_execution_id = f"wfx-hidden-{uuid.uuid4().hex[:8]}"
    mismatched_finding_ids = [f"finding-mismatched-{uuid.uuid4().hex[:8]}" for _index in range(2)]
    client = make_test_app().test_client()
    team_id = ""
    operator_member_id = ""
    recorded_finding_ids: list[str] = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            team = create_team(
                conn,
                name=f"Comparison team {uuid.uuid4().hex[:8]}",
                creator_session_token=owner_session,
            )
            team_id = str(team["id"])
            operator = add_team_member(
                conn,
                team_id=team_id,
                session_token=team_session,
                role="operator",
            )
            operator_member_id = str(operator["id"])
            conn.executemany(
                "INSERT INTO session_tokens (token, created) VALUES (?, '2026-07-13T09:00:00Z')",
                [(owner_session,), (team_session,)],
            )
            conn.executemany(
                "INSERT INTO runs "
                "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                "output_preview, output_line_count) "
                "VALUES (?, ?, ?, 'external', 'scanner darklab.sh', ?, ?, 0, ?, 1)",
                [
                    (
                        left_id,
                        team_session,
                        team_id,
                        "2026-07-13T10:00:00Z",
                        "2026-07-13T10:00:01Z",
                        json.dumps([{
                            "text": "[low] scoped finding",
                            "line_index": 0,
                            "signals": ["findings"],
                        }]),
                    ),
                    (
                        right_id,
                        team_session,
                        team_id,
                        "2026-07-13T11:00:00Z",
                        "2026-07-13T11:00:01Z",
                        json.dumps([{
                            "text": "[high] scoped finding",
                            "line_index": 0,
                            "signals": ["findings"],
                        }]),
                    ),
                    (
                        hidden_personal_run_id,
                        personal_session,
                        "",
                        "2026-07-13T10:30:00Z",
                        "2026-07-13T10:30:01Z",
                        json.dumps([{"text": "personal hidden", "line_index": 0}]),
                    ),
                    (
                        hidden_team_run_id,
                        team_session,
                        "other-team",
                        "2026-07-13T10:45:00Z",
                        "2026-07-13T10:45:01Z",
                        json.dumps([{"text": "other team hidden", "line_index": 0}]),
                    ),
                ],
            )
            left_entries = json.loads(conn.execute(
                "SELECT output_preview FROM runs WHERE id = ?",
                (left_id,),
            ).fetchone()["output_preview"])
            right_entries = json.loads(conn.execute(
                "SELECT output_preview FROM runs WHERE id = ?",
                (right_id,),
            ).fetchone()["output_preview"])
            recorded_finding_ids.extend(
                item["id"] for item in record_run_findings(
                    conn,
                    team_session,
                    left_id,
                    left_entries,
                    team_id=team_id,
                )
            )
            recorded_finding_ids.extend(
                item["id"] for item in record_run_findings(
                    conn,
                    team_session,
                    right_id,
                    right_entries,
                    team_id=team_id,
                )
            )
            conn.executemany(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
                "VALUES (?, ?, ?, ?, ?, 'output', 4, 'test', '2026-07-13T11:00:00Z')",
                [
                    (f"artifact-{left_id}", team_session, left_id, "reports/left.txt", "left.txt"),
                    (f"artifact-{right_id}", team_session, right_id, "reports/right.txt", "right.txt"),
                    (
                        f"artifact-{hidden_personal_run_id}",
                        personal_session,
                        hidden_personal_run_id,
                        "reports/personal.txt",
                        "personal.txt",
                    ),
                ],
            )
            conn.executemany(
                "INSERT INTO findings "
                "(id, session_id, team_id, run_id, scope, severity, tool_root, title, raw_line, "
                "line_number, fingerprint, created) VALUES (?, ?, ?, ?, 'finding', 'critical', "
                "'scanner', 'hidden', '[critical] hidden', 0, ?, '2026-07-13T11:00:00Z')",
                [
                    (
                        mismatched_finding_ids[0],
                        personal_session,
                        "",
                        right_id,
                        mismatched_finding_ids[0],
                    ),
                    (
                        mismatched_finding_ids[1],
                        team_session,
                        "other-team",
                        right_id,
                        mismatched_finding_ids[1],
                    ),
                ],
            )
            conn.executemany(
                "INSERT INTO workflow_executions "
                "(id, session_id, team_id, workflow_id, workflow_source, title, status, current_step_id, "
                "created, updated) VALUES (?, ?, ?, 'deleted-workflow', 'user', ?, 'completed', 'scan', "
                "'2026-07-13T10:00:00Z', '2026-07-13T11:00:00Z')",
                [
                    (valid_execution_id, team_session, team_id, "Scoped workflow"),
                    (hidden_execution_id, team_session, "other-team", "Hidden workflow"),
                ],
            )
            conn.executemany(
                "INSERT INTO workflow_execution_steps "
                "(id, execution_id, step_id, step_index, run_id, status, exit_code, created) "
                "VALUES (?, ?, ?, ?, ?, 'completed', 0, '2026-07-13T10:00:00Z')",
                [
                    (f"step-{left_id}", valid_execution_id, "baseline", 0, left_id),
                    (f"step-{right_id}", valid_execution_id, "scan", 1, right_id),
                    (
                        f"step-hidden-{hidden_team_run_id}",
                        hidden_execution_id,
                        "hidden",
                        0,
                        hidden_team_run_id,
                    ),
                ],
            )
            conn.execute(
                "INSERT INTO projects "
                "(id, session_id, team_id, name, slug, created, updated) "
                "VALUES (?, ?, ?, 'Team comparison', ?, '2026-07-13T09:00:00Z', '2026-07-13T11:00:00Z')",
                (project_id, team_session, team_id, project_id),
            )
            conn.executemany(
                "INSERT INTO project_links "
                "(id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, 'run', ?, 'manual', ?)",
                [
                    (f"link-{left_id}", project_id, left_id, "2026-07-13T10:00:00Z"),
                    (f"link-{right_id}", project_id, right_id, "2026-07-13T11:00:00Z"),
                ],
            )
            conn.execute(
                "UPDATE workflow_executions SET project_id = ? WHERE id = ?",
                (project_id, valid_execution_id),
            )
            conn.commit()

        personal_headers = {"X-Session-ID": personal_session}
        team_headers = {"X-Session-ID": team_session, "X-Team-ID": team_id}
        compare_url = f"/history/compare?left={left_id}&right={right_id}"
        assert client.get(compare_url, headers=personal_headers).status_code == 404
        assert client.get(
            f"/history/compare/lines?left={left_id}&right={right_id}&side=a&start=0&end=1",
            headers=personal_headers,
        ).status_code == 404

        candidates = client.get(
            f"/history/{right_id}/compare-candidates",
            headers=team_headers,
        )
        assert candidates.status_code == 200
        assert [item["id"] for item in candidates.get_json()["candidates"]] == [left_id]

        response = client.get(compare_url, headers=team_headers)
        payload = response.get_json()
        assert response.status_code == 200
        assert payload["left"]["artifact_count"] == 1
        assert payload["right"]["artifact_count"] == 1
        assert payload["left"]["persisted_finding_count"] == 1
        assert payload["right"]["persisted_finding_count"] == 1
        assert payload["right"]["workflow_execution_id"] == valid_execution_id
        assert payload["right"]["workflow_step_id"] == "scan"
        assert payload["objects"]["findings"]["added"] == []
        assert payload["objects"]["findings"]["removed"] == []
        assert len(payload["objects"]["findings"]["changed"]) == 1
        assert "personal.txt" not in json.dumps(payload)
        assert "Hidden workflow" not in json.dumps(payload)
        assert "[critical] hidden" not in json.dumps(payload)

        project_response = client.get(
            f"/history/compare?project_id={project_id}",
            headers=team_headers,
        )
        assert project_response.status_code == 200
        assert project_response.get_json()["project_id"] == project_id
        assert {
            project_response.get_json()["left_run_id"],
            project_response.get_json()["right_run_id"],
        } == {left_id, right_id}

        lazy_response = client.get(
            f"/history/compare/lines?project_id={project_id}&side=b&start=0&end=1",
            headers=team_headers,
        )
        assert lazy_response.status_code == 200
        assert [line["text"] for line in lazy_response.get_json()["lines"]] == [
            "[high] scoped finding"
        ]

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            assert soft_remove_team_member(conn, operator_member_id)
            conn.commit()
        revoked = client.get(
            compare_url,
            headers=team_headers,
        )
        assert revoked.status_code == 403
    finally:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM workflow_execution_steps WHERE execution_id IN (?, ?)", (
                valid_execution_id,
                hidden_execution_id,
            ))
            conn.execute("DELETE FROM workflow_executions WHERE id IN (?, ?)", (
                valid_execution_id,
                hidden_execution_id,
            ))
            conn.execute("DELETE FROM project_links WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.executemany(
                "DELETE FROM findings WHERE id = ?",
                [(finding_id,) for finding_id in (*recorded_finding_ids, *mismatched_finding_ids)],
            )
            conn.execute("DELETE FROM run_file_artifacts WHERE run_id IN (?, ?, ?)", (
                left_id,
                right_id,
                hidden_personal_run_id,
            ))
            conn.executemany("DELETE FROM runs WHERE id = ?", [
                (left_id,),
                (right_id,),
                (hidden_personal_run_id,),
                (hidden_team_run_id,),
            ])
            if team_id:
                conn.execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
                conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
            conn.executemany(
                "DELETE FROM session_tokens WHERE token = ?",
                [(owner_session,), (team_session,)],
            )
            conn.commit()


def test_compare_candidates_only_include_older_completed_external_runs():
    session_id = f"compare-candidates-{uuid.uuid4().hex[:8]}"
    source_id = f"run-source-{uuid.uuid4().hex[:8]}"
    eligible_id = f"run-eligible-{uuid.uuid4().hex[:8]}"
    excluded_ids = [f"run-excluded-{uuid.uuid4().hex[:8]}" for _index in range(3)]
    client = make_test_app().test_client()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany(
                "INSERT INTO runs "
                "(id, session_id, run_kind, command, started, finished, exit_code, output_preview) "
                "VALUES (?, ?, ?, 'scanner darklab.sh', ?, ?, 0, '[]')",
                [
                    (source_id, session_id, "external", "2026-07-13T12:00:00Z", "2026-07-13T12:00:01Z"),
                    (eligible_id, session_id, "external", "2026-07-13T11:00:00Z", "2026-07-13T11:00:01Z"),
                    (excluded_ids[0], session_id, "builtin", "2026-07-13T10:00:00Z", "2026-07-13T10:00:01Z"),
                    (excluded_ids[1], session_id, "external", "2026-07-13T09:00:00Z", None),
                    (excluded_ids[2], session_id, "external", "2026-07-13T13:00:00Z", "2026-07-13T13:00:01Z"),
                ],
            )
            conn.commit()

        response = client.get(
            f"/history/{source_id}/compare-candidates",
            headers={"X-Session-ID": session_id},
        )
        payload = response.get_json()
        assert response.status_code == 200
        assert [item["id"] for item in payload["candidates"]] == [eligible_id]
        assert payload["suggested"]["id"] == eligible_id
    finally:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany(
                "DELETE FROM runs WHERE id = ?",
                [(source_id,), (eligible_id,), *((run_id,) for run_id in excluded_ids)],
            )
            conn.commit()
