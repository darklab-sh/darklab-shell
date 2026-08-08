# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Confirmed takeover finding persistence and fail-closed coverage."""

from __future__ import annotations

import json
from unittest import mock
import uuid

import pytest

from core.database import db_init
from core.database_access import get_db_connect
from services.assessments.dns_takeover_observations import normalize_dnsx_takeover_observation
from services.assessments.nuclei_takeover_command import reviewed_takeover_command_plan
from services.assessments.nuclei_takeover_observations import normalize_nuclei_takeover_observation
from services.assessments.nuclei_takeover_templates import reviewed_nuclei_takeover_launch
from services.assessments.takeover_finding_materialization import materialize_takeover_confirmation
from services.atlas.materializer import upsert_entity
from services.projects.crud import create_project
from services.projects.utils import now
from services.runs.finalization import save_completed_run
from services.runs.finalization_takeover import materialize_takeover_confirmation_for_finalize


@pytest.fixture(scope="module", autouse=True)
def _initialize_takeover_finding_schema():
    db_init()


def _seed_takeover_evidence(
    *,
    link_target_run: bool = True,
    nuclei_timestamp: str = "2026-08-07T22:02:00Z",
):
    suffix = uuid.uuid4().hex[:12]
    session_id = f"tok_takeover_{suffix}"
    project = create_project(session_id, {"name": f"Takeover {suffix}"})
    assert project is not None
    project_id = str(project["id"])
    source_run_id = f"run_dns_source_{suffix}"
    target_run_id = f"run_dns_target_{suffix}"
    nuclei_run_id = f"run_nuclei_{suffix}"
    hostname = f"app-{suffix}.example.test"
    provider_target = f"tenant-{suffix}.github.io"
    source = normalize_dnsx_takeover_observation({
        "host": hostname,
        "cname": [provider_target],
        "status_code": "NOERROR",
        "timestamp": "2026-08-07T22:00:00Z",
    }, command="dnsx -d example.test -cname -json", source_run_id=source_run_id)
    target = normalize_dnsx_takeover_observation({
        "host": provider_target,
        "status_code": "NXDOMAIN",
        "timestamp": "2026-08-07T22:01:00Z",
    }, command=f"dnsx -d {provider_target} -a -aaaa -cname -json", source_run_id=target_run_id)
    reviewed = reviewed_nuclei_takeover_launch()
    nuclei = normalize_nuclei_takeover_observation({
        "template-id": reviewed.template.template_id,
        "matched-at": f"https://{hostname}",
        "timestamp": nuclei_timestamp,
    }, source_run_id=nuclei_run_id, template=reviewed.template)
    plan = reviewed_takeover_command_plan("domain", hostname)
    assert source is not None and target is not None and nuclei is not None and plan is not None
    source_entry = {"line_index": 2, "source_detail": {"takeover_observations": [source]}}
    target_entry = {"line_index": 3, "source_detail": {"takeover_observations": [target]}}
    nuclei_entry = {"line_index": 4, "source_detail": {"nuclei_takeover_observations": [nuclei]}}
    started = "2026-08-07T22:00:00+00:00"
    with get_db_connect()() as conn:
        conn.executemany(
            "INSERT INTO runs (id, session_id, team_id, run_kind, command, started, finished, "
            "exit_code, output_preview, output_line_count) VALUES (?, ?, '', 'external', ?, ?, ?, 0, ?, 5)",
            (
                (source_run_id, session_id, "dnsx -d example.test -cname -json", started,
                 "2026-08-07T22:00:01+00:00", json.dumps([source_entry])),
                (target_run_id, session_id, f"dnsx -d {provider_target} -a -aaaa -cname -json", started,
                 "2026-08-07T22:01:01+00:00", json.dumps([target_entry])),
                (nuclei_run_id, session_id, plan.command, started,
                 "2026-08-07T22:02:01+00:00", json.dumps([nuclei_entry])),
            ),
        )
        linked_runs = [source_run_id, nuclei_run_id]
        if link_target_run:
            linked_runs.append(target_run_id)
        conn.executemany(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', ?, 'manual', ?)",
            [(f"plr_{uuid.uuid4().hex[:16]}", project_id, run_id, now()) for run_id in linked_runs],
        )
        entity_id = upsert_entity(
            conn, session_id, "domain", hostname,
            seen_at="2026-08-07T22:02:00+00:00",
        )
        conn.execute(
            "INSERT INTO entity_run_links "
            "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
            "VALUES (?, ?, ?, ?, 1)",
            (entity_id, nuclei_run_id, started, "2026-08-07T22:02:00+00:00"),
        )
        conn.commit()
    return {
        "session_id": session_id,
        "project_id": project_id,
        "run_id": nuclei_run_id,
        "hostname": hostname,
        "command": plan.command,
        "entry": nuclei_entry,
    }


