# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json

from core.output_nuclei import NUCLEI_JSON_MAX_LINE_BYTES
from services.assessments.service_actions import service_actions, service_evidence_state
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
from services.assessments.nmap_profiles import nmap_profile_args, nmap_profile_keys
from services.assessments.nmap_version_observations import parse_nmap_xml_cpe_observations
from services.assessments.nuclei_takeover_identity import NUCLEI_TAKEOVER_JSON_PARSER_VERSION
from services.assessments.nuclei_takeover_observations import ReviewedNucleiTakeoverTemplate
from services.assessments.takeover_detection import evaluate_takeover_signal
from services.assessments.takeover_confirmation import (
    NUCLEI_TAKEOVER_CONFIRMATION_VERSION,
    confirm_takeover_with_nuclei,
)
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
    class Capture:
        def __init__(self):
            self.events = []

        def add_event(self, event):
            self.events.append(event)

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
    assert to_wire(capture.events[0])["source_detail"]["nuclei_takeover_observations"] == [evidence]
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
    assert "nuclei_takeover_observations" not in untrusted_classifier.classify_line(json.dumps({
        "template-id": "other-template",
        "matched-at": "https://app.example.test",
        "timestamp": "2026-08-07T22:00:00Z",
    }))["source_detail"]
    assert "nuclei_takeover_observations" not in untrusted_classifier.classify_line(
        "{" + (" " * NUCLEI_JSON_MAX_LINE_BYTES)
    )["source_detail"]
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
    assert to_wire(capture.events[0])["source_detail"]["takeover_observations"] == [observation]


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
