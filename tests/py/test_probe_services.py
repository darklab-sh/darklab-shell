# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Contracts for reusable Project-scoped probe planning services."""

from __future__ import annotations

from copy import deepcopy
from io import StringIO
import json
import logging
from types import SimpleNamespace
from typing import cast
from unittest import mock
import uuid

import pytest
from flask import Request

from core.database import db_connect, db_init
from core.logging_setup import GELFFormatter, _TextFormatter
from services.assessments.action_plan_payload import digest_plan
from services.assessments.action_plans import build_assessment_action_plan
from services.assessments.base_action_catalog import ACTIONS, base_action_ids
from services.assessments.command_plans import command_plan
from services.assessments.probe_catalog import probe_catalog
from services.assessments.probe_contracts import (
    PROBE_LAUNCH_CAPABILITIES,
    PROBE_PROTECTED_CAPABILITIES,
    PROBE_VIEW_CAPABILITIES,
    ProbeError,
    ProbePlanRequest,
)
from services.assessments.probe_plan_digest import probe_plan_digest
from services.assessments.probe_plans import build_probe_plan, confirm_probe_plan
from services.assessments.probe_cleanup import observed_probe_cleanup
from services.assessments.probe_broker_launch import launch_confirmed_probe
from services.assessments.probe_log_context import ProbeLogContext
from services.assessments.probe_observability import observe_probe
from services.assessments.http_profile_execution import ProtectedHttpLaunch
from services.assessments.probe_targets import resolve_probe_target
from services.assessments.probe_target_service import resolve_project_probe_target
from services.audit.context import request_audit_fields
from services.nuclei.template_cache import NucleiTemplateCacheSnapshot
from services.projects.crud import create_project, delete_project, update_project
from services.projects.targets import add_project_target
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected


_READY_TEMPLATES = NucleiTemplateCacheSnapshot(
    "ready", "v10.4.3", "sha256:" + "a" * 64, 12,
)
_ACTION_IDS = (
    "curl", "ping", "dnsrecon", "gau", "httpx", "katana", "dalfox",
    "sqlmap", "sslyze", "testssl", "nmap", "nuclei",
)


@pytest.fixture(scope="module", autouse=True)
def _initialize_probe_schema():
    db_init()


@pytest.fixture
def probe_project():
    session_id = "probe-services-" + uuid.uuid4().hex
    project = create_project(session_id, {"name": "Probe services"})
    assert project is not None
    project_id = str(project["id"])
    try:
        yield session_id, project_id
    finally:
        delete_project(session_id, project_id)


def _target(entity_id: str = "ent_probe", target_type: str = "domain") -> dict[str, str]:
    value = "example.test" if target_type != "url" else "https://example.test/path"
    return {"entity_id": entity_id, "type": target_type, "value": value}


def _request(action_id: str, *, target_type: str = "domain", **kwargs) -> ProbePlanRequest:
    del target_type
    return ProbePlanRequest(project_id="prj_probe", action_id=action_id, **kwargs)


def test_base_action_registry_is_complete_and_drives_command_target_compatibility():
    assert base_action_ids() == _ACTION_IDS
    assert tuple(ACTIONS) == _ACTION_IDS
    for action in ACTIONS.values():
        for target_type in action.target_types:
            target_value = (
                "https://example.test/a" if target_type == "url"
                else "192.0.2.10" if target_type == "ip"
                else "example.test"
            )
            plan = command_plan(
                action.action_id,
                target_type,
                target_value,
                allow_intrusive=True,
            )
            assert plan is not None, (action.action_id, target_type)
        assert command_plan(action.action_id, "port", "443") is None


@pytest.mark.parametrize(
    "action_id",
    ("curl", "httpx", "dalfox", "nuclei", "testssl"),
)
def test_url_bearing_ip_actions_bracket_ipv6_literals(action_id):
    plan = command_plan(
        action_id,
        "ip",
        "2001:db8::20",
        allow_intrusive=True,
    )

    assert plan is not None
    assert "https://[2001:db8::20]" in plan.command
    assert "https://2001:db8::20" not in plan.command


