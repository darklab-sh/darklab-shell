# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Any, cast

import pytest

import config as app_config
from core.output_nuclei import NUCLEI_JSON_MAX_LINE_BYTES, nuclei_output_metadata
from services.assessments import action_plan_nuclei
from services.assessments.action_plans import build_assessment_action_plan
from services.assessments.service_actions import service_actions, service_evidence_state
from services.assessments import service_action_recommendations
from services.assessments.command_plans import command_plan
from services.assessments.cyclonedx_package_observations import (
    CYCLONEDX_COMPONENT_PARSER_VERSION,
    CYCLONEDX_MAX_PACKAGE_OBSERVATIONS,
    parse_cyclonedx_package_observations,
)
from services.assessments.cyclonedx_cpe_observations import (
    CYCLONEDX_CPE_PARSER_VERSION,
    CYCLONEDX_MAX_CPE_OBSERVATIONS,
    parse_cyclonedx_cpe_observations,
)
from services.assessments.httpx_version_observations import (
    HTTPX_JSON_CPE_PARSER_VERSION,
    normalize_httpx_version_observations,
)
from services.assessments.command_modes import (
    DALFOX_PARAMETER_DISCOVERY_MODE,
    DALFOX_XSS_VALIDATION_MODE,
    assessment_command_mode,
)
from services.assessments.dalfox_parameter_observations import (
    DALFOX_DISCOVERY_PARSER_VERSION,
    DALFOX_JSON_MAX_LINE_BYTES,
    DALFOX_MAX_PARAMETER_OBSERVATIONS,
    DalfoxParameterObservationState,
    dalfox_parameter_observation_id,
)
from services.assessments.dalfox_parameter_evidence import (
    ReviewedDalfoxParameterEvidence,
)
from services.assessments.dalfox_parameter_options import DalfoxParameterOptions
from services.assessments.dalfox_xss_command import (
    DALFOX_XSS_MAX_PAYLOADS_PER_PARAMETER,
    DALFOX_XSS_RATE_LIMIT_PER_SECOND,
    DALFOX_XSS_REQUEST_LIMIT,
    DALFOX_XSS_SCAN_TIMEOUT_SECONDS,
    DALFOX_XSS_TIME_LIMIT_SECONDS,
    DALFOX_XSS_WORKERS,
    reviewed_dalfox_xss_command_matches,
    reviewed_dalfox_xss_command_plan,
)
from services.assessments.dalfox_xss_execution import ReviewedDalfoxXssExecution
from services.assessments.dalfox_xss_actions import DalfoxXssActionContext
from services.assessments.dalfox_xss_observations import (
    DALFOX_XSS_JSON_MAX_LINE_BYTES,
    DALFOX_XSS_MAX_OBSERVATIONS,
    DALFOX_XSS_PARSER_VERSION,
    ReviewedDalfoxXssContext,
)
from services.assessments.dns_takeover_observations import (
    DNSX_MAX_CNAME_CHAIN,
    DNSX_TAKEOVER_PARSER_VERSION,
    normalize_dnsx_takeover_observation,
)
from services.assessments.dns_takeover_correlation import (
    DNSX_TARGET_CORRELATION_VERSION,
    correlate_dnsx_target_observation,
)
from services.assessments.dns_takeover_event_review import build_dnsx_takeover_event_review
from services.assessments.nmap_profiles import (
    EXCLUDED_CATEGORIES,
    nmap_profile_args,
    nmap_profile_keys,
    public_nmap_profile,
)
from services.assessments.nmap_version_observations import parse_nmap_xml_cpe_observations
from services.assessments.nuclei_takeover_identity import NUCLEI_TAKEOVER_JSON_PARSER_VERSION
from services.assessments.nuclei_takeover_observations import ReviewedNucleiTakeoverTemplate
from services.assessments.nuclei_takeover_command import reviewed_takeover_command_plan
from services.assessments.nuclei_recommendation_evidence import (
    NUCLEI_RECOMMENDATION_MAX_RUNS,
    NucleiTargetSignals,
    load_nuclei_recommendation_signals,
)
from services.assessments import nuclei_recommendations
from services.assessments.schemathesis_command import (
    SCHEMATHESIS_MAX_EXAMPLES_PER_OPERATION,
    SCHEMATHESIS_RATE_LIMIT,
    SCHEMATHESIS_TIME_LIMIT_SECONDS,
    reviewed_schemathesis_command_matches,
    reviewed_schemathesis_command_plan,
)
from services.assessments import schemathesis_actions
from services.assessments.schemathesis_actions import (
    SCHEMATHESIS_ARTIFACT_OPTION_LIMIT,
    SchemathesisActionContext,
    schemathesis_action_context,
)
from services.assessments import schemathesis_artifact
from services.assessments.schemathesis_artifact import (
    SchemathesisArtifactError,
    review_project_openapi_artifact,
)
from services.assessments import schemathesis_material
from services.assessments.schemathesis_material import (
    materialize_reviewed_schemathesis_schema,
)
from services.assessments.schemathesis_schema import (
    SCHEMATHESIS_READ_OPERATION_LIMIT,
    SCHEMATHESIS_SCHEMA_MAX_BYTES,
    SchemathesisSchemaError,
    review_local_openapi_json,
)
from services.assessments.schemathesis_execution import ReviewedSchemathesisExecution
from services.assessments.schemathesis_report import (
    SCHEMATHESIS_REPORT_MAX_BYTES,
    parse_schemathesis_ndjson,
)
from services.assessments.schemathesis_report_contracts import (
    SCHEMATHESIS_REPORT_TOOL_VERSION,
    SchemathesisReportError,
)
from services.assessments.schemathesis_report_context import (
    ReviewedSchemathesisReportContext,
)
from services.assessments import schemathesis_launch
from services.assessments import nuclei_takeover_launch
from services.assessments import run_launch
from services.assessments.nuclei_takeover_launch import (
    NUCLEI_TAKEOVER_CHECK_KEY,
    assessment_run_launch_context,
)
from services.assessments.run_launch import materialize_assessment_run_launch
from services.assessments import nuclei_takeover_templates
from services.assessments.nuclei_takeover_templates import (
    NUCLEI_TAKEOVER_TEMPLATE_ID,
    NUCLEI_TAKEOVER_TEMPLATE_VERSION,
    NucleiTakeoverTemplateError,
    reviewed_nuclei_takeover_launch,
)
from services.assessments.takeover_detection import evaluate_takeover_signal
from services.assessments.takeover_confirmation import (
    NUCLEI_TAKEOVER_CONFIRMATION_VERSION,
    confirm_takeover_with_nuclei,
)
from services.assessments.takeover_finding_evidence import (
    TAKEOVER_EVIDENCE_MAX_RUNS,
    project_takeover_evidence,
)
from services.assessments.web_surface import normalize_httpx_screenshot
from services.assessments.version_correlation import correlate_version_observation, materialize_version_findings
from services.assessments.nuclei_profiles import (
    nuclei_profile,
    nuclei_profile_args,
    nuclei_profile_keys,
    public_nuclei_profile,
)
from services.assessments.historical_urls import (
    filter_historical_urls,
    normalize_domain_scoped_historical_urls,
    normalize_historical_url,
    normalize_historical_urls,
    normalize_scope_domain,
)
from services.assessments.web_gallery import (
    filter_web_surface_rows,
    normalize_web_surface_filters,
    web_surface_filters_active,
    web_surface_row_matches,
    web_surface_rows_from_events,
)
from services.runs.finalization import capture_event_with_signals
from services.runs.lifecycle import PreparedRealCommand, start_real_command_process
from services.runs.completion_policy import (
    RunCompletionPolicy,
    completion_policy_for_signal_context,
    effective_run_exit_code,
)
from services.runs.contracts import RunPreparationError
from services.runs.execution_override import apply_reviewed_execution
from services.runs.output_model import to_wire
from services.runs.signal_context import RunOutputSignalContext, output_signal_classifier_kwargs
from services.runs.start import start_brokered_run
from services.runs.start_contracts import RunStartHandlers
from services.intel.epss import normalize_epss_rows
from services.intel.kev import normalize_kev_catalog
from services.nuclei.provenance import nuclei_template_provenance
from services.nuclei import template_health
from services.nuclei.template_cache import (
    NucleiTemplateCacheSnapshot,
    managed_nuclei_template_snapshot,
    nuclei_template_cache_unavailable_reason,
)
from core.output_signals import OutputSignalClassifier
from services.atlas.observations import app_ports_by_host, public_app_port_record
from services.projects.web_surface_comparison import (
    attach_capture_comparisons,
    capture_matches_change_state,
    normalize_change_state,
)


def _source_detail(metadata: dict[str, object]) -> dict[str, Any]:
    detail = metadata.get("source_detail")
    return detail if isinstance(detail, dict) else {}


def _openapi_json(paths=None, **extra):
    document = {
        "openapi": "3.1.0",
        "info": {"title": "Reviewed API", "version": "1.0.0"},
        "paths": paths or {
            "/items": {
                "get": {"responses": {"200": {"description": "OK"}}},
                "post": {"responses": {"201": {"description": "Created"}}},
            },
            "/health": {
                "head": {"responses": {"200": {"description": "OK"}}},
            },
        },
        **extra,
    }
    return json.dumps(document, separators=(",", ":")).encode()


def _openapi_artifact(content):
    return {
        "id": "rfa_0123456789abcdef",
        "session_id": "artifact-owner",
        "run_team_id": "",
        "workspace_path": "reports/openapi.json",
        "byte_size": len(content),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "file_status": "available",
        "file_available": True,
    }


def _schemathesis_report_bytes(
    *,
    failure=True,
    operation="GET /items/{item_id}",
    request_uri="https://api.example.test/v1/items/generated-secret-value",
    tool_version=SCHEMATHESIS_REPORT_TOOL_VERSION,
    seed=1,
    stop_reason="completed",
    check_names=None,
    include_interaction=True,
):
    names = check_names or (
        "not_a_server_error",
        "status_code_conformance",
        "content_type_conformance",
        "response_schema_conformance",
        "negative_data_rejection",
    )
    checks = []
    for name in names:
        check = {"name": name, "status": "success"}
        if failure and name == "response_schema_conformance":
            check = {
                "name": name,
                "status": "failure",
                "failure_info": {
                    "failure": {
                        "type": "JsonSchemaError",
                        "message": "failure-secret-message\nresponse-secret-body",
                    },
                },
            }
        checks.append(check)
    method, path = operation.split(" ", 1)
    case_id = "case_01"
    events = [
        {
            "Initialize": {
                "schemathesis_version": tool_version,
                "seed": seed,
            },
        },
        {
            "ScenarioFinished": {
                "phase": "Fuzzing",
                "status": "failure" if failure else "success",
                "is_final": False,
                "recorder": {
                    "label": operation,
                    "cases": {
                        case_id: {
                            "value": {
                                "method": method,
                                "path": path,
                                "id": case_id,
                                "path_parameters": {
                                    "item_id": "generated-secret-value",
                                },
                                "meta": {
                                    "generation": {"mode": "negative"},
                                    "phase": {"name": "fuzzing"},
                                },
                            },
                            "is_transition_applied": False,
                        },
                    },
                    "checks": {case_id: checks},
                    "interactions": {
                        case_id: {
                            "request": {"method": method, "uri": request_uri},
                            "response": {
                                "status_code": 200,
                                "content": {"$base64": "response-secret-body"},
                            },
                        },
                    } if include_interaction else {},
                },
            },
        },
        {
            "EngineFinished": {
                "running_time": 1.25,
                "stop_reason": stop_reason,
            },
        },
    ]
    return ("\n".join(json.dumps(event, separators=(",", ":")) for event in events) + "\n").encode()


class _ArtifactStream(io.BytesIO):
    def fileno(self):
        return 42


def test_service_actions_require_explicit_service_evidence_and_target_compatibility():
    actions = service_actions("https", port=443, target_type="domain")
    assert [action.key for action in actions] == ["https_profile"]
    assert service_actions("https", port=443, target_type="port") == ()
    assert service_actions(None, port=443, target_type="domain") == ()
    assert service_actions("unknown", port=443, target_type="domain") == ()


def test_service_evidence_does_not_infer_from_port_numbers():
    assert service_evidence_state(None, port=22) == "needs_review"
    assert service_evidence_state("ssh", port=22) == "identified"
    assert service_evidence_state("telnet", port=22) == "unsupported"
    assert service_evidence_state("ssh?", port=22) == "needs_review"


def test_common_protocol_aliases_are_bounded_safe_recommendations():
    actions = service_actions("microsoft-ds", target_type="ip")
    assert [(action.key, action.command, action.policy_level) for action in actions] == [
        ("smb_enumeration", "command:nmap", "standard"),
    ]
    assert actions[0].nmap_profile == "smb"
    assert service_actions("version-cve", target_type="url")[0].command == (
        "evidence:version_cve_correlation"
    )
    assert service_actions("version-cve", target_type="port") == ()


def test_service_actions_can_be_serialized_for_read_surfaces_without_launching():
    action = service_actions("https")[0]
    assert action.command == "command:httpx"
    assert "url" in action.target_types
    record = public_app_port_record({"port": 443, "service": "https", "_run_ids": {"run-1"}})
    assert record["service_evidence_state"] == "identified"
    assert record["assessment_actions"][0]["command"] == "command:httpx"
    assert record["assessment_actions"][0]["required_features"] == [
        "confirmed_project_target", "httpx",
    ]
    assert record["assessment_actions"][0]["expected_evidence"] == [
        "atlas_service_entity", "http_metadata", "tls_metadata",
    ]
    assert record["assessment_actions"][0]["unsupported_conditions"] == [
        "ambiguous_service", "conflicting_service_evidence", "port_only_inference",
    ]
    assert "_run_ids" not in record


def test_nmap_service_actions_expose_the_reviewed_profile_contract():
    record = public_app_port_record({
        "port": 445,
        "service": "microsoft-ds",
        "_run_ids": {"run-1"},
    })

    profile = record["assessment_actions"][0]["nmap_profile"]
    assert profile["key"] == "smb"
    assert profile["label"] == "SMB protocol and signing"
    assert profile["selector_kind"] == "scripts"
    assert profile["selectors"] == [
        "smb-protocols", "smb-security-mode", "smb2-security-mode",
        "smb2-capabilities", "smb-os-discovery",
    ]
    assert profile["script_arguments"] == []
    assert profile["script_argument_file"] is False

    ftp_profile = public_app_port_record({
        "port": 21,
        "service": "ftp",
        "_run_ids": {"run-2"},
    })["assessment_actions"][0]["nmap_profile"]
    assert ftp_profile["label"] == "FTP details and anonymous access"
    assert ftp_profile["fixed_script_arguments"] == ["ftp-anon.maxlist=0"]
    assert ftp_profile["requires_confirmation"] is True


def test_conflicting_service_evidence_abstains_from_action_suggestions():
    record = public_app_port_record({
        "port": 443,
        "proto": "tcp",
        "service": "https",
        "_service_conflict": True,
    })

    assert record["service_evidence_state"] == "needs_review"
    assert "conflicting services" in record["service_evidence_reason"]
    assert "assessment_actions" not in record


def test_duplicate_port_rows_keep_conflicting_services_in_review():
    class FakeConn:
        def execute(self, query, _params):
            if "FROM entities e" in query:
                return SimpleNamespace(fetchall=lambda: [
                    {
                        "id": "ent_https",
                        "host_entity_id": "ent_target",
                        "canonical_value": "app.example.com:443/tcp",
                        "attributes_json": json.dumps({"service": "https"}),
                        "last_seen_at": "2026-08-09T00:00:00+00:00",
                        "occurrence_count": 1,
                        "project_linked": True,
                    },
                    {
                        "id": "ent_ssh",
                        "host_entity_id": "ent_target",
                        "canonical_value": "app.example.com:443/tcp",
                        "attributes_json": json.dumps({"service": "ssh"}),
                        "last_seen_at": "2026-08-08T00:00:00+00:00",
                        "occurrence_count": 1,
                        "project_linked": True,
                    },
                ])
            return SimpleNamespace(fetchall=lambda: [
                {"entity_id": "ent_https", "run_id": "run-1"},
                {"entity_id": "ent_ssh", "run_id": "run-2"},
            ])

    ports = app_ports_by_host(
        FakeConn(), "session-1", "", "project-1", ["ent_target"],
    )["ent_target"]

    assert len(ports) == 1
    assert ports[0]["occurrence_count"] == 2
    assert ports[0]["source_run_count"] == 2
    public = public_app_port_record(ports[0])
    assert public["service_evidence_state"] == "needs_review"
    assert "assessment_actions" not in public


def test_assessment_service_recommendations_are_project_scoped_and_read_only(monkeypatch):
    monkeypatch.setattr(
        service_action_recommendations,
        "app_ports_by_host",
        lambda *_args, **_kwargs: {
            "ent_target": [
                {
                    "port": 443,
                    "proto": "tcp",
                    "service": "https",
                    "version": "nginx 1.26",
                    "_project_linked": True,
                    "_host_total_count": 3,
                },
                {
                    "port": 22,
                    "proto": "tcp",
                    "service": "ssh?",
                    "version": "",
                    "_project_linked": True,
                },
                {
                    "port": 6379,
                    "proto": "tcp",
                    "service": "redis",
                    "version": "",
                    "_project_linked": False,
                },
            ],
        },
    )
    checks: list[dict[str, Any]] = [{
        "target_entity_id": "ent_target",
        "target_type": "domain",
        "target_value": "app.example.com",
    }]

    service_action_recommendations.attach_service_action_recommendations(
        object(), checks, session_id="session-1", team_id="", project_id="project-1",
    )

    result = checks[0]["service_action_recommendations"]
    assert result["action_count"] == 1
    assert result["evidence_count"] == 2
    assert result["needs_review_count"] == 1
    assert result["unsupported_count"] == 0
    assert result["source_truncated"] is True
    assert result["launch_mode"] == "assessment_action_only"
    assert result["auto_launch"] is False
    assert result["actions"][0]["key"] == "https_profile"
    assert result["actions"][0]["port"] == 443


def test_nuclei_recommendation_evidence_is_target_scoped_and_bounded():
    preview = json.dumps([{
        "source_detail": {
            "screenshots": [{
                "url": "https://app.example.com/",
                "technologies": ["nginx:1.26", "React"],
            }],
        },
    }])

    calls: list[tuple[str, tuple[Any, ...]]] = []

    class FakeConn:
        def execute(self, query, params):
            calls.append((query, params))
            if "e.attributes_json" in query:
                return SimpleNamespace(fetchall=lambda: [{
                    "id": "ent_port",
                    "type": "port",
                    "canonical_value": "example.com:443/tcp",
                    "host_entity_id": "ent_target",
                    "attributes_json": json.dumps({"service": "https"}),
                    "host_type": "domain",
                    "host_value": "example.com",
                }])
            if "validation_method = 'version_inference'" in query:
                return SimpleNamespace(fetchall=lambda: [{
                    "id": "fnd_inferred",
                    "entity_type": "domain",
                    "canonical_value": "app.example.com",
                }])
            return SimpleNamespace(fetchall=lambda: [{
                "id": "run_httpx",
                "output_preview": preview,
            }])

    signals = load_nuclei_recommendation_signals(
        FakeConn(),
        "session-1",
        "",
        "project-1",
        [{"entity_id": "ent_target", "type": "domain", "value": "example.com"}],
    )["ent_target"]

    assert signals.technologies == {"React", "nginx:1.26"}
    assert signals.services == {"https"}
    assert signals.inferred_cve_count == 1
    assert signals.dangling_record_count == 0
    assert signals.truncated is False
    run_query, run_params = next(
        (query, params) for query, params in calls if "r.output_preview" in query
    )
    assert "LIKE 'httpx %'" not in run_query
    assert "LIKE 'dnsx %'" not in run_query
    assert run_params[-3:] == (
        "httpx %",
        "dnsx %",
        NUCLEI_RECOMMENDATION_MAX_RUNS + 1,
    )


def test_nuclei_recommendations_explain_signals_without_recommending_intrusive_runs(
    monkeypatch,
):
    signal = NucleiTargetSignals(
        technologies={"nginx:1.26"},
        services={"https"},
        inferred_cve_count=2,
        dangling_record_count=1,
    )
    monkeypatch.setattr(
        nuclei_recommendations,
        "load_nuclei_recommendation_signals",
        lambda *_args, **_kwargs: {"ent_target": signal},
    )
    checks: list[dict[str, Any]] = [
        {
            "check_key": "vulnerability_templates",
            "recommended_action_key": "command:nuclei",
            "target_entity_id": "ent_target",
            "target_type": "domain",
            "target_value": "example.com",
        },
        {
            "check_key": "subdomain_takeover_confirmation",
            "recommended_action_key": "command:nuclei",
            "target_entity_id": "ent_target",
            "target_type": "domain",
            "target_value": "example.com",
        },
        {
            "check_key": "intrusive_template_validation",
            "recommended_action_key": "command:nuclei",
            "target_entity_id": "ent_target",
            "target_type": "domain",
            "target_value": "example.com",
        },
    ]

    nuclei_recommendations.attach_nuclei_recommendations(
        object(), checks, session_id="session-1", team_id="", project_id="project-1",
    )

    standard = checks[0]["nuclei_recommendation"]
    assert standard["recommended"] is True
    assert standard["profile_key"] == "standard"
    assert standard["reason_codes"] == [
        "inferred_cve", "detected_technology", "service_evidence",
    ]
    assert standard["auto_launch"] is False
    assert standard["launch_mode"] == "manual_confirmation_only"
    takeover = checks[1]["nuclei_recommendation"]
    assert takeover["recommended"] is True
    assert takeover["profile_key"] == "safe"
    assert takeover["reason_codes"] == ["dangling_record"]
    intrusive = checks[2]["nuclei_recommendation"]
    assert intrusive["recommended"] is False
    assert intrusive["profile_key"] == "intrusive"
    assert "never recommended automatically" in intrusive["summary"]


