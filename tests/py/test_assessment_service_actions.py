# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json

from services.assessments.service_actions import service_actions, service_evidence_state
from services.assessments.command_plans import command_plan
from services.assessments.cyclonedx_package_observations import (
    CYCLONEDX_COMPONENT_PARSER_VERSION,
    CYCLONEDX_MAX_PACKAGE_OBSERVATIONS,
    parse_cyclonedx_package_observations,
)
from services.assessments.httpx_version_observations import (
    HTTPX_JSON_CPE_PARSER_VERSION,
    normalize_httpx_version_observations,
)
from services.assessments.nmap_profiles import nmap_profile_args, nmap_profile_keys
from services.assessments.nmap_version_observations import parse_nmap_xml_cpe_observations
from services.assessments.takeover_detection import evaluate_takeover_signal
from services.assessments.web_surface import normalize_httpx_screenshot
from services.assessments.version_correlation import correlate_version_observation, materialize_version_findings
from services.assessments.nuclei_profiles import nuclei_profile, nuclei_profile_args, nuclei_profile_keys
from services.assessments.historical_urls import (
    filter_historical_urls,
    normalize_domain_scoped_historical_urls,
    normalize_historical_url,
    normalize_historical_urls,
    normalize_scope_domain,
)
from services.assessments.web_gallery import filter_web_surface_rows, web_surface_rows_from_events
from services.runs.finalization import capture_event_with_signals
from services.runs.lifecycle import PreparedRealCommand, start_real_command_process
from services.runs.output_model import to_wire
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
    assert evaluate_takeover_signal(
        {
            "hostname": "app.example.test",
            "cname_chain": ["outside.test"],
            "target_resolved": False,
            "in_scope": False,
        }
    )["reason"] == "out_of_scope_target"


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


def test_web_gallery_paging_is_bounded_and_skips_malformed_rows():
    rows = filter_web_surface_rows(
        [None, {"url": "https://one.example", "status_code": 200}, {"url": "https://two.example", "status_code": 200}],
        offset="1",
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
        '{"url":"https://app.example.test","screenshot_path":"screenshots/app.png","status_code":200}'
    )
    assert metadata["screenshots"] == [{
        "url": "https://app.example.test", "artifact_path": "screenshots/app.png",
        "status_code": 200, "title": "", "technologies": [], "captured_at": "",
        "visual_hash": "", "source_run_id": "run-httpx", "profile_role": "anonymous",
    }]
    assert "html" not in metadata


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
    assert to_wire(capture.events[0])["source_detail"]["version_observations"] == [observation]


def test_real_command_classifier_receives_generated_run_id():
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
        validation=None,
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
        cfg={"output_entity_extra_domain_suffixes": []},
        run_output_capture_fn=lambda run_id: {"run_id": run_id},
        popen_fn=lambda *args, **kwargs: Process(),
        pid_register_fn=lambda *args: None,
        active_run_register_fn=lambda *args, **kwargs: None,
        output_signal_classifier_cls=Classifier,
        workspace_path_filter_cls=lambda *args, **kwargs: object(),
        owner_context_for_scope_fn=lambda *args, **kwargs: object(),
        scanner_prefix=(),
        stdbuf_bin=None,
        shell_bin="/bin/sh",
    )
    assert classifier_call == {
        "command": prepared.command,
        "cmd_type": "real",
        "extra_domain_suffixes": [],
        "source_run_id": started.run_id,
    }


def test_httpx_assessment_plan_requests_structured_versioned_cpe_output():
    plan = command_plan("httpx", "url", "https://app.example.test")
    assert plan is not None
    assert "-tech-detect -json -cpe -silent" in plan.command
    assert "versioned CPE metadata" in plan.boundary


def test_gau_output_carries_historical_url_provenance_only():
    classifier = OutputSignalClassifier("gau example.com", source_run_id="run-gau")
    metadata = classifier.classify_line("https://example.com/archive?a=1")
    assert metadata["historical_urls"] == [{
        "url": "https://example.com/archive?a=1", "source": "gau", "source_run_id": "run-gau",
    }]
    url_entity = next(entity for entity in metadata["entities"] if entity.get("type") == "url")
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
    assert wire["source_detail"]["historical_urls"][0]["url"] == "https://example.com/a"


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
        }],
    }
    parsed_components = parse_cyclonedx_package_observations(
        json.dumps(component_payload).encode(),
        source_batch_id="batch-cyclonedx-1",
    )
    assert parsed_components["parser_version"] == CYCLONEDX_COMPONENT_PARSER_VERSION
    assert parsed_components["tool_version"] == "CycloneDX 1.5"
    assert parsed_components["observations"] == [{
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
    }]
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