def test_probe_catalog_pins_public_schema_and_excludes_cycle_only_actions():
    catalog = probe_catalog(
        service="microsoft-ds",
        target_type="ip",
        template_snapshot=_READY_TEMPLATES,
        available_features={
            "curl", "ping", "dnsrecon", "gau", "httpx", "katana", "dalfox",
            "sqlmap", "sslyze", "testssl", "nmap", "reviewed_nse_profiles",
            "nuclei", "managed_nuclei_templates",
        },
    )
    assert set(catalog) == {
        "schema_version", "actions", "nmap_profiles", "nuclei_profiles",
        "service_recommendations", "exclusions",
    }
    assert [item["id"] for item in catalog["actions"]] == [
        action_id for action_id in _ACTION_IDS
        if "ip" in ACTIONS[action_id].target_types
    ]
    assert all("ip" in item["target_types"] for item in catalog["actions"])
    assert set(catalog["actions"][0]) == {
        "id", "revision", "label", "purpose", "mode", "policy_level",
        "target_types", "required_features", "expected_evidence", "exclusions",
        "compatible_profiles", "availability",
    }
    nmap_action = next(item for item in catalog["actions"] if item["id"] == "nmap")
    assert "ssh" in nmap_action["compatible_profiles"]["nmap"]
    nuclei_action = next(item for item in catalog["actions"] if item["id"] == "nuclei")
    assert nuclei_action["availability"] == {"available": True, "code": "", "reason": ""}
    assert catalog["service_recommendations"][0]["action_id"] == "nmap"
    assert catalog["service_recommendations"][0]["nmap_profile"] == "smb"
    assert catalog["nuclei_profiles"][0]["provenance"] == "managed_local_cache"
    assert catalog["nuclei_profiles"][0]["template_snapshot"]["state"] == "ready"
    omitted_features = probe_catalog(template_snapshot=_READY_TEMPLATES)
    omitted_curl = next(item for item in omitted_features["actions"] if item["id"] == "curl")
    assert omitted_curl["availability"]["code"] == "feature_unavailable"
    assert "version_cve_correlation" in catalog["exclusions"]
    assert not probe_catalog(
        service="version-cve",
        target_type="url",
        template_snapshot=_READY_TEMPLATES,
    )["service_recommendations"]
    assert not probe_catalog(
        service="ssh?",
        target_type="ip",
        template_snapshot=_READY_TEMPLATES,
    )["service_recommendations"]
    assert PROBE_VIEW_CAPABILITIES == frozenset()
    assert PROBE_LAUNCH_CAPABILITIES == frozenset({"run_commands"})
    assert PROBE_PROTECTED_CAPABILITIES == frozenset({"run_commands", "manage_secrets"})

    with pytest.raises(ProbeError) as invalid_target_type:
        probe_catalog(
            target_type="cidr",
            template_snapshot=_READY_TEMPLATES,
        )
    assert invalid_target_type.value.code == "invalid_target_type"


@pytest.mark.parametrize(("target_type", "expected_actions"), (
    ("domain", {
        "curl", "ping", "dnsrecon", "gau", "httpx", "katana", "dalfox",
        "sslyze", "testssl", "nmap", "nuclei",
    }),
    ("ip", {
        "curl", "ping", "httpx", "dalfox", "sslyze", "testssl", "nmap", "nuclei",
    }),
    ("url", {"curl", "httpx", "katana", "dalfox", "sqlmap", "nuclei"}),
))
def test_probe_catalog_filters_every_action_by_target_type(target_type, expected_actions):
    catalog = probe_catalog(
        target_type=target_type,
        template_snapshot=_READY_TEMPLATES,
        available_features={
            "curl", "ping", "dnsrecon", "gau", "httpx", "katana", "dalfox",
            "sqlmap", "sslyze", "testssl", "nmap", "reviewed_nse_profiles",
            "nuclei", "managed_nuclei_templates",
        },
    )

    assert {action["id"] for action in catalog["actions"]} == expected_actions
    assert all(target_type in action["target_types"] for action in catalog["actions"])


def test_probe_plan_is_bounded_and_dalfox_never_reaches_intrusive_xss_mode(monkeypatch):
    monkeypatch.setattr(
        "services.assessments.probe_plans.managed_nuclei_template_snapshot",
        lambda: pytest.fail("non-Nuclei plans must not inspect the template cache"),
    )
    plan = build_probe_plan(_request("dalfox"), _target())
    assert plan["policy_level"] == "standard"
    assert plan["action"]["mode"] == "parameter_discovery"
    assert "--only-discovery" in plan["display_command"]
    assert "--skip-mining-dict" in plan["display_command"]
    assert "--custom-payload" not in plan["display_command"]
    assert "xss_payloads" in ACTIONS["dalfox"].exclusions
    assert plan["bounds"]["target_count"] == plan["bounds"]["fan_out"] == 1


def test_probe_profiles_can_raise_but_never_lower_the_base_policy():
    nmap = build_probe_plan(
        _request("nmap", nmap_profile="safe"),
        _target(target_type="ip"),
        available_features={"nmap", "reviewed_nse_profiles"},
    )
    assert nmap["policy_level"] == "standard"
    assert nmap["profile"]["policy_level"] == "safe"
    assert "--script safe" in nmap["display_command"]
    assert "service_metadata" in nmap["expected_evidence"]

    nuclei = build_probe_plan(
        _request("nuclei", nuclei_profile="standard"),
        _target(),
        available_features={"nuclei", "managed_nuclei_templates"},
        template_snapshot=_READY_TEMPLATES,
    )
    assert nuclei["policy_level"] == "standard"
    assert nuclei["profile"]["template_snapshot"]["content_digest"].startswith("sha256:")


def test_intrusive_nuclei_requires_the_instance_gate_and_fresh_confirmation():
    request = _request("nuclei", nuclei_profile="intrusive")
    disabled = build_probe_plan(
        request,
        _target(),
        available_features={"nuclei", "managed_nuclei_templates"},
        template_snapshot=_READY_TEMPLATES,
    )
    assert disabled["launchable"] is False
    assert disabled["availability"]["code"] == "intrusive_actions_disabled"

    enabled = build_probe_plan(
        request,
        _target(),
        available_features={"nuclei", "managed_nuclei_templates"},
        intrusive_actions_enabled=True,
        template_snapshot=_READY_TEMPLATES,
    )
    assert enabled["launchable"] is True
    assert enabled["policy_level"] == "intrusive"
    assert "-headless" in enabled["display_command"]
    assert enabled["requires_confirmation"] is True


