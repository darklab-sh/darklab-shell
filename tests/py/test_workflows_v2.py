# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Focused compiler, capture, persistence, and route coverage for Workflows v2."""

from __future__ import annotations

import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, cast

import pytest

from conftest import make_test_app
from core.database import delete_run_artifacts
from core.database_access import get_db_connect
from services.runs.output_model import LineEntity, LineEvent, LineKind, LineNoiseKind, LineRole
from services.workflows.captures import WorkflowCaptureAccumulator
from services.workflows.collections import WorkflowCollectionAccumulator
from services.workflows.fanout import expand_collection_step
from services.workflows.fanout_policy import FanoutPolicy, normalize_fanout_policy
from services.workflows.fanout_checkpoint import checkpoint_from_payload, create_fanout_checkpoint
from services.workflows.compiler import (
    WorkflowDefinitionError,
    compile_execution_definition,
    compile_workflow_definition,
    normalize_workflow_input_value,
    render_step_command,
    render_step_display_command,
    resolve_workflow_inputs,
    workflow_private_values,
)
from services.workflows.contracts import WorkflowActiveExecutionLimitExceeded
from services.workflows.storage import (
    bind_step_run,
    cancel_execution,
    claim_step_for_launch,
    create_execution,
    finalize_run_step,
    get_execution,
    public_execution,
)
from services.runs.start import BrokeredRunStartResult


_PRIVATE_EXECUTION_FIELDS = {
    "session_id",
    "team_id",
    "definition_snapshot",
    "input_values",
    "variables",
    "workspace_cwd",
    "actor_member_id",
    "actor_role",
    "owner_client_id",
    "owner_tab_id",
}


def _assert_public_execution_payload(
    execution: dict[str, object],
    *private_values: str,
) -> None:
    assert not (_PRIVATE_EXECUTION_FIELDS & execution.keys())
    for step in cast(list[dict[str, object]], execution.get("steps") or []):
        assert "id" not in step
        assert "execution_id" not in step
    serialized = json.dumps(execution, sort_keys=True)
    for value in private_values:
        assert value not in serialized


def _v2_definition() -> dict[str, Any]:
    return {
        "version": 2,
        "id": "resolve_and_scan",
        "title": "Resolve and scan",
        "inputs": [
            {"id": "target", "type": "target", "required": True},
            {"id": "ports", "type": "port_set", "default": "80,443"},
        ],
        "steps": [
            {
                "id": "resolve",
                "cmd": "printf '%s\\n' {{target}}",
                "captures": [{"name": "resolved_ip", "source": "first_nonempty_line", "required": True}],
                "next": {"success": "scan", "failure": "stop"},
            },
            {
                "id": "scan",
                "cmd": "nmap -p {{ports}} {{resolved_ip}}",
                "next": {"codes": {"2": "complete"}, "success": "complete", "failure": "stop"},
            },
        ],
    }


def _team_scope_fixture() -> dict[str, object]:
    from services.teams.storage import add_team_member, create_team

    suffix = uuid.uuid4().hex
    owner_token = f"tok_workflow_owner_{suffix}"
    operator_token = f"tok_workflow_operator_{suffix}"
    viewer_token = f"tok_workflow_viewer_{suffix}"
    with get_db_connect()() as conn:
        team = create_team(
            conn,
            name=f"Workflow team {suffix[:8]}",
            creator_session_token=owner_token,
        )
        operator = add_team_member(
            conn,
            team_id=str(team["id"]),
            session_token=operator_token,
            role="operator",
        )
        viewer = add_team_member(
            conn,
            team_id=str(team["id"]),
            session_token=viewer_token,
            role="viewer",
        )
        created = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            "INSERT INTO session_tokens (token, created) VALUES (?, ?)",
            [(owner_token, created), (operator_token, created), (viewer_token, created)],
        )
        conn.commit()
    return {
        "team": team,
        "owner_token": owner_token,
        "operator_token": operator_token,
        "viewer_token": viewer_token,
        "operator": operator,
        "viewer": viewer,
    }


def test_legacy_definition_gets_snapshot_local_step_ids():
    definition = compile_execution_definition({
        "title": "Legacy",
        "inputs": [{"id": "host", "type": "host"}],
        "steps": [{"cmd": "ping {{host}}"}, {"cmd": "nc -z {{host}} 443"}],
    })

    assert definition["version"] == 1
    steps = cast(list[dict[str, object]], definition["steps"])
    assert [step["id"] for step in steps] == ["step_1", "step_2"]


def test_v2_compiler_rejects_forward_capture_references_and_cycles():
    forward = _v2_definition()
    forward["steps"][0]["cmd"] = "echo {{resolved_ip}}"
    with pytest.raises(WorkflowDefinitionError, match="available"):
        compile_workflow_definition(forward)

    branch_skip = _v2_definition()
    branch_skip["steps"] = [
        {
            "id": "start",
            "cmd": "true",
            "next": {"success": "use", "failure": "capture"},
        },
        {
            "id": "capture",
            "cmd": "printf '192.0.2.10\\n'",
            "captures": [{"name": "resolved_ip", "source": "first_nonempty_line"}],
            "next": {"success": "use", "failure": "stop"},
        },
        {
            "id": "use",
            "cmd": "nmap {{resolved_ip}}",
            "next": {"success": "complete", "failure": "stop"},
        },
    ]
    with pytest.raises(WorkflowDefinitionError, match="not available on every path"):
        compile_workflow_definition(branch_skip)

    cyclic = _v2_definition()
    cyclic["steps"][1]["next"] = {"success": "resolve"}
    with pytest.raises(WorkflowDefinitionError, match="cycles"):
        compile_workflow_definition(cyclic)


def test_v2_compiler_rejects_duplicate_variables_invalid_transitions_and_unreachable_steps():
    duplicate = _v2_definition()
    duplicate["inputs"].append({"id": "target", "type": "text"})
    with pytest.raises(WorkflowDefinitionError, match="duplicate definitions"):
        compile_workflow_definition(duplicate)

    duplicate_step = _v2_definition()
    duplicate_step["steps"][1]["id"] = "resolve"
    with pytest.raises(WorkflowDefinitionError, match="step ids must be unique"):
        compile_workflow_definition(duplicate_step)

    invalid_transition = _v2_definition()
    invalid_transition["steps"][0]["next"]["success"] = "missing_step"
    with pytest.raises(WorkflowDefinitionError, match="unknown step"):
        compile_workflow_definition(invalid_transition)

    unreachable = _v2_definition()
    unreachable["steps"][0]["next"] = {"success": "complete", "failure": "stop"}
    with pytest.raises(WorkflowDefinitionError, match="unreachable steps"):
        compile_workflow_definition(unreachable)


def test_v2_compiler_normalizes_and_rejects_duplicate_exact_exit_codes():
    definition = _v2_definition()
    definition["steps"][1]["next"]["codes"] = {"+02": "complete", "-0": "stop"}
    compiled = compile_workflow_definition(definition)
    compiled_steps = cast(list[dict[str, Any]], compiled["steps"])
    compiled_next = cast(dict[str, Any], compiled_steps[1]["next"])
    assert compiled_next["codes"] == {"2": "complete", "0": "stop"}

    duplicate = _v2_definition()
    duplicate["steps"][1]["next"]["codes"] = {"2": "complete", "02": "stop"}
    with pytest.raises(WorkflowDefinitionError, match="exit codes must be unique") as exc_info:
        compile_workflow_definition(duplicate)
    assert exc_info.value.field == "steps.1.next.codes"

    invalid = _v2_definition()
    invalid["steps"][1]["next"]["codes"] = {"two": "complete"}
    with pytest.raises(WorkflowDefinitionError, match="invalid workflow exit code") as exc_info:
        compile_workflow_definition(invalid)
    assert exc_info.value.field == "steps.1.next.codes"

    response = make_test_app().test_client().post(
        "/session/workflows",
        json=invalid,
        headers={"X-Session-ID": "workflow-exit-code-field-error"},
    )
    assert response.status_code == 400
    assert response.get_json()["errors"] == [{
        "field": "steps.1.next.codes",
        "message": "invalid workflow exit code 'two'",
    }]


def test_typed_inputs_are_canonicalized_and_rendered_as_shell_scalars():
    source = _v2_definition()
    source["inputs"][0]["sensitive"] = True
    definition = compile_execution_definition(source)
    inputs = resolve_workflow_inputs(definition, {"target": "Example.COM", "ports": "80, 8000-8002"})
    steps = cast(list[dict[str, object]], definition["steps"])
    command = render_step_command(steps[0], {**inputs, "target": "host; echo unsafe"})
    display_command = render_step_display_command(
        steps[0],
        definition,
        {**inputs, "target": "host; echo unsafe"},
    )
    capture_display_command = render_step_display_command(
        steps[1],
        definition,
        {**inputs, "resolved_ip": "192.0.2.44"},
    )

    assert inputs == {"target": "example.com", "ports": "80,8000-8002"}
    assert command == "printf '%s\\n' 'host; echo unsafe'"
    assert display_command == "printf '%s\\n' [redacted]"
    assert capture_display_command == "nmap -p 80,8000-8002 [captured:resolved_ip]"
    assert set(workflow_private_values(
        definition,
        {**inputs, "resolved_ip": "192.0.2.44"},
    )) == {"example.com", "192.0.2.44"}
    public_failure = public_execution({
        "definition_snapshot": definition,
        "variables": {**inputs, "resolved_ip": "192.0.2.44"},
        "failure_detail": "example.com failed after 192.0.2.44",
        "steps": [{"error_detail": "could not use 192.0.2.44"}],
    })
    assert public_failure["failure_detail"] == "[redacted] failed after [redacted]"
    assert public_failure["steps"][0]["error_detail"] == "could not use [redacted]"
    with pytest.raises(WorkflowDefinitionError, match="missing variables: target"):
        render_step_command(steps[0], {})
    with pytest.raises(WorkflowDefinitionError, match="missing variables: target"):
        render_step_display_command(steps[0], definition, {})