def test_nmap_profiles_are_fixed_and_reject_arbitrary_script_arguments():
    assert nmap_profile_args("tls") == ("--script", "ssl-cert,ssl-enum-ciphers")
    assert nmap_profile_args("ftp") == (
        "--script", "ftp-syst,ftp-anon", "--script-args", "ftp-anon.maxlist=0",
    )
    assert nmap_profile_args("--script=exploit") == ()
    assert nmap_profile_args("ssh", script_args={"ssh_hostkey": "all"}) == ()
    assert nmap_profile_args("ssh", script_args_file="nmap-script-args.txt") == ()
    assert nmap_profile_keys() == (
        "safe", "default", "version", "discovery", "vuln", "tls", "ssh", "smtp",
        "smb", "snmp", "ldap", "nfs", "rpc", "ftp", "dns", "mysql", "redis",
        "imap", "pop3",
    )
    smb = public_nmap_profile("smb")
    assert smb["selector_kind"] == "scripts"
    assert smb["selectors"] == [
        "smb-protocols", "smb-security-mode", "smb2-security-mode",
        "smb2-capabilities", "smb-os-discovery",
    ]
    assert smb["evidence_kinds"] == ["smb_dialects", "smb_signing", "smb_identity"]
    assert smb["excluded_category_selectors"] == list(EXCLUDED_CATEGORIES)
    assert smb["fixed_script_arguments"] == []
    assert smb["script_arguments"] == []
    assert smb["script_argument_file"] is False
    ftp = public_nmap_profile("ftp")
    assert ftp["selectors"] == ["ftp-syst", "ftp-anon"]
    assert ftp["evidence_kinds"] == ["ftp_capabilities", "anonymous_access"]
    assert ftp["fixed_script_arguments"] == ["ftp-anon.maxlist=0"]
    assert ftp["requires_confirmation"] is True
    assert not set(ftp["selectors"]) & set(EXCLUDED_CATEGORIES)
    assert public_nmap_profile("vuln")["selectors"] == [
        "ssl-heartbleed", "ssl-poodle", "smb-vuln-ms17-010",
    ]
    assert public_nmap_profile("vuln")["requires_confirmation"] is True
    plan = command_plan("nmap", "ip", "192.0.2.10", nmap_profile="ssh")
    assert plan is not None
    assert "--script ssh2-enum-algos,ssh-hostkey" in plan.command
    ftp_plan = command_plan("nmap", "ip", "192.0.2.10", nmap_profile="ftp")
    assert ftp_plan is not None
    assert "--script ftp-syst,ftp-anon --script-args ftp-anon.maxlist=0" in ftp_plan.command


