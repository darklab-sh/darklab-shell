# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed Dalfox finding persistence and fail-closed coverage."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any
from unittest import mock
import uuid

import pytest

from core.database import db_init
from core.database_access import get_db_connect
from services.assessments.dalfox_parameter_evidence import ReviewedDalfoxParameterEvidence
from services.assessments.dalfox_parameter_observations import (
    DALFOX_DISCOVERY_PARSER_VERSION,
    DalfoxParameterObservationState,
)
from services.assessments.dalfox_xss_command import reviewed_dalfox_xss_command_plan
from services.assessments.dalfox_xss_finding_materialization import (
    materialize_dalfox_xss_findings,
)
from services.assessments.dalfox_xss_observations import DalfoxXssObservationState
from services.atlas.materializer import upsert_entity
from services.projects.crud import create_project
from services.projects.links import link_run_to_project_on_conn
from services.runs.finalization import save_completed_run
from services.runs.finalization_dalfox_xss import materialize_dalfox_xss_findings_for_finalize
from services.runs.output_model import LineEntity, LineEvent, LineSignal, to_wire


@pytest.fixture(scope="module", autouse=True)
def _initialize_dalfox_xss_finding_schema():
    db_init()


def _seed_reviewed_xss(*, seed_active_run: bool = True) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:12]
    session_id = f"tok_dalfox_xss_{suffix}"
    project = create_project(session_id, {"name": f"Dalfox XSS {suffix}"})
    assert project is not None
    project_id = str(project["id"])
    source_run_id = f"run_dalfox_discovery_{suffix}"
    active_run_id = f"run_dalfox_xss_{suffix}"
    target = f"https://app-{suffix}.example.test/search?q=one"
    source_command = (
        f"dalfox {target} --only-discovery --skip-mining-dict --format jsonl --no-color"
    )
    source_state = DalfoxParameterObservationState(source_command, source_run_id)
    source_lines = [
        json.dumps({"meta": {
            "dalfox_version": "v3.1.2",
            "mode": "only_discovery",
            "params_discovered": 1,
        }}),
        json.dumps({"url": target, "param": "q", "location": "Query"}),
    ]
    source_details = [source_state.metadata(line)["source_detail"] for line in source_lines]
    source_entries = [
        to_wire(LineEvent(text=line, line_index=index, source_detail=source_details[index]))
        for index, line in enumerate(source_lines)
    ]
    observation_id = str(
        source_details[1]["parameter_observations"][0]["observation_id"]
    )
    evidence = ReviewedDalfoxParameterEvidence(
        source_run_id=source_run_id,
        observation_id=observation_id,
        target=target,
        parameter="q",
        location="Query",
        tool_version="v3.1.2",
        parser_version=DALFOX_DISCOVERY_PARSER_VERSION,
    )
    plan = reviewed_dalfox_xss_command_plan(evidence)
    assert plan is not None
    context = evidence.xss_context(request_limit=int(plan.request_limit or 0))
    active_state = DalfoxXssObservationState(plan.command, active_run_id, context)
    active_lines = [
        json.dumps({"meta": {
            "dalfox_version": "v3.1.2",
            "targets": [target],
            "findings_count": 3,
            "total_requests": 80,
            "scan_duration_ms": 2500,
        }}),
        json.dumps({
            "type": "V", "method": "GET", "param": "q",
            "payload": "secret-confirmed-payload", "evidence": "browser execution proof",
            "cwe": "CWE-79", "inject_type": "inHTML-double",
        }),
        json.dumps({
            "type": "A", "method": "GET", "param": "q",
            "payload": "secret-ast-payload", "evidence": "AST execution path",
            "cwe": "CWE-79", "inject_type": "inJS-double",
        }),
        json.dumps({
            "type": "R", "method": "GET", "param": "q",
            "payload": "secret-reflection-payload", "evidence": "reflected response marker",
            "cwe": "CWE-79", "inject_type": "inHTML-none",
        }),
    ]
    url_entity = LineEntity("url", target, target, "high")
    active_entries = []
    for index, line in enumerate(active_lines):
        metadata = active_state.metadata(line)
        signals = (LineSignal.findings,) if index else ()
        active_entries.append(to_wire(LineEvent(
            text=line,
            line_index=index,
            signals=signals,
            entities=(url_entity,),
            source_detail=dict(metadata.get("source_detail") or {}),
        )))
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO runs (id, session_id, team_id, run_kind, command, started, finished, "
            "exit_code, output_preview, output_line_count) "
            "VALUES (?, ?, '', 'external', ?, ?, ?, 0, ?, ?)",
            (
                source_run_id, session_id, source_command,
                "2026-08-08T10:00:00+00:00", "2026-08-08T10:00:01+00:00",
                json.dumps(source_entries), len(source_entries),
            ),
        )
        link_run_to_project_on_conn(conn, session_id, project_id, source_run_id)
        if seed_active_run:
            conn.execute(
                "INSERT INTO runs (id, session_id, team_id, run_kind, command, started, finished, "
                "exit_code, output_preview, output_line_count) "
                "VALUES (?, ?, '', 'external', ?, ?, ?, 0, ?, ?)",
                (
                    active_run_id, session_id, plan.command,
                    "2026-08-08T10:01:00+00:00", "2026-08-08T10:01:01+00:00",
                    json.dumps(active_entries), len(active_entries),
                ),
            )
            link_run_to_project_on_conn(conn, session_id, project_id, active_run_id)
            entity_id = upsert_entity(
                conn, session_id, "url", target, seen_at="2026-08-08T10:01:01+00:00",
            )
            conn.execute(
                "INSERT INTO entity_run_links "
                "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                "VALUES (?, ?, ?, ?, 1)",
                (
                    entity_id, active_run_id,
                    "2026-08-08T10:01:01+00:00", "2026-08-08T10:01:01+00:00",
                ),
            )
        conn.commit()
    return {
        "session_id": session_id,
        "project_id": project_id,
        "source_run_id": source_run_id,
        "run_id": active_run_id,
        "target": target,
        "command": plan.command,
        "entries": active_entries,
    }


