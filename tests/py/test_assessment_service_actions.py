# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from services.assessments.service_actions import service_actions, service_evidence_state
from services.assessments.command_plans import command_plan
from services.assessments.nmap_profiles import nmap_profile_args, nmap_profile_keys
from services.assessments.takeover_detection import evaluate_takeover_signal
from services.assessments.web_surface import normalize_httpx_screenshot
from services.assessments.version_correlation import correlate_version_observation, materialize_version_findings
from services.assessments.nuclei_profiles import nuclei_profile, nuclei_profile_args, nuclei_profile_keys
from services.assessments.historical_urls import filter_historical_urls, normalize_historical_url, normalize_historical_urls
from services.assessments.web_gallery import filter_web_surface_rows
from services.intel.epss import normalize_epss_rows
from services.intel.kev import normalize_kev_catalog
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


def test_nuclei_profiles_are_reviewed_explicit_and_safe_by_default():
    assert nuclei_profile_keys() == ("safe", "standard", "intrusive")
    assert nuclei_profile("unknown").key == "safe"
    assert nuclei_profile_args("safe") == ("-severity", "high,critical")
    assert nuclei_profile_args("intrusive") == (
        "-severity", "low,medium,high,critical", "-headless"
    )
    assert "exploit" in nuclei_profile("safe").excluded_categories
    assert nuclei_profile("intrusive").requires_confirmation is True
    assert nuclei_profile("safe").template_source == "app-managed"
    safe = command_plan("nuclei", "domain", "example.com")
    standard = command_plan("nuclei", "domain", "example.com", nuclei_profile="standard")
    assert command_plan("nuclei", "domain", "example.com", nuclei_profile="intrusive") is None
    intrusive = command_plan(
        "nuclei", "domain", "example.com", nuclei_profile="intrusive", allow_intrusive=True,
    )
    assert "-severity high,critical" in safe.command
    assert "-severity medium,high,critical" in standard.command
    assert "-headless" in intrusive.command


def test_historical_urls_are_safe_bounded_and_provenance_only():
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


def test_web_gallery_filters_metadata_without_exposing_artifact_contents():
    rows = filter_web_surface_rows([
        {"url": "https://app.example.test", "status_code": 200, "technologies": ["nginx"], "profile_role": "anonymous", "visual_hash": "abc", "html": "secret"},
        {"url": "https://admin.example.test", "status_code": 401, "technologies": ["nginx"], "profile_role": "authenticated", "visual_hash": "def"},
    ], target="app.example", status_code=200, technology="nginx", profile_role="anonymous")
    assert len(rows) == 1
    assert rows[0]["url"] == "https://app.example.test"
    assert "html" not in rows[0]
    assert filter_web_surface_rows(rows, visual_hash="abc", changed_since=["abc"]) == []


def test_web_gallery_paging_is_bounded_and_skips_malformed_rows():
    rows = filter_web_surface_rows(
        [None, {"url": "https://one.example", "status_code": 200}, {"url": "https://two.example", "status_code": 200}],
        offset="1",
        limit=9999,
    )
    assert [row["url"] for row in rows] == ["https://two.example"]
    assert filter_web_surface_rows([{"url": "https://one.example"}], offset=-5, limit=0) == []


def test_httpx_json_output_carries_safe_screenshot_metadata_only():
    classifier = OutputSignalClassifier(
        "httpx -json -screenshot -srd screenshots",
        source_run_id="run-httpx",
        profile_role="anonymous",
    )
    metadata = classifier.classify_line(
        '{"url":"https://app.example.test","screenshot_path":"screenshots/app.png","status_code":200}'
    )
    assert metadata["screenshots"] == [{
        "url": "https://app.example.test", "artifact_path": "screenshots/app.png",
        "status_code": 200, "title": "", "technologies": [], "captured_at": "",
        "visual_hash": "", "source_run_id": "run-httpx", "profile_role": "anonymous",
    }]
    assert "html" not in metadata


def test_gau_output_carries_historical_url_provenance_only():
    classifier = OutputSignalClassifier("gau example.com", source_run_id="run-gau")
    metadata = classifier.classify_line("https://example.com/archive?a=1")
    assert metadata["historical_urls"] == [{
        "url": "https://example.com/archive?a=1", "source": "gau", "source_run_id": "run-gau",
    }]


def test_gau_command_plan_is_domain_scoped_and_passive():
    plan = command_plan("gau", "domain", "example.com")
    assert plan is not None
    assert plan.command == "gau --subs --threads 2 --timeout 10 example.com"
    assert "not probed automatically" in plan.boundary
    assert plan.time_limit_seconds == 120


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
    records = materialize_version_findings(
        {"purl": "pkg:pypi/requests", "version": "2.31.0", "target": "api.example.test", "observation_id": "obs-1"},
        advisories,
        source_run_id="run-1", observed_at="2026-08-07T00:00:00Z", tool_version="nmap 7.96",
    )
    assert records[0]["validation_method"] == "version_inference"
    assert records[0]["source"] == {
        "run_id": "run-1", "kind": "run", "observation_id": "obs-1",
        "observed_at": "2026-08-07T00:00:00Z", "tool_version": "nmap 7.96",
    }