def test_nuclei_profiles_are_reviewed_explicit_and_safe_by_default(tmp_path, monkeypatch):
    template_dir = tmp_path / "nuclei-templates"
    template_dir.mkdir()
    checksum_rows = (
        f"{template_dir}/http/exposure.yaml,{'a' * 32};"
        f"{template_dir}/ssl/certificate.yaml,{'b' * 32};"
    )
    checksum_path = template_dir / ".checksum"
    checksum_path.write_text(checksum_rows, encoding="utf-8")
    refreshed = datetime(2026, 8, 18, 12, tzinfo=UTC)
    os.utime(checksum_path, (refreshed.timestamp(), refreshed.timestamp()))
    config_path = tmp_path / ".templates-config.json"
    config_path.write_text(json.dumps({
        "nuclei-templates-directory": str(template_dir),
        "nuclei-templates-version": "v10.4.3",
    }), encoding="utf-8")
    template_snapshot = managed_nuclei_template_snapshot(
        template_dir, config_path=config_path,
    )
    assert template_snapshot == NucleiTemplateCacheSnapshot(
        state="ready",
        release_version="v10.4.3",
        content_digest="sha256:b045f0d45961f8defc264a57b85d22e0f2f6dd964c130f2e5f9e5bd30e95a694",
        manifest_entry_count=2,
        refreshed_at="2026-08-18T12:00:00Z",
    )
    health_calls: list[list[str]] = []

    def _healthy_nuclei(args, **_kwargs):
        health_calls.append(args)
        if "-version" in args:
            return subprocess.CompletedProcess(args, 0, "Nuclei Engine Version: v3.4.10", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    template_health.clear_nuclei_template_health_cache()
    monkeypatch.setattr(template_health.subprocess, "run", _healthy_nuclei)
    current_health = template_health.managed_nuclei_template_health(
        template_dir,
        snapshot=template_snapshot,
        binary_path="/usr/local/bin/nuclei",
        current_time=refreshed + timedelta(days=1),
    )
    assert current_health.state == "ready"
    assert current_health.validation_state == "passed"
    assert current_health.nuclei_version == "v3.4.10"
    assert current_health.launchable is True
    assert current_health.public()["refreshed_at"] == "2026-08-18T12:00:00Z"
    assert template_health.managed_nuclei_template_health(
        template_dir,
        snapshot=template_snapshot,
        binary_path="/usr/local/bin/nuclei",
        current_time=refreshed + timedelta(days=1),
    ) == current_health
    assert len(health_calls) == 2
    health_calls.clear()
    prefixed_health = template_health.managed_nuclei_template_health(
        template_dir,
        snapshot=template_snapshot,
        binary_path="/usr/local/bin/nuclei",
        current_time=refreshed + timedelta(days=1),
        run_command=_healthy_nuclei,
        command_prefix=("sudo", "-u", "scanner"),
    )
    assert prefixed_health.launchable is True
    assert health_calls == [
        ["sudo", "-u", "scanner", "/usr/local/bin/nuclei", "-version"],
        [
            "sudo", "-u", "scanner", "/usr/local/bin/nuclei", "-validate",
            "-t", str(template_dir), "-ud", str(template_dir),
            "-disable-update-check", "-no-color", "-silent",
        ],
    ]
    stale_health = template_health.managed_nuclei_template_health(
        template_dir,
        snapshot=template_snapshot,
        binary_path="/usr/local/bin/nuclei",
        current_time=refreshed + timedelta(days=8),
        run_command=_healthy_nuclei,
    )
    assert stale_health.state == "stale"
    assert stale_health.launchable is True
    assert stale_health.reason_code == "template_cache_stale"

    def _incompatible_nuclei(args, **_kwargs):
        return subprocess.CompletedProcess(
            args, 0 if "-version" in args else 1, "v3.4.10", "invalid template",
        )

    incompatible_health = template_health.managed_nuclei_template_health(
        template_dir,
        snapshot=template_snapshot,
        binary_path="/usr/local/bin/nuclei",
        run_command=_incompatible_nuclei,
    )
    assert incompatible_health.state == "incompatible"
    assert incompatible_health.launchable is False
    assert incompatible_health.reason_code == "template_validation_failed"

    def _timed_out_nuclei(args, **_kwargs):
        if "-version" in args:
            return subprocess.CompletedProcess(args, 0, "v3.4.10", "")
        raise subprocess.TimeoutExpired(args, 90)

    unavailable_health = template_health.managed_nuclei_template_health(
        template_dir,
        snapshot=template_snapshot,
        binary_path="/usr/local/bin/nuclei",
        run_command=_timed_out_nuclei,
    )
    assert unavailable_health.state == "unavailable"
    assert unavailable_health.validation_state == "unavailable"
    assert unavailable_health.launchable is False
    missing_health = template_health.managed_nuclei_template_health(
        template_dir,
        snapshot=NucleiTemplateCacheSnapshot("missing"),
        run_command=lambda *_args, **_kwargs: pytest.fail("missing cache must not run Nuclei"),
    )
    assert missing_health.state == "missing"
    assert missing_health.validation_state == "not_run"
    assert missing_health.launchable is False
    config_path.write_text("[]", encoding="utf-8")
    assert managed_nuclei_template_snapshot(
        template_dir, config_path=config_path,
    ).release_version == ""
    assert managed_nuclei_template_snapshot(tmp_path / "missing").state == "missing"
    assert "managed template refresh" in nuclei_template_cache_unavailable_reason(
        NucleiTemplateCacheSnapshot("missing")
    )
    provenance = nuclei_template_provenance(
        "nuclei -u https://example.test",
        template_snapshot=template_snapshot.public(),
    )
    assert provenance["template_snapshot"] == template_snapshot.public()
    monkeypatch.setattr(
        action_plan_nuclei, "managed_nuclei_template_snapshot", lambda: template_snapshot,
    )
    monkeypatch.setattr(
        nuclei_takeover_launch, "managed_nuclei_template_snapshot", lambda: template_snapshot,
    )
    assert nuclei_profile_keys() == ("safe", "standard", "intrusive")
    assert nuclei_profile("unknown").key == "safe"
    safe_args = nuclei_profile_args("safe")
    assert safe_args == (
        "-severity", "high,critical",
        "-tags", "exposure,misconfig,tech,ssl",
        "-type", "http,tcp,ssl",
        "-exclude-tags", "auth,brute,dos,exploit,fuzz,intrusive,oast,dast",
        "-exclude-type", "code,javascript,file,workflow,whois,headless",
        "-no-interactsh", "-disable-redirects", "-disable-update-check",
    )
    intrusive_args = nuclei_profile_args("intrusive")
    assert intrusive_args[-3:] == ("-dast", "-fuzz-aggression", "low")
    assert "-headless" in intrusive_args
    assert "-system-chrome" in intrusive_args
    assert intrusive_args[intrusive_args.index("-headless-options") + 1] == "--no-sandbox"
    assert "exploit" in nuclei_profile("safe").excluded_tags
    assert nuclei_profile("intrusive").requires_confirmation is True
    assert nuclei_profile("safe").template_source == "managed_cache"
    assert public_nuclei_profile("standard") == {
        "key": "standard",
        "label": "Standard vulnerability review",
        "policy_level": "standard",
        "template_source": "managed_cache",
        "template_families": [
            "Exposure", "Misconfiguration", "Known CVEs", "Technology",
            "Network services", "TLS", "API",
        ],
        "excluded_tags": [
            "auth", "brute", "dos", "exploit", "fuzz", "intrusive", "oast", "dast",
        ],
        "excluded_protocols": [
            "code", "javascript", "file", "workflow", "whois", "headless",
        ],
        "headless": False,
        "dast": False,
        "update_policy": "explicit_only",
    }
    safe = command_plan("nuclei", "domain", "example.com")
    standard = command_plan("nuclei", "domain", "example.com", nuclei_profile="standard")
    assert command_plan("nuclei", "domain", "example.com", nuclei_profile="intrusive") is None
    intrusive = command_plan(
        "nuclei", "domain", "example.com", nuclei_profile="intrusive", allow_intrusive=True,
    )
    assert safe is not None
    assert standard is not None
    assert intrusive is not None
    assert "-severity high,critical" in safe.command
    assert "-severity medium,high,critical" in standard.command
    assert "-tags exposure,misconfig,cve,tech,network,ssl,api" in standard.command
    assert "-no-interactsh -disable-redirects -disable-update-check" in standard.command
    assert "-headless" in intrusive.command
    assert "-headless -system-chrome -headless-options --no-sandbox" in intrusive.command
    row = {
        "check_id": "ach_nuclei",
        "assessment_id": "asm_nuclei",
        "check_key": "vulnerability_templates",
        "target_entity_id": "ent_nuclei",
        "target_type": "url",
        "target_value": "https://app.example.test",
        "policy_level": "standard",
        "recommended_action_key": "command:nuclei",
        "profile_key": "web",
        "profile_version": "1.5",
        "profile_snapshot": json.dumps({"checks": [{
            "key": "vulnerability_templates",
            "policy_level": "standard",
            "recommended_action": "command:nuclei",
        }]}),
        "assessment_status": "active",
        "project_status": "active",
    }
    target = {
        "entity_id": "ent_nuclei",
        "type": "url",
        "value": "https://app.example.test",
    }

    plan = build_assessment_action_plan(row, target, "prj_nuclei")

    assert plan["launchable"] is True
    assert plan["nuclei_profile"] == public_nuclei_profile(
        "standard", template_snapshot=template_snapshot.public(),
    )
    assert "-severity medium,high,critical" in plan["display_command"]
    assert "-tags exposure,misconfig,cve,tech,network,ssl,api" in plan["display_command"]
    assert "-type http,tcp,ssl" in plan["display_command"]
    assert "-exclude-tags auth,brute,dos,exploit,fuzz,intrusive,oast,dast" in (
        plan["display_command"]
    )
    assert "-exclude-type code,javascript,file,workflow,whois,headless" in (
        plan["display_command"]
    )
    assert "-no-interactsh -disable-redirects -disable-update-check" in (
        plan["display_command"]
    )
    monkeypatch.setattr(
        action_plan_nuclei,
        "managed_nuclei_template_snapshot",
        lambda: NucleiTemplateCacheSnapshot("missing"),
    )
    unavailable = build_assessment_action_plan(row, target, "prj_nuclei")
    assert unavailable["launchable"] is False
    assert "managed template refresh" in unavailable["unavailable_reason"]
    monkeypatch.setattr(
        action_plan_nuclei, "managed_nuclei_template_snapshot", lambda: template_snapshot,
    )
    launch_context = assessment_run_launch_context(plan)
    assert launch_context.trusted_execution_args == ()
    assert launch_context.output_signal_context == RunOutputSignalContext(
        nuclei_template_snapshot=template_snapshot,
    )
    classifier_kwargs = output_signal_classifier_kwargs(launch_context.output_signal_context)
    assert classifier_kwargs["nuclei_template_snapshot"] is template_snapshot
    line_metadata = nuclei_output_metadata(
        plan["display_command"], "[template-id] finding",
        template_snapshot=template_snapshot,
    )
    template_provenance = cast(dict[str, Any], line_metadata["template_provenance"])
    assert template_provenance["template_snapshot"] == (
        template_snapshot.public()
    )
    intrusive_row = {
        **row,
        "check_id": "ach_nuclei_intrusive",
        "check_key": "intrusive_template_validation",
        "policy_level": "intrusive",
        "profile_snapshot": json.dumps({"checks": [{
            "key": "intrusive_template_validation",
            "policy_level": "intrusive",
            "recommended_action": "command:nuclei",
        }]}),
    }
    disabled = build_assessment_action_plan(
        intrusive_row, target, "prj_nuclei",
    )
    assert disabled["launchable"] is False
    assert "operator opt-in" in disabled["unavailable_reason"]
    monkeypatch.setitem(app_config.CFG, "assessment_intrusive_actions_enabled", True)
    enabled = build_assessment_action_plan(
        intrusive_row,
        target,
        "prj_nuclei",
        intrusive_actions_enabled=True,
    )
    assert enabled["launchable"] is True
    assert enabled["nuclei_profile"]["key"] == "intrusive"
    assert "-headless -system-chrome -headless-options --no-sandbox -dast" in (
        enabled["display_command"]
    )
    assert assessment_run_launch_context(enabled).output_signal_context == (
        RunOutputSignalContext(nuclei_template_snapshot=template_snapshot)
    )
    monkeypatch.setitem(app_config.CFG, "assessment_intrusive_actions_enabled", False)
    with pytest.raises(
        nuclei_takeover_launch.AssessmentActionError,
        match="profile is no longer available",
    ) as gated:
        assessment_run_launch_context(enabled)
    assert gated.value.code == "nuclei_profile_contract_changed"
    monkeypatch.setitem(app_config.CFG, "assessment_intrusive_actions_enabled", True)
    monkeypatch.setattr(
        nuclei_takeover_launch,
        "managed_nuclei_template_snapshot",
        lambda: NucleiTemplateCacheSnapshot(
            "ready", "v10.4.4", "sha256:" + ("c" * 64), 3,
        ),
    )
    with pytest.raises(
        nuclei_takeover_launch.AssessmentActionError,
        match="templates changed after preview",
    ) as changed:
        assessment_run_launch_context(plan)
    assert changed.value.code == "nuclei_template_cache_changed"


def test_managed_nuclei_refresh_swaps_only_a_validated_stage(tmp_path, monkeypatch):
    from services.nuclei import template_refresh_worker as worker

    volume = tmp_path / "nuclei-templates"
    volume.mkdir()
    live = volume / "current"
    live.mkdir()
    old_manifest = f"{live}/http/old.yaml,{'a' * 32};"
    (live / ".checksum").write_text(old_manifest, encoding="utf-8")
    live_config_dir = tmp_path / "live-config"
    live_config_dir.mkdir()
    live_config = live_config_dir / ".templates-config.json"
    live_config.write_text(json.dumps({
        "nuclei-templates-directory": str(live),
        "nuclei-templates-version": "v10.4.6",
    }), encoding="utf-8")
    monkeypatch.setattr(worker, "MANAGED_TEMPLATE_DIR", str(live))
    monkeypatch.setenv("NUCLEI_CONFIG_DIR", str(live_config_dir))

    validation_return_code = 0

    def fake_run(args, **kwargs):
        if "-update-templates" in args:
            stage = Path(args[args.index("-ud") + 1])
            (stage / "http").mkdir(exist_ok=True)
            (stage / ".checksum").write_text(
                f"{stage}/http/new.yaml,{'b' * 32};",
                encoding="utf-8",
            )
            config = Path(kwargs["env"]["XDG_CONFIG_HOME"]) / "nuclei" / ".templates-config.json"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(json.dumps({
                "nuclei-templates-directory": str(stage),
                "nuclei-templates-version": "v10.4.7",
            }), encoding="utf-8")
            return subprocess.CompletedProcess(args, 0)
        return subprocess.CompletedProcess(args, validation_return_code)

    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    stage = tmp_path / "stage-success"
    stage.mkdir()
    config_root = tmp_path / "config-success"
    config_root.mkdir()
    updated = worker._run("/usr/local/bin/nuclei", stage, config_root)

    assert updated["status"] == "updated"
    assert updated["release_version"] == "v10.4.7"
    assert "new.yaml" in (live / ".checksum").read_text(encoding="utf-8")
    installed_config = json.loads(live_config.read_text(encoding="utf-8"))
    assert installed_config["nuclei-templates-directory"] == str(live)
    installed_snapshot = managed_nuclei_template_snapshot(
        live,
        config_path=live_config,
        acquire_lock=False,
    )
    assert installed_snapshot.state == "ready"
    assert installed_snapshot.release_version == "v10.4.7"

    installed_manifest = (live / ".checksum").read_text(encoding="utf-8")
    validation_return_code = 1
    failed_stage = tmp_path / "stage-failure"
    failed_stage.mkdir()
    failed_config = tmp_path / "config-failure"
    failed_config.mkdir()
    failed = worker._run("/usr/local/bin/nuclei", failed_stage, failed_config)

    assert failed == {"status": "failed", "reason_code": "staged_cache_incompatible"}
    assert (live / ".checksum").read_text(encoding="utf-8") == installed_manifest


def test_nuclei_refresh_is_locked_bounded_and_wraps_scan_processes(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from services.nuclei import template_lock, template_refresh
    from services.nuclei.template_lock import (
        NucleiTemplateLockBusy,
        managed_nuclei_template_lock,
    )
    from services.runs.lifecycle import real_command_popen_argv

    existing_lock_path = tmp_path / "existing-nuclei.lock"
    existing_lock_path.touch(mode=0o660)
    real_open = template_lock.os.open
    existing_open_flags = []

    def record_existing_open(path, flags, mode=0o777):
        existing_open_flags.append(flags)
        return real_open(path, flags, mode)

    with monkeypatch.context() as lock_patch:
        lock_patch.setattr(template_lock.os, "open", record_existing_open)
        with managed_nuclei_template_lock(
            exclusive=False,
            lock_path=existing_lock_path,
        ):
            pass

    assert len(existing_open_flags) == 1
    assert not existing_open_flags[0] & template_lock.os.O_CREAT

    created_lock_path = tmp_path / "created-nuclei.lock"
    created_open_flags = []

    def record_created_open(path, flags, mode=0o777):
        created_open_flags.append(flags)
        return real_open(path, flags, mode)

    with monkeypatch.context() as lock_patch:
        lock_patch.setattr(template_lock.os, "open", record_created_open)
        with managed_nuclei_template_lock(
            exclusive=False,
            lock_path=created_lock_path,
        ):
            pass

    assert len(created_open_flags) == 2
    assert not created_open_flags[0] & template_lock.os.O_CREAT
    assert created_open_flags[1] & template_lock.os.O_CREAT
    assert created_open_flags[1] & template_lock.os.O_EXCL

    unsafe_lock_path = tmp_path / "unsafe-nuclei.lock"
    unsafe_lock_path.symlink_to(existing_lock_path)
    with pytest.raises(template_lock.NucleiTemplateLockError):
        with managed_nuclei_template_lock(
            exclusive=False,
            lock_path=unsafe_lock_path,
        ):
            pytest.fail("a symlink must not be accepted as the lock file")

    lock_path = tmp_path / "nuclei.lock"
    with managed_nuclei_template_lock(exclusive=True, lock_path=lock_path):
        with pytest.raises(NucleiTemplateLockBusy):
            with managed_nuclei_template_lock(
                exclusive=False,
                lock_path=lock_path,
            ):
                pytest.fail("a scan lock must not cross maintenance")

    @contextmanager
    def fake_lock(**_kwargs):
        yield 1

    monkeypatch.setattr(template_refresh, "managed_nuclei_template_lock", fake_lock)
    monkeypatch.setattr(template_refresh, "SCANNER_PREFIX", [])
    monkeypatch.setenv("NUCLEI_TEMPLATE_REFRESH_ENABLED", "true")
    calls = []

    def fake_worker(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args,
            0,
            json.dumps({
                "status": "updated",
                "release_version": "v10.4.7",
                "content_digest": "sha256:" + "c" * 64,
            }),
            "",
        )

    refreshed = template_refresh.refresh_managed_nuclei_templates(
        active_batch_exists=lambda: False,
        run_command=fake_worker,
    )
    assert refreshed["status"] == "updated"
    assert calls[0][0][-2:] == ["-m", "services.nuclei.template_refresh_worker"]
    assert calls[0][1]["stderr"] is subprocess.DEVNULL

    def failed_worker(args, **_kwargs):
        return subprocess.CompletedProcess(
            args,
            1,
            json.dumps({"status": "failed", "reason_code": "template_install_failed"}),
            "",
        )

    with pytest.raises(
        template_refresh.NucleiTemplateRefreshError,
        match="couldn't be installed",
    ):
        template_refresh.refresh_managed_nuclei_templates(
            active_batch_exists=lambda: False,
            run_command=failed_worker,
        )

    with pytest.raises(template_refresh.NucleiTemplateRefreshError) as active:
        template_refresh.refresh_managed_nuclei_templates(
            active_batch_exists=lambda: True,
            run_command=lambda *_args, **_kwargs: pytest.fail("worker must not run"),
        )
    assert active.value.code == "nuclei_template_refresh_batch_active"

    prepared = PreparedRealCommand(
        registry_command="nuclei -u https://app.example.test",
        execution_command="nuclei -u https://app.example.test",
        command="nuclei -ud /tmp/nuclei-templates/current -u https://app.example.test",
        rewrite_notice=None,
        validation=cast(Any, None),
        missing_runtime=None,
        display_missing_runtime=None,
        env_overrides={},
        secret_env_names=[],
    )
    digest = "sha256:" + "d" * 64
    argv = real_command_popen_argv(
        prepared,
        nuclei_template_digest=digest,
        scanner_prefix=(),
        stdbuf_bin=None,
        shell_bin="/bin/sh",
    )
    assert argv[1:4] == ["-m", "services.nuclei.template_run", "--expected-digest"]
    assert argv[4:6] == [digest, "--"]
    assert argv[-3:] == ["/bin/sh", "-c", prepared.command]


def test_local_openapi_review_keeps_only_bounded_read_operations_and_internal_refs():
    content = _openapi_json(
        servers=[{"url": "/v1"}],
        components={
            "schemas": {
                "Item": {"type": "object"},
                "Envelope": {"$ref": "#/components/schemas/Item"},
                "ServerList": {
                    "type": "object",
                    "properties": {"servers": {"type": "array"}},
                },
            },
        },
    )

    reviewed = review_local_openapi_json(
        content,
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1/",
    )

    assert reviewed.base_url == "https://api.example.test/v1"
    assert reviewed.schema_version == "3.1.0"
    assert reviewed.operations == ("GET /items", "HEAD /health")
    assert reviewed.operation_count == 2
    assert len(reviewed.source_sha256) == 64
    assert reviewed.content == content


@pytest.mark.parametrize(
    ("content", "error_code"),
    [
        (
            _openapi_json(components={
                "schemas": {"Item": {"$ref": "https://schemas.example.test/item.json"}},
            }),
            "external_schema_reference",
        ),
        (
            _openapi_json(servers=[{"url": "https://other.example.test/v1"}]),
            "schema_server_out_of_scope",
        ),
        (
            _openapi_json(paths={
                "/items": {
                    "get": {
                        "servers": [{"url": "https://other.example.test/v1"}],
                        "responses": {"200": {"description": "OK"}},
                    },
                },
            }),
            "schema_server_out_of_scope",
        ),
        (
            _openapi_json(components={
                "schemas": {"Item": {"$id": "https://other.example.test/"}},
            }),
            "schema_base_override",
        ),
        (
            _openapi_json(paths={
                "/items": {"post": {"responses": {"201": {"description": "Created"}}}},
            }),
            "no_read_operations",
        ),
        (
            _openapi_json(paths={
                f"/item/{index}": {
                    "get": {"responses": {"200": {"description": "OK"}}},
                }
                for index in range(SCHEMATHESIS_READ_OPERATION_LIMIT + 1)
            }),
            "operation_limit_exceeded",
        ),
        (
            b'{"openapi":"3.1.0","info":{},"paths":{},"paths":{}}',
            "duplicate_schema_key",
        ),
        (
            b'{"openapi":"3.1.0","info":{"x":NaN},"paths":{}}',
            "invalid_openapi_json",
        ),
        (
            _openapi_json(servers=[{"url": "/v1/%2e%2e/admin"}]),
            "invalid_schema_server",
        ),
    ],
)
def test_local_openapi_review_rejects_fetch_and_execution_scope_expansion(content, error_code):
    with pytest.raises(SchemathesisSchemaError) as exc_info:
        review_local_openapi_json(
            content,
            source_artifact_id="rfa_0123456789abcdef",
            base_url="https://api.example.test/v1",
        )

    assert exc_info.value.code == error_code


def test_local_openapi_review_rejects_byte_depth_and_decoded_node_limit_expansion():
    too_deep = {"leaf": True}
    for _ in range(70):
        too_deep = {"nested": too_deep}

    rejected = (
        (b" " * (SCHEMATHESIS_SCHEMA_MAX_BYTES + 1), "invalid_schema_size"),
        (_openapi_json(components=too_deep), "schema_complexity_exceeded"),
        (
            _openapi_json(components={"schemas": {"Many": {"enum": list(range(50_001))}}}),
            "schema_complexity_exceeded",
        ),
    )
    for content, error_code in rejected:
        with pytest.raises(SchemathesisSchemaError) as exc_info:
            review_local_openapi_json(
                content,
                source_artifact_id="rfa_0123456789abcdef",
                base_url="https://api.example.test/v1",
            )

        assert exc_info.value.code == error_code


def test_schemathesis_report_keeps_bounded_operation_evidence_and_provenance():
    reviewed = review_local_openapi_json(
        _openapi_json(paths={
            "/items/{item_id}": {
                "get": {"responses": {"200": {"description": "OK"}}},
            },
            "/health": {
                "head": {"responses": {"200": {"description": "OK"}}},
            },
        }),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )

    report = parse_schemathesis_ndjson(
        _schemathesis_report_bytes(failure=False),
        reviewed,
        profile_key="api",
        profile_version="1.0",
    )

    assert report.tool_version == SCHEMATHESIS_REPORT_TOOL_VERSION
    assert report.profile_key == "api"
    assert report.profile_version == "1.0"
    assert report.schema_artifact_id == reviewed.source_artifact_id
    assert report.schema_sha256 == reviewed.source_sha256
    assert report.schema_version == "3.1.0"
    assert report.stop_reason == "completed"
    assert report.complete is True
    assert report.expected_operation_count == 2
    assert report.observed_operation_count == 1
    assert report.case_count == 1
    assert report.failure_count == 0
    assert report.missing_operations == ("HEAD /health",)
    assert report.operations[0].operation == "GET /items/{item_id}"
    assert report.operations[0].status == "success"
    assert report.operations[0].response_statuses == (200,)
    assert report.operations[0].failures == ()


def test_schemathesis_report_keeps_safe_failure_shape_without_private_values():
    reviewed = review_local_openapi_json(
        _openapi_json(paths={
            "/items/{item_id}": {
                "get": {"responses": {"200": {"description": "OK"}}},
            },
        }),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )

    report = parse_schemathesis_ndjson(
        _schemathesis_report_bytes(stop_reason="failure_limit"),
        reviewed,
        profile_key="api",
        profile_version="1.0",
    )

    assert report.complete is True
    assert report.failure_count == 1
    assert report.operations[0].status == "failure"
    failure = report.operations[0].failures[0]
    assert failure.check_name == "response_schema_conformance"
    assert failure.failure_type == "JsonSchemaError"
    assert failure.title == "Response violates schema"
    assert failure.severity == "medium"
    assert failure.response_status == 200
    assert failure.parameter_names == ("path:item_id",)
    assert len(failure.fingerprint) == 64
    assert len(failure.example_digest) == 64
    assert len(failure.message_digest) == 64
    public_result = repr(report)
    assert "generated-secret-value" not in public_result
    assert "failure-secret-message" not in public_result
    assert "response-secret-body" not in public_result


@pytest.mark.parametrize(
    ("raw_report", "error_code"),
    [
        (_schemathesis_report_bytes()[:-1], "incomplete_report"),
        (
            _schemathesis_report_bytes(tool_version="4.24.4"),
            "unsupported_report_version",
        ),
        (
            _schemathesis_report_bytes(seed=2),
            "unsupported_report_version",
        ),
        (
            _schemathesis_report_bytes(seed=True),
            "unsupported_report_version",
        ),
        (
            _schemathesis_report_bytes(request_uri="https://other.example.test/v1/items/1"),
            "interaction_out_of_scope",
        ),
        (
            _schemathesis_report_bytes(request_uri="https://api.example.test/v1/other"),
            "interaction_out_of_scope",
        ),
        (
            _schemathesis_report_bytes(check_names=("not_a_server_error",)),
            "incomplete_check_set",
        ),
        (
            _schemathesis_report_bytes(failure=False, stop_reason="failure_limit"),
            "invalid_stop_reason",
        ),
        (
            _schemathesis_report_bytes().replace(
                b'"status":"failure"',
                b'"status":"success"',
                1,
            ),
            "scenario_result_mismatch",
        ),
        (
            _schemathesis_report_bytes(include_interaction=False),
            "missing_case_interaction",
        ),
        (b" " * (SCHEMATHESIS_REPORT_MAX_BYTES + 1), "invalid_report_size"),
    ],
)
def test_schemathesis_report_rejects_incomplete_unpinned_or_out_of_scope_evidence(
    raw_report,
    error_code,
):
    reviewed = review_local_openapi_json(
        _openapi_json(paths={
            "/items/{item_id}": {
                "get": {"responses": {"200": {"description": "OK"}}},
            },
        }),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )

    with pytest.raises(SchemathesisReportError) as exc_info:
        parse_schemathesis_ndjson(
            raw_report,
            reviewed,
            profile_key="api",
            profile_version="1.0",
        )

    assert exc_info.value.code == error_code


def test_schemathesis_report_rejects_duplicate_keys_and_unreviewed_operations():
    reviewed = review_local_openapi_json(
        _openapi_json(paths={
            "/items/{item_id}": {
                "get": {"responses": {"200": {"description": "OK"}}},
            },
        }),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )
    duplicate_key = _schemathesis_report_bytes().replace(
        b'"seed":1',
        b'"seed":1,"seed":1',
        1,
    )
    missing_case_events = [
        json.loads(line)
        for line in _schemathesis_report_bytes().splitlines()
    ]
    missing_case_recorder = missing_case_events[1]["ScenarioFinished"]["recorder"]
    missing_case_recorder["cases"] = {}
    missing_case_recorder["checks"] = {}
    missing_case_recorder["interactions"] = {}
    missing_cases = (
        "\n".join(
            json.dumps(event, separators=(",", ":"))
            for event in missing_case_events
        )
        + "\n"
    ).encode()
    rejected = (
        (duplicate_key, "duplicate_report_key"),
        (missing_cases, "missing_scenario_cases"),
        (
            _schemathesis_report_bytes(
                operation="GET /admin",
                request_uri="https://api.example.test/v1/admin",
            ),
            "operation_out_of_scope",
        ),
    )

    for raw_report, error_code in rejected:
        with pytest.raises(SchemathesisReportError) as exc_info:
            parse_schemathesis_ndjson(
                raw_report,
                reviewed,
                profile_key="api",
                profile_version="1.0",
            )

        assert exc_info.value.code == error_code

    with pytest.raises(SchemathesisReportError) as invalid_profile:
        parse_schemathesis_ndjson(
            _schemathesis_report_bytes(),
            reviewed,
            profile_key="api",
            profile_version=cast(Any, 1),
        )

    assert invalid_profile.value.code == "invalid_profile_provenance"


def test_schemathesis_report_applies_the_failure_limit_across_operations():
    reviewed = review_local_openapi_json(
        _openapi_json(paths={
            "/items/{item_id}": {
                "get": {"responses": {"200": {"description": "OK"}}},
            },
            "/users/{user_id}": {
                "get": {"responses": {"200": {"description": "OK"}}},
            },
        }),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )
    scenarios = []
    for index in range(12):
        resource = "items" if index % 2 == 0 else "users"
        parameter = "item_id" if resource == "items" else "user_id"
        operation = f"GET /{resource}/{{{parameter}}}"
        event = json.loads(
            _schemathesis_report_bytes(
                operation=operation,
                request_uri=f"https://api.example.test/v1/{resource}/{index}",
            ).splitlines()[1]
        )
        recorder = event["ScenarioFinished"]["recorder"]
        case_id = f"case_{index:02}"
        case = recorder["cases"].pop("case_01")
        case["value"]["id"] = case_id
        case["value"]["path_parameters"] = {parameter: index}
        checks = recorder["checks"].pop("case_01")
        checks[3]["failure_info"]["failure"]["message"] = f"failure {index}"
        interaction = recorder["interactions"].pop("case_01")
        recorder["cases"][case_id] = case
        recorder["checks"][case_id] = checks
        recorder["interactions"][case_id] = interaction
        scenarios.append(event)
    events = [
        {
            "Initialize": {
                "schemathesis_version": SCHEMATHESIS_REPORT_TOOL_VERSION,
                "seed": 1,
            },
        },
        *scenarios,
        {
            "EngineFinished": {
                "running_time": 2.5,
                "stop_reason": "failure_limit",
            },
        },
    ]
    raw_report = (
        "\n".join(json.dumps(event, separators=(",", ":")) for event in events)
        + "\n"
    ).encode()

    with pytest.raises(SchemathesisReportError) as exc_info:
        parse_schemathesis_ndjson(
            raw_report,
            reviewed,
            profile_key="api",
            profile_version="1.0",
        )

    assert exc_info.value.code == "failure_limit_exceeded"


def test_project_openapi_artifact_review_rechecks_owner_file_size_and_digest(monkeypatch):
    content = _openapi_json()
    artifact = _openapi_artifact(content)
    calls = {}
    owner = object()

    def get_artifact(session_id, project_id, artifact_id, *, team_id=""):
        calls["query"] = (session_id, project_id, artifact_id, team_id)
        return artifact

    def open_artifact(owner_context, workspace_path):
        calls["open"] = (owner_context, workspace_path)
        return _ArtifactStream(content)

    monkeypatch.setattr(schemathesis_artifact, "get_project_run_file_artifact", get_artifact)
    monkeypatch.setattr(schemathesis_artifact, "artifact_owner_context", lambda *_args: owner)
    monkeypatch.setattr(schemathesis_artifact, "open_owner_workspace_file_for_download", open_artifact)
    monkeypatch.setattr(schemathesis_artifact.os, "fstat", lambda _fd: SimpleNamespace(st_size=len(content)))

    reviewed = review_project_openapi_artifact(
        "viewer-session",
        "prj_reviewed",
        artifact["id"],
        base_url="https://api.example.test/v1",
        team_id="team_reviewed",
    )

    assert calls["query"] == (
        "viewer-session",
        "prj_reviewed",
        artifact["id"],
        "team_reviewed",
    )
    assert calls["open"] == (owner, "reports/openapi.json")
    assert reviewed.source_artifact_id == artifact["id"]
    assert reviewed.source_sha256 == artifact["content_sha256"]
    assert reviewed.operations == ("GET /items", "HEAD /health")


@pytest.mark.parametrize(
    ("artifact_update", "descriptor_size_delta", "error_code"),
    [
        ({"file_status": "changed"}, 0, "schema_artifact_unavailable"),
        ({"content_sha256": ""}, 0, "schema_artifact_digest_missing"),
        ({"byte_size": 0}, 0, "schema_artifact_size_invalid"),
        ({"byte_size": SCHEMATHESIS_SCHEMA_MAX_BYTES + 1}, 0, "schema_artifact_size_invalid"),
        ({}, 1, "schema_artifact_changed"),
        ({"content_sha256": "0" * 64}, 0, "schema_artifact_changed"),
    ],
)
def test_project_openapi_artifact_review_rejects_unavailable_or_changed_files(
    monkeypatch,
    artifact_update,
    descriptor_size_delta,
    error_code,
):
    content = _openapi_json()
    artifact = {**_openapi_artifact(content), **artifact_update}
    monkeypatch.setattr(schemathesis_artifact, "get_project_run_file_artifact", lambda *_args, **_kwargs: artifact)
    monkeypatch.setattr(schemathesis_artifact, "artifact_owner_context", lambda *_args: object())
    monkeypatch.setattr(
        schemathesis_artifact,
        "open_owner_workspace_file_for_download",
        lambda *_args: _ArtifactStream(content),
    )
    monkeypatch.setattr(
        schemathesis_artifact.os,
        "fstat",
        lambda _fd: SimpleNamespace(st_size=len(content) + descriptor_size_delta),
    )

    with pytest.raises(SchemathesisArtifactError) as exc_info:
        review_project_openapi_artifact(
            "viewer-session",
            "prj_reviewed",
            artifact["id"],
            base_url="https://api.example.test/v1",
        )

    assert exc_info.value.code == error_code


def test_project_openapi_artifact_review_hides_cross_project_and_read_failures(monkeypatch):
    monkeypatch.setattr(schemathesis_artifact, "get_project_run_file_artifact", lambda *_args, **_kwargs: None)
    with pytest.raises(SchemathesisArtifactError) as not_found:
        review_project_openapi_artifact(
            "viewer-session",
            "prj_other",
            "rfa_0123456789abcdef",
            base_url="https://api.example.test",
        )
    assert not_found.value.code == "schema_artifact_not_found"

    content = _openapi_json()
    wrong_artifact = {**_openapi_artifact(content), "id": "rfa_fedcba9876543210"}
    monkeypatch.setattr(
        schemathesis_artifact,
        "get_project_run_file_artifact",
        lambda *_args, **_kwargs: wrong_artifact,
    )
    with pytest.raises(SchemathesisArtifactError) as mismatched:
        review_project_openapi_artifact(
            "viewer-session",
            "prj_reviewed",
            "rfa_0123456789abcdef",
            base_url="https://api.example.test",
        )
    assert mismatched.value.code == "schema_artifact_not_found"

    monkeypatch.setattr(
        schemathesis_artifact,
        "get_project_run_file_artifact",
        lambda *_args, **_kwargs: _openapi_artifact(content),
    )
    monkeypatch.setattr(schemathesis_artifact, "artifact_owner_context", lambda *_args: object())
    monkeypatch.setattr(
        schemathesis_artifact,
        "open_owner_workspace_file_for_download",
        lambda *_args: (_ for _ in ()).throw(OSError("unavailable")),
    )
    with pytest.raises(SchemathesisArtifactError) as unavailable:
        review_project_openapi_artifact(
            "viewer-session",
            "prj_reviewed",
            "rfa_0123456789abcdef",
            base_url="https://api.example.test",
        )
    assert unavailable.value.code == "schema_artifact_unavailable"


def test_reviewed_schemathesis_schema_materializes_private_schema_and_report(monkeypatch):
    reviewed = review_local_openapi_json(
        _openapi_json(),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test",
    )
    writes = []

    class FakeMaterial:
        path = Path("/tmp/private-http-runs/run-0123456789abcdef")

        def __init__(self, *, cfg=None):
            self.cfg = cfg

        def write_bytes(self, name, content):
            writes.append((name, content))
            return self.path / name

        def read_bytes(self, name, *, max_bytes):
            writes.append(("read", name.encode(), max_bytes))
            return b"report"

        def cleanup(self):
            writes.append(("cleanup", b""))

    monkeypatch.setattr(schemathesis_material, "PrivateHttpRunMaterial", FakeMaterial)

    material = materialize_reviewed_schemathesis_schema(reviewed, cfg={"data_dir": "/private"})

    assert material.schema == reviewed
    assert writes == [
        ("schema.json", reviewed.content),
        (
            "schemathesis.toml",
            b'[cache]\nenabled = false\n\n[generation]\ndatabase = "none"\n',
        ),
        ("events.ndjson", b""),
    ]
    assert material.schema_path == FakeMaterial.path / "schema.json"
    assert material.config_path == FakeMaterial.path / "schemathesis.toml"
    assert material.report_path == FakeMaterial.path / "events.ndjson"
    assert material.private_values == tuple(map(str, (
        material.schema_path,
        material.config_path,
        material.report_path,
    )))
    assert material.read_report() == b"report"
    assert writes[-1] == ("read", b"events.ndjson", SCHEMATHESIS_REPORT_MAX_BYTES)
    assert reviewed_schemathesis_command_plan(
        material.schema,
        schema_path=material.schema_path,
        config_path=material.config_path,
        report_path=material.report_path,
    ) is not None
    material.cleanup()
    assert writes[-1] == ("cleanup", b"")


def test_schemathesis_materialization_requires_review_and_cleans_partial_files(monkeypatch):
    with pytest.raises(SchemathesisArtifactError) as unreviewed:
        materialize_reviewed_schemathesis_schema(
            cast(Any, SimpleNamespace(content=_openapi_json()))
        )
    assert unreviewed.value.code == "schema_review_required"

    reviewed = review_local_openapi_json(
        _openapi_json(),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test",
    )
    cleaned = []

    class FailingMaterial:
        path = Path("/tmp/private-http-runs/run-0123456789abcdef")

        def __init__(self, *, cfg=None):
            self.write_count = 0

        def write_bytes(self, name, content):
            self.write_count += 1
            if self.write_count == 2:
                raise OSError("full")
            return self.path / name

        def cleanup(self):
            cleaned.append(True)

    monkeypatch.setattr(schemathesis_material, "PrivateHttpRunMaterial", FailingMaterial)
    with pytest.raises(SchemathesisArtifactError) as failed:
        materialize_reviewed_schemathesis_schema(reviewed)
    assert failed.value.code == "schemathesis_materialization_failed"
    assert cleaned == [True]


def test_reviewed_schemathesis_command_is_exact_read_only_and_request_bounded():
    reviewed = review_local_openapi_json(
        _openapi_json(),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )

    display = reviewed_schemathesis_command_plan(reviewed)
    assert display is not None
    assert display.request_limit == 2 * SCHEMATHESIS_MAX_EXAMPLES_PER_OPERATION == 20
    assert display.time_limit_seconds == SCHEMATHESIS_TIME_LIMIT_SECONDS == 300
    assert display.command.startswith(
        "schemathesis --config-file [protected-config] run [protected-schema]"
    )
    assert "--include-method GET --include-method HEAD" in display.command
    assert "--phases fuzzing" in display.command
    assert "--mode negative" in display.command
    assert f"--rate-limit {SCHEMATHESIS_RATE_LIMIT}" in display.command
    assert "--max-redirects 0 --request-timeout 10 --request-retries 0" in display.command
    assert "--workers 1" in display.command
    assert "--max-failures 10" in display.command
    assert "--report ndjson --report-ndjson-path [protected-report]" in display.command
    assert "--generation-database none" in display.command
    assert "--generation-deterministic --no-color" in display.command
    assert "POST" not in display.command

    schema_path = "/tmp/private-http-runs/run-0123456789abcdef/schema.json"
    config_path = "/tmp/private-http-runs/run-0123456789abcdef/schemathesis.toml"
    report_path = "/tmp/private-http-runs/run-0123456789abcdef/events.ndjson"
    execution = reviewed_schemathesis_command_plan(
        reviewed,
        schema_path=schema_path,
        config_path=config_path,
        report_path=report_path,
    )
    assert execution is not None
    assert schema_path in execution.command
    assert config_path in execution.command
    assert report_path in execution.command
    assert reviewed_schemathesis_command_matches(
        execution.command,
        reviewed,
        schema_path=schema_path,
        config_path=config_path,
        report_path=report_path,
    )
    assert not reviewed_schemathesis_command_matches(
        execution.command + " --include-method POST",
        reviewed,
        schema_path=schema_path,
        config_path=config_path,
        report_path=report_path,
    )


def test_reviewed_schemathesis_command_rejects_unreviewed_or_unprotected_material_paths():
    reviewed = review_local_openapi_json(
        _openapi_json(),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test",
    )

    assert reviewed_schemathesis_command_plan(
        cast(Any, SimpleNamespace(**reviewed.__dict__))
    ) is None
    assert reviewed_schemathesis_command_plan(
        reviewed,
        schema_path="/tmp/schema.json",
        config_path="/tmp/schemathesis.toml",
        report_path="/tmp/events.ndjson",
    ) is None
    assert reviewed_schemathesis_command_plan(
        reviewed,
        schema_path="/tmp/run-a/schema.json",
        config_path="/tmp/run-a/schemathesis.toml",
        report_path="/tmp/run-a/events.ndjson",
    ) is None
    assert reviewed_schemathesis_command_plan(
        reviewed,
        schema_path="/tmp/private-http-runs/run-a/schema.json",
        config_path="/tmp/private-http-runs/run-a/schemathesis.toml",
        report_path="/tmp/private-http-runs/run-b/events.ndjson",
    ) is None
    assert reviewed_schemathesis_command_plan(
        reviewed,
        schema_path="/tmp/private-http-runs/run-a/other.json",
        config_path="/tmp/private-http-runs/run-a/schemathesis.toml",
        report_path="/tmp/private-http-runs/run-a/events.ndjson",
    ) is None


def test_schemathesis_action_requires_one_reviewed_saved_artifact():
    reviewed = review_local_openapi_json(
        _openapi_json(),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )
    option = {
        "artifact_id": reviewed.source_artifact_id,
        "run_id": "run_openapi",
        "name": "openapi.json",
        "byte_size": len(reviewed.content),
        "content_type": "application/json",
        "recorded_sha256": reviewed.source_sha256,
        "created": "2026-08-08T00:00:00+00:00",
    }
    row = {
        "check_id": "ach_api",
        "assessment_id": "asm_api",
        "check_key": "openapi_negative_testing",
        "target_entity_id": "ent_api",
        "target_type": "url",
        "target_value": reviewed.base_url,
        "policy_level": "standard",
        "recommended_action_key": "command:schemathesis",
        "profile_key": "api",
        "profile_version": "1.0",
        "profile_snapshot": json.dumps({"checks": [{
            "key": "openapi_negative_testing",
            "policy_level": "standard",
            "recommended_action": "command:schemathesis",
        }]}),
        "assessment_status": "active",
        "project_status": "active",
    }
    target = {"entity_id": "ent_api", "type": "url", "value": reviewed.base_url}
    choose = build_assessment_action_plan(
        row,
        target,
        "prj_api",
        schemathesis=SchemathesisActionContext(
            (option,), None, None, False, False, False,
        ),
    )

    assert choose["launchable"] is False
    assert choose["unavailable_reason"].startswith("Choose one saved OpenAPI JSON")
    assert choose["artifact_selection"] == {
        "kind": "project_openapi_artifact",
        "required": True,
        "overflow": False,
        "options": [option],
        "selected": None,
    }

    selected = SchemathesisActionContext(
        (option,), option, reviewed, True, False, False,
    )
    plan = build_assessment_action_plan(
        row,
        target,
        "prj_api",
        schemathesis=selected,
    )

    assert plan["launchable"] is True
    reviewed_plan = reviewed_schemathesis_command_plan(reviewed)
    assert reviewed_plan is not None
    assert plan["display_command"] == reviewed_plan.command
    assert plan["bounds"]["request_limit"] == 20
    assert plan["bounds"]["time_limit_seconds"] == 300
    assert plan["artifact_selection"]["selected"] == {
        **option,
        "openapi_version": "3.1.0",
        "operation_count": 2,
        "schema_sha256": reviewed.source_sha256,
    }


def test_schemathesis_action_options_are_bounded_and_selected_in_project_scope(monkeypatch):
    reviewed = review_local_openapi_json(
        _openapi_json(),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )
    row = {
        "id": reviewed.source_artifact_id,
        "run_id": "run_openapi",
        "display_name": "openapi.json",
        "workspace_path": "reports/openapi.json",
        "byte_size": len(reviewed.content),
        "content_type": "application/json",
        "content_sha256": reviewed.source_sha256,
        "created": "2026-08-08T00:00:00+00:00",
    }
    calls = []

    class FakeConnection:
        def execute(self, sql, params):
            calls.append((sql, params))
            return SimpleNamespace(fetchall=lambda: [row])

    monkeypatch.setattr(
        schemathesis_actions,
        "review_project_openapi_artifact",
        lambda *_args, **_kwargs: reviewed,
    )
    context = schemathesis_action_context(
        FakeConnection(),
        "session-api",
        "",
        "prj_api",
        "openapi_negative_testing",
        {"type": "url", "value": reviewed.base_url},
        {"schema_artifact_id": reviewed.source_artifact_id},
    )

    assert context is not None
    assert context.reviewed_schema == reviewed
    assert context.public_selection()["selected"]["operation_count"] == 2
    assert calls[0][1][-1] == SCHEMATHESIS_ARTIFACT_OPTION_LIMIT + 1
    assert calls[0][1][-6:-1] == (
        "application/json%",
        "application/openapi+json%",
        "application/vnd.oai.openapi+json%",
        "%.json",
        "%.json",
    )
    assert "pl.project_id = p.id" in calls[0][0]
    assert "a.byte_size <= ?" in calls[0][0]
    assert "LIKE 'application/json%'" not in calls[0][0]

    overflow_rows = [
        {**row, "id": f"rfa_{index:016x}"}
        for index in range(SCHEMATHESIS_ARTIFACT_OPTION_LIMIT + 1)
    ]

    class OverflowConnection:
        def execute(self, _sql, _params):
            return SimpleNamespace(fetchall=lambda: overflow_rows)

    overflow = schemathesis_action_context(
        OverflowConnection(),
        "session-api",
        "",
        "prj_api",
        "openapi_negative_testing",
        {"type": "url", "value": reviewed.base_url},
        {},
    )
    assert overflow is not None
    assert overflow.overflow is True
    assert len(overflow.options) == SCHEMATHESIS_ARTIFACT_OPTION_LIMIT
    assert overflow.unavailable_reason().startswith("Saved JSON artifacts exceed")


def test_reviewed_schemathesis_execution_replaces_only_help_carrier():
    reviewed = review_local_openapi_json(
        _openapi_json(),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )
    execution = ReviewedSchemathesisExecution(
        reviewed,
        Path("/tmp/private-http-runs/run-0123456789abcdef/schema.json"),
        Path("/tmp/private-http-runs/run-0123456789abcdef/schemathesis.toml"),
        Path("/tmp/private-http-runs/run-0123456789abcdef/events.ndjson"),
        ReviewedSchemathesisReportContext(
            schema=reviewed,
            project_id="prj_api",
            assessment_id="asm_api",
            check_id="ach_api",
            profile_key="api",
            profile_version="1.0",
            read_report=lambda: _schemathesis_report_bytes(),
        ),
    )
    prepared = PreparedRealCommand(
        registry_command="schemathesis --help",
        execution_command="schemathesis --help",
        command="schemathesis --help",
        rewrite_notice=None,
        validation=cast(Any, object()),
        missing_runtime=None,
        display_missing_runtime=None,
        env_overrides={},
        secret_env_names=[],
    )

    replaced = apply_reviewed_execution(prepared, execution)

    assert execution.validation_command == "schemathesis --help"
    assert replaced.execution_command == execution.execution_command
    assert replaced.command == execution.execution_command
    with pytest.raises(RunPreparationError, match="carrier no longer matches"):
        apply_reviewed_execution(
            SimpleNamespace(registry_command="schemathesis --version"),
            execution,
        )


def test_schemathesis_launch_rechecks_plan_and_keeps_runtime_paths_private(monkeypatch):
    reviewed = review_local_openapi_json(
        _openapi_json(),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )
    option = {
        "artifact_id": reviewed.source_artifact_id,
        "run_id": "run_openapi",
        "name": "openapi.json",
        "byte_size": len(reviewed.content),
        "content_type": "application/json",
        "recorded_sha256": reviewed.source_sha256,
        "created": "2026-08-08T00:00:00+00:00",
    }
    context = SchemathesisActionContext(
        (option,), option, reviewed, True, False, False,
    )
    reviewed_plan = reviewed_schemathesis_command_plan(reviewed)
    assert reviewed_plan is not None
    plan = {
        "project_id": "prj_api",
        "assessment_id": "asm_api",
        "check_id": "ach_api",
        "check_key": "openapi_negative_testing",
        "profile_key": "api",
        "profile_version": "1.0",
        "policy_level": "standard",
        "action": {"key": "command:schemathesis", "kind": "command", "id": "schemathesis"},
        "target": {"entity_id": "ent_api", "type": "url", "value": reviewed.base_url},
        "display_command": reviewed_plan.command,
        "artifact_selection": context.public_selection(),
    }
    schema_path = Path("/tmp/private-http-runs/run-0123456789abcdef/schema.json")
    config_path = Path("/tmp/private-http-runs/run-0123456789abcdef/schemathesis.toml")
    report_path = Path("/tmp/private-http-runs/run-0123456789abcdef/events.ndjson")
    cleaned = []
    material = SimpleNamespace(
        schema=reviewed,
        schema_path=schema_path,
        config_path=config_path,
        report_path=report_path,
        private_values=(str(schema_path), str(config_path), str(report_path)),
        read_report=lambda: b"",
        cleanup=lambda: cleaned.append(True),
    )
    monkeypatch.setattr(
        schemathesis_launch,
        "review_project_openapi_artifact",
        lambda *_args, **_kwargs: reviewed,
    )
    monkeypatch.setattr(
        schemathesis_launch,
        "materialize_reviewed_schemathesis_schema",
        lambda _schema: material,
    )

    protected, launch_context = materialize_assessment_run_launch(
        "session-api",
        "prj_api",
        plan,
    )

    assert protected.execution_command == "schemathesis --help"
    assert protected.private_values == (
        str(schema_path), str(config_path), str(report_path),
    )
    assert protected.audit_summary == {
        "schema_artifact_id": reviewed.source_artifact_id,
        "schema_operation_count": 2,
    }
    reviewed_execution = launch_context.reviewed_execution
    assert reviewed_execution is not None
    assert getattr(reviewed_execution, "execution_command").startswith(
        f"schemathesis --config-file {config_path} run {schema_path}"
    )
    report_context = getattr(reviewed_execution, "report_context")
    assert type(report_context) is ReviewedSchemathesisReportContext
    assert report_context.schema == reviewed
    assert report_context.project_id == "prj_api"
    assert report_context.assessment_id == "asm_api"
    assert report_context.check_id == "ach_api"
    assert report_context.profile_key == "api"
    assert report_context.profile_version == "1.0"
    assert report_context.read_report() == b""
    assert launch_context.broker_kwargs() == {
        "trusted_execution_args": (),
        "reviewed_execution": launch_context.reviewed_execution,
    }
    assert protected.cleanup is not None
    protected.cleanup()
    assert cleaned == [True]


def test_app_owned_nuclei_takeover_template_is_digest_pinned_and_non_destructive():
    launch = reviewed_nuclei_takeover_launch()

    assert launch.template.template_id == NUCLEI_TAKEOVER_TEMPLATE_ID
    assert launch.template.template_version == NUCLEI_TAKEOVER_TEMPLATE_VERSION
    assert launch.template.template_digest.startswith("sha256:")
    assert launch.template.policy_level == "safe"
    assert launch.template_path.name == "github-pages-dangling-domain.yaml"
    assert launch.trusted_execution_args == (
        "-t", str(launch.template_path), "-jsonl", "-dr", "-ni",
    )
    source = launch.template_path.read_text(encoding="utf-8")
    assert 'path:\n      - "{{BaseURL}}"' in source
    assert "redirects: false" in source
    assert "max-request: 1" in source
    assert "payloads:" not in source
    assert "extractors:" not in source
    assert "interactsh" not in source.lower()


def test_app_owned_nuclei_takeover_template_rejects_tampering_and_symlinks(
    monkeypatch, tmp_path,
):
    shipped_path = reviewed_nuclei_takeover_launch().template_path
    shipped = shipped_path.read_bytes()
    root = tmp_path / "takeovers"
    root.mkdir()
    candidate = root / "github-pages-dangling-domain.yaml"
    candidate.write_bytes(shipped + b"\n")
    monkeypatch.setattr(nuclei_takeover_templates, "_TEMPLATE_ROOT", root)
    monkeypatch.setattr(nuclei_takeover_templates, "_TEMPLATE_PATH", candidate)

    with pytest.raises(NucleiTakeoverTemplateError, match="digest mismatch"):
        reviewed_nuclei_takeover_launch()

    unsafe = shipped.replace(b"redirects: false", b"redirects: true ")
    candidate.write_bytes(unsafe)
    monkeypatch.setattr(
        nuclei_takeover_templates,
        "_TEMPLATE_DIGEST",
        "sha256:" + nuclei_takeover_templates.hashlib.sha256(unsafe).hexdigest(),
    )
    with pytest.raises(NucleiTakeoverTemplateError, match="request is not safe"):
        reviewed_nuclei_takeover_launch()

    candidate.unlink()
    candidate.symlink_to(shipped_path)
    with pytest.raises(NucleiTakeoverTemplateError, match="unavailable"):
        reviewed_nuclei_takeover_launch()


def _takeover_launch_plan(**overrides):
    plan = {
        "project_id": "prj_takeover",
        "assessment_id": "asm_takeover",
        "check_id": "ach_takeover",
        "check_key": NUCLEI_TAKEOVER_CHECK_KEY,
        "profile_key": "web",
        "policy_level": "safe",
        "launchable": True,
        "action": {
            "key": "command:nuclei",
            "kind": "command",
            "id": "nuclei",
        },
        "target": {
            "entity_id": "ent_takeover",
            "type": "domain",
            "value": "dangling.example.com",
        },
        "http_profile": {"name": "", "credential_use": "none"},
        "display_command": (
            "nuclei -u https://dangling.example.com -rl 2 -c 1 -timeout 10 "
            "-retries 0 -silent -t [reviewed-takeover-template] -jsonl -dr -ni"
        ),
    }
    plan.update(overrides)
    return plan


def test_assessment_launch_context_binds_reviewed_template_only_to_takeover_check():
    generic = assessment_run_launch_context(
        {"check_key": "vulnerability_templates"},
        trusted_execution_args=("-H", "X-Test: value"),
    )
    assert generic.broker_kwargs() == {
        "trusted_execution_args": ("-H", "X-Test: value"),
    }

    context = assessment_run_launch_context(
        _takeover_launch_plan(),
        trusted_execution_args=("-H", "X-Test: value"),
    )
    reviewed = reviewed_nuclei_takeover_launch()
    assert context.trusted_execution_args == (
        "-H",
        "X-Test: value",
        *reviewed.trusted_execution_args,
    )
    assert context.output_signal_context == RunOutputSignalContext(
        nuclei_takeover_template=reviewed.template,
    )
    assert context.broker_kwargs()["output_signal_context"] is context.output_signal_context


@pytest.mark.parametrize(
    ("override", "expected_action_id"),
    [
        ({"launchable": False}, "nuclei"),
        ({"profile_key": "network"}, "nuclei"),
        ({"policy_level": "standard"}, "nuclei"),
        ({"action": {"key": "command:httpx", "kind": "command", "id": "httpx"}}, "httpx"),
        ({"target": {"type": "url", "value": "https://dangling.example.com"}}, "nuclei"),
        ({"display_command": "httpx dangling.example.com"}, "nuclei"),
        ({"http_profile": {"id": "ahp_credentials"}}, "nuclei"),
    ],
)
def test_takeover_launch_context_rejects_contract_drift(
    caplog, override, expected_action_id,
):
    with caplog.at_level("WARNING", logger="shell"), pytest.raises(
        nuclei_takeover_launch.AssessmentActionError,
        match="expected safe launch contract",
    ) as exc_info:
        assessment_run_launch_context(_takeover_launch_plan(**override))

    assert exc_info.value.code == "takeover_launch_contract_invalid"
    assert exc_info.value.status_code == 409
    record = next(
        record
        for record in caplog.records
        if record.message == "ASSESSMENT_TAKEOVER_LAUNCH_CONTRACT_REJECTED"
    )
    assert record.project_id == "prj_takeover"
    assert record.assessment_id == "asm_takeover"
    assert record.check_id == "ach_takeover"
    assert record.action_id == expected_action_id
    assert record.reason == "reviewed_contract_changed"
    assert record.levelname == "WARNING"


def test_takeover_launch_context_fails_closed_when_template_validation_fails(
    caplog, monkeypatch,
):
    def _unavailable():
        raise NucleiTakeoverTemplateError("reviewed template unavailable")

    monkeypatch.setattr(nuclei_takeover_launch, "reviewed_nuclei_takeover_launch", _unavailable)
    with caplog.at_level("ERROR", logger="shell"), pytest.raises(
        nuclei_takeover_launch.AssessmentActionError,
        match="reviewed takeover template is unavailable",
    ) as exc_info:
        assessment_run_launch_context(_takeover_launch_plan())

    assert exc_info.value.code == "takeover_template_unavailable"
    assert exc_info.value.status_code == 503
    record = next(
        record
        for record in caplog.records
        if record.message == "ASSESSMENT_TAKEOVER_TEMPLATE_VALIDATION_FAILED"
    )
    assert record.project_id == "prj_takeover"
    assert record.reason == "reviewed template unavailable"


def test_takeover_launch_materialization_never_creates_protected_http_files(
    monkeypatch,
):
    monkeypatch.setattr(
        run_launch,
        "materialize_http_profile_launch",
        lambda *_args, **_kwargs: pytest.fail("takeover launch requested HTTP material"),
    )
    with pytest.raises(
        nuclei_takeover_launch.AssessmentActionError,
        match="expected safe launch contract",
    ):
        materialize_assessment_run_launch(
            "session",
            "prj_takeover",
            _takeover_launch_plan(policy_level="standard"),
        )

def test_reviewed_takeover_command_is_one_domain_one_request_and_not_generic_nuclei():
    display = reviewed_takeover_command_plan("domain", "dangling.example.com")
    execution = reviewed_takeover_command_plan(
        "domain",
        "dangling.example.com",
        protected_display=False,
    )

    assert display is not None and execution is not None
    assert display.command == (
        "nuclei -u https://dangling.example.com -rl 2 -c 1 -timeout 10 "
        "-retries 0 -silent -t [reviewed-takeover-template] -jsonl -dr -ni"
    )
    assert execution.command == (
        "nuclei -u https://dangling.example.com -rl 2 -c 1 -timeout 10 "
        "-retries 0 -silent"
    )
    assert display.request_limit == 1
    assert display.time_limit_seconds == 30
    assert display.credential_use == "none"
    assert "no resource claim" in display.boundary
    assert "-severity" not in display.command
    assert reviewed_takeover_command_plan("url", "https://dangling.example.com") is None
    assert reviewed_takeover_command_plan("domain", "dangling.example.com;whoami") is None


def test_historical_urls_are_safe_bounded_and_provenance_only():
    assert normalize_scope_domain("Example.COM.") == "example.com"
    assert normalize_scope_domain("-invalid.example") is None
    assert normalize_scope_domain("example.com/path") is None
    assert normalize_historical_url(
        "HTTPS://Example.COM/a#fragment", run_id="run-1"
    ) is None
    assert normalize_historical_url("https://user:pass@example.com/a") is None
    rows = normalize_historical_urls([
        "HTTPS://Example.COM/a?x=1", "https://example.com/a?x=1", "ftp://example.com/a",
        "https://example.com/b#ignored",
    ], source="gau", run_id="run-1")
    assert rows == [{
        "url": "https://example.com/a?x=1", "source": "gau", "source_run_id": "run-1",
    }]
    assert [row["url"] for row in filter_historical_urls(
        [
            {"url": "https://example.com/a", "source": "gau"},
            {"url": "https://example.com.evil/a", "source": "gau"},
            {"url": "https://other.example/a", "source": "gau"},
        ],
        allowed_hosts=["example.com"],
        scope_roots=["https://example.com/a"],
    )] == ["https://example.com/a"]
    scoped = normalize_domain_scoped_historical_urls(
        [
            "HTTPS://Example.COM/a?x=1",
            "https://example.com/a?x=1",
            "https://api.example.com/live",
            "https://example.com.evil.test/lookalike",
            "https://other.test/outside",
        ],
        "example.com",
        source="gau",
        run_id="run-1",
    )
    assert scoped == [
        {"url": "https://example.com/a?x=1", "source": "gau", "source_run_id": "run-1"},
        {"url": "https://api.example.com/live", "source": "gau", "source_run_id": "run-1"},
    ]
    bounded = normalize_domain_scoped_historical_urls(
        [f"https://outside.test/{index}" for index in range(300)]
        + [f"https://sub.example.com/{index}" for index in range(300)],
        "example.com",
    )
    assert len(bounded) == 256
    assert bounded[-1]["url"] == "https://sub.example.com/255"


def test_epss_and_kev_feeds_normalize_risk_signals_without_network_access():
    assert normalize_epss_rows(
        "# comment\ncve,epss,percentile,date\nCVE-2026-12345,0.42,0.91,2026-08-01\nCVE-invalid,2,0.1,"
    ) == [{"cve": "CVE-2026-12345", "epss": 0.42, "percentile": 0.91, "date": "2026-08-01"}]
    assert normalize_kev_catalog({"vulnerabilities": [{
        "cveID": "CVE-2026-12345", "vendorProject": "Vendor", "product": "Product",
        "vulnerabilityName": "Example", "dateAdded": "2026-08-01", "dueDate": "2026-08-21",
        "knownRansomwareCampaignUse": "Known",
    }, {"cveID": "not-cve"}]}) == [{
        "cve": "CVE-2026-12345", "vendor": "Vendor", "product": "Product", "name": "Example",
        "date_added": "2026-08-01", "due_date": "2026-08-21", "known_ransomware_use": "Known",
    }]


def test_takeover_signal_keeps_dangling_records_potential_until_reviewed_confirmation():
    class Capture:
        def __init__(self):
            self.events = []

        def add_event(self, event):
            self.events.append(event)

    query_calls: list[tuple[str, tuple[Any, ...]]] = []

    class EmptyConnection:
        def execute(self, sql, params):
            query_calls.append((sql, params))
            return SimpleNamespace(fetchall=lambda: [])

    project_evidence = project_takeover_evidence(
        EmptyConnection(), "session-1", "", "project-1", "run-current", [],
    )
    assert project_evidence is not None
    assert "LIKE 'dnsx %'" not in query_calls[0][0]
    assert query_calls[0][1][-2:] == (
        "dnsx %",
        TAKEOVER_EVIDENCE_MAX_RUNS + 1,
    )

    direct_potential = evaluate_takeover_signal({
        "hostname": "app.example.test", "cname_chain": ["app.vendor.test."],
        "provider": "vendor", "target_resolved": False, "in_scope": True,
    })
    assert direct_potential["state"] == "potential"
    assert evaluate_takeover_signal({
        "hostname": "app.example.test", "cname_chain": ["app.vendor.test"],
        "provider": "vendor", "target_resolved": False, "in_scope": True,
        "reviewed_takeover_template_match": True,
    })["state"] == "potential"
    source = normalize_dnsx_takeover_observation(
        {
            "host": "app.example.test",
            "cname": ["app.vendor.test"],
            "status_code": "NOERROR",
            "timestamp": "2026-08-07T21:59:00Z",
        },
        command="dnsx -d example.test -cname -json",
        source_run_id="run-dnsx-source",
    )
    target = normalize_dnsx_takeover_observation(
        {
            "host": "app.vendor.test",
            "status_code": "NXDOMAIN",
            "timestamp": "2026-08-07T21:59:30Z",
        },
        command="dnsx -d vendor.test -a -aaaa -cname -json",
        source_run_id="run-dnsx-target",
    )
    assert source is not None and target is not None
    event_review = build_dnsx_takeover_event_review(
        [
            {"source_detail": {"takeover_observations": [source]}},
            {"source_detail": {"takeover_observations": [target]}},
        ],
        allowed_source_run_ids={"run-dnsx-source", "run-dnsx-target"},
    )
    potential = event_review["reviews"][0]
    assert potential["state"] == "potential"
    reviewed_template = ReviewedNucleiTakeoverTemplate(
        template_id="http-takeover-reviewed",
        template_version="2026.08.1",
        template_digest="sha256:" + ("a" * 64),
        policy_level="safe",
    )
    reviewed_templates = {reviewed_template.template_id: reviewed_template.registry_entry()}
    nuclei_line = json.dumps({
        "template-id": "http-takeover-reviewed",
        "matched-at": "https://App.Example.Test:443/login",
        "timestamp": "2026-08-07T22:00:00Z",
        "template-version": "untrusted-output-version",
        "template-digest": "sha256:" + ("b" * 64),
        "policy-level": "intrusive",
    })
    capture = Capture()
    metadata, event = capture_event_with_signals(
        capture,
        OutputSignalClassifier(
            "nuclei -u https://app.example.test -jsonl",
            source_run_id="run-nuclei-owned",
            nuclei_takeover_template=reviewed_template,
        ),
        nuclei_line,
    )
    evidence = event.source_detail["nuclei_takeover_observations"][0]
    assert evidence == {
        "observation_id": evidence["observation_id"],
        "parser_version": NUCLEI_TAKEOVER_JSON_PARSER_VERSION,
        "adapter": "nuclei",
        "match_state": "matched",
        "template_id": "http-takeover-reviewed",
        "template_version": "2026.08.1",
        "template_digest": "sha256:" + ("a" * 64),
        "policy_level": "safe",
        "source_run_id": "run-nuclei-owned",
        "matched_hostname": "app.example.test",
        "observed_at": "2026-08-07T22:00:00Z",
    }
    assert metadata["source_detail"]["nuclei_takeover_observations"] == [evidence]
    assert _source_detail(to_wire(capture.events[0]))[
        "nuclei_takeover_observations"
    ] == [evidence]
    confirmed = confirm_takeover_with_nuclei(
        potential,
        evidence,
        dns_source_observation=source,
        dns_target_observation=target,
        reviewed_templates=reviewed_templates,
        allowed_source_run_ids={"run-dnsx-source", "run-dnsx-target", "run-nuclei-owned"},
    )
    assert potential["state"] == "potential"
    assert confirmed == {
        **potential,
        "state": "confirmed",
        "reason": "reviewed_nuclei_template_match",
        "confirmation_status": "confirmed",
        "confirmation": {
            "confirmation_id": confirmed["confirmation"]["confirmation_id"],
            "confirmation_version": NUCLEI_TAKEOVER_CONFIRMATION_VERSION,
            "method": "nuclei_template",
            "template_id": "http-takeover-reviewed",
            "template_version": "2026.08.1",
            "template_digest": "sha256:" + ("a" * 64),
            "source_run_id": "run-nuclei-owned",
            "source_observation_id": evidence["observation_id"],
            "parser_version": NUCLEI_TAKEOVER_JSON_PARSER_VERSION,
            "matched_hostname": "app.example.test",
            "observed_at": "2026-08-07T22:00:00Z",
            "policy_level": "safe",
        },
    }
    assert confirmed["confirmation"]["confirmation_id"].startswith("ntc_")
    rejected_cases = (
        ({**evidence, "source_run_id": "run-other-owner"}, reviewed_templates, "source_run_not_allowed"),
        ({**evidence, "matched_hostname": "app.example.test.evil.test"}, reviewed_templates,
         "matched_target_mismatch"),
        ({**evidence, "matched_hostname": "https://user:secret@app.example.test"}, reviewed_templates,
         "matched_target_mismatch"),
        ({**evidence, "template_version": "2026.08.2"}, reviewed_templates,
         "template_version_mismatch"),
        ({**evidence, "template_digest": "sha256:" + ("b" * 64)}, reviewed_templates,
         "template_digest_mismatch"),
        ({**evidence, "policy_level": "standard"}, reviewed_templates,
         "template_policy_mismatch"),
        ({**evidence, "observation_id": "nucobs_" + ("0" * 32)}, reviewed_templates,
         "invalid_observation_identity"),
        ({**evidence, "parser_version": "nuclei-takeover-json-v0"}, reviewed_templates,
         "invalid_nuclei_evidence"),
        (evidence, {
            "http-takeover-reviewed": {
                **reviewed_templates["http-takeover-reviewed"], "policy_level": "intrusive",
            },
        }, "template_policy_not_allowed"),
    )
    for candidate, registry, reason in rejected_cases:
        rejected = confirm_takeover_with_nuclei(
            potential,
            candidate,
            dns_source_observation=source,
            dns_target_observation=target,
            reviewed_templates=registry,
            allowed_source_run_ids={"run-dnsx-source", "run-dnsx-target", "run-nuclei-owned"},
        )
        assert rejected["state"] == "potential"
        assert rejected["confirmation_status"] == "rejected"
        assert rejected["confirmation_reason"] == reason
        assert "confirmation" not in rejected
    forged_review = confirm_takeover_with_nuclei(
        direct_potential,
        evidence,
        dns_source_observation=source,
        dns_target_observation=target,
        reviewed_templates=reviewed_templates,
        allowed_source_run_ids={"run-nuclei-owned"},
    )
    assert forged_review["confirmation_reason"] == "invalid_dns_review"
    tampered_review = confirm_takeover_with_nuclei(
        potential,
        evidence,
        dns_source_observation={**source, "hostname": "other.example.test"},
        dns_target_observation=target,
        reviewed_templates=reviewed_templates,
        allowed_source_run_ids={"run-dnsx-source", "run-dnsx-target", "run-nuclei-owned"},
    )
    assert tampered_review["confirmation_reason"] == "invalid_dns_review"
    untrusted_classifier = OutputSignalClassifier(
        "nuclei -u https://app.example.test -jsonl",
        source_run_id="run-nuclei-owned",
        nuclei_takeover_template=reviewed_template,
    )
    assert "nuclei_takeover_observations" not in _source_detail(
        untrusted_classifier.classify_line(json.dumps({
            "template-id": "other-template",
            "matched-at": "https://app.example.test",
            "timestamp": "2026-08-07T22:00:00Z",
        }))
    )
    assert "nuclei_takeover_observations" not in _source_detail(
        untrusted_classifier.classify_line(
            "{" + (" " * NUCLEI_JSON_MAX_LINE_BYTES)
        )
    )
    assert evaluate_takeover_signal({"hostname": "app.example.test", "resolution_state": "timeout"})["state"] == "uncertain"
    assert evaluate_takeover_signal(
        {
            "hostname": "app.example.test",
            "cname_chain": ["outside.test"],
            "target_resolved": False,
            "in_scope": False,
        }
    )["reason"] == "out_of_scope_target"


def test_dnsx_json_preserves_bounded_takeover_evidence_without_claiming_a_dangling_target():
    record = {
        "host": "App.Example.test.",
        "cname": [f"hop-{index}.vendor.test." for index in range(20)],
        "a": ["93.184.216.34"],
        "aaaa": ["2001:4860:4860::8888"],
        "resolver": ["udp:1.1.1.1:53", "https://user:secret@resolver.test/dns-query"],
        "status_code": "NOERROR",
        "timestamp": "2026-08-07T20:00:00Z",
        "cdn-name": "CloudFront",
        "cdn-type": "cdn",
        "raw": "must not survive",
    }
    observation = normalize_dnsx_takeover_observation(
        record,
        command="dnsx -d example.test -a -aaaa -cname -cdn -json -auto-wildcard",
        source_run_id="run-dnsx",
    )
    assert observation is not None
    assert observation == {
        "observation_id": observation["observation_id"],
        "hostname": "app.example.test",
        "cname_chain": [f"hop-{index}.vendor.test" for index in range(DNSX_MAX_CNAME_CHAIN)],
        "addresses": ["93.184.216.34", "2001:4860:4860::8888"],
        "status_code": "NOERROR",
        "resolution_state": "resolved",
        "target_resolution_state": "not_checked",
        "provider_fingerprint": {"name": "cloudfront", "type": "cdn"},
        "resolvers": ["udp:1.1.1.1:53"],
        "wildcard_filter": "auto",
        "scope_root": "example.test",
        "scope_decision": "in_scope",
        "source_run_id": "run-dnsx",
        "observed_at": "2026-08-07T20:00:00Z",
        "parser_version": DNSX_TAKEOVER_PARSER_VERSION,
        "truncated": True,
    }
    assert observation["observation_id"].startswith("dnsobs_")
    assert evaluate_takeover_signal(observation)["state"] == "not_indicated"
    assert "raw" not in observation


def test_dnsx_takeover_observations_fail_closed_on_missing_provenance_and_record_scope():
    base = {
        "host": "app.example.test",
        "cname": ["app.vendor.test"],
        "status_code": "NOERROR",
        "timestamp": "2026-08-07T20:00:00Z",
    }
    assert normalize_dnsx_takeover_observation(
        base, command="dnsx -d example.test -json", source_run_id="",
    ) is None
    assert normalize_dnsx_takeover_observation(
        {**base, "timestamp": "2026-08-07T20:00:00"},
        command="dnsx -d example.test -json", source_run_id="run-1",
    ) is None
    ambiguous_scope = normalize_dnsx_takeover_observation(
        base, command="dnsx -d example.test -d other.test -json", source_run_id="run-1",
    )
    assert ambiguous_scope is not None
    assert ambiguous_scope["scope_decision"] == "unknown"
    out_of_scope = normalize_dnsx_takeover_observation(
        base, command="dnsx -d other.test -json", source_run_id="run-1",
    )
    assert out_of_scope is not None
    assert out_of_scope["scope_decision"] == "out_of_scope"
    negative_target = {
        **out_of_scope,
        "scope_decision": "in_scope",
        "target_resolution_state": "negative",
    }
    potential = evaluate_takeover_signal(negative_target)
    assert potential["state"] == "potential"
    assert potential["uncertainties"] == ["wildcard_not_checked"]


def test_dnsx_json_takeover_evidence_survives_event_wire_without_resolver_entities():
    class Capture:
        def __init__(self):
            self.events = []

        def add_event(self, event):
            self.events.append(event)

    line = json.dumps({
        "host": "app.example.test",
        "cname": ["app.vendor.test"],
        "a": ["93.184.216.34"],
        "resolver": ["1.1.1.1:53"],
        "status_code": "NOERROR",
        "timestamp": "2026-08-07T20:00:00Z",
    })
    capture = Capture()
    classifier = OutputSignalClassifier(
        "dnsx -d example.test -a -cname -json -silent",
        source_run_id="run-dnsx",
    )
    metadata, event = capture_event_with_signals(capture, classifier, line)
    assert metadata["signals"] == ["findings"]
    assert {
        (entity["type"], entity["canonical_value"])
        for entity in metadata["entities"]
    } == {
        ("domain", "app.example.test"),
        ("domain", "app.vendor.test"),
        ("ip", "93.184.216.34"),
    }
    assert ("ip", "1.1.1.1") not in {
        (entity["type"], entity["canonical_value"])
        for entity in metadata["entities"]
    }
    observation = event.source_detail["takeover_observations"][0]
    assert observation["source_run_id"] == "run-dnsx"
    assert _source_detail(to_wire(capture.events[0]))["takeover_observations"] == [
        observation
    ]


def test_dnsx_target_correlation_joins_exact_owner_scoped_evidence_without_network_work():
    source = normalize_dnsx_takeover_observation({
        "host": "app.example.test", "cname": ["tenant.vendor.test"],
        "status_code": "NOERROR", "timestamp": "2026-08-07T20:00:00Z",
        "cdn-name": "Vendor",
    }, command="dnsx -d example.test -cname -json -auto-wildcard", source_run_id="run-source")
    target = normalize_dnsx_takeover_observation({
        "host": "tenant.vendor.test", "cname": ["terminal.vendor.test"],
        "status_code": "NXDOMAIN",
        "timestamp": "2026-08-07T20:05:00Z",
    }, command="dnsx -d tenant.vendor.test -a -aaaa -json", source_run_id="run-target")
    assert target is not None
    correlated = correlate_dnsx_target_observation(
        source, target, allowed_source_run_ids={"run-source", "run-target"},
    )
    assert correlated is not None
    assert correlated["cname_chain"] == ["tenant.vendor.test", "terminal.vendor.test"]
    assert correlated["target_resolution_state"] == "negative"
    assert correlated["correlation_version"] == DNSX_TARGET_CORRELATION_VERSION
    assert correlated["target_observation"] == {
        "observation_id": target["observation_id"],
        "source_run_id": "run-target",
        "hostname": "tenant.vendor.test",
        "resolution_state": "negative",
        "status_code": "NXDOMAIN",
        "scope_decision": "in_scope",
        "observed_at": "2026-08-07T20:05:00Z",
        "parser_version": DNSX_TAKEOVER_PARSER_VERSION,
    }
    potential = evaluate_takeover_signal(correlated)
    assert potential["state"] == "potential"
    assert potential["target_observation"] == correlated["target_observation"]
    assert "secret" not in evaluate_takeover_signal({
        **correlated, "target_observation": {**correlated["target_observation"], "secret": "no"},
    })["target_observation"]


def test_dnsx_target_correlation_rejects_incompatible_or_untrusted_evidence():
    source = normalize_dnsx_takeover_observation({
        "host": "app.example.test", "cname": ["tenant.vendor.test"],
        "status_code": "NOERROR", "timestamp": "2026-08-07T20:00:00Z",
    }, command="dnsx -d example.test -cname -json", source_run_id="run-source")
    mismatch = normalize_dnsx_takeover_observation({
        "host": "other.vendor.test", "status_code": "SERVFAIL",
        "timestamp": "2026-08-07T20:05:00Z",
    }, command="dnsx -d other.vendor.test -a -json", source_run_id="run-target")
    allowed = {"run-source", "run-target"}
    assert correlate_dnsx_target_observation(source, mismatch, allowed_source_run_ids=allowed) is None
    matching = normalize_dnsx_takeover_observation({
        "host": "tenant.vendor.test", "status_code": "SERVFAIL",
        "timestamp": "2026-08-07T20:05:00Z",
    }, command="dnsx -d tenant.vendor.test -a -json", source_run_id="run-target")
    assert matching is not None
    assert correlate_dnsx_target_observation(
        source, matching, allowed_source_run_ids={"run-source"},
    ) is None
    assert correlate_dnsx_target_observation(
        source, {**matching, "hostname": "changed.vendor.test"}, allowed_source_run_ids=allowed,
    ) is None
    stale = normalize_dnsx_takeover_observation({
        "host": "tenant.vendor.test", "status_code": "SERVFAIL",
        "timestamp": "2026-08-09T20:05:00Z",
    }, command="dnsx -d tenant.vendor.test -a -json", source_run_id="run-target")
    assert correlate_dnsx_target_observation(source, stale, allowed_source_run_ids=allowed) is None
    tampered = {**matching, "parser_version": "dnsx-json-takeover-v1"}
    assert correlate_dnsx_target_observation(source, tampered, allowed_source_run_ids=allowed) is None
    assert correlate_dnsx_target_observation(
        source, {**matching, "resolution_state": "negative"}, allowed_source_run_ids=allowed,
    ) is None
    truncated = normalize_dnsx_takeover_observation({
        "host": "app.example.test", "cname": [f"hop-{index}.vendor.test" for index in range(17)],
        "status_code": "NOERROR", "timestamp": "2026-08-07T20:00:00Z",
    }, command="dnsx -d example.test -cname -json", source_run_id="run-source")
    assert correlate_dnsx_target_observation(truncated, matching, allowed_source_run_ids=allowed) is None
    uncertain = correlate_dnsx_target_observation(source, matching, allowed_source_run_ids=allowed)
    assert uncertain is not None
    assert evaluate_takeover_signal(uncertain) == {
        "state": "uncertain", "reason": "transient_dns_result", "hostname": "app.example.test",
    }


def test_dnsx_event_review_uses_newest_target_result_and_reports_same_time_conflicts():
    source = normalize_dnsx_takeover_observation({
        "host": "app.example.test", "cname": ["tenant.vendor.test"],
        "status_code": "NOERROR", "timestamp": "2026-08-07T20:00:00Z",
    }, command="dnsx -d example.test -cname -json", source_run_id="run-source")
    negative = normalize_dnsx_takeover_observation({
        "host": "tenant.vendor.test", "status_code": "NXDOMAIN",
        "timestamp": "2026-08-07T20:05:00Z",
    }, command="dnsx -d tenant.vendor.test -a -json", source_run_id="run-negative")
    resolved = normalize_dnsx_takeover_observation({
        "host": "tenant.vendor.test", "a": ["93.184.216.34"], "status_code": "NOERROR",
        "timestamp": "2026-08-07T20:10:00Z",
    }, command="dnsx -d tenant.vendor.test -a -json", source_run_id="run-resolved")
    def event(row):
        return {"source_detail": {"takeover_observations": [row]}}
    allowed = {"run-source", "run-negative", "run-resolved"}
    review = build_dnsx_takeover_event_review(
        [event(source), event(negative), event(resolved)], allowed_source_run_ids=allowed,
    )
    assert review["status"] == "ready"
    assert review["reviews"][0]["state"] == "not_indicated"
    assert review["reviews"][0]["target_observation"]["source_run_id"] == "run-resolved"

    conflicting = normalize_dnsx_takeover_observation({
        "host": "tenant.vendor.test", "status_code": "NXDOMAIN",
        "timestamp": "2026-08-07T20:10:00Z",
    }, command="dnsx -d tenant.vendor.test -a -json", source_run_id="run-conflict")
    conflict_review = build_dnsx_takeover_event_review(
        [event(source), event(resolved), event(conflicting)],
        allowed_source_run_ids={"run-source", "run-resolved", "run-conflict"},
    )
    assert conflict_review["reviews"][0]["state"] == "uncertain"
    assert conflict_review["reviews"][0]["reason"] == "conflicting_target_results"
    assert len(conflict_review["reviews"][0]["target_observations"]) == 2
    assert conflict_review["reviews"][0]["target_observation_count"] == 2
    assert conflict_review["reviews"][0]["target_observations_truncated"] is False


def test_dnsx_event_review_rejects_limits_and_never_returns_partial_rows():
    assert build_dnsx_takeover_event_review(
        [{}] * 1001, allowed_source_run_ids={"run-1"},
    ) == {
        "status": "rejected",
        "reason": "event_or_observation_limit_exceeded",
        "observation_count": 0,
        "review_count": 0,
        "reviews": [],
    }
    oversized_observations = [{"source_run_id": "run-1"}] * 257
    assert build_dnsx_takeover_event_review(
        [{"source_detail": {"takeover_observations": oversized_observations}}],
        allowed_source_run_ids={"run-1"},
    )["reason"] == "event_or_observation_limit_exceeded"
    assert build_dnsx_takeover_event_review([], allowed_source_run_ids=set())["reason"] == (
        "invalid_run_allowlist"
    )
    assert build_dnsx_takeover_event_review(
        [], allowed_source_run_ids={"x" * 129},
    )["reason"] == "invalid_run_allowlist"


def test_httpx_screenshot_metadata_is_bounded_and_path_safe():
    record = normalize_httpx_screenshot({
        "url": "https://app.example.test/login",
        "screenshot_path": "/scanner/output/screenshots/screenshot/app.example.test/app.png",
        "screenshot_path_rel": "app.example.test/app.png",
        "status_code": "200", "title": "  Login   page ", "technologies": ["nginx", "nginx"],
        "run_id": "run-1", "profile_role": "authenticated",
    }, output_directory="screenshots")
    assert record == {
        "url": "https://app.example.test/login",
        "artifact_path": "screenshots/screenshot/app.example.test/app.png",
        "status_code": 200, "title": "Login page", "technologies": ["nginx", "nginx"],
        "captured_at": "", "visual_hash": "", "source_run_id": "run-1", "profile_role": "authenticated",
    }
    prefixed = normalize_httpx_screenshot({
        "url": "https://app.example.test",
        "screenshot_path_rel": "screenshot/app.example.test/prefixed.png",
    }, output_directory="screenshots")
    assert prefixed and prefixed["artifact_path"] == (
        "screenshots/screenshot/app.example.test/prefixed.png"
    )
    assert normalize_httpx_screenshot({"url": "https://app.example.test", "screenshot_path": "../secret.png"}) is None
    assert normalize_httpx_screenshot({
        "url": "https://app.example.test",
        "screenshot_path_rel": "../secret.png",
    }, output_directory="screenshots") is None
    assert normalize_httpx_screenshot({"url": "https://user:pass@app.example.test", "screenshot_path": "ok.png"}) is None


def test_web_gallery_filters_metadata_without_exposing_artifact_contents():
    rows = filter_web_surface_rows(
        [
            {
                "url": "https://app.example.test",
                "status_code": 200,
                "technologies": ["nginx"],
                "profile_role": "anonymous",
                "visual_hash": "abc",
                "html": "secret",
            },
            {
                "url": "https://admin.example.test",
                "status_code": 401,
                "technologies": ["nginx"],
                "profile_role": "authenticated",
                "visual_hash": "def",
            },
        ],
        target="app.example",
        status_code=200,
        technology="nginx",
        profile_role="anonymous",
    )
    assert len(rows) == 1
    assert rows[0]["url"] == "https://app.example.test"
    assert "html" not in rows[0]
    assert filter_web_surface_rows(rows, visual_hash="abc", changed_since=["abc"]) == []


def test_web_gallery_normalizes_collection_filters_and_matches_enriched_rows():
    filters = normalize_web_surface_filters({
        "target": "  APP.EXAMPLE  ",
        "status_code": "200",
        "technology": " NGINX ",
        "profile_role": "Authenticated",
        "visual_hash": "ABC",
    })
    assert filters == {
        "target": "APP.EXAMPLE",
        "status_code": 200,
        "technology": "NGINX",
        "profile_role": "Authenticated",
        "visual_hash": "ABC",
    }
    assert web_surface_filters_active(filters) is True
    assert web_surface_row_matches({
        "url": "https://app.example/login",
        "status_code": 200,
        "technologies": ["nginx"],
        "profile_role": "authenticated",
        "visual_hash": "abc",
        "artifact": {"id": "kept-outside-public-metadata"},
    }, filters) is True
    assert normalize_web_surface_filters({"status_code": "99"})["status_code"] is None


def test_web_surface_comparison_uses_exact_url_role_and_prior_run_evidence():
    def capture(artifact_id, run_id, captured_at, visual_hash, *, role="anonymous", url="https://app.example/login"):
        return {
            "url": url,
            "captured_at": captured_at,
            "visual_hash": visual_hash,
            "profile_role": role,
            "artifact": {"id": artifact_id, "created": captured_at},
            "source_run": {"id": run_id},
        }

    previous = capture("artifact-1", "run-1", "2026-08-06T00:00:00Z", "hash-old")
    current = capture("artifact-2", "run-2", "2026-08-07T00:00:00Z", "hash-new")
    other_role = capture(
        "artifact-3", "run-3", "2026-08-06T12:00:00Z", "hash-new", role="authenticated",
    )
    same_run = capture("artifact-same-run", "run-2", "2026-08-06T18:00:00Z", "hash-same-run")
    attach_capture_comparisons([current], [previous, current, other_role, same_run])

    assert current["comparison"] == {
        "state": "changed",
        "basis": "exact_url_and_profile_role",
        "previous_capture": {
            "artifact_id": "artifact-1",
            "source_run_id": "run-1",
            "captured_at": "2026-08-06T00:00:00Z",
            "visual_hash": "hash-old",
        },
    }
    assert capture_matches_change_state(current, "changed") is True
    assert capture_matches_change_state(current, "unchanged") is False
    assert normalize_change_state(" CHANGED ") == "changed"
    assert normalize_change_state("invented") == ""

    unchanged = capture("artifact-4", "run-4", "2026-08-08T00:00:00Z", "hash-new")
    attach_capture_comparisons([unchanged], [current, unchanged])
    assert unchanged["comparison"]["state"] == "unchanged"

    no_hash = capture("artifact-5", "run-5", "2026-08-09T00:00:00Z", "")
    attach_capture_comparisons([no_hash], [unchanged, no_hash])
    assert no_hash["comparison"]["state"] == "incomparable"

    oldest = capture("artifact-0", "run-0", "2026-08-05T00:00:00Z", "hash-oldest")
    attach_capture_comparisons([oldest], [oldest], history_truncated=False)
    assert oldest["comparison"]["state"] == "no_baseline"
    attach_capture_comparisons([oldest], [oldest], history_truncated=True)
    assert oldest["comparison"]["state"] == "unknown"


def test_web_gallery_paging_is_bounded_and_skips_malformed_rows():
    rows = filter_web_surface_rows(
        [None, {"url": "https://one.example", "status_code": 200}, {"url": "https://two.example", "status_code": 200}],
        offset=cast(Any, "1"),
        limit=9999,
    )
    assert [row["url"] for row in rows] == ["https://two.example"]
    assert filter_web_surface_rows([{"url": "https://one.example"}], offset=-5, limit=0) == []


def test_web_gallery_extracts_only_bounded_screenshot_metadata_from_event_wires():
    rows = web_surface_rows_from_events([
        {"source_detail": {"screenshots": [{"url": "https://app.example", "artifact_path": "shots/app.png", "html": "secret"}]}},
        {"source_detail": {"screenshots": [{"url": ""}, None]}},
    ])
    assert rows == [{"url": "https://app.example", "artifact_path": "shots/app.png"}]


def test_httpx_json_output_carries_safe_screenshot_metadata_only():
    classifier = OutputSignalClassifier(
        "httpx -json -screenshot -srd screenshots",
        source_run_id="run-httpx",
        profile_role="anonymous",
    )
    metadata = classifier.classify_line(
        '{"url":"https://app.example.test","screenshot_path":"/screenshots/screenshot/app.example.test/app.png",'
        '"screenshot_path_rel":"app.example.test/app.png","status_code":200}'
    )
    assert metadata["screenshots"] == [{
        "url": "https://app.example.test",
        "artifact_path": "screenshots/screenshot/app.example.test/app.png",
        "status_code": 200, "title": "", "technologies": [], "captured_at": "",
        "visual_hash": "", "source_run_id": "run-httpx", "profile_role": "anonymous",
    }]
    assert "html" not in metadata


def test_dalfox_discovery_jsonl_preserves_bounded_parameter_evidence():
    state = DalfoxParameterObservationState(
        "dalfox scan https://App.Example.test/search?q=one --only-discovery "
        "--skip-mining-dict --format jsonl",
        "run-dalfox",
    )
    summary = state.metadata(json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "mode": "only_discovery",
        "params_discovered": 2,
    }}))
    first = state.metadata(json.dumps({
        "url": "https://app.example.test/search?q=one",
        "param": "q",
        "location": "Query",
    }))
    second = state.metadata(json.dumps({
        "url": "https://app.example.test/search?q=one",
        "param": "X-Search-Mode",
        "location": "Header",
    }))

    assert summary["source_detail"]["parameter_discovery"] == {
        "target": "https://app.example.test/search?q=one",
        "mode": "only_discovery",
        "reported_parameter_count": 2,
        "source_run_id": "run-dalfox",
        "tool_version": "v3.1.2",
        "parser_version": DALFOX_DISCOVERY_PARSER_VERSION,
        "truncated": False,
    }
    assert first["source_detail"]["parameter_observations"] == [{
        "observation_id": first["source_detail"]["parameter_observations"][0]["observation_id"],
        "target": "https://app.example.test/search?q=one",
        "parameter": "q",
        "location": "Query",
        "source_run_id": "run-dalfox",
        "tool_version": "v3.1.2",
        "parser_version": DALFOX_DISCOVERY_PARSER_VERSION,
    }]
    assert first["source_detail"]["parameter_observations"][0]["observation_id"].startswith("obs_")
    assert second["source_detail"]["parameter_observations"][0]["location"] == "Header"
    assert state.metadata(json.dumps({
        "url": "https://app.example.test/search?q=one", "param": "q", "location": "Query",
    })) == {}


