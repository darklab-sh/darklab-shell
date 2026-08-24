# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
CLI_SRC = ROOT_DIR / "tools" / "darklab_cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))


@pytest.fixture
def assessment_cli(monkeypatch):
    cli_main = import_module("darklab_cli.__main__")
    calls = []
    assessment = {
        "id": "asmt_cli",
        "status": "active",
        "profile_key": "network",
        "profile_version": "1",
        "title": "External assessment",
    }
    check = {
        "id": "asmc_cli",
        "state": "not_started",
        "state_source": "derived",
        "state_reason": "",
        "policy_level": "safe",
        "category": "discovery",
        "target_type": "domain",
        "target_value": "darklab.sh",
        "check_key": "network.port_discovery",
    }
    profile_summaries = [
        {
            "key": key,
            "version": "1.0",
            "label": label,
            "purpose": f"Run the maintained {label.lower()}.",
            "target_types": target_types,
            "check_count": check_count,
        }
        for key, label, target_types, check_count in (
            ("network", "Network assessment", ["domain", "ip"], 3),
            ("web", "Web assessment", ["domain", "ip", "url"], 9),
            ("api", "API assessment", ["url"], 1),
            ("tls", "TLS assessment", ["domain", "ip"], 2),
            ("combined", "Combined assessment", ["domain", "ip", "url"], 15),
        )
    ]

    class FakeClient:
        def __init__(self, config):
            self.team = config.team

        def request(self, method, path, *, params=None, body=None, **_kwargs):
            calls.append((method, path, params, body))
            if path == "/projects" and method == "GET":
                return {
                    "projects": [{
                        "id": "prj_cli", "slug": "assessment-project", "status": "active",
                    }],
                    "has_more": False,
                }
            if path == "/projects/prj_cli/assessments" and method == "GET":
                return {
                    "assessments": [] if (params or {}).get("status") == "completed" else [assessment],
                    "total": 0 if (params or {}).get("status") == "completed" else 1,
                    "limit": 50,
                    "offset": 0,
                    "has_more": False,
                    "profiles": profile_summaries,
                }
            if path == "/projects/prj_cli/assessments" and method == "POST":
                if self.team == "team_viewer":
                    raise cli_main.DarklabCliError(
                        "team_forbidden: denied",
                        status=403,
                        code="team_forbidden",
                    )
                created_assessment = {
                    **assessment,
                    "id": "asmt_created",
                    "profile_key": str((body or {}).get("profile_key") or ""),
                    "title": str((body or {}).get("title") or ""),
                }
                return {"ok": True, "assessment": created_assessment}
            if method == "PATCH" and "/checks/" not in path and path.startswith(
                "/projects/prj_cli/assessments/"
            ):
                assessment_id = path.rsplit("/", 1)[-1]
                if assessment_id == "asmt_pending":
                    raise cli_main.DarklabCliError(
                        "assessment_batch_cancellation_pending: pending",
                        status=409,
                        code="assessment_batch_cancellation_pending",
                        details={"batch_id": "abx_one", "batch_ids": ["abx_one", "abx_two"]},
                    )
                return {
                    "ok": True,
                    "assessment": {
                        **assessment,
                        "id": assessment_id,
                        "status": str((body or {}).get("status") or ""),
                    },
                }
            if path.endswith("/delete-preview") and method == "GET":
                assessment_id = path.split("/")[-2]
                can_delete = assessment_id != "asmt_active"
                return {
                    "preview": {
                        "assessment": {
                            **assessment,
                            "id": assessment_id,
                            "status": "archived" if can_delete else "active",
                        },
                        "can_delete": can_delete,
                        "requires_archived": True,
                        "will_delete": {
                            "assessments": 1,
                            "checks": 3,
                            "evidence_links": 2,
                            "available_evidence_links": 2,
                            "unavailable_evidence_links": 0,
                            "evidence_links_by_type": {"run": 2},
                            "schemathesis_reports": 0,
                            "schemathesis_operations": 0,
                            "reconciliation_observations": 0,
                            "reconciliation_matches": 0,
                        },
                        "source_records_deleted": False,
                    },
                }
            if path == "/projects/prj_cli/assessments/asmt_archived" and method == "DELETE":
                return {
                    "ok": True,
                    "deleted": {
                        "assessment": {
                            **assessment,
                            "id": "asmt_archived",
                            "status": "archived",
                        },
                        "can_delete": True,
                        "requires_archived": True,
                        "will_delete": {"assessments": 1, "checks": 3},
                        "source_records_deleted": False,
                    },
                }
            if path == "/projects/prj_cli/assessments/asmt_cli" and method == "GET":
                return {
                    "assessment": assessment,
                    "rollup": {
                        "applicable_checks": 1,
                        "covered_checks": 0,
                        "checks_awaiting_review": 0,
                        "untested_checks": 1,
                    },
                    "category_rollups": [],
                    "checks": {
                        "checks": [check],
                        "total": 1,
                        "limit": 50,
                        "offset": 0,
                        "has_more": False,
                    },
                }
            if path == "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli" and method == "PATCH":
                state = str((body or {}).get("state") or "")
                reason = str((body or {}).get("reason") or "")
                return {
                    "ok": True,
                    "check": {
                        **check,
                        "state": "not_started" if state == "not_started" else state,
                        "state_source": "derived" if state == "not_started" else "manual",
                        "state_reason": reason,
                    },
                }
            if path == (
                "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli/"
                "recommended-action"
            ):
                plan = {
                    "action": {"key": "command:nmap", "kind": "command", "id": "nmap"},
                    "target": {"type": "domain", "value": "darklab.sh"},
                    "policy_level": "standard",
                    "http_profile": {"name": "", "credential_use": "none"},
                    "display_command": "nmap --top-ports 100 darklab.sh",
                    "launchable": True,
                    "unavailable_reason": "",
                    "plan_digest": "a" * 64,
                }
                if method == "GET":
                    return {"plan": plan}
                if method == "POST":
                    return {
                        "plan": plan,
                        "run": {
                            "id": "run_cli_verification",
                            "status": "running",
                            "command": plan["display_command"],
                        },
                    }
            raise cli_main.DarklabCliError(f"unexpected request: {method} {path}")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)
    return SimpleNamespace(cli_main=cli_main, calls=calls)