def test_typed_input_boundaries_reject_unsafe_paths_controls_and_sizes():
    assert normalize_workflow_input_value(
        {"id": "target", "type": "target"},
        "192.0.2.129/24",
    ) == "192.0.2.0/24"
    assert normalize_workflow_input_value(
        {"id": "path", "type": "workspace_path"},
        "reports/targets.txt",
    ) == "reports/targets.txt"
    assert normalize_workflow_input_value(
        {"id": "list", "type": "wordlist"},
        "/usr/share/wordlists/seclists/Discovery/DNS/common.txt",
    ) == "/usr/share/wordlists/seclists/Discovery/DNS/common.txt"

    invalid_values = (
        ({"id": "ports", "type": "port_set"}, "443,8000-7000"),
        ({"id": "path", "type": "workspace_path"}, "/tmp/targets.txt"),
        ({"id": "path", "type": "workspace_path"}, "../targets.txt"),
        ({"id": "list", "type": "wordlist"}, "/usr/share/wordlists/../shadow"),
        ({"id": "text", "type": "text"}, "unsafe\x00value"),
        ({"id": "text", "type": "text"}, "x" * 4097),
    )
    for definition, value in invalid_values:
        with pytest.raises(WorkflowDefinitionError):
            normalize_workflow_input_value(definition, value)


def test_capture_accumulator_ignores_noise_and_supports_entities_and_json_pointer():
    accumulator = WorkflowCaptureAccumulator([
        {"name": "line", "source": "first_nonempty_line", "required": True},
        {"name": "host", "source": "entity", "entity_type": "domain", "required": True},
        {"name": "port", "source": "json_pointer", "pointer": "/service/port", "required": True},
    ])
    accumulator.observe(LineEvent("50% done", role=LineRole.progress, noise_kind=LineNoiseKind.progress))
    accumulator.observe(LineEvent(
        "scan result",
        entities=(LineEntity("domain", "Example.COM", "example.com", "high"),),
    ))
    accumulator.observe(LineEvent('{"service":{"port":443}}'))

    values, error = accumulator.result()
    assert values == {"line": "scan result", "host": "example.com", "port": "443"}
    assert error == ""

    containing = WorkflowCaptureAccumulator([{
        "name": "answer",
        "source": "first_line_containing",
        "contains": "ANSWER=",
        "required": True,
    }])
    for role in (
        LineRole.prompt_echo,
        LineRole.progress,
        LineRole.status_line,
        LineRole.pty_marker,
        LineRole.exit_ok,
        LineRole.exit_fail,
    ):
        containing.observe(LineEvent("ANSWER=ignored", role=role))
    for noise_kind in LineNoiseKind:
        containing.observe(LineEvent("ANSWER=ignored", noise_kind=noise_kind))
    containing.observe(LineEvent("ANSWER=ignored", kind=LineKind.notice))
    containing.observe(LineEvent("prefix ANSWER=kept\r\n"))
    assert containing.result() == ({"answer": "prefix ANSWER=kept"}, "")

    json_pointer = WorkflowCaptureAccumulator([{
        "name": "escaped",
        "source": "json_pointer",
        "pointer": "/items/0/a~1b/~0key",
        "required": True,
    }])
    json_pointer.observe(LineEvent("not json"))
    json_pointer.observe(LineEvent('{"items":[{"a/b":{"~key":" recovered "}}]}'))
    assert json_pointer.result() == ({"escaped": "recovered"}, "")


def test_capture_accumulator_reports_required_misses_without_using_notices():
    accumulator = WorkflowCaptureAccumulator([
        {"name": "answer", "source": "first_line_containing", "contains": "ANSWER", "required": True},
    ])
    accumulator.observe(LineEvent("ANSWER from app", kind=LineKind.notice))

    assert accumulator.result() == ({}, "required captures were not found: answer")


def test_capture_accumulator_enforces_value_total_and_control_character_limits():
    boundary = WorkflowCaptureAccumulator([
        {"name": "result", "source": "first_nonempty_line", "required": True},
    ])
    boundary.observe(LineEvent("x" * 2048))
    assert boundary.result() == ({"result": "x" * 2048}, "")

    oversized = WorkflowCaptureAccumulator([
        {"name": "result", "source": "first_nonempty_line", "required": True},
    ])
    oversized.observe(LineEvent("x" * 2049))
    values, error = oversized.result()
    assert values == {}
    assert "capture result exceeds the value limit" in error
    assert "required captures were not found: result" in error

    total = WorkflowCaptureAccumulator([
        {"name": f"value_{index}", "source": "first_nonempty_line"}
        for index in range(5)
    ])
    total.observe(LineEvent("x" * 2048))
    values, error = total.result()
    assert len(values) == 4
    assert error == "workflow captures exceed the execution limit"

    controlled = WorkflowCaptureAccumulator([
        {"name": "result", "source": "first_nonempty_line"},
    ])
    controlled.observe(LineEvent("unsafe\x01value"))
    assert controlled.result() == ({}, "capture result contains control characters")


def test_collection_capture_accumulator_is_bounded_deduplicated_and_required():
    accumulator = WorkflowCollectionAccumulator([{
        "name": "hosts", "kind": "collection", "source": "json_pointer",
        "pointer": "/hosts", "item_limit": 2, "required": True,
    }])
    accumulator.observe(LineEvent('{"hosts":[" one ","two","two","three"]}'))
    assert accumulator.result() == ({"hosts": ["one", "two"]}, "")

    entities = WorkflowCollectionAccumulator([{
        "name": "domains", "mode": "collection", "source": "entity",
        "entity_type": "domain", "required": True,
    }])
    entities.observe(LineEvent(
        "entities",
        entities=(
            LineEntity("domain", "One.EXAMPLE", "one.example", "high"),
            LineEntity("domain", "Two.EXAMPLE", "two.example", "high"),
        ),
    ))
    assert entities.result() == ({"domains": ["one.example", "two.example"]}, "")

    missing = WorkflowCollectionAccumulator([{
        "name": "items", "kind": "collection", "source": "json_pointer",
        "pointer": "/items", "required": True,
    }])
    assert missing.result() == ({}, "required collection captures were not found: items")


def test_collection_capture_definitions_require_version_three_and_validate_limits():
    base = {
        "id": "collect_hosts",
        "title": "Collect hosts",
        "inputs": [],
        "steps": [{
            "id": "collect",
            "cmd": "echo hosts",
            "captures": [{
                "name": "hosts", "kind": "collection", "source": "json_pointer",
                "pointer": "/hosts", "item_limit": 4,
            }],
        }],
    }
    with pytest.raises(WorkflowDefinitionError, match="version 3"):
        compile_workflow_definition({**base, "version": 2})
    compiled = compile_workflow_definition({**base, "version": 3})
    assert compiled["version"] == 3
    assert compiled["steps"][0]["captures"][0]["kind"] == "collection"
    with pytest.raises(WorkflowDefinitionError, match="between 1 and 32"):
        compile_workflow_definition({
            **base,
            "version": 3,
            "steps": [{**base["steps"][0], "captures": [{**base["steps"][0]["captures"][0], "item_limit": 33}]}],
        })


def test_collection_fanout_renders_bounded_deduplicated_child_commands_without_public_items():
    children = expand_collection_step(
        {"cmd": "probe --host {{host}} --mode safe"},
        {},
        "host",
        ["one.example", "one.example", "two.example", "three.example"],
        max_children=2,
    )
    assert children == [
        {"ordinal": 0, "command": "probe --host one.example --mode safe"},
        {"ordinal": 1, "command": "probe --host two.example --mode safe"},
    ]
    with pytest.raises(WorkflowDefinitionError, match="control characters"):
        expand_collection_step({"cmd": "probe {{host}}"}, {}, "host", ["bad\x01host"])


def test_collection_fanout_policy_normalizes_retry_parallel_and_failure_modes():
    assert normalize_fanout_policy({"mode": "continue", "retries": 2, "max_parallel": 4, "max_failures": 5}) == FanoutPolicy(
        "continue", 2, 4, 5
    )
    assert normalize_fanout_policy({}) == FanoutPolicy()
    with pytest.raises(ValueError, match="fail-fast"):
        normalize_fanout_policy({"failure_mode": "fail_fast", "max_failures": 2})
    with pytest.raises(ValueError, match="between 0 and 3"):
        normalize_fanout_policy({"retries": 4})


def test_collection_fanout_checkpoint_resumes_without_relaunching_completed_children():
    checkpoint = create_fanout_checkpoint(4)
    assert checkpoint.next_batch(2) == (0, 1)
    checkpoint = checkpoint.mark_completed([0, 1])
    assert checkpoint.next_batch(2) == (2, 3)
    checkpoint = checkpoint.mark_failed([2])
    assert checkpoint.next_batch(2) == (3,)
    assert checkpoint.failed == (2,)
    assert checkpoint.cancel().next_batch(2) == ()
    with pytest.raises(ValueError, match="between 0 and 32"):
        create_fanout_checkpoint(33)
    restored = checkpoint_from_payload(checkpoint.to_payload())
    assert restored == checkpoint
    with pytest.raises(ValueError, match="overlap"):
        checkpoint_from_payload({"pending": [1], "completed": [1], "failed": [], "cancelled": False})


def test_execution_state_machine_advances_once_and_keeps_snapshot():
    from services.workflows.events import replay_execution_events

    make_test_app()
    session_id = "workflow-v2-" + uuid.uuid4().hex
    definition = compile_execution_definition(_v2_definition())
    execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "80,443"},
    )
    execution_id = execution["id"]
    first_run = "run-" + uuid.uuid4().hex
    second_run = "run-" + uuid.uuid4().hex

    assert claim_step_for_launch(execution_id, "resolve") is not None
    assert bind_step_run(execution_id, "resolve", first_run) is True
    advanced = finalize_run_step(first_run, 0, captures={"resolved_ip": "192.0.2.10"})
    assert advanced is not None
    assert advanced["destination"] == "scan"
    assert finalize_run_step(first_run, 0, captures={"resolved_ip": "198.51.100.1"}) is None
    assert claim_step_for_launch(execution_id, "scan") is not None
    assert bind_step_run(execution_id, "scan", second_run) is True
    completed = finalize_run_step(second_run, 2)

    stored = get_execution(session_id, execution_id)
    assert completed is not None
    assert stored is not None
    assert completed["destination"] == "complete"
    assert stored["status"] == "completed"
    assert stored["variables"]["resolved_ip"] == "192.0.2.10"
    assert stored["definition_snapshot"]["title"] == "Resolve and scan"
    assert [step["status"] for step in stored["steps"]] == ["succeeded", "failed"]
    event_page = replay_execution_events(stored, after=0, limit=100)
    events = cast(list[dict[str, Any]], event_page["events"])
    assert [event["type"] for event in events] == [
        "started",
        "step_started",
        "step_completed",
        "capture_saved",
        "step_started",
        "step_completed",
        "completed",
    ]
    assert events[3]["capture_names"] == ["resolved_ip"]
    assert "192.0.2.10" not in json.dumps(event_page)
    with get_db_connect()() as conn:
        delete_run_artifacts(conn, [first_run])
        conn.commit()
    stored_after_delete = get_execution(session_id, execution_id)
    assert stored_after_delete is not None
    assert stored_after_delete["steps"][0]["run_id"] == ""