def test_dalfox_discovery_jsonl_fails_closed_on_untrusted_or_malformed_rows():
    command = (
        "dalfox scan https://app.example.test/search?q=one --only-discovery "
        "--skip-mining-dict --format jsonl"
    )
    invalid_commands = (
        command.replace(" --only-discovery", ""),
        command.replace(" --skip-mining-dict", ""),
        command.replace("jsonl", "plain"),
        command + " --skip-discovery",
    )
    meta = json.dumps({"meta": {
        "dalfox_version": "v3.1.2", "mode": "only_discovery", "params_discovered": 1,
    }})
    assert all(not DalfoxParameterObservationState(value, "run-1").metadata(meta)
               for value in invalid_commands)
    assert not DalfoxParameterObservationState(command, "").metadata(meta)

    state = DalfoxParameterObservationState(command, "run-1")
    assert state.metadata("{not-json") == {}
    assert state.metadata("{" + " " * DALFOX_JSON_MAX_LINE_BYTES + "}") == {}
    assert state.metadata(json.dumps({"meta": {
        "dalfox_version": "v3.1.2", "mode": "scan", "params_discovered": 1,
    }})) == {}
    assert state.metadata(json.dumps({"meta": {
        "dalfox_version": "v3.1.2", "mode": "only_discovery", "params_discovered": True,
    }})) == {}
    assert state.metadata(meta)
    invalid_rows = (
        {"url": "https://other.example.test/search?q=one", "param": "q", "location": "Query"},
        {"url": "https://user:secret@app.example.test/search?q=one", "param": "q", "location": "Query"},
        {"url": "https://app.example.test/search?q=one", "param": "q\nsecret", "location": "Query"},
        {"url": "https://app.example.test/search?q=one", "param": "q", "location": "Cookie"},
    )
    assert all(state.metadata(json.dumps(value)) == {} for value in invalid_rows)