def test_reviewed_xss_observations_materialize_separate_safe_idempotent_findings():
    seeded = _seed_reviewed_xss()
    with get_db_connect()() as conn:
        first = materialize_dalfox_xss_findings(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            seeded["command"], 0, seeded["entries"],
        )
        second = materialize_dalfox_xss_findings(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            seeded["command"], 0, seeded["entries"],
        )
        assert len(first) == len(second) == 3
        assert {item["id"] for item in first} == {item["id"] for item in second}
        assert all(item["created_now"] for item in first)
        assert not any(item["created_now"] for item in second)
        assert {
            (item["validation_method"], item["severity"], item["confidence"])
            for item in first
        } == {
            ("active_confirmation", "high", "high"),
            ("captured_observation", "medium", "medium"),
            ("captured_observation", "low", "low"),
        }
        assert all(item["cwe_ids"] == ["CWE-79"] for item in first)
        rows = conn.execute(
            "SELECT raw_line, occurrence_count FROM findings WHERE session_id = ?",
            (seeded["session_id"],),
        ).fetchall()
        assert len(rows) == 3
        assert all(row["occurrence_count"] == 1 for row in rows)
        assert all("secret-" not in row["raw_line"] for row in rows)
        links = conn.execute(
            "SELECT finding_id, evidence_type, evidence_id FROM finding_evidence_links "
            "WHERE session_id = ?",
            (seeded["session_id"],),
        ).fetchall()
        assert len(links) == 6
        assert {row["evidence_type"] for row in links} == {"run", "run_line"}
        assert {row["evidence_id"] for row in links} == {
            seeded["source_run_id"], seeded["run_id"],
        }