def test_execution_state_machine_routes_failures_and_skips_unvisited_branches(caplog):
    from services.workflows import executions as workflow_executions

    make_test_app()
    caplog.set_level(logging.INFO, logger="shell")
    session_id = "workflow-branch-" + uuid.uuid4().hex
    definition = compile_execution_definition({
        "version": 2,
        "id": "fallback_branch",
        "title": "Fallback branch",
        "inputs": [],
        "steps": [
            {
                "id": "primary",
                "cmd": "false",
                "next": {"success": "success_path", "failure": "fallback"},
            },
            {
                "id": "success_path",
                "cmd": "echo primary",
                "next": {"success": "complete", "failure": "stop"},
            },
            {
                "id": "fallback",
                "cmd": "echo fallback",
                "next": {"success": "complete", "failure": "stop"},
            },
        ],
    })
    execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="fallback_branch",
        workflow_source="config",
        definition=definition,
        inputs={},
    )
    failed_run_id = "run-" + uuid.uuid4().hex
    fallback_run_id = "run-" + uuid.uuid4().hex
    assert claim_step_for_launch(execution["id"], "primary") is not None
    assert bind_step_run(execution["id"], "primary", failed_run_id) is True
    advanced = finalize_run_step(failed_run_id, 7)
    assert advanced is not None
    assert advanced["destination"] == "fallback"
    assert advanced["transition_reason"] == "failure"
    workflow_executions._log_step_transition(advanced)
    assert not any(record.getMessage() == "WORKFLOW_STEP_FAILED" for record in caplog.records)
    workflow_executions._log_step_transition({
        **advanced,
        "transition_reason": "exit_code:7",
    })
    assert not any(record.getMessage() == "WORKFLOW_STEP_FAILED" for record in caplog.records)
    assert claim_step_for_launch(execution["id"], "fallback") is not None
    assert bind_step_run(execution["id"], "fallback", fallback_run_id) is True
    completed = finalize_run_step(fallback_run_id, 0)
    assert completed is not None and completed["destination"] == "complete"

    stored = get_execution(session_id, execution["id"])
    assert stored is not None
    assert stored["status"] == "completed"
    assert [step["status"] for step in stored["steps"]] == ["failed", "skipped", "succeeded"]

    stop_definition = compile_execution_definition({
        "version": 2,
        "id": "unhandled_failure",
        "title": "Unhandled failure",
        "inputs": [],
        "steps": [{"id": "only", "cmd": "false", "next": {"success": "complete"}}],
    })
    stopped = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="unhandled_failure",
        workflow_source="config",
        definition=stop_definition,
        inputs={},
    )
    stopped_run_id = "run-" + uuid.uuid4().hex
    assert claim_step_for_launch(stopped["id"], "only") is not None
    assert bind_step_run(stopped["id"], "only", stopped_run_id) is True
    stopped_state = finalize_run_step(stopped_run_id, 9)
    assert stopped_state is not None and stopped_state["destination"] == "stop"
    workflow_executions._log_step_transition(stopped_state)
    failure_records = [
        record for record in caplog.records if record.getMessage() == "WORKFLOW_STEP_FAILED"
    ]
    assert len(failure_records) == 1
    assert failure_records[0].levelno == logging.WARNING
    assert failure_records[0].transition_reason == "implicit_failure"
    stopped_execution = get_execution(session_id, stopped["id"])
    assert stopped_execution is not None
    assert stopped_execution["status"] == "failed"


def test_execution_cancel_marks_active_and_pending_steps_terminal():
    make_test_app()
    session_id = "workflow-cancel-" + uuid.uuid4().hex
    definition = compile_execution_definition(_v2_definition())
    execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "443"},
    )
    run_id = "run-" + uuid.uuid4().hex
    assert claim_step_for_launch(execution["id"], "resolve") is not None
    assert bind_step_run(execution["id"], "resolve", run_id) is True

    canceled = cancel_execution(session_id, execution["id"])
    assert canceled is not None
    assert canceled["status"] == "canceled"
    assert canceled["_canceled_run_ids"] == [run_id]
    assert [step["status"] for step in canceled["steps"]] == ["canceled", "canceled"]
    assert finalize_run_step(run_id, 0, captures={"resolved_ip": "192.0.2.10"}) is None


def test_cancel_route_contains_missing_and_failed_process_signals(monkeypatch, caplog):
    from blueprints import run as run_routes

    client = make_test_app().test_client()
    session_id = "workflow-cancel-process-" + uuid.uuid4().hex
    definition = compile_execution_definition(_v2_definition())
    pid_by_run: dict[str, int | None] = {}
    validation_failures: set[str] = set()
    signal_failures: set[int] = set()
    validated: list[tuple[str, int, str, str]] = []
    signaled: list[int] = []

    monkeypatch.setattr(
        run_routes,
        "pid_for_session",
        lambda run_id, _session_id: pid_by_run.get(run_id),
    )

    def ensure_process_group(run_id, pid, active_session_id, *, team_id=""):
        validated.append((run_id, pid, active_session_id, team_id))
        if run_id in validation_failures:
            raise RuntimeError("process identity changed")

    def signal_process_group(pid):
        signaled.append(pid)
        if pid in signal_failures:
            raise OSError("signal denied")

    monkeypatch.setattr(run_routes, "_ensure_scanner_process_group_current", ensure_process_group)
    monkeypatch.setattr(run_routes, "_signal_process_group", signal_process_group)
    caplog.set_level(logging.WARNING, logger="shell")

    cases = (
        ("missing_pid", None),
        ("validation_failed", 4102),
        ("signal_failed", 4103),
    )
    executions = []
    for mode, pid in cases:
        execution = create_execution(
            session_id=session_id,
            team_id="",
            workflow_id=f"cancel_{mode}",
            workflow_source="config",
            definition=definition,
            inputs={"target": "example.com", "ports": "443"},
        )
        run_id = f"run-{mode}-{uuid.uuid4().hex}"
        assert claim_step_for_launch(execution["id"], "resolve") is not None
        assert bind_step_run(execution["id"], "resolve", run_id) is True
        pid_by_run[run_id] = pid
        if mode == "validation_failed":
            validation_failures.add(run_id)
        if mode == "signal_failed" and pid is not None:
            signal_failures.add(pid)

        response = client.post(
            f"/workflow-executions/{execution['id']}/cancel",
            headers={"X-Session-ID": session_id},
        )
        assert response.status_code == 200
        stored = get_execution(session_id, execution["id"])
        assert stored is not None
        assert stored["status"] == "canceled"
        assert [step["status"] for step in stored["steps"]] == ["canceled", "canceled"]
        assert finalize_run_step(run_id, 0, captures={"resolved_ip": "private.example"}) is None
        executions.append((execution, run_id))

    assert [item[1] for item in validated] == [4102, 4103]
    assert signaled == [4103]
    warnings = [
        record for record in caplog.records
        if record.getMessage() == "WORKFLOW_CANCEL_SIGNAL_FAILED"
    ]
    assert [(record.run_id, record.error_type) for record in warnings] == [
        (executions[1][1], "RuntimeError"),
        (executions[2][1], "OSError"),
    ]
    assert "private.example" not in caplog.text