def test_dalfox_discovery_jsonl_rejects_new_rows_after_the_fixed_cap():
    state = DalfoxParameterObservationState(
        "dalfox scan https://app.example.test --only-discovery --skip-mining-dict --format=jsonl",
        "run-dalfox",
    )
    assert state.metadata(json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "mode": "only_discovery",
        "params_discovered": DALFOX_MAX_PARAMETER_OBSERVATIONS + 1,
    }}))["source_detail"]["parameter_discovery"]["truncated"] is True
    observations = [state.metadata(json.dumps({
        "url": "https://app.example.test",
        "param": f"parameter_{index}",
        "location": "Query",
    })) for index in range(DALFOX_MAX_PARAMETER_OBSERVATIONS + 1)]
    assert all(observations[:DALFOX_MAX_PARAMETER_OBSERVATIONS])
    assert observations[-1] == {}


def test_dalfox_parameter_observations_survive_run_event_wire_round_trip():
    class Capture:
        def __init__(self):
            self.events = []

        def add_event(self, event):
            self.events.append(event)

    capture = Capture()
    classifier = OutputSignalClassifier(
        "dalfox scan https://app.example.test --only-discovery --skip-mining-dict --format jsonl",
        source_run_id="run-dalfox",
    )
    capture_event_with_signals(capture, classifier, json.dumps({"meta": {
        "dalfox_version": "v3.1.2", "mode": "only_discovery", "params_discovered": 1,
    }}))
    capture_event_with_signals(capture, classifier, json.dumps({
        "url": "https://app.example.test", "param": "view", "location": "Query",
    }))

    summary = capture.events[0].source_detail["parameter_discovery"]
    observation = capture.events[1].source_detail["parameter_observations"][0]
    assert summary["source_run_id"] == "run-dalfox"
    assert observation["parameter"] == "view"
    assert _source_detail(to_wire(capture.events[1]))["parameter_observations"] == [
        observation
    ]