@pytest.mark.parametrize("profile_key", ("safe", "standard", "intrusive"))
def test_protected_nuclei_launch_keeps_the_reviewed_profile(
    monkeypatch,
    profile_key,
):
    from services.assessments import http_profile_execution

    http_summary = {
        "id": "ahp_probe_nuclei",
        "revision": 1,
        "role": "user",
        "credential_use": ["headers"],
        "rate_limit_per_second": 3,
        "concurrency": 2,
    }
    plan = build_probe_plan(
        _request(
            "nuclei",
            nuclei_profile=profile_key,
            http_profile_id=http_summary["id"],
        ),
        _target(target_type="url"),
        available_features={"nuclei", "managed_nuclei_templates"},
        intrusive_actions_enabled=True,
        template_snapshot=_READY_TEMPLATES,
        http_profile=http_summary,
        http_profile_target="https://example.test/path",
    )
    monkeypatch.setitem(
        http_profile_execution.app_config.CFG,
        "assessment_intrusive_actions_enabled",
        True,
    )
    monkeypatch.setattr(
        http_profile_execution,
        "load_http_profile_plan_context",
        lambda *_args, **_kwargs: (
            http_summary,
            "https://example.test/path",
            "",
            {"include_paths": [], "exclude_paths": []},
        ),
    )
    monkeypatch.setattr(
        http_profile_execution,
        "_resolved_headers",
        lambda *_args, **_kwargs: ([], []),
    )
    monkeypatch.setattr(
        http_profile_execution,
        "materialize_tool_profile",
        lambda *_args, **_kwargs: SimpleNamespace(
            trusted_args=(), private_values=(), cleanup=None,
        ),
    )

    materialized = http_profile_execution.materialize_http_profile_launch(
        "session-probe",
        "prj_probe",
        plan,
    )

    assert materialized.execution_command == plan["display_command"].removesuffix(
        " -sf [protected]"
    )


def test_probe_plan_fails_closed_for_profiles_features_and_target_types(monkeypatch):
    with pytest.raises(ProbeError, match="Nmap profile") as unknown:
        build_probe_plan(_request("nmap", nmap_profile="missing"), _target())
    assert unknown.value.code == "probe_profile_not_found"

    missing_feature = build_probe_plan(
        _request("curl"),
        _target(),
    )
    assert missing_feature["availability"]["code"] == "feature_unavailable"
    assert missing_feature["feature_gates"] == ["curl"]

    incompatible = build_probe_plan(
        _request("sqlmap"),
        _target(),
    )
    assert incompatible["availability"]["code"] == "unsupported_target_type"

    logger = mock.Mock()
    monkeypatch.setattr("services.assessments.probe_observability.log", logger)

    @observe_probe("plan")
    def reject(status_code):
        raise ProbeError("test_rejection", "Rejected", status_code=status_code)

    with pytest.raises(ProbeError):
        reject(404)
    logger.info.assert_called_once()
    logger.warning.assert_not_called()
    with pytest.raises(ProbeError):
        reject(409)
    logger.warning.assert_called_once()

    @observe_probe("catalog")
    def catalog(*, project_id):
        return {"project": project_id}

    catalog(project_id="prj_keyword")
    assert logger.debug.call_args.kwargs["extra"]["project_id"] == "prj_keyword"


def test_probe_cleanup_retries_failed_or_incomplete_removal(monkeypatch):
    outcomes = []
    logger = mock.Mock()
    monkeypatch.setattr(
        "services.assessments.probe_cleanup.app_metrics.record_probe_operation",
        lambda _phase, outcome, **_kwargs: outcomes.append(outcome),
    )
    monkeypatch.setattr("services.assessments.probe_cleanup.log", logger)
    results = iter((False, True))
    cleanup = mock.Mock(side_effect=lambda: next(results))
    observed = observed_probe_cleanup(cleanup)
    assert observed is not None

    assert observed() is False
    assert observed() is True
    assert observed() is None
    assert cleanup.call_count == 2
    assert outcomes == ["failed", "success"]
    logger.debug.assert_called_once()
    assert logger.debug.call_args.args == ("PROJECT_PROBE_PROTECTED_CLEANUP_COMPLETED",)
    assert logger.debug.call_args.kwargs["extra"]["cleanup_stage"] == "protected_material"

    raised = mock.Mock(side_effect=(RuntimeError("remove failed"), True))
    observed_raised = observed_probe_cleanup(raised)
    assert observed_raised is not None
    with pytest.raises(RuntimeError, match="remove failed"):
        observed_raised()
    assert observed_raised() is True
    assert raised.call_count == 2