def test_team_execution_routes_enforce_roles_scope_and_team_process_control(monkeypatch):
    from blueprints import run as run_routes
    from services.teams.storage import create_team, soft_remove_team_member, update_team_status

    client = make_test_app().test_client()
    fixture = _team_scope_fixture()
    team = cast(dict[str, object], fixture["team"])
    team_id = str(team["id"])
    owner_token = str(fixture["owner_token"])
    operator_token = str(fixture["operator_token"])
    viewer_token = str(fixture["viewer_token"])
    owner_headers = {"X-Session-ID": owner_token, "X-Team-ID": team_id}
    operator_headers = {"X-Session-ID": operator_token, "X-Team-ID": team_id}
    viewer_headers = {"X-Session-ID": viewer_token, "X-Team-ID": team_id}
    launches: list[str] = []
    monkeypatch.setattr(
        "blueprints.workflows.launch_execution_step",
        lambda execution_id: launches.append(execution_id) or {"execution_id": execution_id},
    )

    workflow_definition = _v2_definition()
    workflow_definition["inputs"][0]["sensitive"] = True
    workflow_response = client.post(
        "/session/workflows",
        json=workflow_definition,
        headers=owner_headers,
    )
    workflow = workflow_response.get_json()["workflow"]
    owner_create = client.post(
        "/workflow-executions",
        json={"workflow_id": workflow["id"], "inputs": {"target": "owner.example"}},
        headers=owner_headers,
    )
    operator_create = client.post(
        "/workflow-executions",
        json={"workflow_id": workflow["id"], "inputs": {"target": "operator.example"}},
        headers=operator_headers,
    )
    viewer_create = client.post(
        "/workflow-executions",
        json={"workflow_id": workflow["id"], "inputs": {"target": "viewer.example"}},
        headers=viewer_headers,
    )
    owner_execution = owner_create.get_json()["execution"]
    operator_execution = operator_create.get_json()["execution"]

    assert workflow_response.status_code == 201
    assert owner_create.status_code == 202
    assert operator_create.status_code == 202
    assert viewer_create.status_code == 403
    _assert_public_execution_payload(
        owner_execution,
        "owner.example",
        "operator.example",
        owner_token,
        operator_token,
        viewer_token,
    )
    _assert_public_execution_payload(
        operator_execution,
        "owner.example",
        "operator.example",
        owner_token,
        operator_token,
        viewer_token,
    )
    for headers in (owner_headers, operator_headers, viewer_headers):
        listed = client.get("/workflow-executions?limit=10", headers=headers)
        detail = client.get(
            f"/workflow-executions/{owner_execution['id']}",
            headers=headers,
        )
        events = client.get(
            f"/workflow-executions/{owner_execution['id']}/events",
            headers=headers,
        )
        assert listed.status_code == 200
        assert {item["id"] for item in listed.get_json()["executions"]} == {
            owner_execution["id"],
            operator_execution["id"],
        }
        assert detail.status_code == 200
        assert events.status_code == 200
        for item in listed.get_json()["executions"]:
            _assert_public_execution_payload(
                item,
                "owner.example",
                "operator.example",
                owner_token,
                operator_token,
                viewer_token,
            )
        _assert_public_execution_payload(
            detail.get_json()["execution"],
            "owner.example",
            "operator.example",
            owner_token,
            operator_token,
            viewer_token,
        )
        serialized_events = json.dumps(events.get_json(), sort_keys=True)
        assert "owner.example" not in serialized_events
        assert "operator.example" not in serialized_events
        assert owner_token not in serialized_events
        assert operator_token not in serialized_events
        assert viewer_token not in serialized_events

    assert client.get(
        f"/workflow-executions/{owner_execution['id']}",
        headers={"X-Session-ID": owner_token},
    ).status_code == 404
    with get_db_connect()() as conn:
        other_team = create_team(
            conn,
            name="Other workflow team " + uuid.uuid4().hex[:8],
            creator_session_token=owner_token,
        )
        conn.commit()
    assert client.get(
        f"/workflow-executions/{owner_execution['id']}",
        headers={"X-Session-ID": owner_token, "X-Team-ID": str(other_team["id"])},
    ).status_code == 404

    run_id = "run-team-cancel-" + uuid.uuid4().hex
    assert claim_step_for_launch(owner_execution["id"], "resolve") is not None
    assert bind_step_run(owner_execution["id"], "resolve", run_id) is True
    team_pid_reads: list[tuple[str, str]] = []
    validated: list[tuple[str, int, str, str]] = []
    signaled: list[int] = []
    monkeypatch.setattr(
        run_routes,
        "pid_for_team",
        lambda active_run_id, active_team_id: team_pid_reads.append(
            (active_run_id, active_team_id)
        ) or 5201,
    )
    monkeypatch.setattr(
        run_routes,
        "pid_for_session",
        lambda *_args: pytest.fail("team cancellation used personal process lookup"),
    )
    monkeypatch.setattr(
        run_routes,
        "_ensure_scanner_process_group_current",
        lambda active_run_id, pid, session_id, *, team_id="": validated.append(
            (active_run_id, pid, session_id, team_id)
        ),
    )
    monkeypatch.setattr(run_routes, "_signal_process_group", lambda pid: signaled.append(pid))

    viewer_cancel = client.post(
        f"/workflow-executions/{owner_execution['id']}/cancel",
        headers=viewer_headers,
    )
    operator_cancel = client.post(
        f"/workflow-executions/{owner_execution['id']}/cancel",
        headers=operator_headers,
    )
    owner_cancel = client.post(
        f"/workflow-executions/{operator_execution['id']}/cancel",
        headers=owner_headers,
    )
    assert viewer_cancel.status_code == 403
    assert operator_cancel.status_code == 200
    assert owner_cancel.status_code == 200
    _assert_public_execution_payload(
        operator_cancel.get_json()["execution"],
        "owner.example",
        "operator.example",
        owner_token,
        operator_token,
        viewer_token,
    )
    _assert_public_execution_payload(
        owner_cancel.get_json()["execution"],
        "owner.example",
        "operator.example",
        owner_token,
        operator_token,
        viewer_token,
    )
    assert team_pid_reads == [(run_id, team_id)]
    assert validated == [(run_id, 5201, operator_token, team_id)]
    assert signaled == [5201]
    assert launches == [owner_execution["id"], operator_execution["id"]]
    assert finalize_run_step(run_id, 0, captures={"resolved_ip": "192.0.2.40"}) is None

    with get_db_connect()() as conn:
        assert soft_remove_team_member(conn, str(cast(dict[str, object], fixture["operator"])["id"]))
        conn.commit()
    assert client.get(
        f"/workflow-executions/{owner_execution['id']}",
        headers=operator_headers,
    ).status_code == 403
    with get_db_connect()() as conn:
        update_team_status(conn, team_id, status="archived")
        conn.commit()
    assert client.get("/workflow-executions", headers=viewer_headers).status_code == 409


def test_execution_routes_are_scoped_and_launch_server_execution(monkeypatch):
    from blueprints import workflows as workflow_routes

    client = make_test_app().test_client()
    session_id = "workflow-route-" + uuid.uuid4().hex
    other_session = "workflow-route-other-" + uuid.uuid4().hex
    created = client.post(
        "/session/workflows",
        json=_v2_definition(),
        headers={"X-Session-ID": session_id},
    ).get_json()["workflow"]
    launches = []
    monkeypatch.setattr(
        "blueprints.workflows.launch_execution_step",
        lambda execution_id: launches.append(execution_id) or {"execution_id": execution_id},
    )

    response = client.post(
        "/workflow-executions",
        json={
            "workflow_id": created["id"],
            "inputs": {"target": "example.com", "ports": "61001-61003"},
        },
        headers={"X-Session-ID": session_id},
    )
    execution = response.get_json()["execution"]

    assert response.status_code == 202
    assert launches == [execution["id"]]
    _assert_public_execution_payload(execution, "example.com", "61001-61003", session_id)
    listed = client.get(
        "/workflow-executions?limit=10",
        headers={"X-Session-ID": session_id},
    ).get_json()["executions"]
    assert [item["id"] for item in listed] == [execution["id"]]
    assert [step["step_id"] for step in listed[0]["steps"]] == ["resolve", "scan"]
    filtered = client.get(
        f"/workflow-executions?limit=10&workflow_id={created['id']}",
        headers={"X-Session-ID": session_id},
    ).get_json()["executions"]
    unrelated = client.get(
        "/workflow-executions?limit=10&workflow_id=unrelated_workflow",
        headers={"X-Session-ID": session_id},
    ).get_json()["executions"]
    assert [item["id"] for item in filtered] == [execution["id"]]
    assert unrelated == []
    assert client.get(
        "/workflow-executions?limit=10",
        headers={"X-Session-ID": other_session},
    ).get_json()["executions"] == []
    monkeypatch.setattr(
        workflow_routes,
        "resolve_effective_cfg",
        lambda: {"workflow_active_execution_limit": 1},
    )
    limited = client.post(
        "/workflow-executions",
        json={"workflow_id": created["id"], "inputs": {"target": "example.net", "ports": "80"}},
        headers={"X-Session-ID": session_id},
    )
    assert limited.status_code == 429
    assert limited.get_json()["error"] == "workflow_execution_limit"
    assert client.get(
        f"/workflow-executions/{execution['id']}",
        headers={"X-Session-ID": other_session},
    ).status_code == 404
    started_events = client.get(
        f"/workflow-executions/{execution['id']}/events?limit=1",
        headers={"X-Session-ID": session_id},
    ).get_json()
    assert [event["type"] for event in started_events["events"]] == ["started"]
    assert started_events["next_cursor"] == 1
    assert started_events["has_more"] is False
    assert client.get(
        f"/workflow-executions/{execution['id']}/events",
        headers={"X-Session-ID": other_session},
    ).status_code == 404
    blocked_migration = client.post(
        "/session/migrate",
        json={"from_session_id": session_id, "to_session_id": str(uuid.uuid4())},
        headers={"X-Session-ID": session_id},
    )
    assert blocked_migration.status_code == 409
    assert blocked_migration.get_json()["error"] == "active_workflow_execution"
    from blueprints import run as run_routes

    old_run_id = "run-" + uuid.uuid4().hex
    new_run_id = "run-" + uuid.uuid4().hex
    assert claim_step_for_launch(execution["id"], "resolve") is not None
    assert bind_step_run(execution["id"], "resolve", old_run_id) is True
    real_cancel_execution = workflow_routes.cancel_execution

    def transition_then_cancel(active_session_id, active_execution_id, *, team_id=""):
        state = finalize_run_step(old_run_id, 0, captures={"resolved_ip": "192.0.2.10"})
        assert state is not None and state["destination"] == "scan"
        assert claim_step_for_launch(active_execution_id, "scan") is not None
        assert bind_step_run(active_execution_id, "scan", new_run_id) is True
        return real_cancel_execution(active_session_id, active_execution_id, team_id=team_id)

    monkeypatch.setattr(workflow_routes, "cancel_execution", transition_then_cancel)
    monkeypatch.setattr(
        run_routes,
        "pid_for_session",
        lambda run_id, _session: 4321 if run_id == new_run_id else None,
    )
    monkeypatch.setattr(
        run_routes,
        "_ensure_scanner_process_group_current",
        lambda *_args, **_kwargs: None,
    )
    signal_group = []
    monkeypatch.setattr(run_routes, "_signal_process_group", lambda pid: signal_group.append(pid))
    canceled = client.post(
        f"/workflow-executions/{execution['id']}/cancel",
        headers={"X-Session-ID": session_id},
    )
    assert canceled.status_code == 200
    assert canceled.get_json()["execution"].get("_canceled_run_ids") is None
    assert signal_group == [4321]
    terminal_events = client.get(
        f"/workflow-executions/{execution['id']}/events?after=1",
        headers={"X-Session-ID": session_id},
    ).get_json()
    assert [event["type"] for event in terminal_events["events"]][-1] == "canceled"
    assert terminal_events["next_cursor"] == 1 + len(terminal_events["events"])
    serialized_events = json.dumps(terminal_events, sort_keys=True)
    assert "example.com" not in serialized_events
    assert "61001-61003" not in serialized_events
    changed_definition = _v2_definition()
    changed_definition["title"] = "Changed after execution"
    update_response = client.put(
        f"/session/workflows/{created['id']}",
        json=changed_definition,
        headers={"X-Session-ID": session_id},
    )
    delete_response = client.delete(
        f"/session/workflows/{created['id']}",
        headers={"X-Session-ID": session_id},
    )
    saved_execution = client.get(
        f"/workflow-executions/{execution['id']}",
        headers={"X-Session-ID": session_id},
    ).get_json()["execution"]
    stored_execution = get_execution(session_id, execution["id"])
    assert update_response.status_code == 200
    assert delete_response.status_code == 200
    _assert_public_execution_payload(saved_execution, "example.com", "61001-61003", session_id)
    assert stored_execution is not None
    assert stored_execution["definition_snapshot"]["title"] == "Resolve and scan"
    with get_db_connect()() as conn:
        audit_rows = conn.execute(
            "SELECT event_type, target_type, target_id, details FROM audit_events "
            "WHERE target_id = ? ORDER BY created, id",
            (execution["id"],),
        ).fetchall()
    assert [row["event_type"] for row in audit_rows] == [
        "workflow_execution.start",
        "workflow_execution.cancel",
    ]
    assert {row["target_type"] for row in audit_rows} == {"workflow_execution"}
    serialized_audit = json.dumps([json.loads(row["details"]) for row in audit_rows])
    assert "example.com" not in serialized_audit
    assert "443" not in serialized_audit