def _dalfox_xss_context(**overrides):
    values = {
        "target": "https://app.example.test/search?q=one",
        "parameter": "q",
        "location": "Query",
        "source_parameter_run_id": "run-dalfox-discovery",
        "source_parameter_observation_id": "obs_" + ("a" * 32),
        "request_limit": 120,
    }
    values.update(overrides)
    return ReviewedDalfoxXssContext(**values)


def _dalfox_xss_classifier(context=None):
    return OutputSignalClassifier(
        "dalfox scan https://app.example.test/search?q=one -p q:query --skip-discovery "
        "--skip-mining --format jsonl",
        source_run_id="run-dalfox-xss",
        dalfox_xss_context=context or _dalfox_xss_context(),
    )


def _reviewed_dalfox_parameter_evidence(**overrides):
    values = {
        "source_run_id": "run-dalfox-discovery",
        "target": "https://app.example.test/search?q=one",
        "parameter": "q",
        "location": "Query",
        "tool_version": "v3.1.2",
        "parser_version": DALFOX_DISCOVERY_PARSER_VERSION,
    }
    values.update(overrides)
    values.setdefault("observation_id", dalfox_parameter_observation_id(
        values["source_run_id"], values["target"], values["location"], values["parameter"],
    ))
    return ReviewedDalfoxParameterEvidence(**values)


def test_reviewed_dalfox_xss_command_is_exact_bounded_and_evidence_derived():
    evidence = _reviewed_dalfox_parameter_evidence()
    plan = reviewed_dalfox_xss_command_plan(evidence)

    assert plan is not None
    assert plan.command.startswith("dalfox scan ")
    assert plan.request_limit is not None
    assert plan.request_limit == DALFOX_XSS_REQUEST_LIMIT == 256
    assert plan.time_limit_seconds == DALFOX_XSS_TIME_LIMIT_SECONDS == 90
    assert f"--max-payloads-per-param {DALFOX_XSS_MAX_PAYLOADS_PER_PARAMETER}" in plan.command
    assert f"--rate-limit {DALFOX_XSS_RATE_LIMIT_PER_SECOND}" in plan.command
    assert f"--scan-timeout {DALFOX_XSS_SCAN_TIMEOUT_SECONDS}" in plan.command
    assert f"--workers {DALFOX_XSS_WORKERS}" in plan.command
    assert "--param q:query" in plan.command
    assert "--skip-discovery --skip-mining" in plan.command
    assert "--max-concurrent-targets 1 --max-targets-per-host 1" in plan.command
    assert "--skip-waf-probe --waf-bypass off --insecure=false" in plan.command
    assert all(flag not in plan.command for flag in (
        "--follow-redirects", "--remote-payloads", "--custom-payload",
        "--blind", "--blind-oob", "--include-request", "--include-response",
    ))
    assert reviewed_dalfox_xss_command_matches(plan.command, evidence)
    assert assessment_command_mode(plan.command) == DALFOX_XSS_VALIDATION_MODE
    assert not reviewed_dalfox_xss_command_matches(plan.command + " --deep-scan", evidence)
    context = evidence.xss_context(request_limit=plan.request_limit)
    assert context.request_limit == DALFOX_XSS_REQUEST_LIMIT
    classifier = OutputSignalClassifier(
        plan.command,
        source_run_id="run-dalfox-xss",
        dalfox_xss_context=context,
    )
    metadata = classifier.classify_line(json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "targets": [evidence.target],
        "findings_count": 0,
        "total_requests": DALFOX_XSS_REQUEST_LIMIT,
        "scan_duration_ms": 60_000,
    }}))
    assert _source_detail(metadata)["dalfox_xss_scan"]["reported_finding_count"] == 0


def test_reviewed_dalfox_xss_action_requires_enabled_saved_parameter_selection():
    evidence = _reviewed_dalfox_parameter_evidence()
    options = DalfoxParameterOptions((evidence,))
    row = {
        "check_id": "ach_xss",
        "assessment_id": "asm_xss",
        "check_key": "xss_validation",
        "target_entity_id": "ent_xss",
        "target_type": "url",
        "target_value": evidence.target,
        "policy_level": "intrusive",
        "recommended_action_key": "command:dalfox",
        "profile_key": "web",
        "profile_version": "1.4",
        "profile_snapshot": json.dumps({"checks": [{
            "key": "xss_validation",
            "policy_level": "intrusive",
            "recommended_action": "command:dalfox",
        }]}),
        "assessment_status": "active",
        "project_status": "active",
    }
    target = {"entity_id": "ent_xss", "type": "url", "value": evidence.target}
    choose = build_assessment_action_plan(
        row, target, "prj_xss",
        dalfox_xss=DalfoxXssActionContext(options, None, False, False, True),
    )
    assert choose["launchable"] is False
    assert choose["unavailable_reason"].startswith("Choose one saved query-parameter")
    assert choose["evidence_selection"]["options"] == options.public_items()
    assert choose["evidence_selection"]["selected"] is None

    selected = DalfoxXssActionContext(options, evidence, True, False, True)
    plan = build_assessment_action_plan(row, target, "prj_xss", dalfox_xss=selected)
    assert plan["launchable"] is True
    assert plan["policy_level"] == "intrusive"
    reviewed_plan = reviewed_dalfox_xss_command_plan(evidence)
    assert reviewed_plan is not None
    assert plan["display_command"] == reviewed_plan.command
    assert plan["bounds"]["request_limit"] == DALFOX_XSS_REQUEST_LIMIT
    assert plan["bounds"]["time_limit_seconds"] == DALFOX_XSS_TIME_LIMIT_SECONDS
    assert plan["evidence_selection"]["selected"] == options.public_items()[0]

    protected = build_assessment_action_plan(
        row, target, "prj_xss",
        http_profile={"credential_use": ["headers"]},
        dalfox_xss=selected,
    )
    assert protected["display_command"].endswith("--config [protected]")
    assert protected["bounds"]["credential_use"] == "protected_http_profile"
    disabled = build_assessment_action_plan(
        row, target, "prj_xss",
        dalfox_xss=DalfoxXssActionContext(options, evidence, True, False, False),
    )
    assert disabled["launchable"] is False
    assert disabled["unavailable_reason"] == (
        "Intrusive Assessment actions are disabled on this deployment."
    )


def test_reviewed_dalfox_xss_command_rejects_unbound_or_unsupported_evidence():
    assert reviewed_dalfox_xss_command_plan(
        _reviewed_dalfox_parameter_evidence(location="Header"),
    ) is None
    assert reviewed_dalfox_xss_command_plan(
        _reviewed_dalfox_parameter_evidence(parameter="missing"),
    ) is None
    assert reviewed_dalfox_xss_command_plan(
        _reviewed_dalfox_parameter_evidence(
            target="https://app.example.test/search?q%3Aquery=one",
            parameter="q:query",
        ),
    ) is None
    assert reviewed_dalfox_xss_command_plan(
        _reviewed_dalfox_parameter_evidence(parser_version="caller-made"),
    ) is None
    assert reviewed_dalfox_xss_command_plan(
        _reviewed_dalfox_parameter_evidence(observation_id="obs_" + ("f" * 32)),
    ) is None
    assert reviewed_dalfox_xss_command_plan(cast(Any, SimpleNamespace(
        target="https://app.example.test/search?q=one",
        parameter="q",
        location="Query",
    ))) is None
    discovery = command_plan("dalfox", "url", "https://app.example.test/search?q=one")
    assert discovery is not None
    assert "--only-discovery" in discovery.command
    assert "--param" not in discovery.command
    assert assessment_command_mode(discovery.command) == DALFOX_PARAMETER_DISCOVERY_MODE