@pytest.mark.parametrize(
    "failure",
    (
        RunPreparationError("probe preparation failed"),
        RunSpawnError("probe spawn failed"),
        RuntimeError("unexpected probe start failure"),
    ),
    ids=("preparation", "spawn", "unexpected"),
)
def test_probe_broker_cleans_material_when_start_raises(monkeypatch, failure):
    cleanup = mock.Mock(return_value=True)
    protected = ProtectedHttpLaunch(
        execution_command="httpx -u example.test",
        trusted_execution_args=("-H", "Authorization: protected"),
        private_values=("Authorization: protected",),
        cleanup=cleanup,
        audit_summary={},
    )
    context = SimpleNamespace(
        broker_kwargs=lambda: {"trusted_execution_args": protected.trusted_execution_args},
    )
    monkeypatch.setattr(
        "services.assessments.probe_broker_launch.materialize_probe_run_launch",
        lambda *_args, **_kwargs: (protected, context),
    )

    def failed_start(**_kwargs):
        raise failure

    with pytest.raises(type(failure), match=str(failure)):
        launch_confirmed_probe(
            {"display_command": "httpx -u example.test"},
            session_id="session-probe", project_id="prj_probe", team_id="",
            team_role="", actor_member_id="", client_ip="127.0.0.1",
            owner_client_id="client-probe", owner_tab_id="tab-probe",
            workspace_cwd="", handlers={}, start_run=failed_start,
            thread_name_prefix="probe-test",
        )

    cleanup.assert_called_once_with()


def test_probe_broker_preserves_start_failure_when_cleanup_is_incomplete(monkeypatch):
    cleanup = mock.Mock(return_value=False)
    protected = ProtectedHttpLaunch(
        execution_command="httpx -u example.test",
        trusted_execution_args=(), private_values=(), cleanup=cleanup, audit_summary={},
    )
    context = SimpleNamespace(broker_kwargs=lambda: {"trusted_execution_args": ()})
    monkeypatch.setattr(
        "services.assessments.probe_broker_launch.materialize_probe_run_launch",
        lambda *_args, **_kwargs: (protected, context),
    )

    def failed_start(**_kwargs):
        raise RunSpawnError("primary spawn failure")

    with pytest.raises(RunSpawnError, match="primary spawn failure"):
        launch_confirmed_probe(
            {"display_command": "httpx -u example.test"},
            session_id="session-probe", project_id="prj_probe", team_id="",
            team_role="", actor_member_id="", client_ip="127.0.0.1",
            owner_client_id="client-probe", owner_tab_id="tab-probe",
            workspace_cwd="", handlers={}, start_run=failed_start,
            thread_name_prefix="probe-test",
        )

    cleanup.assert_called_once_with()


def test_probe_failure_logging_sanitizes_chained_run_errors(monkeypatch):
    sensitive = "Bearer-probe-secret nmap target.example /tmp/private-http-runs/run-secret"
    rendered = []
    logger = logging.Logger("probe-observability-test", logging.DEBUG)
    logger.propagate = False
    monkeypatch.setattr("services.assessments.probe_observability.log", logger)

    @observe_probe("launch")
    def fail_spawn(_request):
        try:
            raise ValueError(sensitive)
        except ValueError as cause:
            raise RunSpawnError("Run could not start") from cause

    for formatter in (_TextFormatter(), GELFFormatter()):
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        logger.handlers[:] = [handler]
        with pytest.raises(RunSpawnError):
            fail_spawn(_request("httpx", http_profile_id="hpr_private"))
        rendered.append(stream.getvalue())

    assert all("PROJECT_PROBE_OPERATION_FAILED" in body for body in rendered)
    assert all("Project probe operation failed" in body for body in rendered)
    assert all(sensitive not in body for body in rendered)
    assert all("run_spawn_failed" in body for body in rendered)

    logger = mock.Mock()
    monkeypatch.setattr("services.assessments.probe_observability.log", logger)

    @observe_probe("launch")
    def reject_start(_request, error):
        raise error

    with pytest.raises(RunStartRejected):
        reject_start(_request("ping"), RunStartRejected("raw_code", sensitive))
    logger.info.assert_called_once()
    assert logger.info.call_args.kwargs["extra"]["error_code"] == "run_start_rejected"
    assert "exc_info" not in logger.info.call_args.kwargs

    with pytest.raises(RunPreparationError):
        reject_start(_request("ping"), RunPreparationError(sensitive))
    logger.warning.assert_called_once()
    assert logger.warning.call_args.kwargs["extra"]["error_code"] == "run_preparation_rejected"
    assert "exc_info" not in logger.warning.call_args.kwargs


def test_probe_log_fields_reject_control_characters_and_unbounded_identifiers(monkeypatch):
    logger = mock.Mock()
    monkeypatch.setattr("services.assessments.probe_observability.log", logger)
    malicious = "forged\nrecord" + "x" * 5000
    request = ProbePlanRequest(
        project_id=malicious,
        entity_id=malicious,
        action_id=malicious,
    )

    @observe_probe("plan")
    def reject(_request):
        raise ProbeError(malicious, "Rejected", status_code=400)

    with pytest.raises(ProbeError):
        reject(request)

    fields = logger.info.call_args.kwargs["extra"]
    assert fields["project_id"] == ""
    assert fields["entity_id"] == ""
    assert fields["action_id"] == "unknown"
    assert fields["error_code"] == ""
    assert fields["error_class"] == "ProbeError"
    assert malicious not in json.dumps(fields)