def test_darklab_cli_assessment_lifecycle_commands(assessment_cli, capsys):
    cli_main = assessment_cli.cli_main
    calls = assessment_cli.calls
    try:
        cli_main.main(["assessment", "create", "--help"])
    except SystemExit as help_exit:
        assert help_exit.code == 0
    else:
        raise AssertionError("assessment create help did not exit")
    lifecycle_help = capsys.readouterr().out
    assert "PROFILE_KEY" in lifecycle_help
    assert "--title" in lifecycle_help
    assert "profile-version" not in lifecycle_help

    assert cli_main.main([
        "assessment", "create", "assessment-project", "combined",
        "--title", "CLI assessment",
    ]) == 0
    assert "asmt_created" in capsys.readouterr().out
    assert calls[-2:] == [
        ("GET", "/projects", {"limit": 100, "offset": 0}, None),
        (
            "POST",
            "/projects/prj_cli/assessments",
            None,
            {"profile_key": "combined", "title": "CLI assessment"},
        ),
    ]

    assert cli_main.main([
        "assessment", "create", "prj_cli", "network", "--format", "json",
    ]) == 0
    created_payload = json.loads(capsys.readouterr().out)
    assert created_payload["assessment"]["profile_key"] == "network"
    assert calls[-1] == (
        "POST", "/projects/prj_cli/assessments", None, {"profile_key": "network"},
    )

    assert cli_main.main([
        "assessment", "complete", "prj_cli", "asmt_cli", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["assessment"]["status"] == "completed"
    assert calls[-1] == (
        "PATCH",
        "/projects/prj_cli/assessments/asmt_cli",
        None,
        {"status": "completed"},
    )

    assert cli_main.main([
        "assessment", "archive", "prj_cli", "asmt_cli",
    ]) == 0
    assert "archived" in capsys.readouterr().out
    assert calls[-1] == (
        "PATCH",
        "/projects/prj_cli/assessments/asmt_cli",
        None,
        {"status": "archived"},
    )

    call_count = len(calls)
    assert cli_main.main([
        "assessment", "delete", "prj_cli", "asmt_archived",
    ]) == 0
    preview_output = capsys.readouterr().out
    assert "Assessment deletion preview" in preview_output
    assert "Source records preserved: yes" in preview_output
    assert "Preview only. Re-run with --confirm" in preview_output
    assert calls[call_count:] == [(
        "GET",
        "/projects/prj_cli/assessments/asmt_archived/delete-preview",
        None,
        None,
    )]

    call_count = len(calls)
    assert cli_main.main([
        "assessment", "delete", "prj_cli", "asmt_archived", "--confirm",
        "--format", "json",
    ]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["deleted"]["assessment"]["id"] == "asmt_archived"
    assert json.loads(captured.err)["preview"]["source_records_deleted"] is False
    assert calls[call_count:] == [
        (
            "GET",
            "/projects/prj_cli/assessments/asmt_archived/delete-preview",
            None,
            None,
        ),
        ("DELETE", "/projects/prj_cli/assessments/asmt_archived", None, None),
    ]

    call_count = len(calls)
    assert cli_main.main([
        "assessment", "delete", "prj_cli", "asmt_active", "--confirm",
    ]) == 1
    active_delete = capsys.readouterr()
    assert "archive this assessment first" in active_delete.out
    assert "must be archived" in active_delete.err
    assert calls[call_count:] == [(
        "GET",
        "/projects/prj_cli/assessments/asmt_active/delete-preview",
        None,
        None,
    )]

    assert cli_main.main([
        "assessment", "complete", "prj_cli", "asmt_pending",
    ]) == 1
    pending_error = capsys.readouterr().err
    assert "abx_one, abx_two" in pending_error
    assert "reach a terminal state" in pending_error
    assert "retry assessment complete" in pending_error

    assert cli_main.main([
        "--team", "team_viewer", "assessment", "create", "prj_cli", "network",
    ]) == 1
    permission_error = capsys.readouterr().err
    assert "MUTATE_PROJECTS capability" in permission_error


def test_darklab_cli_assessment_read_and_state_commands(assessment_cli, capsys):
    cli_main = assessment_cli.cli_main
    calls = assessment_cli.calls
    assert cli_main.main([
        "assessment",
        "list",
        "assessment-project",
        "--status",
        "archived",
    ]) == 0
    assert "asmt_cli" in capsys.readouterr().out
    assert calls[-2:] == [
        ("GET", "/projects", {"limit": 100, "offset": 0}, None),
        (
            "GET",
            "/projects/prj_cli/assessments",
            {"limit": 50, "offset": 0, "status": "archived", "include_archived": True},
            None,
        ),
    ]

    assert cli_main.main([
        "assessment",
        "list",
        "prj_cli",
        "--format",
        "json",
    ]) == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert [profile["key"] for profile in list_payload["profiles"]] == [
        "network",
        "web",
        "api",
        "tls",
        "combined",
    ]

    assert cli_main.main([
        "assessment", "list", "prj_cli", "--status", "completed",
    ]) == 0
    assert capsys.readouterr().out == "No results.\n"

    assert cli_main.main(["assessment", "show", "prj_cli", "asmt_cli"]) == 0
    show_output = capsys.readouterr().out
    assert "External assessment" in show_output
    assert "APPLICABLE CHECKS" in show_output
    assert calls[-1] == ("GET", "/projects/prj_cli/assessments/asmt_cli", None, None)

    assert cli_main.main([
        "assessment",
        "checks",
        "prj_cli",
        "asmt_cli",
        "--state",
        "not_started",
        "--policy-level",
        "safe",
        "--evidence-state",
        "none",
        "--target-type",
        "domain",
        "--category",
        "discovery",
    ]) == 0
    checks_output = capsys.readouterr().out
    assert "asmc_cli" in checks_output
    assert "darklab.sh" in checks_output
    assert calls[-1] == (
        "GET",
        "/projects/prj_cli/assessments/asmt_cli",
        {
            "limit": 50,
            "offset": 0,
            "category": "discovery",
            "state": "not_started",
            "target_type": "domain",
            "policy_level": "safe",
            "evidence_state": "none",
        },
        None,
    )

    assert cli_main.main([
        "assessment",
        "set-state",
        "prj_cli",
        "asmt_cli",
        "asmc_cli",
        "blocked",
        "--reason",
        "Waiting for authorization",
    ]) == 0
    assert "Waiting for authorization" in capsys.readouterr().out
    assert calls[-1] == (
        "PATCH",
        "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli",
        None,
        {"state": "blocked", "reason": "Waiting for authorization"},
    )

    assert cli_main.main([
        "assessment",
        "clear-state",
        "prj_cli",
        "asmt_cli",
        "asmc_cli",
        "--format",
        "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["check"]["state_source"] == "derived"
    assert calls[-1] == (
        "PATCH",
        "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli",
        None,
        {"state": "not_started", "reason": ""},
    )


def test_darklab_cli_assessment_recommended_action_commands(assessment_cli, capsys):
    cli_main = assessment_cli.cli_main
    calls = assessment_cli.calls
    assert cli_main.main([
        "assessment",
        "start-action",
        "prj_cli",
        "asmt_cli",
        "asmc_cli",
    ]) == 0
    preview_output = capsys.readouterr().out
    assert "command:nmap" in preview_output
    assert "Preview only. Re-run with --confirm" in preview_output
    assert calls[-1] == (
        "GET",
        "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli/recommended-action",
        None,
        None,
    )

    assert cli_main.main([
        "assessment",
        "start-action",
        "prj_cli",
        "asmt_cli",
        "asmc_cli",
        "--confirm",
    ]) == 0
    confirmed_output = capsys.readouterr().out
    assert confirmed_output.index("command:nmap") < confirmed_output.index("run_cli_verification")

    call_count = len(calls)
    assert cli_main.main([
        "assessment",
        "start-action",
        "prj_cli",
        "asmt_cli",
        "asmc_cli",
        "--http-profile-id",
        "htp_cli",
        "--source-run-id",
        "run_cli_source",
        "--parameter-observation-id",
        "dpx_cli",
        "--schema-artifact-id",
        "art_cli_schema",
        "--confirm",
        "--workspace-cwd",
        "evidence",
        "--format",
        "json",
    ]) == 0
    launched = json.loads(capsys.readouterr().out)
    assert launched["run"]["id"] == "run_cli_verification"
    assert calls[call_count:] == [
        (
            "GET",
            "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli/recommended-action",
            {
                "http_profile_id": "htp_cli",
                "source_run_id": "run_cli_source",
                "parameter_observation_id": "dpx_cli",
                "schema_artifact_id": "art_cli_schema",
            },
            None,
        ),
        (
            "POST",
            "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli/recommended-action",
            None,
            {
                "confirmed": True,
                "plan_digest": "a" * 64,
                "http_profile_id": "htp_cli",
                "source_run_id": "run_cli_source",
                "parameter_observation_id": "dpx_cli",
                "schema_artifact_id": "art_cli_schema",
                "workspace_cwd": "evidence",
            },
        ),
    ]


@pytest.fixture
def assessment_batch_cli(monkeypatch):
    cli_main = import_module("darklab_cli.__main__")
    calls = []
    digest = "b" * 64
    preview = {
        "schema_version": 1,
        "preview_id": "abp_cli",
        "project_id": "prj_cli",
        "assessment_id": "asmt_cli",
        "source_batch_id": "",
        "profile": {"key": "network", "version": "1"},
        "selection": {"include_standard": False, "item_limit": 128},
        "summary": {
            "selected_target_count": 1,
            "estimated_min_seconds": 10,
            "estimated_max_seconds": 60,
            "potential_covered_check_count": 2,
            "requires_standard_confirmation": False,
            "reason_counts": {"not_applicable": 1},
        },
        "plan_digest": digest,
        "candidate_item_count": 1,
        "selected_item_count": 1,
        "potential_covered_check_count": 2,
        "safe_item_count": 1,
        "standard_item_count": 0,
        "concurrency": {"batch": 8, "target": 1, "owner": 16, "instance": 32},
        "expires_at": "2026-08-17 12:15:00",
        "created": "2026-08-17 12:00:00",
    }
    item = {
        "item_index": 0,
        "execution_key": "c" * 64,
        "selected": True,
        "policy_level": "safe",
        "action": {"key": "command:nmap", "id": "nmap"},
        "target": {"entity_id": "ent_cli", "type": "ip", "value": "192.0.2.10"},
        "profile_identity": {"kind": "nmap", "id": "safe"},
        "bounds": {"summary": "One approved target."},
        "display_command": "nmap -sV 192.0.2.10",
        "public_plan_digest": "d" * 64,
        "public_plan": {},
        "duration_bound_seconds": 60,
        "check_mappings": [{"check_id": "asmc_cli"}],
    }
    progress = {
        "total": 1,
        "pending": 0,
        "launching": 0,
        "running": 0,
        "succeeded": 1,
        "failed": 0,
        "unavailable": 0,
        "canceled": 0,
        "skipped": 0,
        "could_not_cancel": 0,
        "settled": 1,
        "status": "completed",
    }
    batch = {
        "schema_version": 1,
        "batch_id": "wfx_cli",
        "assessment_id": "asmt_cli",
        "project_id": "prj_cli",
        "preview_id": "abp_cli",
        "preview_digest": digest,
        "source_batch_id": "",
        "status": "completed",
        "item_count": 1,
        "chunk_count": 1,
        "concurrency": {"batch": 8, "target": 1, "owner": 16, "instance": 32},
        "progress": progress,
        "next_event_sequence": 3,
        "created": "2026-08-17 12:00:00",
        "updated": "2026-08-17 12:01:00",
        "finished": "2026-08-17 12:01:00",
        "failure_code": "",
    }
    retry_preview = {
        **preview,
        "preview_id": "abp_retry_cli",
        "source_batch_id": "wfx_cli",
        "summary": {
            **preview["summary"],
            "source_item_count": 1,
            "source_retry_eligible_item_count": 1,
            "source_succeeded_item_count": 0,
        },
    }
    retry_batch = {
        **batch,
        "batch_id": "wfx_retry_cli",
        "preview_id": "abp_retry_cli",
        "source_batch_id": "wfx_cli",
        "status": "running",
        "progress": {
            **progress,
            "pending": 1,
            "succeeded": 0,
            "settled": 0,
            "status": "running",
        },
        "finished": "",
    }
    event = {
        "batch_id": "wfx_cli",
        "sequence": 2,
        "event_type": "parent_completed",
        "chunk_index": None,
        "item_ordinal": None,
        "status": "completed",
        "reason_code": "",
        "run_id": "",
        "source_batch_id": "",
        "retry_batch_id": "",
        "details": {"succeeded": 1},
        "created": "2026-08-17 12:01:00",
    }

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, **_kwargs):
            calls.append((method, path, params, body))
            if path == "/projects":
                return {
                    "projects": [{"id": "prj_cli", "slug": "assessment-project", "status": "active"}],
                    "has_more": False,
                }
            if path.endswith("/batch-previews") and method == "POST":
                include_standard = bool((body or {}).get("include_standard"))
                if include_standard:
                    return {
                        "preview": {
                            **preview,
                            "selection": {**preview["selection"], "include_standard": True},
                            "standard_item_count": 1,
                            "summary": {
                                **preview["summary"],
                                "requires_standard_confirmation": True,
                            },
                        }
                    }
                return {"preview": preview}
            if path == "/projects/prj_cli/assessment-batches/wfx_cli/retry-previews":
                include_standard = bool((body or {}).get("include_standard"))
                if include_standard:
                    return {
                        "preview": {
                            **retry_preview,
                            "selection": {
                                **retry_preview["selection"],
                                "include_standard": True,
                            },
                            "standard_item_count": 1,
                            "summary": {
                                **retry_preview["summary"],
                                "requires_standard_confirmation": True,
                            },
                        }
                    }
                return {"preview": retry_preview}
            if path == "/assessment-batch-previews/abp_cli/items":
                return {
                    "schema_version": 1,
                    "preview_id": "abp_cli",
                    "items": [item],
                    "next_cursor": None,
                }
            if path == "/assessment-batch-previews/abp_retry_cli/items":
                return {
                    "schema_version": 1,
                    "preview_id": "abp_retry_cli",
                    "items": [item],
                    "next_cursor": None,
                }
            if path.endswith("/assessment-batches") and method == "POST":
                return {"batch": batch, "launch": {"status": "completed", "launched": 1}}
            if path == "/projects/prj_cli/assessment-batches":
                return {
                    "schema_version": 1,
                    "batches": [batch],
                    "next_cursor": "next_cli",
                    "has_more": True,
                }
            if path == "/assessment-batches/wfx_cli":
                return {"batch": batch}
            if path == "/projects/prj_cli/assessment-batches/wfx_cli/retry":
                return {
                    "batch": retry_batch,
                    "launch": {"status": "running", "launched": 1},
                }
            if path == "/assessment-batches/wfx_cli/items":
                return {
                    "schema_version": 1,
                    "batch_id": "wfx_cli",
                    "items": [{
                        "item_index": 0,
                        "status": "succeeded",
                        "attempt": 1,
                        "action_id": "nmap",
                        "target": item["target"],
                        "run_id": "run_cli",
                        "reason_code": "",
                    }],
                    "next_cursor": None,
                    "has_more": False,
                }
            if path == "/assessment-batches/wfx_cli/events":
                return {
                    "schema_version": 1,
                    "batch_id": "wfx_cli",
                    "events": [event],
                    "next_cursor": None,
                    "has_more": False,
                }
            if path == "/projects/prj_cli/assessment-batches/wfx_cli/cancel":
                return {"batch": {**batch, "status": "canceled"}, "signal_failures": 0}
            raise cli_main.DarklabCliError(f"unexpected request: {method} {path}")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)
    return SimpleNamespace(cli_main=cli_main, calls=calls, digest=digest)


def test_darklab_cli_assessment_batch_plan_command(assessment_batch_cli, capsys):
    cli_main = assessment_batch_cli.cli_main
    calls = assessment_batch_cli.calls
    assert cli_main.main([
        "assessment", "batch", "plan", "assessment-project", "asmt_cli",
        "--target", "ent_cli", "--category", "discovery",
    ]) == 0
    plan_output = capsys.readouterr().out
    assert "Assessment batch preview: abp_cli" in plan_output
    assert "nmap -sV 192.0.2.10" in plan_output
    assert calls[-2:] == [
        (
            "POST",
            "/projects/prj_cli/assessments/asmt_cli/batch-previews",
            None,
            {
                "target_entity_ids": ["ent_cli"],
                "excluded_target_entity_ids": [],
                "categories": ["discovery"],
                "excluded_categories": [],
                "include_standard": False,
                "item_limit": 128,
                "max_parallel": 8,
                "max_owner_parallel": 16,
                "max_instance_parallel": 32,
            },
        ),
        (
            "GET",
            "/assessment-batch-previews/abp_cli/items",
            {"cursor": 0, "limit": 100},
            None,
        ),
    ]



def test_darklab_cli_assessment_batch_start_command(assessment_batch_cli, capsys):
    cli_main = assessment_batch_cli.cli_main
    calls = assessment_batch_cli.calls
    digest = assessment_batch_cli.digest
    assert cli_main.main([
        "assessment", "batch", "start", "prj_cli", "asmt_cli",
        "--include-standard", "--confirm",
    ]) == 1
    assert "add --confirm-standard" in capsys.readouterr().err
    assert not any(call[0] == "POST" and call[1].endswith("/assessment-batches") for call in calls)

    assert cli_main.main([
        "assessment", "batch", "start", "prj_cli", "asmt_cli",
        "--include-standard", "--confirm", "--confirm-standard", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["batch"]["batch_id"] == "wfx_cli"
    assert calls[-1] == (
        "POST",
        "/projects/prj_cli/assessments/asmt_cli/assessment-batches",
        None,
        {
            "preview_id": "abp_cli",
            "plan_digest": digest,
            "confirmed": True,
            "standard_confirmed": True,
        },
    )



def test_darklab_cli_assessment_batch_read_commands(assessment_batch_cli, capsys):
    cli_main = assessment_batch_cli.cli_main
    calls = assessment_batch_cli.calls
    assert cli_main.main([
        "assessment", "batch", "list", "assessment-project", "--limit", "1",
    ]) == 0
    assert "wfx_cli" in capsys.readouterr().out
    assert calls[-1] == (
        "GET",
        "/projects/prj_cli/assessment-batches",
        {"assessment_id": None, "cursor": None, "limit": 1},
        None,
    )

    assert cli_main.main([
        "assessment", "batch", "show", "wfx_cli", "--items", "--events",
        "--item-cursor", "0", "--event-cursor", "1",
    ]) == 0
    show_output = capsys.readouterr().out
    assert "run_cli" in show_output
    assert "parent_completed" in show_output
    assert calls[-2:] == [
        ("GET", "/assessment-batches/wfx_cli/items", {"cursor": 0, "limit": 100}, None),
        ("GET", "/assessment-batches/wfx_cli/events", {"cursor": 1, "limit": 100}, None),
    ]

    assert cli_main.main(["assessment", "batch", "follow", "wfx_cli", "--cursor", "1"]) == 0
    follow_output = capsys.readouterr().out
    assert "[2]" in follow_output
    assert "Final status:" in follow_output



def test_darklab_cli_assessment_batch_cancel_command(assessment_batch_cli, capsys):
    cli_main = assessment_batch_cli.cli_main
    calls = assessment_batch_cli.calls
    assert cli_main.main(["assessment", "batch", "cancel", "wfx_cli"]) == 0
    assert "Preview only" in capsys.readouterr().out
    assert cli_main.main([
        "assessment", "batch", "cancel", "wfx_cli", "--confirm", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["batch"]["status"] == "canceled"
    assert calls[-1] == (
        "POST",
        "/projects/prj_cli/assessment-batches/wfx_cli/cancel",
        None,
        {},
    )

def test_darklab_cli_assessment_batch_retry_command(assessment_batch_cli, capsys):
    cli_main = assessment_batch_cli.cli_main
    calls = assessment_batch_cli.calls
    digest = assessment_batch_cli.digest
    retry_call_count = len(calls)
    assert cli_main.main([
        "assessment", "batch", "retry", "wfx_cli",
    ]) == 0
    retry_output = capsys.readouterr().out
    assert "Retry of: wfx_cli" in retry_output
    assert "Preview only" in retry_output
    assert calls[retry_call_count:] == [
        ("GET", "/assessment-batches/wfx_cli", None, None),
        (
            "POST",
            "/projects/prj_cli/assessment-batches/wfx_cli/retry-previews",
            None,
            {
                "target_entity_ids": [],
                "excluded_target_entity_ids": [],
                "categories": [],
                "excluded_categories": [],
                "include_standard": False,
                "item_limit": 128,
                "max_parallel": 8,
                "max_owner_parallel": 16,
                "max_instance_parallel": 32,
            },
        ),
        (
            "GET",
            "/assessment-batch-previews/abp_retry_cli/items",
            {"cursor": 0, "limit": 100},
            None,
        ),
    ]

    assert cli_main.main([
        "assessment", "batch", "retry", "wfx_cli",
        "--include-standard", "--confirm",
    ]) == 1
    assert "add --confirm-standard" in capsys.readouterr().err

    assert cli_main.main([
        "assessment", "batch", "retry", "wfx_cli",
        "--include-standard", "--confirm", "--confirm-standard", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["batch"]["batch_id"] == "wfx_retry_cli"
    assert calls[-1] == (
        "POST",
        "/projects/prj_cli/assessment-batches/wfx_cli/retry",
        None,
        {
            "preview_id": "abp_retry_cli",
            "plan_digest": digest,
            "confirmed": True,
            "standard_confirmed": True,
        },
    )



def test_darklab_cli_assessment_batch_follow_reports_resumable_interrupt(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")
    batch_reads = import_module("darklab_cli.commands.assessment_batch_reads")

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, **_kwargs):
            if path.endswith("/events"):
                return {
                    "events": [{
                        "sequence": 7,
                        "event_type": "item_started",
                        "created": "2026-08-17 12:00:00",
                        "status": "running",
                    }],
                    "has_more": False,
                    "next_cursor": None,
                }
            return {"batch": {"batch_id": "wfx_running", "status": "running"}}

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)
    monkeypatch.setattr(batch_reads.time, "sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    assert cli_main.main([
        "assessment", "batch", "follow", "wfx_running", "--cursor", "5",
    ]) == 130
    captured = capsys.readouterr()
    assert "[7]" in captured.out
    assert "--cursor 7" in captured.err


@pytest.mark.parametrize(
    ("batch", "expected"),
    [
        pytest.param({"status": "completed", "progress": {"succeeded": 2}}, 0, id="success"),
        pytest.param(
            {"status": "completed", "progress": {"succeeded": 1, "failed": 1}},
            "partial",
            id="partial",
        ),
        pytest.param(
            {"status": "canceled", "progress": {"canceled": 1}},
            "canceled",
            id="canceled",
        ),
        pytest.param({"status": "failed"}, 1, id="failed"),
    ],
)
def test_darklab_cli_assessment_batch_terminal_exit_codes(batch, expected):
    batch_reads = import_module("darklab_cli.commands.assessment_batch_reads")
    expected_code = {
        "partial": batch_reads.BATCH_PARTIAL_EXIT_CODE,
        "canceled": batch_reads.BATCH_CANCELED_EXIT_CODE,
    }.get(expected, expected)
    assert batch_reads._terminal_exit_code(batch) == expected_code


def test_darklab_cli_assessment_batch_follow_rejects_invalid_event_page(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")

    class BrokenClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, **_kwargs):
            return {"events": "not-a-page"}


    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", BrokenClient)
    assert cli_main.main([
        "assessment", "batch", "follow", "wfx_broken",
    ]) == 1
    assert "invalid event page" in capsys.readouterr().err