def test_reviewed_dalfox_execution_replaces_only_its_exact_validated_carrier():
    evidence = _reviewed_dalfox_parameter_evidence()
    reviewed = ReviewedDalfoxXssExecution(evidence)
    output_context = RunOutputSignalContext(
        dalfox_xss_context=reviewed.output_context,
    )
    discovery = command_plan("dalfox", "url", evidence.target, protected_display=False)
    active = reviewed_dalfox_xss_command_plan(evidence)

    assert discovery is not None
    assert active is not None
    assert reviewed.validation_command == discovery.command
    assert "--only-discovery" in reviewed.validation_command
    assert reviewed.execution_command == active.command
    assert "--skip-discovery" in reviewed.execution_command
    assert reviewed.output_context == evidence.xss_context(
        request_limit=DALFOX_XSS_REQUEST_LIMIT,
    )
    prepared = PreparedRealCommand(
        registry_command=reviewed.validation_command,
        execution_command=reviewed.validation_command,
        command=reviewed.validation_command + " --only-discovery --skip-mining-dict",
        rewrite_notice="Added bounded discovery flags.",
        validation=cast(Any, object()),
        missing_runtime=None,
        display_missing_runtime=None,
        env_overrides={},
        secret_env_names=[],
    )
    replaced = apply_reviewed_execution(
        prepared,
        reviewed,
        output_signal_context=output_context,
    )

    assert replaced.registry_command == reviewed.validation_command
    assert replaced.execution_command == reviewed.execution_command
    assert replaced.command == reviewed.execution_command
    assert replaced.rewrite_notice is None
    with pytest.raises(RunPreparationError, match="carrier no longer matches"):
        apply_reviewed_execution(
            SimpleNamespace(registry_command="dalfox https://other.example.test"),
            reviewed,
            output_signal_context=output_context,
        )
    with pytest.raises(RunPreparationError, match="output context no longer matches"):
        apply_reviewed_execution(prepared, reviewed)
    with pytest.raises(RunPreparationError, match="output context no longer matches"):
        apply_reviewed_execution(
            prepared,
            reviewed,
            output_signal_context=RunOutputSignalContext(
                dalfox_xss_context=_dalfox_xss_context(parameter="other"),
            ),
        )
    with pytest.raises(RunPreparationError, match="context is invalid"):
        apply_reviewed_execution(
            prepared,
            "caller-made",
            output_signal_context=output_context,
        )
    with pytest.raises(ValueError, match="execution is unavailable"):
        ReviewedDalfoxXssExecution(
            _reviewed_dalfox_parameter_evidence(location="Header"),
        )


def test_reviewed_dalfox_xss_jsonl_preserves_confidence_aware_proof():
    classifier = _dalfox_xss_classifier()
    summary = classifier.classify_line(json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "targets": ["https://app.example.test/search?q=one"],
        "findings_count": 5,
        "total_requests": 80,
        "scan_duration_ms": 2500,
    }}))
    rows = []
    for result_type, suffix in (("V", "executed"), ("A", "ast"), ("R", "reflected")):
        rows.append(_source_detail(classifier.classify_line(json.dumps({
            "type": result_type,
            "type_description": f"{result_type} result",
            "inject_type": "inHTML-double",
            "method": "GET",
            "param": "q",
            "payload": f"<svg id={suffix} onload=alert(1)>",
            "evidence": f"proof-{suffix}",
            "cwe": "CWE-79",
            "severity": "High",
            "message_id": f"{result_type}01",
            "message_str": f"Dalfox {suffix} result",
        })))["dalfox_xss_observations"][0])
    duplicate = classifier.classify_line(json.dumps({
        "type": "V", "type_description": "V result", "inject_type": "inHTML-double",
        "method": "GET", "param": "q", "payload": "<svg id=executed onload=alert(1)>",
        "evidence": "proof-executed", "cwe": "CWE-79", "severity": "High",
        "message_id": "V01", "message_str": "Dalfox executed result",
    }))
    informational = classifier.classify_line(json.dumps({
        "type": "I", "param": "q", "message_str": "informational component",
    }))

    assert _source_detail(summary)["dalfox_xss_scan"] == {
        "target": "https://app.example.test/search?q=one",
        "parameter": "q",
        "location": "Query",
        "source_parameter_run_id": "run-dalfox-discovery",
        "source_parameter_observation_id": "obs_" + ("a" * 32),
        "source_run_id": "run-dalfox-xss",
        "tool_version": "v3.1.2",
        "parser_version": DALFOX_XSS_PARSER_VERSION,
        "policy_level": "intrusive",
        "reported_finding_count": 5,
        "total_requests": 80,
        "scan_duration_ms": 2500,
        "truncated": False,
    }
    assert [(item["result_type"], item["validation_state"], item["confidence"])
            for item in rows] == [
        ("V", "confirmed", "high"),
        ("A", "needs_runtime_confirmation", "medium"),
        ("R", "reflected_unconfirmed", "low"),
    ]
    assert [item["validation_method"] for item in rows] == [
        "dalfox_dom_execution", "dalfox_ast_analysis", "dalfox_reflection",
    ]
    assert all(item["source_parameter_observation_id"] == "obs_" + ("a" * 32) for item in rows)
    assert all(item["source_parameter_run_id"] == "run-dalfox-discovery" for item in rows)
    assert all(item["proof_digest"].startswith("sha256:") for item in rows)
    assert all(item["cwe_ids"] == ["CWE-79"] for item in rows)
    assert "dalfox_xss_observations" not in _source_detail(duplicate)
    assert "dalfox_xss_observations" not in _source_detail(informational)


def test_reviewed_dalfox_findings_exit_requires_accepted_bound_evidence():
    context = _dalfox_xss_context()
    signal_context = RunOutputSignalContext(dalfox_xss_context=context)
    policy = completion_policy_for_signal_context(signal_context)
    classifier = _dalfox_xss_classifier(context)

    assert policy == RunCompletionPolicy(context)
    assert completion_policy_for_signal_context(None) is None
    assert effective_run_exit_code(
        1, completion_policy=policy, signal_classifier=classifier, output_sink_error=False,
    ) == 1
    classifier.classify_line(json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "targets": [context.target],
        "findings_count": 1,
        "total_requests": 80,
        "scan_duration_ms": 2500,
    }}))
    assert effective_run_exit_code(
        1, completion_policy=policy, signal_classifier=classifier, output_sink_error=False,
    ) == 1
    classifier.classify_line(json.dumps({
        "type": "V",
        "method": "GET",
        "param": context.parameter,
        "payload": "<svg onload=alert(1)>",
        "evidence": "executed in the reviewed DOM sink",
        "cwe": "CWE-79",
    }))

    assert effective_run_exit_code(
        1, completion_policy=policy, signal_classifier=classifier, output_sink_error=False,
    ) == 0
    assert effective_run_exit_code(
        1, completion_policy=policy, signal_classifier=classifier, output_sink_error=True,
    ) == 1
    assert effective_run_exit_code(
        2, completion_policy=policy, signal_classifier=classifier, output_sink_error=False,
    ) == 2
    assert effective_run_exit_code(
        1, completion_policy=None, signal_classifier=classifier, output_sink_error=False,
    ) == 1
    with pytest.raises(ValueError, match="invalid run completion context"):
        RunCompletionPolicy(cast(Any, "caller-made"))


def test_reviewed_schemathesis_findings_exit_requires_complete_private_report(caplog):
    reviewed = review_local_openapi_json(
        _openapi_json(paths={
            "/items/{item_id}": {
                "get": {"responses": {"200": {"description": "OK"}}},
            },
        }),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )
    reports = [_schemathesis_report_bytes()]
    report_context = ReviewedSchemathesisReportContext(
        schema=reviewed,
        project_id="prj_api",
        assessment_id="asm_api",
        check_id="ach_api",
        profile_key="api",
        profile_version="1.0",
        read_report=lambda: reports[0],
    )
    execution = ReviewedSchemathesisExecution(
        reviewed,
        Path("/tmp/private-http-runs/run-0123456789abcdef/schema.json"),
        Path("/tmp/private-http-runs/run-0123456789abcdef/schemathesis.toml"),
        Path("/tmp/private-http-runs/run-0123456789abcdef/events.ndjson"),
        report_context,
    )
    policy = completion_policy_for_signal_context(
        None,
        reviewed_execution=execution,
    )
    classifier = SimpleNamespace()

    assert policy == RunCompletionPolicy(schemathesis_execution=execution)
    assert policy is not None
    assert policy.name == "schemathesis_findings"
    assert effective_run_exit_code(
        1, completion_policy=policy, signal_classifier=classifier, output_sink_error=False,
    ) == 0
    assert effective_run_exit_code(
        1, completion_policy=policy, signal_classifier=classifier, output_sink_error=True,
    ) == 1
    assert effective_run_exit_code(
        2, completion_policy=policy, signal_classifier=classifier, output_sink_error=False,
    ) == 2

    reports[0] = _schemathesis_report_bytes(failure=False)
    assert effective_run_exit_code(
        1, completion_policy=policy, signal_classifier=classifier, output_sink_error=False,
    ) == 1
    reports[0] = b""
    assert effective_run_exit_code(
        1, completion_policy=policy, signal_classifier=classifier, output_sink_error=False,
    ) == 1
    assert [record.message for record in caplog.records].count(
        "SCHEMATHESIS_FINDINGS_EXIT_REJECTED"
    ) == 2


def test_reviewed_dalfox_xss_context_and_rows_fail_closed():
    with pytest.raises(ValueError, match="invalid reviewed Dalfox XSS context"):
        _dalfox_xss_context(target="https://user:secret@app.example.test/search?q=one")
    with pytest.raises(ValueError, match="invalid reviewed Dalfox XSS context"):
        _dalfox_xss_context(policy_level="standard")
    with pytest.raises(ValueError, match="invalid reviewed Dalfox XSS context"):
        _dalfox_xss_context(source_parameter_observation_id="caller-made")

    meta = json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "targets": ["https://app.example.test/search?q=one"],
        "findings_count": 5,
        "total_requests": 80,
        "scan_duration_ms": 2500,
    }})
    commands = (
        "dalfox scan https://app.example.test/search?q=one -p q:query --skip-mining --format jsonl",
        "dalfox scan https://app.example.test/search?q=one -p q:query --skip-discovery --format jsonl",
        "dalfox scan https://app.example.test/search?q=one -p other:query --skip-discovery --skip-mining --format jsonl",
        "dalfox scan https://other.example.test/search?q=one -p q:query --skip-discovery --skip-mining --format jsonl",
    )
    assert all("dalfox_xss_scan" not in _source_detail(OutputSignalClassifier(
        command,
        source_run_id="run-dalfox-xss",
        dalfox_xss_context=_dalfox_xss_context(),
    ).classify_line(meta)) for command in commands)
    assert "dalfox_xss_scan" not in _source_detail(OutputSignalClassifier(
        commands[0] + " --skip-discovery",
        source_run_id="run-dalfox-xss",
    ).classify_line(meta))
    assert "dalfox_xss_scan" not in _source_detail(OutputSignalClassifier(
        commands[0] + " --skip-discovery",
        source_run_id="run-dalfox-xss",
        dalfox_xss_context=cast(
            Any, {"target": "https://app.example.test/search?q=one"}
        ),
    ).classify_line(meta))

    classifier = _dalfox_xss_classifier()
    assert "dalfox_xss_scan" not in _source_detail(classifier.classify_line(json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "targets": ["https://other.example.test/search?q=one"],
        "findings_count": 1,
        "total_requests": 80,
        "scan_duration_ms": 2500,
    }})))
    assert "dalfox_xss_scan" not in _source_detail(classifier.classify_line(json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "targets": ["https://app.example.test/search?q=one"],
        "findings_count": 1,
        "total_requests": 121,
        "scan_duration_ms": 2500,
    }})))
    assert _source_detail(classifier.classify_line(meta))["dalfox_xss_scan"]
    invalid_rows = (
        {"type": "V", "param": "other", "method": "GET", "payload": "<svg>",
         "evidence": "proof", "cwe": "CWE-79"},
        {"type": "V", "param": "q", "method": "GET", "payload": "<svg>",
         "evidence": "proof", "cwe": "CWE-89"},
        {"type": "V", "param": "q", "method": "GET", "payload": "<svg>",
         "evidence": "proof", "cwe": "CWE-79", "request": "GET /private"},
        {"type": "V", "param": "q", "method": "GET", "payload": "<svg>\n",
         "evidence": "proof", "cwe": "CWE-79"},
        {"type": "X", "param": "q", "method": "GET", "payload": "<svg>",
         "evidence": "proof", "cwe": "CWE-79"},
    )
    assert all("dalfox_xss_observations" not in _source_detail(classifier.classify_line(
        json.dumps(row),
    )) for row in invalid_rows)


def test_dalfox_xss_observations_are_bounded_and_survive_event_wire_round_trip():
    class Capture:
        def __init__(self):
            self.events = []

        def add_event(self, event):
            self.events.append(event)

    capture = Capture()
    classifier = _dalfox_xss_classifier(_dalfox_xss_context(request_limit=10_000))
    capture_event_with_signals(capture, classifier, json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "targets": ["https://app.example.test/search?q=one"],
        "findings_count": DALFOX_XSS_MAX_OBSERVATIONS + 1,
        "total_requests": 1000,
        "scan_duration_ms": 2500,
    }}))
    for index in range(DALFOX_XSS_MAX_OBSERVATIONS + 1):
        capture_event_with_signals(capture, classifier, json.dumps({
            "type": "R",
            "method": "GET",
            "param": "q",
            "payload": f"payload-{index}",
            "evidence": f"evidence-{index}",
            "cwe": "79",
        }))

    summary = capture.events[0].source_detail["dalfox_xss_scan"]
    observations = [event.source_detail["dalfox_xss_observations"][0]
                    for event in capture.events[1:] if "dalfox_xss_observations" in event.source_detail]
    assert summary["truncated"] is True
    assert len(observations) == DALFOX_XSS_MAX_OBSERVATIONS
    assert _source_detail(to_wire(capture.events[1]))["dalfox_xss_observations"] == [
        observations[0]
    ]
    assert _dalfox_xss_classifier().classify_line(
        "{" + (" " * DALFOX_XSS_JSON_MAX_LINE_BYTES) + "}",
    ).get("source_detail", {}) == {}


def test_httpx_json_preserves_only_exact_versioned_technology_cpe_observations():
    record = {
        "url": "https://App.Example.test:443/",
        "timestamp": "2026-08-07T20:00:00Z",
        "tech": ["Nginx:1.25.5", "PHP"],
        "cpe": [{
            "product": "nginx",
            "vendor": "F5",
            "cpe": "cpe:2.3:a:f5:nginx:1.25.5:*:*:*:*:*:*:*",
        }],
    }
    parsed = normalize_httpx_version_observations(record, source_run_id="run-httpx")
    assert parsed["source"] == "httpx_json"
    assert parsed["parser_version"] == HTTPX_JSON_CPE_PARSER_VERSION
    assert parsed["truncated"] is False
    assert parsed["observations"] == [{
        "observation_id": parsed["observations"][0]["observation_id"],
        "target": "https://app.example.test",
        "cpe": "cpe:2.3:a:f5:nginx:1.25.5:*:*:*:*:*:*:*",
        "version": "1.25.5",
        "technology": "Nginx:1.25.5",
        "product": "nginx",
        "vendor": "F5",
        "source_run_id": "run-httpx",
        "observed_at": "2026-08-07T20:00:00Z",
        "parser_version": HTTPX_JSON_CPE_PARSER_VERSION,
    }]
    assert parsed["observations"][0]["observation_id"].startswith("obs_")


def test_httpx_json_version_observations_fail_closed_on_ambiguous_or_unsafe_input():
    base = {
        "url": "https://app.example.test",
        "timestamp": "2026-08-07T20:00:00+00:00",
        "tech": ["Nginx:1.25.5"],
        "cpe": [{
            "product": "nginx", "vendor": "F5",
            "cpe": "cpe:2.3:a:f5:nginx:1.25.5:*:*:*:*:*:*:*",
        }],
    }
    assert not normalize_httpx_version_observations(
        {**base, "tech": ["Nginx"]}, source_run_id="run-1",
    )["observations"]
    assert not normalize_httpx_version_observations(
        {**base, "tech": ["Nginx:1.25.4"]}, source_run_id="run-1",
    )["observations"]
    assert not normalize_httpx_version_observations(
        {**base, "tech": ["Nginx:1.25.5", "Nginx:1.26.0"]}, source_run_id="run-1",
    )["observations"]
    assert not normalize_httpx_version_observations(
        {**base, "url": "https://user:secret@app.example.test"}, source_run_id="run-1",
    )["observations"]
    assert not normalize_httpx_version_observations(
        {**base, "timestamp": "2026-08-07T20:00:00"}, source_run_id="run-1",
    )["observations"]
    assert not normalize_httpx_version_observations(
        {**base, "cpe": [{**base["cpe"][0], "product": "Apache"}]},
        source_run_id="run-1",
    )["observations"]


def test_httpx_json_version_observations_are_bounded_without_evicting_earlier_rows():
    parsed = normalize_httpx_version_observations({
        "url": "https://app.example.test",
        "timestamp": "2026-08-07T20:00:00Z",
        "tech": ["Nginx:1.25.5"],
        "cpe": [{
            "product": "nginx",
            "vendor": "F5",
            "cpe": f"cpe:2.3:a:f5:nginx:1.25.5:update-{index}:*:*:*:*:*:*",
        } for index in range(40)],
    }, source_run_id="run-httpx")
    assert len(parsed["observations"]) == 32
    assert parsed["truncated"] is True
    assert parsed["observations"][0]["cpe"].endswith("update-0:*:*:*:*:*:*")
    assert parsed["observations"][-1]["cpe"].endswith("update-31:*:*:*:*:*:*")


def test_httpx_json_version_observations_survive_run_event_wire_round_trip():
    class Capture:
        def __init__(self):
            self.events = []

        def add_event(self, event):
            self.events.append(event)

    line = (
        '{"url":"https://app.example.test","timestamp":"2026-08-07T20:00:00Z",'
        '"tech":["Nginx:1.25.5"],"cpe":[{"product":"nginx","vendor":"F5",'
        '"cpe":"cpe:2.3:a:f5:nginx:1.25.5:*:*:*:*:*:*:*"}]}'
    )
    capture = Capture()
    classifier = OutputSignalClassifier("httpx -json -cpe", source_run_id="run-httpx")
    capture_event_with_signals(capture, classifier, line)
    observation = capture.events[0].source_detail["version_observations"][0]
    assert observation["source_run_id"] == "run-httpx"
    assert observation["technology"] == "Nginx:1.25.5"
    assert _source_detail(to_wire(capture.events[0]))["version_observations"] == [
        observation
    ]