def test_probe_logging_classifies_unavailable_plans_and_broker_modes(monkeypatch):
    logger = mock.Mock()
    monkeypatch.setattr("services.assessments.probe_observability.log", logger)

    @observe_probe("plan")
    def unavailable(code):
        return {"launchable": False, "availability": {"code": code}}

    unavailable("intrusive_actions_disabled")
    assert logger.info.call_args.kwargs["extra"]["error_code"] == (
        "intrusive_actions_disabled"
    )
    logger.reset_mock()
    unavailable("feature_unavailable")
    assert logger.warning.call_args.kwargs["extra"]["error_code"] == "feature_unavailable"

    @observe_probe("launch")
    def broker_failure(reason):
        raise ProbeError("broker_unavailable", reason, status_code=503)

    logger.reset_mock()
    with pytest.raises(ProbeError):
        broker_failure("Run broker is disabled by configuration.")
    assert logger.info.call_args.kwargs["extra"]["error_code"] == "broker_disabled"
    logger.reset_mock()
    with pytest.raises(ProbeError):
        broker_failure("Run broker requires Redis, but Redis is not available.")
    assert logger.warning.call_args.kwargs["extra"]["error_code"] == (
        "broker_dependency_unavailable"
    )


@pytest.mark.parametrize(
    ("case", "outcome", "level", "event", "error_code"),
    (
        ("success", "success", "debug", "PROJECT_PROBE_OPERATION_COMPLETED", ""),
        (
            "unavailable_result", "unavailable", "warning",
            "PROJECT_PROBE_OPERATION_COMPLETED", "feature_unavailable",
        ),
        (
            "rejected", "rejected", "info",
            "PROJECT_PROBE_OPERATION_REJECTED", "probe_target_not_found",
        ),
        (
            "unavailable_error", "unavailable", "warning",
            "PROJECT_PROBE_OPERATION_REJECTED", "provider_unavailable",
        ),
        (
            "failed", "failed", "error",
            "PROJECT_PROBE_OPERATION_FAILED", "unexpected_failure",
        ),
    ),
)
def test_probe_observer_records_each_outcome_without_private_labels(
    monkeypatch,
    case,
    outcome,
    level,
    event,
    error_code,
):
    sensitive = "private-target.example Bearer-secret /tmp/private-probe-profile"
    logger = mock.Mock()
    metrics = mock.Mock()
    monkeypatch.setattr("services.assessments.probe_observability.log", logger)
    monkeypatch.setattr(
        "services.assessments.probe_observability.app_metrics.record_probe_operation",
        metrics,
    )
    request = ProbePlanRequest(
        project_id="prj_observed",
        action_id="httpx",
        entity_id="ent_observed",
        target_value=sensitive,
        http_profile_id="hpr_observed",
    )

    @observe_probe("plan")
    def observed(_request):
        if case == "success":
            return {"launchable": True, "display_command": sensitive}
        if case == "unavailable_result":
            return {
                "launchable": False,
                "availability": {"code": "feature_unavailable", "reason": sensitive},
            }
        if case == "rejected":
            raise ProbeError("probe_target_not_found", sensitive, status_code=404)
        if case == "unavailable_error":
            raise ProbeError("provider_unavailable", sensitive, status_code=503)
        raise RuntimeError(sensitive)

    if case in {"success", "unavailable_result"}:
        observed(request)
    else:
        with pytest.raises((ProbeError, RuntimeError)):
            observed(request)

    metrics.assert_called_once_with("plan", outcome, protected=True)
    log_call = getattr(logger, level).call_args
    assert log_call.args == (event,)
    fields = log_call.kwargs["extra"]
    assert fields["probe_phase"] == "plan"
    assert fields["probe_outcome"] == outcome
    assert fields["project_id"] == "prj_observed"
    assert fields["entity_id"] == "ent_observed"
    assert fields["action_id"] == "httpx"
    assert fields["protected"] is True
    assert fields["error_code"] == error_code
    serialized = json.dumps(
        {"metrics": metrics.call_args_list, "log": log_call},
        default=str,
    )
    assert sensitive not in serialized


def test_probe_logs_and_audit_rows_share_bounded_request_correlation(monkeypatch):
    logger = mock.Mock()
    monkeypatch.setattr("services.assessments.probe_observability.log", logger)
    context = ProbeLogContext(
        "api_v1", "request-probe-123", "tok_probe-secret", "team_probe"
    )

    @observe_probe("launch")
    def launch(_request, *, observability):
        del observability
        return SimpleNamespace(
            plan={"policy_level": "standard"},
            started=SimpleNamespace(run_id="run_probe_context"),
        )

    launch(_request("ping"), observability=context)
    fields = logger.info.call_args.kwargs["extra"]
    assert fields == {
        **fields,
        "source": "api_v1",
        "request_id": "request-probe-123",
        "session": "tok_prob********",
        "team_id": "team_probe",
        "policy_level": "standard",
        "run_id": "run_probe_context",
    }

    audit_request = cast(
        Request, Request.from_values(headers={"X-Request-ID": "caller-request"})
    )
    audit_request.environ["darklab_request_id"] = "server-request"
    assert request_audit_fields(audit_request)["request_id"] == "server-request"
    invalid_request = cast(Request, Request.from_values())
    invalid_request.environ["HTTP_X_REQUEST_ID"] = "forged\nrequest"
    assert request_audit_fields(invalid_request)["request_id"] == ""