def test_linked_runs_expose_sanitized_workflow_provenance_to_history_and_projects():
    client = make_test_app().test_client()
    session_id = "workflow-provenance-" + uuid.uuid4().hex
    definition = compile_execution_definition(_v2_definition())
    execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "sensitive.example", "ports": "80,443"},
    )
    first_run = "run-" + uuid.uuid4().hex
    second_run = "run-" + uuid.uuid4().hex
    assert claim_step_for_launch(execution["id"], "resolve") is not None
    assert bind_step_run(execution["id"], "resolve", first_run) is True
    assert finalize_run_step(first_run, 0, captures={"resolved_ip": "192.0.2.25"}) is not None
    assert claim_step_for_launch(execution["id"], "scan") is not None
    assert bind_step_run(execution["id"], "scan", second_run) is True
    with get_db_connect()() as conn:
        for run_id, command in (
            (first_run, "printf resolved"),
            (second_run, "nmap redacted"),
        ):
            conn.execute(
                "INSERT INTO runs "
                "(id, session_id, command, started, finished, exit_code, output_preview, output_line_count) "
                "VALUES (?, ?, ?, datetime('now'), datetime('now'), 0, '[]', 0)",
                (run_id, session_id, command),
            )
        conn.commit()

    headers = {"X-Session-ID": session_id}
    project = client.post(
        "/projects",
        json={"name": "Playbook evidence"},
        headers=headers,
    ).get_json()["project"]
    for run_id in (first_run, second_run):
        response = client.post(
            f"/projects/{project['id']}/links",
            json={"entity_type": "run", "entity_id": run_id, "source": "manual"},
            headers=headers,
        )
        assert response.status_code == 201

    history_run = client.get(f"/history/{first_run}?json=1", headers=headers).get_json()
    project_runs = client.get(f"/projects/{project['id']}/runs", headers=headers).get_json()["runs"]
    provenance = history_run["workflow_execution"]
    assert history_run["workflow_execution_id"] == execution["id"]
    assert history_run["workflow_step_id"] == "resolve"
    assert provenance["execution_id"] == execution["id"]
    assert provenance["step"]["step_id"] == "resolve"
    assert [step["run_id"] for step in provenance["steps"]] == [first_run, second_run]
    assert {run["workflow_execution_id"] for run in project_runs} == {execution["id"]}
    assert {run["workflow_step_id"] for run in project_runs} == {"resolve", "scan"}
    serialized = json.dumps(provenance, sort_keys=True)
    for private_value in (
        "sensitive.example",
        "80,443",
        "192.0.2.25",
        "definition_snapshot",
        "input_values",
        "variables",
        "workspace_cwd",
        "command",
    ):
        assert private_value not in serialized
    hidden = client.get(f"/history/{first_run}?json=1", headers={"X-Session-ID": "other-session"}).get_json()
    assert hidden["workflow_execution"] is None
    assert hidden["workflow_execution_id"] == ""


def test_server_orchestrator_launches_capture_fed_steps_through_normal_run_service(monkeypatch):
    from blueprints import run as run_routes
    from services.workflows.executions import launch_execution_step

    make_test_app()
    session_id = "workflow-engine-" + uuid.uuid4().hex
    source = _v2_definition()
    source["inputs"][0]["sensitive"] = True
    definition = compile_execution_definition(source)
    execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "443"},
        workspace_cwd="cases/external-review",
        project_id="prj_workflow_context",
        owner_client_id="client-workflow-context",
        owner_tab_id="tab-workflow-context",
    )
    launched: list[dict[str, object]] = []

    class Capture:
        _event_observer: Callable[[LineEvent], None]

    def fake_start(**kwargs):
        launched.append({
            key: kwargs[key]
            for key in (
                "original_command",
                "display_command",
                "private_values",
                "session_id",
                "team_id",
                "workspace_cwd",
                "link_project_id",
                "owner_client_id",
                "owner_tab_id",
            )
        })
        run_id = "run-" + uuid.uuid4().hex
        capture = Capture()
        kwargs["run_created_hook"](run_id, capture)
        capture._event_observer(LineEvent("192.0.2.44"))
        return BrokeredRunStartResult(run_id, "builtin", "succeeded", 0)

    monkeypatch.setattr(run_routes, "broker_available", lambda: True)
    monkeypatch.setattr(run_routes, "_start_brokered_run_service", fake_start)

    launch_execution_step(execution["id"])

    stored = get_execution(session_id, execution["id"])
    assert stored is not None
    assert [item["original_command"] for item in launched] == [
        "printf '%s\\n' example.com",
        "nmap -p 443 192.0.2.44",
    ]
    assert [item["display_command"] for item in launched] == [
        "printf '%s\\n' [redacted]",
        "nmap -p 443 [captured:resolved_ip]",
    ]
    assert [set(cast(tuple[str, ...], item["private_values"])) for item in launched] == [
        {"example.com"},
        {"example.com", "192.0.2.44"},
    ]
    assert all(item["session_id"] == session_id for item in launched)
    assert all(item["team_id"] == "" for item in launched)
    assert all(item["workspace_cwd"] == "cases/external-review" for item in launched)
    assert all(item["link_project_id"] == "prj_workflow_context" for item in launched)
    assert all(item["owner_client_id"] == "client-workflow-context" for item in launched)
    assert all(item["owner_tab_id"] == "tab-workflow-context" for item in launched)
    assert stored["status"] == "completed"