def test_takeover_confirmation_materializes_one_active_finding_with_three_evidence_lines():
    seeded = _seed_takeover_evidence()
    with get_db_connect()() as conn:
        first = materialize_takeover_confirmation(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            seeded["command"], 0, [seeded["entry"]],
        )
        second = materialize_takeover_confirmation(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            seeded["command"], 0, [seeded["entry"]],
        )
        assert first is not None and second is not None
        assert first["id"] == second["id"]
        assert first["created_now"] is True
        assert second["created_now"] is False
        assert first["validation_method"] == "active_confirmation"
        assert first["severity"] == "high"
        assert first["title"] == f"Subdomain takeover confirmed for {seeded['hostname']}"
        assert first["confirmation_id"].startswith("ntc_")
        row = conn.execute(
            "SELECT occurrence_count, first_run_id, last_run_id FROM findings WHERE id = ?",
            (first["id"],),
        ).fetchone()
        assert dict(row) == {
            "occurrence_count": 1,
            "first_run_id": seeded["run_id"],
            "last_run_id": seeded["run_id"],
        }
        links = conn.execute(
            "SELECT evidence_type, evidence_id, line_number, snippet "
            "FROM finding_evidence_links WHERE finding_id = ? ORDER BY evidence_id",
            (first["id"],),
        ).fetchall()
        assert len(links) == 3
        assert {row["evidence_type"] for row in links} == {"run_line"}
        assert {int(row["line_number"]) for row in links} == {2, 3, 4}
        assert all(seeded["hostname"] not in row["snippet"] or "secret" not in row["snippet"] for row in links)


def test_takeover_confirmation_rejects_missing_dns_scope_failed_runs_and_command_drift():
    missing = _seed_takeover_evidence(link_target_run=False)
    with get_db_connect()() as conn:
        assert materialize_takeover_confirmation(
            conn, missing["session_id"], "", missing["project_id"], missing["run_id"],
            missing["command"], 0, [missing["entry"]],
        ) is None
    seeded = _seed_takeover_evidence()
    with get_db_connect()() as conn:
        assert materialize_takeover_confirmation(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            seeded["command"], 1, [seeded["entry"]],
        ) is None
        assert materialize_takeover_confirmation(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            seeded["command"] + " -tags takeover", 0, [seeded["entry"]],
        ) is None
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM findings WHERE session_id = ?",
            (seeded["session_id"],),
        ).fetchone()["count"] == 0
    stale = _seed_takeover_evidence(nuclei_timestamp="2026-08-09T22:02:00Z")
    with get_db_connect()() as conn:
        assert materialize_takeover_confirmation(
            conn, stale["session_id"], "", stale["project_id"], stale["run_id"],
            stale["command"], 0, [stale["entry"]],
        ) is None


def test_completed_run_finalization_materializes_the_confirmed_takeover_finding():
    seeded = _seed_takeover_evidence()
    with get_db_connect()() as conn:
        conn.execute(
            "DELETE FROM project_links WHERE project_id = ? AND entity_type = 'run' AND entity_id = ?",
            (seeded["project_id"], seeded["run_id"]),
        )
        conn.execute("DELETE FROM entity_run_links WHERE run_id = ?", (seeded["run_id"],))
        conn.execute("DELETE FROM runs WHERE id = ?", (seeded["run_id"],))
        conn.commit()

    class Capture:
        preview_lines = [seeded["entry"]]
        preview_truncated = False
        output_line_count = 5
        full_output_available = False
        full_output_truncated = False
        full_output_bytes = 0
        artifact_rel_path = None

        def finalize(self):
            return None

    summary: dict[str, object] = {}
    link = save_completed_run(
        seeded["run_id"], seeded["session_id"], "", seeded["command"],
        "2026-08-07T22:02:00+00:00", "2026-08-07T22:02:01+00:00", 0, Capture(),
        link_project_id=seeded["project_id"], finalize_summary=summary,
    )
    assert link is not None and link["project_id"] == seeded["project_id"]
    assert summary["finding_count"] == 1
    with get_db_connect()() as conn:
        finding = conn.execute(
            "SELECT validation_method, title FROM findings WHERE session_id = ?",
            (seeded["session_id"],),
        ).fetchone()
        assert dict(finding) == {
            "validation_method": "active_confirmation",
            "title": f"Subdomain takeover confirmed for {seeded['hostname']}",
        }


def test_takeover_finalize_failure_rolls_back_its_savepoint_and_keeps_the_run_path_safe():
    seeded = _seed_takeover_evidence()
    recorded_findings: list[dict[str, object]] = []

    def fail_after_write(conn, *_args):
        conn.execute(
            "UPDATE projects SET name = 'unsafe partial write' WHERE id = ?",
            (seeded["project_id"],),
        )
        raise RuntimeError("materialization failed")

    with get_db_connect()() as conn, \
         mock.patch("services.runs.finalization_takeover.app_metrics.record_run_finalize_error") as metric, \
         mock.patch("services.runs.finalization_takeover.log.error") as error_log:
        result = materialize_takeover_confirmation_for_finalize(
            conn,
            seeded["session_id"],
            "",
            seeded["run_id"],
            seeded["command"],
            0,
            [seeded["entry"]],
            {"project_id": seeded["project_id"]},
            recorded_findings,
            materialize_takeover_confirmation_fn=fail_after_write,
        )
        project_name = conn.execute(
            "SELECT name FROM projects WHERE id = ?", (seeded["project_id"],),
        ).fetchone()["name"]

    assert result is None
    assert recorded_findings == []
    assert project_name != "unsafe partial write"
    metric.assert_called_once_with("takeover_confirmation")
    assert error_log.call_args.args == ("TAKEOVER_CONFIRMATION_FINALIZE_ERROR",)
    assert error_log.call_args.kwargs["extra"]["error_class"] == "RuntimeError"