def test_probe_target_resolution_emits_bounded_success_and_rejection_events(monkeypatch):
    from services.assessments import probe_target_resolution

    logger = mock.Mock()
    metrics = mock.Mock()
    database = mock.MagicMock()
    database.__enter__.return_value = mock.Mock()
    monkeypatch.setattr(probe_target_resolution, "log", logger)
    monkeypatch.setattr(probe_target_resolution.app_metrics, "record_probe_operation", metrics)
    monkeypatch.setattr(probe_target_resolution, "get_db_connect", lambda: lambda: database)
    target_value = "private-target.example"
    resolved = {"entity_id": "ent_probe", "type": "domain", "value": target_value}
    resolve_target = mock.Mock(return_value=resolved)
    monkeypatch.setattr(probe_target_resolution, "resolve_probe_target", resolve_target)
    context = ProbeLogContext("browser_terminal", "request-resolve", "session-resolve")

    assert resolve_project_probe_target(
        "session-resolve", "prj_probe", target_value=target_value,
        observability=context,
    ) == resolved
    fields = logger.debug.call_args.kwargs["extra"]
    assert logger.debug.call_args.args == ("PROJECT_PROBE_TARGET_RESOLVED",)
    assert fields["entity_id"] == "ent_probe"
    assert fields["target_type"] == "domain"
    assert fields["selector_kind"] == "exact_value"
    assert fields["candidate_count"] == 1
    assert fields["request_id"] == "request-resolve"
    assert target_value not in json.dumps(fields)

    ambiguous = ProbeError(
        "probe_target_ambiguous", "Ambiguous", status_code=409,
        details={"candidate_entity_ids": ["ent_one", "ent_two"]},
    )
    resolve_target.side_effect = ambiguous
    with pytest.raises(ProbeError):
        resolve_project_probe_target(
            "session-resolve", "prj_probe", target_value=target_value,
            observability=context,
        )
    rejected = logger.warning.call_args.kwargs["extra"]
    assert logger.warning.call_args.args == ("PROJECT_PROBE_TARGET_REJECTED",)
    assert rejected["candidate_count"] == 2
    assert rejected["error_code"] == "probe_target_ambiguous"
    assert target_value not in json.dumps(rejected)
    assert [call.args[:2] for call in metrics.call_args_list] == [
        ("resolve", "success"), ("resolve", "rejected"),
    ]


def test_probe_cleanup_observation_starts_before_launch_context_validation(monkeypatch):
    from services.assessments import probe_protected_launch

    outcomes = []
    cleanup = mock.Mock(side_effect=RuntimeError("cleanup failed"))
    protected = ProtectedHttpLaunch("ping example.test", (), (), cleanup, {})
    monkeypatch.setattr(
        probe_protected_launch,
        "materialize_http_profile_launch",
        lambda *_args, **_kwargs: protected,
    )
    monkeypatch.setattr(
        "services.assessments.probe_cleanup.app_metrics.record_probe_operation",
        lambda phase, outcome, **_kwargs: outcomes.append((phase, outcome)),
    )
    logger = mock.Mock()
    monkeypatch.setattr("services.assessments.probe_cleanup.log", logger)

    def reject_context(*_args, **_kwargs):
        raise ValueError("primary context failure")

    with pytest.raises(ValueError, match="primary context failure"):
        probe_protected_launch.materialize_probe_run_launch(
            "session-probe",
            "prj_probe",
            {"display_command": "ping example.test"},
            launch_context=reject_context,
        )

    cleanup.assert_called_once()
    assert outcomes == [("cleanup", "failed")]
    fields = logger.error.call_args.kwargs["extra"]
    assert fields == {
        "project_id": "",
        "entity_id": "",
        "action_id": "",
        "profile_id": "",
        "cleanup_stage": "protected_material",
        "error_class": "RuntimeError",
    }


def test_probe_cleanup_tracebacks_never_render_private_values(monkeypatch):
    sensitive = "Bearer-cleanup-secret /tmp/private-http-runs/run-private"
    logger = logging.Logger("probe-cleanup-test", logging.DEBUG)
    logger.propagate = False
    monkeypatch.setattr("services.assessments.probe_cleanup.log", logger)

    def fail_cleanup():
        raise OSError(sensitive)

    for formatter in (_TextFormatter(), GELFFormatter()):
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        logger.handlers[:] = [handler]
        cleanup = observed_probe_cleanup(
            fail_cleanup,
            context={
                "project_id": "prj_safe",
                "entity_id": "ent_safe",
                "action_id": "httpx",
                "profile_id": "hpr_safe",
            },
        )
        assert cleanup is not None
        with pytest.raises(OSError):
            cleanup()
        body = stream.getvalue()
        assert sensitive not in body
        assert "Project probe operation failed" in body
        assert "cleanup_stage" in body


def _digest_test_plan():
    return build_probe_plan(
        _request(
            "nuclei",
            nuclei_profile="standard",
            http_profile_id="hpr_digest",
        ),
        _target(target_type="url"),
        available_features={"nuclei", "managed_nuclei_templates"},
        template_snapshot=_READY_TEMPLATES,
        http_profile={
            "id": "hpr_digest", "revision": 2, "name": "Digest profile",
            "role": "user", "credential_use": ["headers"], "enabled": True,
            "rate_limit_per_second": 3, "concurrency": 2,
            "scope": {
                "allowed_hosts": ["example.test"],
                "scope_roots": ["https://example.test/app"],
                "include_paths": ["/app"],
                "exclude_paths": ["/app/private"],
            },
        },
        http_profile_target="https://example.test/path",
    )


