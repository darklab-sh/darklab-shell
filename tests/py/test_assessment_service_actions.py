# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from services.assessments.service_actions import service_actions, service_evidence_state
from services.assessments.command_plans import command_plan
from services.assessments.nmap_profiles import nmap_profile_args, nmap_profile_keys
from services.assessments.takeover_detection import evaluate_takeover_signal
from services.assessments.web_surface import normalize_httpx_screenshot
from services.assessments.version_correlation import correlate_version_observation
from core.output_signals import OutputSignalClassifier
from services.atlas.observations import public_app_port_record


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
    assert service_actions("version-cve", target_type="url")[0].command == (
        "evidence:version_cve_correlation"
    )
    assert service_actions("version-cve", target_type="port") == ()


def test_service_actions_can_be_serialized_for_read_surfaces_without_launching():
    action = service_actions("https")[0]
    assert action.command == "command:httpx"
    assert "url" in action.target_types
    record = public_app_port_record({"port": 443, "service": "https", "_run_ids": {"run-1"}})
    assert record["assessment_actions"][0]["command"] == "command:httpx"
    assert "_run_ids" not in record


def test_nmap_profiles_are_fixed_and_reject_arbitrary_script_arguments():
    assert nmap_profile_args("tls") == ("--script", "ssl-cert,ssl-enum-ciphers")
    assert nmap_profile_args("--script=exploit") == ()
    assert nmap_profile_keys() == ("safe", "version", "discovery", "tls", "ssh", "smtp")
    plan = command_plan("nmap", "ip", "192.0.2.10", nmap_profile="ssh")
    assert plan is not None
    assert "--script ssh2-enum-algos,ssh-hostkey" in plan.command


def test_takeover_signal_keeps_dangling_records_potential_until_reviewed_confirmation():
    potential = evaluate_takeover_signal({
        "hostname": "app.example.test", "cname_chain": ["app.vendor.test."],
        "provider": "vendor", "target_resolved": False, "in_scope": True,
    })
    assert potential["state"] == "potential"
    confirmed = evaluate_takeover_signal({
        "hostname": "app.example.test", "cname_chain": ["app.vendor.test"],
        "provider": "vendor", "target_resolved": False, "in_scope": True,
        "reviewed_takeover_template_match": True,
    })
    assert confirmed["state"] == "confirmed"
    assert evaluate_takeover_signal({"hostname": "app.example.test", "resolution_state": "timeout"})["state"] == "uncertain"
    assert evaluate_takeover_signal({"hostname": "app.example.test", "cname_chain": ["outside.test"], "target_resolved": False, "in_scope": False})["reason"] == "out_of_scope_target"


def test_httpx_screenshot_metadata_is_bounded_and_path_safe():
    record = normalize_httpx_screenshot({
        "url": "https://app.example.test/login", "screenshot_path": "screenshots/app.png",
        "status_code": "200", "title": "  Login   page ", "technologies": ["nginx", "nginx"],
        "run_id": "run-1", "profile_role": "authenticated",
    })
    assert record == {
        "url": "https://app.example.test/login", "artifact_path": "screenshots/app.png",
        "status_code": 200, "title": "Login page", "technologies": ["nginx", "nginx"],
        "captured_at": "", "visual_hash": "", "source_run_id": "run-1", "profile_role": "authenticated",
    }
    assert normalize_httpx_screenshot({"url": "https://app.example.test", "screenshot_path": "../secret.png"}) is None
    assert normalize_httpx_screenshot({"url": "https://user:pass@app.example.test", "screenshot_path": "ok.png"}) is None


def test_httpx_json_output_carries_safe_screenshot_metadata_only():
    classifier = OutputSignalClassifier("httpx -json -screenshot -srd screenshots")
    metadata = classifier.classify_line(
        '{"url":"https://app.example.test","screenshot_path":"screenshots/app.png","status_code":200}'
    )
    assert metadata["screenshots"] == [{
        "url": "https://app.example.test", "artifact_path": "screenshots/app.png",
        "status_code": 200, "title": "", "technologies": [], "captured_at": "",
        "visual_hash": "", "source_run_id": "", "profile_role": "",
    }]
    assert "html" not in metadata


def test_version_correlation_requires_exact_identifier_and_version_matches():
    advisories = [{
        "id": "CVE-2026-1234", "purls": ["pkg:pypi/requests"],
        "affected_versions": ["2.31.0"], "affected_range": "==2.31.0",
    }]
    matches = correlate_version_observation({"purl": "pkg:pypi/requests", "version": "2.31.0"}, advisories)
    assert matches == [{
        "vulnerability_id": "CVE-2026-1234", "confidence": "high",
        "match_basis": "exact_purl_version", "observed_identifier": "pkg:pypi/requests",
        "observed_version": "2.31.0", "affected_range": "==2.31.0",
        "validation_method": "version_inference",
    }]
    assert correlate_version_observation({"product": "requests", "version": "2.31.0"}, advisories) == []
    assert correlate_version_observation({"purl": "pkg:pypi/requests", "version": "2.32.0"}, advisories) == []