def test_sensitive_workflow_run_redacts_real_lifecycle_metadata(monkeypatch, caplog):
    from blueprints import run as run_routes
    from dataclasses import replace
    from services.runs.contracts import RunPreparationError, RunSpawnError
    from services.runs import finalization as run_finalization

    client = make_test_app().test_client()
    session_id = "workflow-lifecycle-" + uuid.uuid4().hex
    private_value = "workflow-private-" + uuid.uuid4().hex
    denied_value = "workflow-denied-" + uuid.uuid4().hex
    spawn_value = "workflow-spawn-" + uuid.uuid4().hex
    missing_value = "workflow-missing-" + uuid.uuid4().hex
    raw_command = f"true {private_value}"
    display_command = "true [redacted]"
    headers = {"X-Session-ID": session_id}
    project_response = client.post("/projects", json={"name": "Workflow privacy"}, headers=headers)
    project_id = project_response.get_json()["project"]["id"]
    caplog.set_level(logging.DEBUG, logger="shell")

    launched_commands: list[str] = []
    active_commands: list[str] = []
    metric_commands: list[str] = []
    notification_commands: list[str] = []
    real_popen = run_routes.subprocess.Popen
    real_active_run_register = run_routes.active_run_register

    def capture_popen(argv, **kwargs):
        launched_commands.append(str(argv[-1]))
        return real_popen(argv, **kwargs)

    def capture_active_run(*args, **kwargs):
        active_commands.append(str(args[3]))
        return real_active_run_register(*args, **kwargs)

    monkeypatch.setattr(run_routes, "is_command_allowed", lambda _command: (True, ""))
    monkeypatch.setattr(
        run_routes,
        "rewrite_command",
        lambda command, **_kwargs: (command, None),
    )
    monkeypatch.setattr(run_routes, "runtime_missing_command_name", lambda _command: None)
    monkeypatch.setattr(run_routes, "publish_run_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(run_routes, "active_run_register", capture_active_run)
    monkeypatch.setattr(run_routes.subprocess, "Popen", capture_popen)
    monkeypatch.setattr(run_routes, "STDBUF_BIN", None)
    monkeypatch.setattr(
        run_finalization.app_metrics,
        "record_completed_run",
        lambda command, *_args, **_kwargs: metric_commands.append(str(command)),
    )
    monkeypatch.setattr(
        run_finalization,
        "enqueue_run_complete",
        lambda **kwargs: notification_commands.append(str(kwargs["command"])),
    )

    started = run_routes._start_brokered_run_service(
        original_command=raw_command,
        display_command=display_command,
        session_id=session_id,
        client_ip="127.0.0.1",
        handlers=run_routes._run_start_handlers(),
        link_project_id=project_id,
        private_values=(private_value,),
        thread_name_prefix="workflow-run",
    )

    saved_command = ""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with get_db_connect()() as conn:
            row = conn.execute(
                "SELECT command, finished FROM runs WHERE id = ?",
                (started.run_id,),
            ).fetchone()
        if row and row["finished"] and metric_commands and notification_commands:
            saved_command = str(row["command"])
            break
        time.sleep(0.01)

    assert launched_commands == [raw_command]
    assert active_commands == [display_command]
    assert saved_command == display_command
    assert metric_commands == [display_command]
    assert notification_commands == [display_command]
    history_response = client.get(f"/history/{started.run_id}?json=1", headers=headers)
    project_runs_response = client.get(f"/projects/{project_id}/runs", headers=headers)
    assert history_response.status_code == 200
    assert project_runs_response.status_code == 200
    assert history_response.get_json()["command"] == display_command
    project_run = next(
        item
        for item in project_runs_response.get_json()["runs"]
        if item["id"] == started.run_id
    )
    assert project_run["command"] == display_command

    monkeypatch.setattr(
        run_routes,
        "is_command_allowed",
        lambda _command: (False, f"blocked {denied_value} by command policy"),
    )
    with pytest.raises(RunPreparationError, match=r"blocked \[redacted\] by command policy"):
        run_routes._start_brokered_run_service(
            original_command=f"true {denied_value}",
            display_command=display_command,
            session_id=session_id,
            client_ip="127.0.0.1",
            handlers=run_routes._run_start_handlers(),
            private_values=(denied_value,),
        )

    monkeypatch.setattr(run_routes, "is_command_allowed", lambda _command: (True, ""))
    monkeypatch.setattr(
        run_routes.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (
            _ for _ in ()
        ).throw(OSError(f"spawn failed for {spawn_value}")),
    )
    with pytest.raises(RunSpawnError, match=r"spawn failed for \[redacted\]"):
        run_routes._start_brokered_run_service(
            original_command=f"true {spawn_value}",
            display_command=display_command,
            session_id=session_id,
            client_ip="127.0.0.1",
            handlers=run_routes._run_start_handlers(),
            private_values=(spawn_value,),
        )

    missing_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def capture_missing_run(*args, **kwargs):
        missing_calls.append((args, kwargs))
        return "run-missing-private"

    monkeypatch.setattr(
        run_routes,
        "runtime_missing_command_name",
        lambda _command: missing_value,
    )
    missing_handlers = replace(
        run_routes._run_start_handlers(),
        brokered_synthetic_run=capture_missing_run,
    )
    missing_display_command = "[redacted] --help"
    missing_started = run_routes._start_brokered_run_service(
        original_command=f"{missing_value} --help",
        display_command=missing_display_command,
        session_id=session_id,
        client_ip="127.0.0.1",
        handlers=missing_handlers,
        private_values=(missing_value,),
    )
    assert missing_started.run_id == "run-missing-private"
    assert missing_calls[0][0][0] == missing_display_command
    assert missing_value not in json.dumps(missing_calls, default=str)

    lifecycle_records = {
        record.getMessage(): record
        for record in caplog.records
        if record.getMessage() in {
            "RUN_START",
            "RUN_END",
            "CMD_DENIED",
            "CMD_MISSING",
            "RUN_SPAWN_ERROR",
        }
    }
    assert lifecycle_records.keys() == {
        "RUN_START",
        "RUN_END",
        "CMD_DENIED",
        "CMD_MISSING",
        "RUN_SPAWN_ERROR",
    }
    assert lifecycle_records["CMD_MISSING"].cmd == missing_display_command
    assert lifecycle_records["CMD_MISSING"].missing == "[redacted]"
    assert all(
        getattr(record, "cmd", "") == display_command
        for name, record in lifecycle_records.items()
        if name != "CMD_MISSING"
    )
    serialized_logs = json.dumps(
        [
            {
                key: str(value)
                for key, value in vars(record).items()
                if key not in {"exc_info", "exc_text", "stack_info"}
            }
            for record in caplog.records
        ],
        sort_keys=True,
    )
    for value in (private_value, denied_value, spawn_value, missing_value):
        assert value not in serialized_logs


def test_required_capture_failure_uses_failure_branch_without_leaking_values(monkeypatch, caplog):
    from blueprints import run as run_routes
    from services.workflows import executions
    from services.workflows.events import replay_execution_events

    make_test_app()
    session_id = "workflow-required-capture-" + uuid.uuid4().hex
    private_value = "capture-private.example"
    definition = compile_execution_definition({
        "version": 2,
        "id": "required_capture_branch",
        "title": "Required capture branch",
        "inputs": [{"id": "target", "type": "domain", "required": True}],
        "steps": [
            {
                "id": "probe",
                "cmd": "printf no-match {{target}}",
                "captures": [{
                    "name": "answer",
                    "source": "first_line_containing",
                    "contains": "ANSWER=",
                    "required": True,
                }],
                "next": {"success": "success_path", "failure": "fallback"},
            },
            {
                "id": "success_path",
                "cmd": "echo should-not-run",
                "next": {"success": "complete", "failure": "stop"},
            },
            {
                "id": "fallback",
                "cmd": "echo fallback",
                "next": {"success": "complete", "failure": "stop"},
            },
        ],
    })
    execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="required_capture_branch",
        workflow_source="personal",
        definition=definition,
        inputs={"target": private_value},
    )
    launched_commands: list[str] = []
    capture_failures: list[str] = []

    class Capture:
        _event_observer: Callable[[LineEvent], None]

    def fake_start(**kwargs):
        command = str(kwargs["original_command"])
        launched_commands.append(command)
        run_id = "run-" + uuid.uuid4().hex
        capture = Capture()
        kwargs["run_created_hook"](run_id, capture)
        capture._event_observer(LineEvent("ordinary output without the required marker"))
        return BrokeredRunStartResult(run_id, "builtin", "succeeded", 0)

    monkeypatch.setattr(run_routes, "broker_available", lambda: True)
    monkeypatch.setattr(run_routes, "_start_brokered_run_service", fake_start)
    monkeypatch.setattr(
        executions.app_metrics,
        "record_workflow_capture_failure",
        lambda reason: capture_failures.append(reason),
    )
    caplog.set_level(logging.INFO, logger="shell")

    executions.launch_execution_step(execution["id"])

    stored = get_execution(session_id, execution["id"])
    assert stored is not None
    assert stored["status"] == "completed"
    assert launched_commands == [
        f"printf no-match {private_value}",
        "echo fallback",
    ]
    assert [step["status"] for step in stored["steps"]] == ["failed", "skipped", "succeeded"]
    probe = stored["steps"][0]
    assert probe["exit_code"] == 0
    assert probe["error_code"] == "required_capture_missing"
    assert probe["selected_transition"] == "fallback"
    assert probe["transition_reason"] == "failure"
    assert capture_failures == ["required_missing"]
    assert any(record.getMessage() == "WORKFLOW_CAPTURE_FAILED" for record in caplog.records)
    assert private_value not in caplog.text
    event_page = replay_execution_events(stored, after=0, limit=100)
    assert private_value not in json.dumps(event_page, sort_keys=True)
    with get_db_connect()() as conn:
        audit_payload = [dict(row) for row in conn.execute("SELECT * FROM audit_events").fetchall()]
        notification_payload = [
            dict(row) for row in conn.execute("SELECT * FROM notification_events").fetchall()
        ]
    assert private_value not in json.dumps(audit_payload, default=str, sort_keys=True)
    assert private_value not in json.dumps(notification_payload, default=str, sort_keys=True)


def test_server_orchestrator_rejects_interactive_pty_steps(monkeypatch):
    from blueprints import run as run_routes
    from services.workflows.executions import launch_execution_step

    make_test_app()
    session_id = "workflow-interactive-" + uuid.uuid4().hex
    definition = compile_execution_definition({
        "version": 2,
        "id": "interactive_monitor",
        "title": "Interactive monitor",
        "inputs": [],
        "steps": [{
            "id": "monitor",
            "cmd": "mtr --interactive example.com",
            "next": {"success": "complete", "failure": "stop"},
        }],
    })
    execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="interactive_monitor",
        workflow_source="personal",
        definition=definition,
        inputs={},
    )
    monkeypatch.setattr(
        run_routes,
        "interactive_pty_spec_for_command",
        lambda _command: {"trigger_flag": "--interactive"},
    )
    monkeypatch.setattr(
        run_routes,
        "_start_brokered_run_service",
        lambda **_kwargs: pytest.fail("interactive workflow step reached the run broker"),
    )

    assert launch_execution_step(execution["id"]) is None
    stored = get_execution(session_id, execution["id"])
    assert stored is not None
    assert stored["status"] == "failed"
    assert stored["failure_code"] == "interactive_pty_unsupported"
    assert stored["steps"][0]["error_code"] == "interactive_pty_unsupported"