def _replace_digest_field(plan, path, value):
    changed = deepcopy(plan)
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return changed


@pytest.mark.parametrize(("path", "value"), (
    (("digest_version",), 999),
    (("schema_version",), 999),
    (("project_id",), "prj_changed"),
    (("action", "id"), "httpx"),
    (("action", "revision"), "changed"),
    (("action", "mode"), "changed"),
    (("target", "entity_id"), "ent_changed"),
    (("target", "type"), "domain"),
    (("target", "value"), "https://changed.example/path"),
    (("profile", "kind"), "nmap"),
    (("profile", "id"), "intrusive"),
    (("profile", "revision"), 999),
    (("profile", "policy_level"), "intrusive"),
    (("profile", "requires_confirmation"), True),
    (("profile", "evidence_kinds"), ["services"]),
    (("profile", "template_snapshot", "state"), "stale"),
    (("profile", "template_snapshot", "release_version"), "v99"),
    (("profile", "template_snapshot", "content_digest"), "sha256:changed"),
    (("profile", "template_snapshot", "manifest_entry_count"), 999),
    (("http_profile", "id"), "hpr_changed"),
    (("http_profile", "revision"), 3),
    (("http_profile", "role"), "administrator"),
    (("http_profile", "credential_use"), ["cookies"]),
    (("http_profile", "scope"), {"allowed_hosts": ["changed.example"]}),
    (("policy_level",), "intrusive"),
    (("required_features",), ["nuclei"]),
    (("feature_gates",), ["managed_nuclei_templates"]),
    (("scope",), {"kind": "changed"}),
    (("bounds",), {"target_count": 2}),
    (("display_command",), "nuclei -u https://changed.example"),
    (("expected_evidence",), ["services"]),
    (("availability", "code"), "feature_unavailable"),
    (("availability", "available"), False),
    (("launchable",), False),
    (("requires_confirmation",), False),
))
def test_probe_digest_changes_for_every_approval_field(path, value):
    plan = _digest_test_plan()

    assert probe_plan_digest(_replace_digest_field(plan, path, value)) != plan["plan_digest"]


@pytest.mark.parametrize(("path", "value"), (
    (("action", "label"), "Localized label"),
    (("action", "purpose"), "Localized help"),
    (("profile_details",), {"label": "Presentation only"}),
    (("http_profile", "name"), "Localized profile name"),
    (("http_profile", "enabled"), False),
    (("http_profile", "rate_limit_per_second"), 99),
    (("http_profile", "concurrency"), 99),
    (("availability", "reason"), "Friendlier explanation"),
    (("unavailable_reason",), "Friendlier explanation"),
    (("plan_digest",), "caller-supplied-value-is-ignored"),
))
def test_probe_digest_ignores_every_presentation_field(path, value):
    plan = _digest_test_plan()

    assert probe_plan_digest(_replace_digest_field(plan, path, value)) == plan["plan_digest"]


def test_probe_digest_normalizes_set_like_list_order():
    plan = _digest_test_plan()
    plan["required_features"] = ["zeta", "alpha"]
    plan["feature_gates"] = ["second", "first"]
    plan["expected_evidence"] = ["findings", "services"]
    plan["profile"]["evidence_kinds"] = ["findings", "services"]
    digest = probe_plan_digest(plan)
    reordered = deepcopy(plan)
    reordered["required_features"].reverse()
    reordered["feature_gates"].reverse()
    reordered["expected_evidence"].reverse()
    reordered["profile"]["evidence_kinds"].reverse()

    assert probe_plan_digest(reordered) == digest


def test_probe_digest_public_shape_remains_versioned():
    plan = _digest_test_plan()
    assert set(plan) == {
        "schema_version", "digest_version", "project_id", "action", "target", "profile",
        "profile_details", "http_profile", "policy_level", "required_features",
        "feature_gates", "scope", "bounds", "display_command", "expected_evidence",
        "availability", "launchable", "unavailable_reason", "requires_confirmation",
        "plan_digest",
    }
    assert plan["digest_version"] == 1


def test_probe_confirmation_rebuilds_the_plan_and_rejects_stale_or_extra_fields():
    plan = build_probe_plan(
        _request("ping"),
        _target(),
        available_features={"ping"},
    )
    assert confirm_probe_plan(
        {"confirmed": True, "plan_digest": plan["plan_digest"]},
        lambda: plan,
    ) is plan
    with pytest.raises(ProbeError) as stale:
        confirm_probe_plan(
            {"confirmed": True, "plan_digest": "0" * 64},
            lambda: plan,
        )
    assert stale.value.code == "stale_plan"
    assert stale.value.status_code == 409
    with pytest.raises(ProbeError) as unsupported:
        confirm_probe_plan(
            {"confirmed": True, "plan_digest": plan["plan_digest"], "command": "ping"},
            lambda: plan,
        )
    assert unsupported.value.code == "unsupported_fields"