def test_reviewed_xss_materialization_rejects_drift_tampering_and_failed_runs():
    seeded = _seed_reviewed_xss()
    tampered = deepcopy(seeded["entries"])
    tampered[1]["source_detail"]["dalfox_xss_observations"][0]["confidence"] = "low"
    with get_db_connect()() as conn:
        assert materialize_dalfox_xss_findings(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            seeded["command"], 1, seeded["entries"],
        ) == []
        assert materialize_dalfox_xss_findings(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            seeded["command"] + " --deep-scan", 0, seeded["entries"],
        ) == []
        assert materialize_dalfox_xss_findings(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            seeded["command"], 0, tampered,
        ) == []
        assert materialize_dalfox_xss_findings(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            seeded["command"], 0, seeded["entries"][:-1],
        ) == []
        assert materialize_dalfox_xss_findings(
            conn, seeded["session_id"], "", "prj_missing", seeded["run_id"],
            seeded["command"], 0, seeded["entries"],
        ) == []
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM findings WHERE session_id = ?",
            (seeded["session_id"],),
        ).fetchone()["count"]
        assert count == 0
        protected_command = seeded["command"] + " --config /tmp/reviewed-http.yaml"
        conn.execute(
            "UPDATE runs SET command = ? WHERE id = ?",
            (protected_command, seeded["run_id"]),
        )
        assert len(materialize_dalfox_xss_findings(
            conn, seeded["session_id"], "", seeded["project_id"], seeded["run_id"],
            protected_command, 0, seeded["entries"],
        )) == 3


def test_completed_run_materializes_reviewed_xss_findings_without_raw_duplicates():
    seeded = _seed_reviewed_xss(seed_active_run=False)

    class Capture:
        preview_lines = seeded["entries"]
        preview_truncated = False
        output_line_count = len(seeded["entries"])
        full_output_available = False
        full_output_truncated = False
        full_output_bytes = 0
        artifact_rel_path = None

        def finalize(self):
            return None

    summary: dict[str, object] = {}
    link = save_completed_run(
        seeded["run_id"], seeded["session_id"], "", seeded["command"],
        "2026-08-08T10:01:00+00:00", "2026-08-08T10:01:01+00:00", 0, Capture(),
        link_project_id=seeded["project_id"], finalize_summary=summary,
    )
    assert link is not None and link["project_id"] == seeded["project_id"]
    assert summary["finding_count"] == 3
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT tool_root, COUNT(*) AS count FROM findings WHERE session_id = ? "
            "GROUP BY tool_root",
            (seeded["session_id"],),
        ).fetchall()
        assert [dict(row) for row in rows] == [{"tool_root": "dalfox", "count": 3}]
        entity = conn.execute(
            "SELECT id FROM entities WHERE session_id = ? AND type = 'url' AND canonical_value = ?",
            (seeded["session_id"], seeded["target"]),
        ).fetchone()
        assert entity is not None


def test_dalfox_xss_finalize_failure_rolls_back_its_savepoint_and_keeps_run_safe():
    seeded = _seed_reviewed_xss()
    recorded_findings: list[dict[str, object]] = []

    def fail_after_write(conn, *_args):
        conn.execute(
            "UPDATE projects SET name = 'unsafe partial write' WHERE id = ?",
            (seeded["project_id"],),
        )
        raise RuntimeError("materialization failed")

    with get_db_connect()() as conn, \
         mock.patch(
             "services.runs.finalization_dalfox_xss.app_metrics.record_run_finalize_error"
         ) as metric, \
         mock.patch("services.runs.finalization_dalfox_xss.log.error") as error_log:
        result = materialize_dalfox_xss_findings_for_finalize(
            conn,
            seeded["session_id"],
            "",
            seeded["run_id"],
            seeded["command"],
            0,
            seeded["entries"],
            {"project_id": seeded["project_id"]},
            recorded_findings,
            materialize_dalfox_xss_findings_fn=fail_after_write,
        )
        project_name = conn.execute(
            "SELECT name FROM projects WHERE id = ?", (seeded["project_id"],),
        ).fetchone()["name"]

    assert result == []
    assert recorded_findings == []
    assert project_name != "unsafe partial write"
    metric.assert_called_once_with("dalfox_xss_findings")
    assert error_log.call_args.args == ("DALFOX_XSS_FINDINGS_FINALIZE_ERROR",)
    assert error_log.call_args.kwargs["extra"]["error_class"] == "RuntimeError"