def test_server_orchestrator_records_broker_or_policy_launch_failures(monkeypatch, caplog):
    from blueprints import run as run_routes
    from services.runs.contracts import RunPreparationError
    from services.workflows.executions import launch_execution_step

    make_test_app()
    session_id = "workflow-launch-failure-" + uuid.uuid4().hex
    definition = compile_execution_definition({
        "version": 2,
        "id": "policy_recheck",
        "title": "Policy recheck",
        "inputs": [],
        "steps": [{"id": "run", "cmd": "echo private.example"}],
    })
    execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="policy_recheck",
        workflow_source="personal",
        definition=definition,
        inputs={},
    )
    monkeypatch.setattr(run_routes, "broker_available", lambda: True)
    monkeypatch.setattr(
        run_routes,
        "_start_brokered_run_service",
        lambda **_kwargs: (_ for _ in ()).throw(RunPreparationError("command policy changed")),
    )
    caplog.set_level(logging.INFO, logger="shell")

    assert launch_execution_step(execution["id"]) is None
    stored = get_execution(session_id, execution["id"])
    assert stored is not None
    assert stored["status"] == "failed"
    assert stored["failure_code"] == "launch_failed"
    assert stored["steps"][0]["error_code"] == "launch_failed"
    warning = next(
        record for record in caplog.records
        if record.getMessage() == "WORKFLOW_STEP_LAUNCH_FAILED"
    )
    assert warning.levelno == logging.WARNING
    assert warning.execution_id == execution["id"]
    assert warning.step_id == "run"
    assert warning.stage == "run_start"
    assert warning.exc_info is None

    unexpected = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="policy_recheck",
        workflow_source="personal",
        definition=definition,
        inputs={},
    )
    monkeypatch.setattr(
        run_routes,
        "_start_brokered_run_service",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    caplog.clear()

    assert launch_execution_step(unexpected["id"]) is None
    launch_error = next(
        record for record in caplog.records
        if record.getMessage() == "WORKFLOW_STEP_LAUNCH_ERROR"
    )
    assert launch_error.levelno == logging.ERROR
    assert launch_error.execution_id == unexpected["id"]
    assert launch_error.step_id == "run"
    assert launch_error.stage == "run_start"
    assert launch_error.exc_info is not None
    assert "private.example" not in caplog.text

    rechecked_definition = compile_execution_definition(_v2_definition())
    rechecked = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="resolve_and_scan",
        workflow_source="personal",
        definition=rechecked_definition,
        inputs={"target": "example.com", "ports": "443"},
    )
    policy_calls: list[str] = []

    class Capture:
        _event_observer: Callable[[LineEvent], None]

    def policy_changes_between_steps(**kwargs):
        command = str(kwargs["original_command"])
        policy_calls.append(command)
        if len(policy_calls) == 2:
            raise RunPreparationError("restricted network policy changed")
        run_id = "run-policy-recheck-" + uuid.uuid4().hex
        capture = Capture()
        kwargs["run_created_hook"](run_id, capture)
        capture._event_observer(LineEvent("192.0.2.75"))
        return BrokeredRunStartResult(run_id, "builtin", "succeeded", 0)

    monkeypatch.setattr(run_routes, "_start_brokered_run_service", policy_changes_between_steps)
    assert launch_execution_step(rechecked["id"]) is not None
    rechecked_stored = get_execution(session_id, rechecked["id"])
    assert rechecked_stored is not None
    assert rechecked_stored["status"] == "failed"
    assert [step["status"] for step in rechecked_stored["steps"]] == ["succeeded", "failed"]
    assert rechecked_stored["steps"][0]["run_id"].startswith("run-policy-recheck-")
    assert rechecked_stored["steps"][1]["run_id"] == ""
    assert policy_calls == [
        "printf '%s\\n' example.com",
        "nmap -p 443 192.0.2.75",
    ]


def test_active_execution_limit_is_enforced_per_owner():
    make_test_app()
    session_id = "workflow-limit-" + uuid.uuid4().hex
    definition = compile_execution_definition(_v2_definition())
    create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "443"},
        max_active=1,
    )

    with pytest.raises(WorkflowActiveExecutionLimitExceeded, match="limit reached"):
        create_execution(
            session_id=session_id,
            team_id="",
            workflow_id="resolve_and_scan",
            workflow_source="config",
            definition=definition,
            inputs={"target": "example.net", "ports": "80"},
            max_active=1,
        )


def test_step_launch_fails_execution_after_wall_clock_limit(monkeypatch):
    from services.workflows import executions

    make_test_app()
    session_id = "workflow-timeout-" + uuid.uuid4().hex
    definition = compile_execution_definition(_v2_definition())
    execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "443"},
    )
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE workflow_executions SET created = '2000-01-01 00:00:00' WHERE id = ?",
            (execution["id"],),
        )
        conn.commit()
    monkeypatch.setattr(executions, "_max_runtime_seconds", lambda: 1)

    assert executions.launch_execution_step(execution["id"]) is None
    stored = get_execution(session_id, execution["id"])
    assert stored is not None
    assert stored["status"] == "failed"
    assert stored["failure_code"] == "execution_timeout"
    assert stored["steps"][0]["status"] == "failed"
    assert stored["steps"][1]["status"] == "skipped"


def test_step_launch_rechecks_team_and_initiator_state():
    from services.workflows import executions
    from services.teams.storage import add_team_member, create_team, soft_remove_team_member

    make_test_app()
    session_id = "workflow-permission-" + uuid.uuid4().hex
    definition = compile_execution_definition(_v2_definition())
    execution = create_execution(
        session_id=session_id,
        team_id="team-missing-" + uuid.uuid4().hex,
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "443"},
        actor_member_id="member-missing",
        actor_role="operator",
    )

    assert executions.launch_execution_step(execution["id"]) is None
    stored = executions.storage.get_execution_by_id(execution["id"])
    assert stored is not None
    assert stored["status"] == "failed"
    assert stored["failure_code"] == "team_unavailable"

    owner_token = "tok_" + uuid.uuid4().hex
    actor_token = "tok_" + uuid.uuid4().hex
    viewer_token = "tok_" + uuid.uuid4().hex
    with get_db_connect()() as conn:
        team = create_team(
            conn,
            name="Workflow permissions " + uuid.uuid4().hex[:8],
            creator_session_token=owner_token,
        )
        actor = add_team_member(
            conn,
            team_id=team["id"],
            session_token=actor_token,
            role="operator",
        )
        viewer = add_team_member(
            conn,
            team_id=team["id"],
            session_token=viewer_token,
            role="viewer",
        )
        created = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            "INSERT INTO session_tokens (token, created) VALUES (?, ?)",
            [(actor_token, created), (viewer_token, created)],
        )
        conn.commit()

    revoked_member_execution = create_execution(
        session_id=actor_token,
        team_id=team["id"],
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "443"},
        actor_member_id=actor["id"],
        actor_role="operator",
    )
    with get_db_connect()() as conn:
        assert soft_remove_team_member(conn, actor["id"]) is True
        conn.commit()
    assert executions.launch_execution_step(revoked_member_execution["id"]) is None
    revoked_member = executions.storage.get_execution_by_id(revoked_member_execution["id"])
    assert revoked_member is not None and revoked_member["failure_code"] == "member_revoked"

    downgraded_execution = create_execution(
        session_id=viewer_token,
        team_id=team["id"],
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "443"},
        actor_member_id=viewer["id"],
        actor_role="operator",
    )
    assert executions.launch_execution_step(downgraded_execution["id"]) is None
    downgraded = executions.storage.get_execution_by_id(downgraded_execution["id"])
    assert downgraded is not None and downgraded["failure_code"] == "permission_revoked"

    token = "tok_" + uuid.uuid4().hex
    with get_db_connect()() as conn:
        token_actor = add_team_member(
            conn,
            team_id=team["id"],
            session_token=token,
            role="operator",
        )
        conn.execute(
            "INSERT INTO session_tokens (token, created) VALUES (?, ?)",
            (token, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    token_execution = create_execution(
        session_id=token,
        team_id=team["id"],
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "443"},
        actor_member_id=token_actor["id"],
        actor_role="operator",
    )
    with get_db_connect()() as conn:
        conn.execute("DELETE FROM session_tokens WHERE token = ?", (token,))
        conn.commit()
    assert executions.launch_execution_step(token_execution["id"]) is None
    revoked_token = executions.storage.get_execution_by_id(token_execution["id"])
    assert revoked_token is not None and revoked_token["failure_code"] == "token_revoked"

    personal_token = "tok_" + uuid.uuid4().hex
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO session_tokens (token, created) VALUES (?, ?)",
            (personal_token, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    personal_execution = create_execution(
        session_id=personal_token,
        team_id="",
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "443"},
    )
    with get_db_connect()() as conn:
        conn.execute("DELETE FROM session_tokens WHERE token = ?", (personal_token,))
        conn.commit()
    assert executions.launch_execution_step(personal_execution["id"]) is None
    personal_revoked = executions.storage.get_execution_by_id(personal_execution["id"])
    assert personal_revoked is not None and personal_revoked["failure_code"] == "token_revoked"


def test_recovery_replays_completed_runs_and_fails_vanished_runs(monkeypatch, caplog):
    from services.workflows import executions

    make_test_app()
    caplog.set_level(logging.INFO, logger="shell")
    session_id = "workflow-recovery-" + uuid.uuid4().hex
    definition = compile_execution_definition({
        "version": 2,
        "id": "recover_echo",
        "title": "Recover echo",
        "inputs": [],
        "steps": [{
            "id": "echo",
            "cmd": "echo recovered",
            "next": {"success": "complete", "failure": "stop"},
        }],
    })
    completed = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="recover_echo",
        workflow_source="config",
        definition=definition,
        inputs={},
    )
    completed_run_id = "run-" + uuid.uuid4().hex
    assert claim_step_for_launch(completed["id"], "echo") is not None
    assert bind_step_run(completed["id"], "echo", completed_run_id) is True
    finished = datetime.now(timezone.utc).isoformat()
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output_preview, output_line_count) "
            "VALUES (?, ?, 'echo recovered', ?, ?, 0, '[]', 0)",
            (completed_run_id, session_id, finished, finished),
        )
        conn.execute(
            "UPDATE runs SET full_output_available = 1 WHERE id = ?",
            (completed_run_id,),
        )
        conn.execute(
            "INSERT INTO run_output_artifacts "
            "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
            "VALUES (?, 'private/recovery-output.jsonl.gz', 'gzip', 10, 1, 0, ?)",
            (completed_run_id, finished),
        )
        conn.commit()

    vanished = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="recover_echo",
        workflow_source="config",
        definition=definition,
        inputs={},
    )
    vanished_run_id = "run-" + uuid.uuid4().hex
    assert claim_step_for_launch(vanished["id"], "echo") is not None
    assert bind_step_run(vanished["id"], "echo", vanished_run_id) is True
    monkeypatch.setattr(executions, "_run_is_still_active", lambda _execution, _run_id: False)

    completed_result = executions.recover_workflow_execution(completed["id"])
    vanished_result = executions.recover_workflow_execution(vanished["id"])

    recovered = get_execution(session_id, completed["id"])
    missing = get_execution(session_id, vanished["id"])
    assert completed_result == "recovered"
    assert vanished_result == "failed"
    assert executions.recover_workflow_execution(completed["id"]) == "ignored"
    assert recovered is not None and recovered["status"] == "completed"
    assert missing is not None and missing["failure_code"] == "active_run_missing"
    output_warning = next(
        record for record in caplog.records
        if record.getMessage() == "WORKFLOW_RECOVERY_OUTPUT_LOAD_FAILED"
    )
    assert output_warning.execution_id == completed["id"]
    assert output_warning.step_id == "echo"
    assert output_warning.run_id == completed_run_id
    assert output_warning.stage == "load_completed_run_output"
    assert output_warning.reason == "FileNotFoundError"
    assert not hasattr(output_warning, "rel_path")
    assert "private/recovery-output.jsonl.gz" not in caplog.text

    recovery_refs = [
        (f"wfx_page_{index:03d}", f"2026-07-13 00:{index // 60:02d}:{index % 60:02d}")
        for index in range(205)
    ]

    def recovery_page(*, limit, after_created="", after_id=""):
        remaining = [
            item for item in recovery_refs
            if (item[1], item[0]) > (after_created, after_id)
        ]
        return remaining[:limit]

    examined = []
    failed_recovery_id = recovery_refs[57][0]
    monkeypatch.setattr(executions.storage, "active_execution_page_for_recovery", recovery_page)
    def recover_page_execution(execution_id):
        examined.append(execution_id)
        if execution_id == failed_recovery_id:
            raise RuntimeError("recovery failed unexpectedly")
        return "left_running"

    monkeypatch.setattr(executions, "recover_workflow_execution", recover_page_execution)
    caplog.clear()
    recovery_result = executions.recover_workflow_executions(limit=100)
    assert recovery_result["left_running"] == 204
    assert recovery_result["errors"] == 1
    assert examined == [execution_id for execution_id, _created in recovery_refs]
    recovery_error = next(
        record for record in caplog.records
        if record.getMessage() == "WORKFLOW_RECOVERY_ERROR"
    )
    assert recovery_error.levelno == logging.ERROR
    assert recovery_error.execution_id == failed_recovery_id
    assert recovery_error.stage == "recover_execution"
    assert recovery_error.recovery_owner is True
    assert recovery_error.exc_info is not None
    summary = next(
        record for record in caplog.records
        if record.getMessage() == "WORKFLOW_RECOVERY_COMPLETED"
    )
    assert summary.examined == 205
    assert summary.errors == 1
    assert summary.ignored == 0
    assert summary.pid > 0
    assert summary.recovery_owner is True