def test_assessment_adapter_keeps_its_full_payload_digest_contract():
    row = {
        "assessment_id": "asm_digest", "check_id": "ach_digest",
        "check_key": "host_reachability", "target_entity_id": "ent_digest",
        "target_type": "domain", "target_value": "example.test",
        "policy_level": "safe", "recommended_action_key": "command:ping",
        "profile_key": "network", "profile_version": "1.0",
        "profile_snapshot": json.dumps({"checks": [{
            "key": "host_reachability", "policy_level": "safe",
            "recommended_action": "command:ping",
        }]}),
        "assessment_status": "active", "project_status": "active",
    }
    plan = build_assessment_action_plan(row, _target("ent_digest"), "prj_digest")
    expected_payload = {key: value for key, value in plan.items() if key != "plan_digest"}
    assert plan["plan_digest"] == (
        "424b41660fe6651edbbed28deb35d00b59591ba6d5af04abdbbbefb2c40a2d7a"
    )
    assert plan["plan_digest"] == digest_plan(expected_payload)
    presentation_change = deepcopy(expected_payload)
    presentation_change["bounds"]["summary"] = "Changed presentation"
    assert digest_plan(presentation_change) != plan["plan_digest"]


def test_probe_target_resolver_requires_one_confirmed_owner_scoped_project_link(
    probe_project,
):
    session_id, project_id = probe_project
    confirmed = add_project_target(
        session_id,
        project_id,
        {"type": "domain", "value": "resolve.example", "review_state": "confirmed"},
    )
    pending = add_project_target(
        session_id,
        project_id,
        {"type": "domain", "value": "pending.example", "review_state": "pending"},
    )
    assert confirmed and pending
    with db_connect() as conn:
        by_id = resolve_probe_target(
            conn, session_id, "",
            ProbePlanRequest(project_id, "ping", entity_id=str(confirmed["id"])),
        )
        by_value = resolve_probe_target(
            conn, session_id, "",
            ProbePlanRequest(project_id, "ping", target_value="resolve.example"),
        )
        assert by_id == by_value
        assert by_id["entity_id"] == confirmed["id"]
        with pytest.raises(ProbeError) as unconfirmed:
            resolve_probe_target(
                conn, session_id, "",
                ProbePlanRequest(project_id, "ping", entity_id=str(pending["id"])),
            )
        assert unconfirmed.value.code == "probe_target_not_found"
        with pytest.raises(ProbeError) as foreign:
            resolve_probe_target(
                conn, "foreign-session", "",
                ProbePlanRequest(project_id, "ping", entity_id=str(confirmed["id"])),
            )
        assert foreign.value.code == "project_not_found"
        with pytest.raises(ProbeError) as empty_selector:
            resolve_probe_target(
                conn, session_id, "",
                ProbePlanRequest(project_id, "ping"),
            )
        assert empty_selector.value.code == "target_selector_invalid"

        conn.execute(
            "UPDATE entities SET type = 'email' WHERE id = ?",
            (confirmed["id"],),
        )
        conn.commit()
        with pytest.raises(ProbeError) as unsupported:
            resolve_probe_target(
                conn, session_id, "",
                ProbePlanRequest(project_id, "ping", entity_id=str(confirmed["id"])),
            )
        assert unsupported.value.code == "probe_target_type_unsupported"
        conn.execute(
            "UPDATE entities SET type = 'domain' WHERE id = ?",
            (confirmed["id"],),
        )
        conn.commit()

    update_project(session_id, project_id, {"status": "archived"})
    with db_connect() as conn, pytest.raises(ProbeError) as archived:
        resolve_probe_target(
            conn, session_id, "",
            ProbePlanRequest(project_id, "ping", entity_id=str(confirmed["id"])),
        )
    assert archived.value.code == "project_archived"


class _AmbiguousTargetConnection:
    def __init__(self):
        self.calls = 0

    def execute(self, _sql, _params):
        self.calls += 1
        rows = [{"status": "active"}] if self.calls == 1 else [
            {"id": "ent_a", "type": "domain", "canonical_value": "same.example"},
            {"id": "ent_b", "type": "domain", "canonical_value": "same.example"},
        ]
        return _Rows(rows)


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def test_probe_target_value_ambiguity_returns_only_safe_entity_identifiers():
    with pytest.raises(ProbeError) as ambiguous:
        resolve_probe_target(
            _AmbiguousTargetConnection(),
            "session",
            "",
            ProbePlanRequest("prj_probe", "ping", target_value="same.example"),
        )
    assert ambiguous.value.code == "probe_target_ambiguous"
    assert ambiguous.value.details == {"candidate_entity_ids": ["ent_a", "ent_b"]}


def test_probe_target_resolver_uses_team_scope_instead_of_the_callers_session():
    creator = "probe-team-owner-" + uuid.uuid4().hex
    team_id = "team-probe-" + uuid.uuid4().hex
    project = create_project(creator, {"name": "Team probes"}, team_id=team_id)
    assert project is not None
    project_id = str(project["id"])
    try:
        target = add_project_target(
            creator,
            project_id,
            {"type": "ip", "value": "192.0.2.25", "review_state": "confirmed"},
            team_id=team_id,
        )
        assert target is not None
        with db_connect() as conn:
            resolved = resolve_probe_target(
                conn,
                "another-team-member",
                team_id,
                ProbePlanRequest(project_id, "nmap", entity_id=str(target["id"])),
            )
        assert resolved == {
            "entity_id": target["id"], "type": "ip", "value": "192.0.2.25",
        }
    finally:
        delete_project(creator, project_id, team_id=team_id)