def test_real_command_classifier_receives_generated_run_id(monkeypatch):
    classifier_call = {}

    class Classifier:
        def __init__(self, command, **kwargs):
            classifier_call.update({"command": command, **kwargs})

    class Process:
        pid = 4321

    prepared = PreparedRealCommand(
        registry_command="httpx -u https://app.example.test -json -cpe",
        execution_command="httpx -u https://app.example.test -json -cpe",
        command="httpx -u https://app.example.test -json -cpe",
        rewrite_notice=None,
        validation=cast(Any, None),
        missing_runtime=None,
        display_missing_runtime=None,
        env_overrides={},
        secret_env_names=[],
    )
    started = start_real_command_process(
        prepared.command,
        "session-httpx",
        "192.0.2.1",
        prepared,
        output_signal_context=RunOutputSignalContext(
            nuclei_takeover_template=ReviewedNucleiTakeoverTemplate(
                "http-takeover-reviewed", "2026.08.1", "sha256:" + ("a" * 64), "safe",
            ),
            dalfox_xss_context=_dalfox_xss_context(),
        ),
        cfg={"output_entity_extra_domain_suffixes": []},
        run_output_capture_fn=cast(Any, lambda run_id: {"run_id": run_id}),
        popen_fn=cast(Any, lambda *args, **kwargs: Process()),
        pid_register_fn=lambda *args: None,
        active_run_register_fn=lambda *args, **kwargs: None,
        output_signal_classifier_cls=cast(Any, Classifier),
        workspace_path_filter_cls=lambda *args, **kwargs: object(),
        owner_context_for_scope_fn=cast(Any, lambda *args, **kwargs: object()),
        scanner_prefix=(),
        stdbuf_bin=None,
        shell_bin="/bin/sh",
    )
    assert classifier_call == {
        "command": prepared.command,
        "cmd_type": "real",
        "extra_domain_suffixes": [],
        "source_run_id": started.run_id,
        "nuclei_takeover_template": ReviewedNucleiTakeoverTemplate(
            "http-takeover-reviewed", "2026.08.1", "sha256:" + ("a" * 64), "safe",
        ),
        "dalfox_xss_context": _dalfox_xss_context(),
    }
    assert output_signal_classifier_kwargs(None) == {}
    with pytest.raises(ValueError, match="invalid run output signal context"):
        output_signal_classifier_kwargs(cast(
            Any, {"nuclei_takeover_template": "caller-made"}
        ))
    with pytest.raises(ValueError, match="invalid Dalfox XSS signal context"):
        RunOutputSignalContext(dalfox_xss_context=cast(Any, "caller-made"))
    with pytest.raises(ValueError, match="invalid Nuclei template snapshot context"):
        RunOutputSignalContext(nuclei_template_snapshot=cast(Any, "caller-made"))

    context = RunOutputSignalContext(
        nuclei_takeover_template=ReviewedNucleiTakeoverTemplate(
            "http-takeover-reviewed", "2026.08.1", "sha256:" + ("a" * 64), "safe",
        ),
        dalfox_xss_context=_dalfox_xss_context(),
    )
    broker_call = {}

    def start_real(*args, **kwargs):
        broker_call.update({"args": args, "kwargs": kwargs})
        return SimpleNamespace(
            run_id="run-context",
            run_started="2026-08-07T20:00:00+00:00",
            proc=Process(),
            capture=object(),
            signal_classifier=object(),
            workspace_path_filter=object(),
        )

    class Thread:
        created = {}

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            type(self).created = kwargs

        def start(self):
            return None

    handlers = RunStartHandlers(
        resolves_exact_special_builtin_command=lambda _command: False,
        execute_builtin_command=lambda *_args, **_kwargs: ([], 0),
        history_safe_command_for_storage=str,
        brokered_synthetic_run=lambda *_args, **_kwargs: "run-synthetic",
        prepare_command_input=lambda command, *_args, **_kwargs: SimpleNamespace(
            execution_command=command,
            variable_notice="",
            postfilter=SimpleNamespace(output_sink_error=False),
        ),
        resolve_builtin_command=lambda _command: None,
        filter_builtin_command_events=lambda events, *_args: events,
        prepare_real_command=lambda *_args, **_kwargs: prepared,
        runtime_missing_command_message=str,
        start_real_command_process=start_real,
        publish_run_event=lambda *_args: None,
        brokered_real_run_worker=lambda **_kwargs: None,
        workspace_notice_lines=lambda _validation: [],
        workspace_artifacts_from_validation=lambda *_args: [],
    )
    monkeypatch.setattr("services.runs.start.owner_context_for_scope", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("services.runs.start.threading.Thread", Thread)
    brokered = start_brokered_run(
        original_command=prepared.command,
        session_id="session-httpx",
        client_ip="192.0.2.1",
        handlers=handlers,
        output_signal_context=context,
    )
    assert brokered.run_id == "run-context"
    assert broker_call["kwargs"]["output_signal_context"] is context
    assert Thread.created["kwargs"]["completion_policy"] == RunCompletionPolicy(
        context.dalfox_xss_context,
    )
    reviewed_execution = ReviewedDalfoxXssExecution(
        _reviewed_dalfox_parameter_evidence(),
    )
    prepare_call = {}

    def prepare_with_reviewed_execution(*args, **kwargs):
        prepare_call.update({"args": args, "kwargs": kwargs})
        return prepared

    monkeypatch.setattr(
        "services.runs.start.private_data.prepare_real_command",
        prepare_with_reviewed_execution,
    )
    start_brokered_run(
        original_command=reviewed_execution.validation_command,
        display_command=reviewed_execution.execution_command,
        session_id="session-httpx",
        client_ip="192.0.2.1",
        handlers=handlers,
        reviewed_execution=reviewed_execution,
        output_signal_context=RunOutputSignalContext(
            dalfox_xss_context=reviewed_execution.output_context,
        ),
    )
    assert prepare_call["kwargs"]["reviewed_execution"] is reviewed_execution
    assert (
        prepare_call["kwargs"]["output_signal_context"].dalfox_xss_context
        == reviewed_execution.output_context
    )
    reviewed_schema = review_local_openapi_json(
        _openapi_json(),
        source_artifact_id="rfa_0123456789abcdef",
        base_url="https://api.example.test/v1",
    )
    schemathesis_execution = ReviewedSchemathesisExecution(
        reviewed_schema,
        Path("/tmp/private-http-runs/run-0123456789abcdef/schema.json"),
        Path("/tmp/private-http-runs/run-0123456789abcdef/schemathesis.toml"),
        Path("/tmp/private-http-runs/run-0123456789abcdef/events.ndjson"),
        ReviewedSchemathesisReportContext(
            schema=reviewed_schema,
            project_id="prj_api",
            assessment_id="asm_api",
            check_id="ach_api",
            profile_key="api",
            profile_version="1.0",
            read_report=lambda: b"",
        ),
    )
    start_brokered_run(
        original_command=schemathesis_execution.validation_command,
        display_command=schemathesis_execution.execution_command,
        session_id="session-httpx",
        client_ip="192.0.2.1",
        handlers=handlers,
        reviewed_execution=schemathesis_execution,
    )
    assert prepare_call["kwargs"]["reviewed_execution"] is schemathesis_execution
    assert Thread.created["kwargs"]["completion_policy"] == RunCompletionPolicy(
        schemathesis_execution=schemathesis_execution,
    )
    with pytest.raises(ValueError, match="invalid run output signal context"):
        start_brokered_run(
            original_command=prepared.command,
            session_id="session-httpx",
            client_ip="192.0.2.1",
            handlers=handlers,
            output_signal_context=cast(
                Any, {"nuclei_takeover_template": "caller-made"}
            ),
        )


def test_httpx_assessment_plan_requests_structured_versioned_cpe_output():
    plan = command_plan("httpx", "url", "https://app.example.test")
    assert plan is not None
    assert "-tech-detect -json -cpe -silent" in plan.command
    assert "-rl 10 -threads 5" in plan.command
    assert "versioned CPE metadata" in plan.boundary
    assert "10 requests per second, and concurrency 5" in plan.boundary


def test_gau_output_carries_historical_url_provenance_only():
    classifier = OutputSignalClassifier("gau example.com", source_run_id="run-gau")
    metadata = classifier.classify_line("https://example.com/archive?a=1")
    assert metadata["historical_urls"] == [{
        "url": "https://example.com/archive?a=1", "source": "gau", "source_run_id": "run-gau",
    }]
    entities = metadata["entities"]
    assert isinstance(entities, list)
    url_entity = next(entity for entity in entities if entity.get("type") == "url")
    assert url_entity["attributes"] == {
        "discovery_mode": "passive", "provider": "gau", "source_run_id": "run-gau",
    }
    assert "signals" not in metadata


def test_passive_web_metadata_survives_run_event_wire_round_trip():
    class Capture:
        def __init__(self):
            self.events = []

        def add_event(self, event):
            self.events.append(event)

    capture = Capture()
    capture_event_with_signals(capture, OutputSignalClassifier("gau example.com", source_run_id="run-1"), "https://example.com/a")
    assert capture.events[0].source_detail["historical_urls"][0]["source_run_id"] == "run-1"
    wire = to_wire(capture.events[0])
    assert _source_detail(wire)["historical_urls"][0]["url"] == "https://example.com/a"


def test_gau_command_plan_is_domain_scoped_and_passive():
    plan = command_plan("gau", "domain", "example.com")
    assert plan is not None
    assert plan.command == "gau --subs --threads 2 --timeout 10 example.com"
    assert "not probed automatically" in plan.boundary
    assert plan.time_limit_seconds == 120


def test_version_correlation_requires_exact_identifier_and_version_matches():
    component_payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "metadata": {"timestamp": "2026-08-07T00:00:00Z"},
        "components": [{
            "type": "library",
            "bom-ref": "pkg:pypi/requests@2.31.0",
            "name": "requests",
            "version": "2.31.0",
            "purl": "pkg:pypi/requests@2.31.0",
        }, {
            "name": "conflict",
            "version": "2.32.0",
            "purl": "pkg:pypi/requests@2.31.0",
        }, {
            "type": "application",
            "bom-ref": "component-server-2.5.1",
            "name": "server",
            "version": "2.5.1",
            "purl": "pkg:generic/example/server@2.5.1",
            "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
        }, {
            "name": "conflicting CPE version",
            "version": "2.6.0",
            "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
        }],
    }
    parsed_components = parse_cyclonedx_package_observations(
        json.dumps(component_payload).encode(),
        source_batch_id="batch-cyclonedx-1",
    )
    assert parsed_components["parser_version"] == CYCLONEDX_COMPONENT_PARSER_VERSION
    assert parsed_components["tool_version"] == "CycloneDX 1.5"
    assert parsed_components["observations"] == [
        {
            "observation_id": parsed_components["observations"][0]["observation_id"],
            "target": "pkg:pypi/requests",
            "purl": "pkg:pypi/requests",
            "version": "2.31.0",
            "component_name": "requests",
            "component_type": "library",
            "bom_ref": "pkg:pypi/requests@2.31.0",
            "source_batch_id": "batch-cyclonedx-1",
            "observed_at": "2026-08-07T00:00:00Z",
            "tool_version": "CycloneDX 1.5",
            "parser_version": CYCLONEDX_COMPONENT_PARSER_VERSION,
        },
        {
            "observation_id": parsed_components["observations"][1]["observation_id"],
            "target": "pkg:generic/example/server",
            "purl": "pkg:generic/example/server",
            "version": "2.5.1",
            "component_name": "server",
            "component_type": "application",
            "bom_ref": "component-server-2.5.1",
            "source_batch_id": "batch-cyclonedx-1",
            "observed_at": "2026-08-07T00:00:00Z",
            "tool_version": "CycloneDX 1.5",
            "parser_version": CYCLONEDX_COMPONENT_PARSER_VERSION,
        },
    ]
    bounded_components = parse_cyclonedx_package_observations(
        json.dumps({
            **component_payload,
            "components": [{
                "name": f"package-{index}",
                "version": "1.0.0",
                "purl": f"pkg:pypi/package-{index}@1.0.0",
            } for index in range(CYCLONEDX_MAX_PACKAGE_OBSERVATIONS + 1)],
        }).encode(),
        source_batch_id="batch-cyclonedx-bounded",
    )
    assert len(bounded_components["observations"]) == CYCLONEDX_MAX_PACKAGE_OBSERVATIONS
    assert bounded_components["truncated"] is True
    parsed_cpes = parse_cyclonedx_cpe_observations(
        json.dumps(component_payload).encode(),
        source_batch_id="batch-cyclonedx-cpe-1",
    )
    assert parsed_cpes["parser_version"] == CYCLONEDX_CPE_PARSER_VERSION
    assert parsed_cpes["observations"] == [{
        "observation_id": parsed_cpes["observations"][0]["observation_id"],
        "target": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
        "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
        "version": "2.5.1",
        "component_name": "server",
        "component_type": "application",
        "component_purl": "pkg:generic/example/server@2.5.1",
        "bom_ref": "component-server-2.5.1",
        "source_batch_id": "batch-cyclonedx-cpe-1",
        "observed_at": "2026-08-07T00:00:00Z",
        "tool_version": "CycloneDX 1.5",
        "parser_version": CYCLONEDX_CPE_PARSER_VERSION,
    }]
    bounded_cpes = parse_cyclonedx_cpe_observations(
        json.dumps({
            **component_payload,
            "components": [{
                "name": f"product-{index}",
                "version": "1.0.0",
                "cpe": f"cpe:2.3:a:example:product{index}:1.0.0:*:*:*:*:*:*:*",
            } for index in range(CYCLONEDX_MAX_CPE_OBSERVATIONS + 1)],
        }).encode(),
        source_batch_id="batch-cyclonedx-cpe-bounded",
    )
    assert len(bounded_cpes["observations"]) == CYCLONEDX_MAX_CPE_OBSERVATIONS
    assert bounded_cpes["truncated"] is True
    advisories = [{
        "id": "CVE-2026-1234", "purls": ["pkg:pypi/requests"],
        "affected_versions": ["2.31.0"], "affected_range": "==2.31.0",
    }]
    matches = correlate_version_observation({"purl": "pkg:pypi/requests", "version": "2.31.0"}, advisories)
    assert matches == [{
        "vulnerability_id": "CVE-2026-1234", "confidence": "high",
        "match_basis": "exact_purl_version", "observed_identifier": "pkg:pypi/requests",
        "observed_version": "2.31.0", "affected_range": "==2.31.0",
        "range_type": "EXACT", "advisory_source": "", "advisory_source_version": "",
        "validation_method": "version_inference",
    }]
    assert correlate_version_observation({"product": "requests", "version": "2.31.0"}, advisories) == []
    assert correlate_version_observation({"purl": "pkg:pypi/requests", "version": "2.32.0"}, advisories) == []
    records = materialize_version_findings(
        {"purl": "pkg:pypi/requests", "version": "2.31.0", "target": "api.example.test", "observation_id": "obs-1"},
        advisories,
        source_run_id="run-1", observed_at="2026-08-07T00:00:00Z", tool_version="nmap 7.96",
        parser_version="nmap-xml-v2",
    )
    assert records[0]["validation_method"] == "version_inference"
    assert records[0]["observed_identifier"] == "pkg:pypi/requests"
    assert records[0]["observed_version"] == "2.31.0"
    assert records[0]["source"] == {
        "run_id": "run-1", "kind": "run", "observation_id": "obs-1",
        "observed_at": "2026-08-07T00:00:00Z", "tool_version": "nmap 7.96",
        "parser_version": "nmap-xml-v2",
    }
    imported = materialize_version_findings(
        {"purl": "pkg:pypi/requests@2.31.0", "target": "api.example.test", "observation_id": "obs-2"},
        advisories,
        source_kind="import", source_batch_id="imp-1", observed_at="2026-08-07T00:01:00Z",
        tool_version="cyclonedx 1.6", parser_version="cyclonedx-v1",
    )
    assert imported[0]["source"] == {
        "kind": "import", "observation_id": "obs-2", "observed_at": "2026-08-07T00:01:00Z",
        "tool_version": "cyclonedx 1.6", "batch_id": "imp-1", "parser_version": "cyclonedx-v1",
    }
    ranged_advisory = [{
        "id": "GHSA-range", "source": "osv", "source_version": "2026-08-07",
        "package_purl": "pkg:pypi/requests",
        "ranges": [{
            "range_type": "SEMVER",
            "events_json": '[{"introduced":"2.30.0"},{"fixed":"2.32.0"}]',
        }],
    }]
    ranged = correlate_version_observation({"purl": "pkg:pypi/requests@2.31.0"}, ranged_advisory)
    assert ranged == [{
        "vulnerability_id": "GHSA-range", "confidence": "high",
        "match_basis": "exact_purl_semver_range", "observed_identifier": "pkg:pypi/requests",
        "observed_version": "2.31.0", "affected_range": "SEMVER: introduced 2.30.0; fixed 2.32.0",
        "range_type": "SEMVER", "advisory_source": "osv", "advisory_source_version": "2026-08-07",
        "validation_method": "version_inference",
    }]
    assert correlate_version_observation({"purl": "pkg:pypi/requests@2.29.9"}, ranged_advisory) == []
    assert correlate_version_observation({"purl": "pkg:pypi/requests@2.32.0"}, ranged_advisory) == []
    assert correlate_version_observation({
        "purl": "pkg:pypi/requests@2.31.0", "version": "2.32.0",
    }, ranged_advisory) == []
    unsupported = [{
        **ranged_advisory[0],
        "ranges": [{"range_type": "ECOSYSTEM", "introduced": "2.30.0", "fixed": "2.32.0"}],
    }]
    assert correlate_version_observation({"purl": "pkg:pypi/requests@2.31.0"}, unsupported) == []
    assert correlate_version_observation({"purl": "pkg:npm/@scope/widget@2.31.0"}, [{
        **ranged_advisory[0], "package_purl": "pkg:npm/@scope/widget",
    }])[0]["observed_identifier"] == "pkg:npm/@scope/widget"
    reversed_events = [{
        **ranged_advisory[0],
        "ranges": [{
            "range_type": "SEMVER",
            "events": [{"fixed": "2.32.0"}, {"introduced": "2.30.0"}],
        }],
    }]
    assert correlate_version_observation({"purl": "pkg:pypi/requests@2.31.0"}, reversed_events) == []
    ranged_records = materialize_version_findings(
        {"purl": "pkg:pypi/requests@2.31.0", "target": "api.example.test"}, ranged_advisory,
    )
    assert ranged_records[0]["advisory_source"] == "osv"
    assert ranged_records[0]["advisory_source_version"] == "2026-08-07"
    cpe_observation = {
        "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
    }
    cpe_advisory = [{
        "id": "CVE-2026-5678", "source": "nvd", "source_version": "2026-08-07T12:00:00Z",
        "cpe_matches": [{
            "criteria": "cpe:2.3:a:example:server:*:*:*:*:*:*:*:*",
            "vulnerable": True,
            "applicability_complete": True,
            "versionStartIncluding": "2.4",
            "versionEndExcluding": "2.6",
        }],
    }]
    cpe_matches = correlate_version_observation(cpe_observation, cpe_advisory)
    assert cpe_matches[0] == {
        "vulnerability_id": "CVE-2026-5678", "confidence": "high",
        "match_basis": "exact_cpe_nvd_range", "observed_identifier": cpe_observation["cpe"],
        "observed_version": "2.5.1", "affected_range": "NVD: >= 2.4; < 2.6",
        "range_type": "CPE_NUMERIC", "advisory_source": "nvd",
        "advisory_source_version": "2026-08-07T12:00:00Z",
        "validation_method": "version_inference",
    }
    assert correlate_version_observation({
        "cpe": "cpe:2.3:a:example:server:2.6:*:*:*:*:*:*:*",
    }, cpe_advisory) == []
    nmap_xml = """<?xml version="1.0"?>
<nmaprun version="7.96">
  <host><address addr="192.0.2.10" addrtype="ipv4"/><ports>
    <port protocol="tcp" portid="443"><state state="open"/><service name="https">
      <cpe>cpe:/a:example:server:2.5.1</cpe>
    </service></port>
    <port protocol="tcp" portid="22"><state state="closed"/><service name="ssh">
      <cpe>cpe:/a:example:ssh:1.0</cpe>
    </service></port>
  </ports></host>
</nmaprun>"""
    nmap_observations = parse_nmap_xml_cpe_observations(
        nmap_xml,
        source_run_id="run-nmap-xml-1",
        observed_at="2026-08-07T12:00:00+00:00",
    )
    assert nmap_observations == {
        "source": "nmap_xml",
        "source_run_id": "run-nmap-xml-1",
        "tool_version": "7.96",
        "parser_version": "nmap-xml-cpe-v1",
        "observed_at": "2026-08-07T12:00:00+00:00",
        "observations": [{
            "observation_id": nmap_observations["observations"][0]["observation_id"],
            "target": "192.0.2.10:443/tcp",
            "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
            "version": "2.5.1",
        }],
        "truncated": False,
    }
    assert nmap_observations["observations"][0]["observation_id"].startswith("obs_")
    assert parse_nmap_xml_cpe_observations(
        '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><nmaprun version="7.96">&xxe;</nmaprun>',
        source_run_id="run-nmap-xml-1",
        observed_at="2026-08-07T12:00:00+00:00",
    )["observations"] == []
    bounded_ports = "".join(
        f'<port protocol="tcp" portid="{1000 + index}"><state state="open"/>'
        f'<service><cpe>cpe:2.3:a:example:service{index}:1.0:*:*:*:*:*:*:*</cpe>'
        "</service></port>"
        for index in range(51)
    )
    bounded_nmap = parse_nmap_xml_cpe_observations(
        f'<nmaprun version="7.96"><host><address addr="192.0.2.20"/>'
        f"<ports>{bounded_ports}</ports></host></nmaprun>",
        source_run_id="run-nmap-xml-bounded",
        observed_at="2026-08-07T12:00:00+00:00",
    )
    assert len(bounded_nmap["observations"]) == 50
    assert bounded_nmap["truncated"] is True
    incomplete_cpe = [{
        **cpe_advisory[0],
        "cpe_matches": [{
            **cpe_advisory[0]["cpe_matches"][0], "applicability_complete": False,
        }],
    }]
    assert correlate_version_observation(cpe_observation, incomplete_cpe) == []
    unbounded_cpe = [{
        **cpe_advisory[0],
        "cpe_matches": [{
            "criteria": "cpe:2.3:a:example:server:*:*:*:*:*:*:*:*",
            "vulnerable": True, "applicability_complete": True,
        }],
    }]
    assert correlate_version_observation(cpe_observation, unbounded_cpe) == []
    assert correlate_version_observation(cpe_observation, [{
        **unbounded_cpe[0],
        "cpe_matches": [{**unbounded_cpe[0]["cpe_matches"][0], "all_versions": True}],
    }])[0]["match_basis"] == "exact_cpe_all_versions"
    nonnumeric_cpe = [{
        **cpe_advisory[0],
        "cpe_matches": [{
            **cpe_advisory[0]["cpe_matches"][0], "versionEndExcluding": "2.6-beta",
        }],
    }]
    assert correlate_version_observation(cpe_observation, nonnumeric_cpe) == []
    malformed_cpe = [{
        **cpe_advisory[0],
        "cpe_matches": [{
            **cpe_advisory[0]["cpe_matches"][0],
            "negate": [], "versionEndExcluding": {},
        }],
    }]
    assert correlate_version_observation(cpe_observation, malformed_cpe) == []
    environment_specific = [{
        **cpe_advisory[0],
        "cpe_matches": [{
            **cpe_advisory[0]["cpe_matches"][0],
            "criteria": "cpe:2.3:a:example:server:*:*:*:*:*:windows:*:*",
        }],
    }]
    assert correlate_version_observation(cpe_observation, environment_specific) == []
    assert correlate_version_observation(cpe_observation, [{
        **cpe_advisory[0],
        "cpe_matches": cpe_advisory[0]["cpe_matches"] * 65,
    }]) == []