def test_recovery_reclaims_stale_states_and_advances_completed_step_once(monkeypatch):
    from services.workflows import executions

    make_test_app()
    session_id = "workflow-recovery-matrix-" + uuid.uuid4().hex
    one_step = compile_execution_definition({
        "version": 2,
        "id": "recovery_matrix",
        "title": "Recovery matrix",
        "inputs": [],
        "steps": [{
            "id": "probe",
            "cmd": "echo probe",
            "next": {"success": "complete", "failure": "stop"},
        }],
    })
    launched: list[tuple[str, str]] = []
    active_run_ids: set[str] = set()

    def bind_recovered_launch(execution_id):
        pointer = executions.storage.execution_launch_pointer(execution_id)
        if not pointer:
            return None
        _session_id, _team_id, step_id = pointer
        if executions.storage.claim_step_for_launch(execution_id, step_id) is None:
            return None
        run_id = "run-recovered-" + uuid.uuid4().hex
        assert executions.storage.bind_step_run(execution_id, step_id, run_id)
        active_run_ids.add(run_id)
        launched.append((execution_id, step_id))
        return {"execution_id": execution_id, "step_id": step_id, "run_id": run_id}

    monkeypatch.setattr(executions, "launch_execution_step", bind_recovered_launch)
    monkeypatch.setattr(
        executions,
        "_run_is_still_active",
        lambda _execution, run_id: run_id in active_run_ids,
    )

    stale = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="recovery_matrix",
        workflow_source="config",
        definition=one_step,
        inputs={},
    )
    assert claim_step_for_launch(stale["id"], "probe") is not None
    pending = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="recovery_matrix",
        workflow_source="config",
        definition=one_step,
        inputs={},
    )

    assert executions.recover_workflow_execution(stale["id"]) == "recovered"
    assert executions.recover_workflow_execution(pending["id"]) == "recovered"
    assert executions.recover_workflow_execution(stale["id"]) == "left_running"
    assert executions.recover_workflow_execution(pending["id"]) == "left_running"
    assert launched[:2] == [(stale["id"], "probe"), (pending["id"], "probe")]

    malformed = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="recovery_matrix",
        workflow_source="config",
        definition=one_step,
        inputs={},
    )
    malformed_run_id = "run-malformed-" + uuid.uuid4().hex
    assert claim_step_for_launch(malformed["id"], "probe") is not None
    assert bind_step_run(malformed["id"], "probe", malformed_run_id)
    finished = datetime.now(timezone.utc).isoformat()
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, command, started, finished, exit_code, output_preview, output_line_count) "
            "VALUES (?, ?, 'echo malformed', ?, ?, 0, '[]', 0)",
            (malformed_run_id, session_id, finished, finished),
        )
        conn.execute(
            "UPDATE workflow_executions SET definition_snapshot = ? WHERE id = ?",
            (json.dumps({"version": 2, "steps": []}), malformed["id"]),
        )
        conn.commit()
    assert executions.recover_workflow_execution(malformed["id"]) == "recovered"
    malformed_stored = get_execution(session_id, malformed["id"])
    assert malformed_stored is not None
    assert malformed_stored["failure_code"] == "recovery_definition_error"

    invalid = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="recovery_matrix",
        workflow_source="config",
        definition=one_step,
        inputs={},
    )
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE workflow_executions SET status = 'running' WHERE id = ?",
            (invalid["id"],),
        )
        conn.execute(
            "UPDATE workflow_execution_steps SET status = 'succeeded' "
            "WHERE execution_id = ? AND step_id = 'probe'",
            (invalid["id"],),
        )
        conn.commit()
    assert executions.recover_workflow_execution(invalid["id"]) == "failed"
    invalid_stored = get_execution(session_id, invalid["id"])
    assert invalid_stored is not None
    assert invalid_stored["failure_code"] == "recovery_state_invalid"

    capture_definition = compile_execution_definition({
        "version": 2,
        "id": "recovery_capture",
        "title": "Recovery capture",
        "inputs": [],
        "steps": [
            {
                "id": "resolve",
                "cmd": "echo 192.0.2.55",
                "captures": [{
                    "name": "resolved_ip",
                    "source": "first_nonempty_line",
                    "required": True,
                }],
                "next": {"success": "inspect", "failure": "stop"},
            },
            {
                "id": "inspect",
                "cmd": "echo {{resolved_ip}}",
                "next": {"success": "complete", "failure": "stop"},
            },
        ],
    })
    racing = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="recovery_capture",
        workflow_source="config",
        definition=capture_definition,
        inputs={},
    )
    racing_run_id = "run-racing-" + uuid.uuid4().hex
    assert claim_step_for_launch(racing["id"], "resolve") is not None
    assert bind_step_run(racing["id"], "resolve", racing_run_id)
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, command, started, finished, exit_code, output_preview, output_line_count) "
            "VALUES (?, ?, 'echo 192.0.2.55', ?, ?, 0, ?, 1)",
            (
                racing_run_id,
                session_id,
                finished,
                finished,
                json.dumps([{"text": "192.0.2.55", "cls": ""}]),
            ),
        )
        conn.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(
            lambda _index: executions.recover_workflow_execution(racing["id"]),
            range(2),
        ))

    racing_stored = get_execution(session_id, racing["id"])
    assert racing_stored is not None
    assert "recovered" in outcomes
    assert set(outcomes) <= {"recovered", "left_running"}
    assert racing_stored["variables"]["resolved_ip"] == "192.0.2.55"
    assert [item for item in launched if item == (racing["id"], "inspect")] == [
        (racing["id"], "inspect")
    ]


def test_completed_personal_execution_moves_with_session_migration(monkeypatch):
    from blueprints import session as session_routes

    client = make_test_app().test_client()
    source_session = "workflow-migrate-source-" + uuid.uuid4().hex
    destination_session = "workflow-migrate-destination-" + uuid.uuid4().hex
    definition = compile_execution_definition({
        "version": 2,
        "id": "migrated_execution",
        "title": "Migrated execution",
        "inputs": [],
        "steps": [{
            "id": "finish",
            "cmd": "true",
            "next": {"success": "complete", "failure": "stop"},
        }],
    })
    execution = create_execution(
        session_id=source_session,
        team_id="",
        workflow_id="migrated_execution",
        workflow_source="personal",
        definition=definition,
        inputs={},
    )
    run_id = "run-migrated-" + uuid.uuid4().hex
    assert claim_step_for_launch(execution["id"], "finish") is not None
    assert bind_step_run(execution["id"], "finish", run_id)
    assert finalize_run_step(run_id, 0) is not None
    monkeypatch.setattr(
        session_routes,
        "migrate_session_workspace",
        lambda _from_id, _to_id: type("Migration", (), {
            "migrated_files": 0,
            "skipped_files": 0,
            "migrated_directories": 0,
            "skipped_directories": 0,
            "migrated_file_paths": (),
        })(),
    )

    response = client.post(
        "/session/migrate",
        headers={"X-Session-ID": source_session},
        json={
            "from_session_id": source_session,
            "to_session_id": destination_session,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["migrated_workflow_executions"] == 1
    assert get_execution(source_session, execution["id"]) is None
    migrated = get_execution(destination_session, execution["id"])
    assert migrated is not None
    assert migrated["session_id"] == destination_session
    assert migrated["steps"][0]["step_id"] == "finish"
    assert migrated["steps"][0]["run_id"] == run_id


def test_finalization_hook_failure_marks_workflow_failed_without_raising(monkeypatch):
    from services.workflows import hooks

    make_test_app()
    session_id = "workflow-hook-" + uuid.uuid4().hex
    definition = compile_execution_definition(_v2_definition())
    execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="resolve_and_scan",
        workflow_source="config",
        definition=definition,
        inputs={"target": "example.com", "ports": "443"},
    )
    run_id = "run-" + uuid.uuid4().hex
    assert claim_step_for_launch(execution["id"], "resolve") is not None
    assert bind_step_run(execution["id"], "resolve", run_id) is True
    monkeypatch.setattr(hooks, "finalize_workflow_run", lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")))

    hooks.finalize_workflow_run_safely(True, run_id, session_id, 0, None)

    stored = get_execution(session_id, execution["id"])
    assert stored is not None
    assert stored["status"] == "failed"
    assert stored["failure_code"] == "finalization_hook_failed"
