# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared CVE risk feeds, ranking, snapshots, and escalation contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
import sqlite3

import pytest
from pydantic import ValidationError

from config import CveRiskConfig
from core.database_backend import DatabaseBackend
from core.migrations import MIGRATIONS
from core.migrations.runner import run_migrations
from services.cve_risk import bootstrap, maintenance, osv_external, osv_external_http, refresh
from services.cve_risk import escalation
from services.cve_risk.escalation import (
    acknowledge_escalation,
    list_project_risk_escalations,
    process_risk_work,
)
from services.cve_risk.links import remediation_identity
from services.cve_risk.nvd_advisory import (
    ParsedNvdDataset,
    accept_local_nvd_dataset,
    get_advisory_source_status,
    load_configured_local_nvd,
    parse_nvd_dataset,
    persist_external_nvd_lookup,
)
from services.cve_risk.osv_acquisition import (
    get_osv_source_status,
    load_configured_local_osv,
)
from services.cve_risk.osv_parser import OsvDatasetError, parse_osv_dataset
from services.cve_risk.osv_external_store import accept_external_osv_query
from services.cve_risk.osv_store import accept_local_osv_dataset
from services.cve_risk.parsers import FeedValidationError, ParsedFeed, parse_epss, parse_kev
from services.cve_risk.ranking import (
    attach_risk_to_findings,
    build_remediation_worklist,
    cve_risk_order_sql,
)
from services.cve_risk.snapshot import build_cve_risk_snapshot
from services.cve_risk.store import accept_feed, get_feed_status
from services.assessments.nvd_cpe_correlation import correlate_stored_nvd_cpe_page
from services.assessments.osv_package_correlation import correlate_stored_osv_package_page
from services.assessments.cyclonedx_stored_nvd import correlate_cyclonedx_json_with_stored_nvd
from services.assessments.cyclonedx_stored_osv import correlate_cyclonedx_json_with_stored_osv
from services.assessments.httpx_stored_nvd import correlate_httpx_json_with_stored_nvd
from services.assessments.httpx_inference_materialization import (
    HTTPX_INFERENCE_MAX_CANDIDATES,
    materialize_httpx_json_version_inferences,
)
from services.assessments.nmap_inference_materialization import (
    NMAP_INFERENCE_MAX_CANDIDATES,
    materialize_nmap_xml_version_inferences,
)
from services.assessments.nmap_stored_nvd import correlate_nmap_xml_with_stored_nvd
from services.assessments.stored_nvd_inference import materialize_stored_nvd_cpe_candidate_page
from services.assessments.version_inference_persistence import persist_version_inference_candidate
from services.intel.nvd_applicability import normalize_nvd_cpe_matches
from services.reports.rendering import (
    render_report_html_from_context,
    render_report_markdown_from_context,
)


@pytest.fixture
def risk_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn, MIGRATIONS, backend=DatabaseBackend.SQLITE)
    try:
        yield conn
    finally:
        conn.close()


def _epss_feed(version: str, score_date: str, *rows: tuple[str, float, float]) -> ParsedFeed:
    return ParsedFeed(
        source="epss",
        version=f"{version}:{score_date}",
        model_version=version,
        published_at=score_date,
        records=tuple({
            "cve_id": cve_id,
            "epss_probability": probability,
            "epss_percentile": percentile,
        } for cve_id, probability, percentile in rows),
    )


def _nvd_dataset(version: str, *, status: str, score: float) -> ParsedNvdDataset:
    cve: dict[str, object] = {
        "id": "CVE-2026-12345",
        "vulnStatus": status,
        "published": "2026-08-01T00:00:00Z",
        "lastModified": version,
        "metrics": {"cvssMetricV31": [{
            "baseSeverity": "HIGH",
            "cvssData": {
                "version": "3.1",
                "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                "baseScore": score,
            },
        }]},
    }
    if status == "Disputed":
        cve["vulnStatus"] = "Analyzed"
        cve["cveTags"] = [{"tags": ["disputed"]}]
    return parse_nvd_dataset(json.dumps({
        "timestamp": version,
        "vulnerabilities": [{"cve": cve}],
    }).encode())


def _osv_record(**overrides):
    record = {
        "schema_version": "1.6.0",
        "id": "GHSA-abcd-1234-efgh",
        "modified": "2026-08-04T12:00:00Z",
        "published": "2026-08-01T00:00:00Z",
        "aliases": ["CVE-2026-12345"],
        "summary": "Example package vulnerability",
        "affected": [{
            "package": {
                "ecosystem": "PyPI",
                "name": "requests",
                "purl": "pkg:pypi/requests",
            },
            "versions": ["2.30.0"],
            "ranges": [{
                "type": "SEMVER",
                "events": [{"introduced": "2.0.0"}, {"fixed": "2.32.0"}],
            }],
        }],
    }
    record.update(overrides)
    return record


def _insert_project_finding(
    conn: sqlite3.Connection,
    *,
    finding_id: str,
    project_id: str,
    session_id: str = "session-one",
    team_id: str = "",
    cve_id: str = "CVE-2026-12345",
    target_id: str = "target-one",
) -> None:
    now = "2026-08-04T00:00:00+00:00"
    conn.execute(
        "INSERT INTO projects (id, session_id, team_id, name, slug, created, updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project_id, session_id, team_id, project_id, project_id, now, now),
    )
    conn.execute(
        "INSERT INTO findings (id, session_id, team_id, target_id, title, created) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (finding_id, session_id, team_id, target_id, f"Affected by {cve_id}", now),
    )
    conn.execute(
        "INSERT INTO finding_cve_links (finding_id, cve_id, created_at) VALUES (?, ?, ?)",
        (finding_id, cve_id, now),
    )
    conn.execute(
        "INSERT INTO project_links (id, project_id, entity_type, entity_id, created) "
        "VALUES (?, ?, 'finding', ?, ?)",
        (f"link-{finding_id}", project_id, finding_id, now),
    )


def test_nmap_version_inference_materialization_counts_created_repeated_and_rejected_candidates():
    candidates = [{"candidate": index} for index in range(3)]
    persisted = []

    def correlate(*_args, **_kwargs):
        return {
            "observations": [{"candidates": candidates[:2]}, {"candidates": candidates[2:]}],
            "truncated": False,
        }

    def persist(_conn, session_id, candidate, *, team_id=""):
        persisted.append((session_id, team_id, candidate))
        if candidate == candidates[2]:
            return None
        return {
            "created": candidate == candidates[0],
            "source_created": candidate == candidates[0],
        }

    summary = materialize_nmap_xml_version_inferences(
        object(),
        "session-version",
        b"<nmaprun/>",
        source_run_id="run-version",
        team_id="team-version",
        correlate_fn=correlate,
        persist_fn=persist,
    )

    assert persisted == [
        ("session-version", "team-version", candidate) for candidate in candidates
    ]
    assert summary == {
        "observation_count": 2,
        "candidate_count": 3,
        "attempted_count": 3,
        "materialized_count": 2,
        "finding_created_count": 1,
        "source_created_count": 1,
        "rejected_count": 1,
        "skipped_count": 0,
        "truncated": False,
    }


def test_nmap_version_inference_materialization_rejects_over_cap_instead_of_evicting():
    candidates = [{"candidate": index} for index in range(NMAP_INFERENCE_MAX_CANDIDATES + 1)]
    persisted = []

    summary = materialize_nmap_xml_version_inferences(
        object(),
        "session-version",
        b"<nmaprun/>",
        source_run_id="run-version",
        correlate_fn=lambda *_args, **_kwargs: {
            "observations": [{"candidates": candidates}],
            "truncated": False,
        },
        persist_fn=lambda _conn, _session_id, candidate, **_kwargs: (
            persisted.append(candidate) or {"created": True, "source_created": True}
        ),
    )

    assert persisted == candidates[:NMAP_INFERENCE_MAX_CANDIDATES]
    assert summary["candidate_count"] == NMAP_INFERENCE_MAX_CANDIDATES + 1
    assert summary["attempted_count"] == NMAP_INFERENCE_MAX_CANDIDATES
    assert summary["materialized_count"] == NMAP_INFERENCE_MAX_CANDIDATES
    assert summary["skipped_count"] == 1
    assert summary["truncated"] is True


def test_httpx_version_inference_materialization_counts_and_caps_candidates():
    candidates = [{"candidate": index} for index in range(HTTPX_INFERENCE_MAX_CANDIDATES + 1)]
    persisted = []

    summary = materialize_httpx_json_version_inferences(
        object(),
        "session-version",
        {"url": "https://example.test"},
        source_run_id="run-httpx-version",
        tool_version="httpx 1.10.0",
        team_id="team-version",
        correlate_fn=lambda *_args, **_kwargs: {
            "observations": [{"candidates": candidates}],
            "truncated": False,
        },
        persist_fn=lambda _conn, session_id, candidate, *, team_id="": (
            persisted.append((session_id, team_id, candidate))
            or {"created": True, "source_created": True}
        ),
    )

    assert persisted == [
        ("session-version", "team-version", candidate)
        for candidate in candidates[:HTTPX_INFERENCE_MAX_CANDIDATES]
    ]
    assert summary == {
        "observation_count": 1,
        "candidate_count": HTTPX_INFERENCE_MAX_CANDIDATES + 1,
        "attempted_count": HTTPX_INFERENCE_MAX_CANDIDATES,
        "materialized_count": HTTPX_INFERENCE_MAX_CANDIDATES,
        "finding_created_count": HTTPX_INFERENCE_MAX_CANDIDATES,
        "source_created_count": HTTPX_INFERENCE_MAX_CANDIDATES,
        "rejected_count": 0,
        "skipped_count": 1,
        "truncated": True,
    }


def test_public_feed_parsers_require_metadata_ranges_and_unique_cves():
    epss = parse_epss(
        b"#model_version:v-test,score_date:2026-08-04\n"
        b"cve,epss,percentile\nCVE-2026-12345,0.125,0.95\n"
    )
    assert epss.version == "v-test:2026-08-04"
    assert epss.records[0]["epss_probability"] == 0.125

    with pytest.raises(FeedValidationError, match="metadata"):
        parse_epss(b"cve,epss,percentile\nCVE-2026-12345,0.1,0.9\n")
    with pytest.raises(FeedValidationError, match="between 0 and 1"):
        parse_epss(
            b"#model_version:v-test,score_date:2026-08-04\n"
            b"cve,epss,percentile\nCVE-2026-12345,1.1,0.9\n"
        )
    with pytest.raises(FeedValidationError, match="duplicate"):
        parse_epss(
            b"#model_version:v-test,score_date:2026-08-04\n"
            b"cve,epss,percentile\nCVE-2026-12345,0.1,0.9\nCVE-2026-12345,0.2,0.8\n"
        )


def test_cve_risk_config_bounds_network_and_hysteresis_contracts():
    parsed = CveRiskConfig(allowed_hosts=["WWW.CISA.GOV", "www.cisa.gov"])
    assert parsed.allowed_hosts == ["www.cisa.gov"]

    with pytest.raises(ValidationError, match="refresh_interval_seconds"):
        CveRiskConfig(refresh_interval_seconds=299)
    with pytest.raises(ValidationError, match="must be lower"):
        CveRiskConfig(
            epss_activation_probability=0.10,
            epss_reset_probability=0.10,
        )
    with pytest.raises(ValidationError, match="must be hostnames"):
        CveRiskConfig(allowed_hosts=["https://www.cisa.gov/feed"])
    with pytest.raises(ValidationError, match="advisory_mode"):
        CveRiskConfig(advisory_mode="automatic")
    with pytest.raises(ValidationError, match="nvd_local_path"):
        CveRiskConfig(advisory_mode="local")
    assert "api.osv.dev" in CveRiskConfig(osv_advisory_mode="external").allowed_hosts
    with pytest.raises(ValidationError, match="osv_advisory_mode"):
        CveRiskConfig(osv_advisory_mode="automatic")
    with pytest.raises(ValidationError, match="osv_local_path"):
        CveRiskConfig(osv_advisory_mode="local")
    with pytest.raises(ValidationError, match="advisory_cvss_downgrade_delta"):
        CveRiskConfig(advisory_cvss_downgrade_delta=0)


def test_osv_parser_normalizes_exact_package_versions_and_semver_ranges():
    first = _osv_record()
    first["affected"].append({
        "package": {
            "ecosystem": "PyPI",
            "name": "requests",
            "purl": "pkg:pypi/requests",
        },
        "versions": ["2.31.0", "2.30.0"],
        "ranges": [{
            "type": "SEMVER",
            "events": [{"introduced": "2.0.0"}, {"fixed": "2.32.0"}],
        }],
    })
    withdrawn = _osv_record(
        id="GHSA-withdrawn-1234",
        aliases=["CVE-2026-99999"],
        modified="2026-08-05T12:00:00Z",
        withdrawn="2026-08-05T13:00:00Z",
        affected=[],
    )

    parsed = parse_osv_dataset(json.dumps([first, withdrawn]).encode())

    assert parsed.version == "osv:2026-08-05T12:00:00+00:00"
    assert parsed.published_at == "2026-08-05T12:00:00+00:00"
    assert parsed.withdrawn_record_count == 1
    assert parsed.skipped_affected_count == 0
    assert parsed.skipped_range_count == 0
    assert len(parsed.records) == 1
    record = parsed.records[0]
    assert record["advisory_id"].startswith("osv_")
    assert record["source_advisory_id"] == "GHSA-abcd-1234-efgh"
    assert record["normalized_vulnerability_id"] == "CVE-2026-12345"
    assert record["package_purl"] == "pkg:pypi/requests"
    assert record["affected_versions"] == ["2.30.0", "2.31.0"]
    assert record["ranges"] == [{
        "range_type": "SEMVER",
        "events": [{"introduced": "2.0.0"}, {"fixed": "2.32.0"}],
    }]


def test_osv_parser_keeps_arbitrary_exact_versions_but_skips_unsupported_ranges():
    valid = _osv_record(affected=[{
        "package": {
            "ecosystem": "Debian:12",
            "name": "openssl",
            "purl": "pkg:deb/debian/openssl",
        },
        "versions": ["1:3.0.17-1~deb12u2"],
        "ranges": [{
            "type": "ECOSYSTEM",
            "events": [{"introduced": "0"}, {"fixed": "1:3.0.18-1"}],
        }],
    }, {
        "package": {"ecosystem": "PyPI", "name": "missing-purl"},
        "versions": ["1.0.0"],
    }])

    parsed = parse_osv_dataset(json.dumps([valid]).encode())

    assert parsed.records[0]["affected_versions"] == ["1:3.0.17-1~deb12u2"]
    assert parsed.records[0]["ranges"] == []
    assert parsed.skipped_range_count == 1
    assert parsed.skipped_affected_count == 1


@pytest.mark.parametrize(("payload", "message"), (
    ({"id": "GHSA-index-only", "modified": "2026-08-04T00:00:00Z"}, "root"),
    ([_osv_record(schema_version="2.0.0")], "schema version"),
    ([_osv_record(modified="2026-08-04T00:00:00")], "timezone"),
    ([_osv_record(id="bad id")], "id is invalid"),
    ([_osv_record(affected={})], "affected field"),
))
def test_osv_parser_rejects_malformed_dataset_contracts(payload, message):
    with pytest.raises(OsvDatasetError, match=message):
        parse_osv_dataset(json.dumps(payload).encode())


def test_osv_parser_rejects_duplicates_invalid_semver_and_bounded_inputs():
    duplicate = _osv_record()
    with pytest.raises(OsvDatasetError, match="duplicate advisory"):
        parse_osv_dataset(json.dumps([duplicate, duplicate]).encode())

    invalid_range = _osv_record()
    invalid_range["affected"][0]["ranges"][0]["events"][1]["fixed"] = "not-semver"
    with pytest.raises(OsvDatasetError, match="SEMVER boundary"):
        parse_osv_dataset(json.dumps([invalid_range]).encode())

    reversed_range = _osv_record()
    reversed_range["affected"][0]["ranges"][0]["events"] = [
        {"introduced": "2.0.0"},
        {"fixed": "1.0.0"},
    ]
    with pytest.raises(OsvDatasetError, match="SEMVER range"):
        parse_osv_dataset(json.dumps([reversed_range]).encode())

    with pytest.raises(OsvDatasetError, match="record count"):
        parse_osv_dataset(json.dumps([_osv_record()]).encode(), max_records=0)
    with pytest.raises(OsvDatasetError, match="size limit"):
        parse_osv_dataset(json.dumps([_osv_record()]).encode(), max_uncompressed_bytes=32)


def test_osv_parser_requires_at_least_one_exact_supported_package_identity():
    unsupported = _osv_record(affected=[{
        "package": {"ecosystem": "PyPI", "name": "requests"},
        "versions": ["2.31.0"],
    }])

    with pytest.raises(OsvDatasetError, match="no supported package"):
        parse_osv_dataset(json.dumps([unsupported]).encode())


def test_local_osv_acceptance_replaces_complete_package_applicability(risk_db):
    first = parse_osv_dataset(json.dumps([_osv_record()]).encode())

    result = accept_local_osv_dataset(
        risk_db,
        first,
        checksum="a" * 64,
        now=datetime.fromisoformat("2026-08-07T12:00:00+00:00"),
    )

    assert result == {
        "source": "osv",
        "outcome": "loaded",
        "record_count": 1,
        "exact_version_count": 1,
        "range_count": 1,
    }
    advisory = dict(risk_db.execute(
        "SELECT * FROM package_advisories WHERE source = 'osv'"
    ).fetchone())
    assert advisory["source_advisory_id"] == "GHSA-abcd-1234-efgh"
    assert advisory["normalized_vulnerability_id"] == "CVE-2026-12345"
    assert advisory["package_purl"] == "pkg:pypi/requests"
    assert advisory["schema_version"] == "1.6.0"
    assert advisory["source_version"] == first.version
    assert json.loads(advisory["affected_versions_json"]) == ["2.30.0"]
    stored_range = dict(risk_db.execute(
        "SELECT range_index, range_type, events_json FROM package_advisory_ranges"
    ).fetchone())
    assert stored_range == {
        "range_index": 0,
        "range_type": "SEMVER",
        "events_json": '[{"introduced":"2.0.0"},{"fixed":"2.32.0"}]',
    }
    source = dict(risk_db.execute(
        "SELECT * FROM cve_advisory_sources WHERE source = 'osv'"
    ).fetchone())
    assert source["acquisition_mode"] == "local"
    assert source["origin"] == "local"
    assert source["status"] == "current"
    assert source["checksum_sha256"] == "a" * 64
    assert source["record_count"] == 1
    assert source["attribution"]
    assert source["terms_url"].startswith("https://")

    replacement = parse_osv_dataset(json.dumps([_osv_record(
        id="GHSA-replacement-1234",
        modified="2026-08-08T12:00:00Z",
        aliases=["CVE-2026-54321"],
        affected=[{
            "package": {
                "ecosystem": "PyPI",
                "name": "flask",
                "purl": "pkg:pypi/flask",
            },
            "versions": ["3.1.1"],
        }],
    )]).encode())
    accept_local_osv_dataset(
        risk_db,
        replacement,
        checksum="b" * 64,
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )

    rows = risk_db.execute(
        "SELECT source_advisory_id, normalized_vulnerability_id, package_purl "
        "FROM package_advisories WHERE source = 'osv'"
    ).fetchall()
    assert [tuple(row) for row in rows] == [(
        "GHSA-replacement-1234",
        "CVE-2026-54321",
        "pkg:pypi/flask",
    )]
    assert risk_db.execute("SELECT COUNT(*) FROM package_advisory_ranges").fetchone()[0] == 0


def test_local_osv_acceptance_rolls_back_to_last_good_dataset(risk_db):
    current = parse_osv_dataset(json.dumps([_osv_record()]).encode())
    accept_local_osv_dataset(
        risk_db,
        current,
        checksum="c" * 64,
        now=datetime.fromisoformat("2026-08-07T12:00:00+00:00"),
    )
    risk_db.execute(
        "CREATE TRIGGER reject_osv_replacement BEFORE INSERT ON package_advisories "
        "WHEN NEW.source_advisory_id = 'GHSA-rejected-1234' "
        "BEGIN SELECT RAISE(ABORT, 'reject replacement'); END"
    )
    replacement = parse_osv_dataset(json.dumps([_osv_record(
        id="GHSA-rejected-1234",
        modified="2026-08-08T12:00:00Z",
    )]).encode())

    with pytest.raises(sqlite3.IntegrityError, match="reject replacement"):
        accept_local_osv_dataset(
            risk_db,
            replacement,
            checksum="d" * 64,
            now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
        )

    advisory = risk_db.execute(
        "SELECT source_advisory_id FROM package_advisories WHERE source = 'osv'"
    ).fetchone()
    source = risk_db.execute(
        "SELECT source_version, checksum_sha256 FROM cve_advisory_sources WHERE source = 'osv'"
    ).fetchone()
    assert advisory["source_advisory_id"] == "GHSA-abcd-1234-efgh"
    assert tuple(source) == (current.version, "c" * 64)
    assert risk_db.execute("SELECT COUNT(*) FROM package_advisory_ranges").fetchone()[0] == 1


def test_stored_osv_package_correlation_is_bounded_read_only_and_fail_closed(risk_db):
    payload = json.dumps([
        _osv_record(),
        _osv_record(
            id="GHSA-wxyz-5678-abcd",
            aliases=["CVE-2026-54321"],
            modified="2026-08-05T12:00:00Z",
        ),
    ]).encode()
    parsed = parse_osv_dataset(payload)
    accept_local_osv_dataset(
        risk_db,
        parsed,
        checksum=hashlib.sha256(payload).hexdigest(),
        now=datetime.fromisoformat("2026-08-07T12:00:00+00:00"),
    )
    changes_before_read = risk_db.total_changes

    first = correlate_stored_osv_package_page(
        risk_db,
        {"purl": "pkg:pypi/requests@2.31.0"},
        limit=1,
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )
    assert first["candidate_advisory_count"] == 1
    assert first["rejected_candidate_count"] == 0
    assert first["has_more"] is True
    assert first["next_offset"] == 1
    assert first["matches"] == [{
        "vulnerability_id": "CVE-2026-12345",
        "confidence": "high",
        "match_basis": "exact_purl_semver_range",
        "observed_identifier": "pkg:pypi/requests",
        "observed_version": "2.31.0",
        "affected_range": "SEMVER: introduced 2.0.0; fixed 2.32.0",
        "range_type": "SEMVER",
        "advisory_source": "osv",
        "advisory_source_version": parsed.version,
        "validation_method": "version_inference",
        "advisory_id": first["matches"][0]["advisory_id"],
        "advisory_source_id": "GHSA-abcd-1234-efgh",
        "advisory_schema_version": "1.6.0",
        "advisory_origin": "local",
        "advisory_modified_at": "2026-08-04T12:00:00+00:00",
        "advisory_expires_at": "2026-08-14T12:00:00+00:00",
        "advisory_source_state": "current",
    }]
    assert first["matches"][0]["advisory_id"].startswith("osv_")
    cyclonedx_result = correlate_cyclonedx_json_with_stored_osv(
        risk_db,
        json.dumps({
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "components": [{
                "type": "library",
                "bom-ref": "pkg:pypi/requests@2.31.0",
                "name": "requests",
                "version": "2.31.0",
                "purl": "pkg:pypi/requests@2.31.0",
            }],
        }).encode(),
        source_batch_id="batch-osv-cyclonedx-1",
        observed_at="2026-08-08T11:00:00Z",
        advisory_limit=1,
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )
    assert cyclonedx_result["observation_count"] == 1
    assert cyclonedx_result["candidate_count"] == 1
    cyclonedx_observation = cyclonedx_result["observations"][0]
    assert {
        key: cyclonedx_observation[key]
        for key in ("purl", "version", "component_name", "component_type", "bom_ref")
    } == {
        "purl": "pkg:pypi/requests",
        "version": "2.31.0",
        "component_name": "requests",
        "component_type": "library",
        "bom_ref": "pkg:pypi/requests@2.31.0",
    }
    cyclonedx_candidate = cyclonedx_observation["candidates"][0]
    assert cyclonedx_candidate["target"] == "pkg:pypi/requests"
    assert cyclonedx_candidate["match_basis"] == "exact_purl_semver_range"
    assert cyclonedx_candidate["advisory_source_id"] == "GHSA-abcd-1234-efgh"
    assert cyclonedx_candidate["advisory_schema_version"] == "1.6.0"
    assert cyclonedx_candidate["source"] == {
        "kind": "import",
        "observation_id": cyclonedx_result["observations"][0]["observation_id"],
        "observed_at": "2026-08-08T11:00:00Z",
        "tool_version": "CycloneDX 1.5",
        "batch_id": "batch-osv-cyclonedx-1",
        "parser_version": "cyclonedx-component-v1",
    }
    assert risk_db.total_changes == changes_before_read
    second = correlate_stored_osv_package_page(
        risk_db,
        {"purl": "pkg:pypi/requests", "version": "2.31.0"},
        limit=1,
        offset=1,
        now=datetime.fromisoformat("2026-08-15T12:00:00+00:00"),
    )
    assert second["matches"][0]["vulnerability_id"] == "CVE-2026-54321"
    assert second["matches"][0]["advisory_source_state"] == "stale"
    assert second["has_more"] is False
    assert risk_db.total_changes == changes_before_read

    assert correlate_stored_osv_package_page(risk_db, {
        "purl": "pkg:pypi/requests@2.31.0", "version": "2.32.0",
    })["matches"] == []
    rejected_id = risk_db.execute(
        "SELECT advisory_id FROM package_advisories WHERE normalized_vulnerability_id = ?",
        ("CVE-2026-54321",),
    ).fetchone()[0]
    risk_db.execute(
        "UPDATE package_advisories SET affected_versions_json = 'not-json' WHERE advisory_id = ?",
        (rejected_id,),
    )
    rejected = correlate_stored_osv_package_page(
        risk_db, {"purl": "pkg:pypi/requests@2.31.0"}, limit=50,
    )
    assert [match["vulnerability_id"] for match in rejected["matches"]] == ["CVE-2026-12345"]
    assert rejected["rejected_candidate_count"] == 1


def test_stored_osv_package_correlation_supports_exact_versions(risk_db):
    record = _osv_record()
    record["affected"][0]["versions"] = ["2.30.0"]
    record["affected"][0]["ranges"] = []
    payload = json.dumps([record]).encode()
    parsed = parse_osv_dataset(payload)
    accept_local_osv_dataset(
        risk_db,
        parsed,
        checksum=hashlib.sha256(payload).hexdigest(),
        now=datetime.fromisoformat("2026-08-07T12:00:00+00:00"),
    )

    match = correlate_stored_osv_package_page(
        risk_db, {"purl": "pkg:pypi/requests", "version": "2.30.0"},
    )["matches"][0]
    assert match["match_basis"] == "exact_purl_version"
    assert match["affected_range"] == "==2.30.0"


def test_configured_local_osv_load_reports_status_and_preserves_last_good(
    risk_db,
    tmp_path,
    caplog,
):
    payload = json.dumps([_osv_record()]).encode()
    path = tmp_path / "osv.json"
    path.write_bytes(payload)
    cfg = {"cve_risk": {
        "osv_advisory_mode": "local",
        "osv_local_path": str(path),
    }}

    loaded = load_configured_local_osv(risk_db, cfg=cfg)
    status = get_osv_source_status(risk_db, cfg=cfg)

    assert loaded == {
        "source": "osv",
        "outcome": "loaded",
        "record_count": 1,
        "exact_version_count": 1,
        "range_count": 1,
    }
    assert status["acquisition_mode"] == "local"
    assert status["origin"] == "local"
    assert status["status"] == "current"
    assert status["record_count"] == 1
    assert status["checksum_sha256"] == hashlib.sha256(payload).hexdigest()

    path.write_text("not json", encoding="utf-8")
    failed = load_configured_local_osv(risk_db, cfg=cfg)
    failed_status = get_osv_source_status(risk_db, cfg=cfg)

    assert failed == {"source": "osv", "outcome": "failed", "error": "OsvDatasetError"}
    assert failed_status["status"] == "failed"
    assert failed_status["source_version"] == status["source_version"]
    assert failed_status["checksum_sha256"] == status["checksum_sha256"]
    assert risk_db.execute(
        "SELECT COUNT(*) FROM package_advisories WHERE source = 'osv'"
    ).fetchone()[0] == 1
    failure_log = next(
        record for record in caplog.records
        if record.getMessage() == "OSV_ADVISORY_LOCAL_LOAD_FAILED"
    )
    assert failure_log.source == "osv"
    assert failure_log.error_type == "OsvDatasetError"
    assert str(path) not in caplog.text

    path.write_bytes(payload)
    assert load_configured_local_osv(risk_db, cfg=cfg) == {
        "source": "osv",
        "outcome": "unchanged",
    }
    assert get_osv_source_status(risk_db, cfg=cfg)["status"] == "current"


def test_cve_risk_maintenance_runs_independent_local_advisory_loaders(monkeypatch):
    executed = []
    monkeypatch.setattr(
        maintenance,
        "load_configured_local_nvd",
        lambda conn, *, cfg: executed.append("nvd"),
    )
    monkeypatch.setattr(
        maintenance,
        "load_configured_local_osv",
        lambda conn, *, cfg: executed.append("osv"),
    )
    monkeypatch.setattr(
        maintenance,
        "sync_finding_cve_links",
        lambda conn: executed.append("links"),
    )
    steps = []

    def run_step(name, callback):
        steps.append(name)
        callback()

    maintenance.run_cve_risk_maintenance(
        object(),
        run_step,
        {"cve_risk": {
            "bootstrap_enabled": False,
            "advisory_mode": "local",
            "nvd_local_path": "/configured/nvd.json",
            "osv_advisory_mode": "local",
            "osv_local_path": "/configured/osv.json",
        }},
    )

    assert steps == [
        "cve_advisory_local_nvd",
        "cve_advisory_local_osv",
        "finding_cve_link_backfill",
    ]
    assert executed == ["nvd", "osv", "links"]


def test_external_osv_query_uses_hash_cache_and_replaces_one_package(
    risk_db,
    monkeypatch,
    caplog,
):
    payload = json.dumps({"vulns": [_osv_record()]}).encode()
    monkeypatch.setattr(osv_external, "download_osv_query", lambda *_args: payload)
    cfg = {"cve_risk": {
        "osv_advisory_mode": "external",
        "max_attempts": 1,
    }}
    now = datetime.fromisoformat("2026-08-07T13:00:00+00:00")

    stored = osv_external.query_external_osv(
        risk_db,
        "pkg:pypi/requests",
        "2.30.0",
        cfg=cfg,
        now=now,
    )

    assert stored == {
        "source": "osv",
        "outcome": "stored",
        "record_count": 1,
        "exact_version_count": 1,
        "range_count": 1,
    }
    advisory = dict(risk_db.execute(
        "SELECT package_purl, origin, affected_versions_json "
        "FROM package_advisories WHERE source = 'osv'"
    ).fetchone())
    assert advisory == {
        "package_purl": "pkg:pypi/requests",
        "origin": "external",
        "affected_versions_json": '["2.30.0"]',
    }
    changes_before_read = risk_db.total_changes
    correlation = correlate_stored_osv_package_page(
        risk_db,
        {"purl": "pkg:pypi/requests@2.30.0"},
        now=datetime.fromisoformat("2026-08-07T13:01:00+00:00"),
    )
    assert correlation["matches"][0]["match_basis"] == "exact_purl_semver_range"
    assert correlation["matches"][0]["advisory_origin"] == "external"
    assert risk_db.total_changes == changes_before_read
    cache = dict(risk_db.execute(
        "SELECT lookup_kind, lookup_key_hash, result_state, record_count "
        "FROM cve_advisory_lookup_cache WHERE source = 'osv'"
    ).fetchone())
    assert cache["lookup_kind"] == "purl_version"
    assert len(cache["lookup_key_hash"]) == 64
    assert "requests" not in cache["lookup_key_hash"]
    assert cache["result_state"] == "positive"
    assert cache["record_count"] == 1

    monkeypatch.setattr(
        osv_external,
        "download_osv_query",
        lambda *_args: pytest.fail("fresh positive cache attempted a provider query"),
    )
    assert osv_external.query_external_osv(
        risk_db,
        "pkg:pypi/requests",
        "2.30.0",
        cfg=cfg,
        now=datetime.fromisoformat("2026-08-07T13:01:00+00:00"),
    ) == {"source": "osv", "outcome": "positive_cached", "record_count": 1}

    monkeypatch.setattr(osv_external, "download_osv_query", lambda *_args: b"{}")
    assert osv_external.query_external_osv(
        risk_db,
        "pkg:pypi/requests",
        "2.30.0",
        cfg=cfg,
        force=True,
        now=datetime.fromisoformat("2026-08-07T14:00:00+00:00"),
    ) == {
        "source": "osv",
        "outcome": "negative_cached",
        "record_count": 0,
        "exact_version_count": 0,
        "range_count": 0,
    }
    assert risk_db.execute(
        "SELECT COUNT(*) FROM package_advisories WHERE source = 'osv'"
    ).fetchone()[0] == 0
    assert risk_db.execute(
        "SELECT result_state FROM cve_advisory_lookup_cache WHERE source = 'osv'"
    ).fetchone()[0] == "negative"
    assert "pkg:pypi/requests" not in caplog.text
    assert "2.30.0" not in caplog.text


def test_external_osv_failure_preserves_last_good_and_hides_identifiers(
    risk_db,
    monkeypatch,
    caplog,
):
    cfg = {"cve_risk": {
        "osv_advisory_mode": "external",
        "max_attempts": 1,
    }}
    monkeypatch.setattr(
        osv_external,
        "download_osv_query",
        lambda *_args: json.dumps({"vulns": [_osv_record()]}).encode(),
    )
    assert osv_external.query_external_osv(
        risk_db,
        "pkg:pypi/requests",
        "2.30.0",
        cfg=cfg,
        now=datetime.fromisoformat("2026-08-07T13:00:00+00:00"),
    )["outcome"] == "stored"

    def fail_download(*_args):
        raise osv_external.URLError("offline")

    monkeypatch.setattr(osv_external, "download_osv_query", fail_download)
    failed = osv_external.query_external_osv(
        risk_db,
        "pkg:pypi/requests",
        "2.30.0",
        cfg=cfg,
        force=True,
        now=datetime.fromisoformat("2026-08-08T13:00:00+00:00"),
    )

    assert failed == {"source": "osv", "outcome": "failed", "error": "URLError"}
    assert risk_db.execute(
        "SELECT COUNT(*) FROM package_advisories "
        "WHERE source = 'osv' AND origin = 'external'"
    ).fetchone()[0] == 1
    source = dict(risk_db.execute(
        "SELECT status, source_version, record_count, last_error "
        "FROM cve_advisory_sources WHERE source = 'osv'"
    ).fetchone())
    assert source["status"] == "failed"
    assert source["source_version"].startswith("osv:")
    assert source["record_count"] == 1
    assert source["last_error"] == "URLError"
    assert "pkg:pypi/requests" not in caplog.text
    assert "2.30.0" not in caplog.text


def test_external_osv_query_replacement_is_scoped_to_one_hash(risk_db):
    parsed = parse_osv_dataset(json.dumps([_osv_record()]).encode())
    now = datetime.fromisoformat("2026-08-07T13:00:00+00:00")
    for lookup_hash in ("a" * 64, "b" * 64):
        accept_external_osv_query(
            risk_db,
            package_purl="pkg:pypi/requests",
            lookup_key_hash=lookup_hash,
            parsed=parsed,
            now=now,
            source_url="https://api.osv.dev/v1/query",
        )

    rows = risk_db.execute(
        "SELECT lookup_key_hash, advisory_id FROM package_advisories "
        "WHERE source = 'osv' AND origin = 'external' ORDER BY lookup_key_hash"
    ).fetchall()
    assert [row["lookup_key_hash"] for row in rows] == ["a" * 64, "b" * 64]
    assert rows[0]["advisory_id"] != rows[1]["advisory_id"]

    accept_external_osv_query(
        risk_db,
        package_purl="pkg:pypi/requests",
        lookup_key_hash="a" * 64,
        parsed=None,
        now=now,
        source_url="https://api.osv.dev/v1/query",
    )

    remaining = risk_db.execute(
        "SELECT lookup_key_hash FROM package_advisories "
        "WHERE source = 'osv' AND origin = 'external'"
    ).fetchall()
    assert [row["lookup_key_hash"] for row in remaining] == ["b" * 64]


def test_external_osv_http_boundary_posts_one_identifier_and_rejects_redirects(monkeypatch):
    captured = {}

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return "https://api.osv.dev/v1/query"

        def read(self, limit):
            captured["read_limit"] = limit
            return b"{}"

    class Opener:
        def open(self, request, *, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

    def build_test_opener(*handlers):
        captured["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(osv_external_http, "build_opener", build_test_opener)
    settings = {
        "allowed_hosts": ["api.osv.dev"],
        "http_timeout_seconds": 9,
        "max_download_bytes": 2048,
    }
    assert osv_external_http.download_osv_query(
        settings, "pkg:pypi/requests", "2.30.0"
    ) == b"{}"
    request = captured["request"]
    assert request.full_url == "https://api.osv.dev/v1/query"
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {
        "package": {"purl": "pkg:pypi/requests"},
        "version": "2.30.0",
    }
    assert captured["timeout"] == 9
    assert captured["read_limit"] == 2049
    assert len(captured["handlers"]) == 1
    assert isinstance(captured["handlers"][0], osv_external_http.RejectRedirects)
    assert captured["handlers"][0].redirect_request(None, None, 302, "", {}, "") is None
    osv_external_http.validate_response_url("https://api.osv.dev/v1/query", settings)
    with pytest.raises(OsvDatasetError, match="redirected outside"):
        osv_external_http.validate_response_url("https://example.invalid/v1/query", settings)
    with pytest.raises(OsvDatasetError, match="redirected outside"):
        osv_external_http.validate_response_url(
            "https://api.osv.dev/v1/query?next=1", settings
        )
    with pytest.raises(OsvDatasetError, match="outside the configured"):
        osv_external_http.allowed_query_url({"allowed_hosts": []})


def test_external_osv_disabled_and_invalid_queries_never_open_network(risk_db, monkeypatch):
    monkeypatch.setattr(
        osv_external,
        "download_osv_query",
        lambda *_args: pytest.fail("disabled or invalid OSV query opened the network"),
    )
    assert osv_external.query_external_osv(
        risk_db,
        "pkg:pypi/requests",
        "2.30.0",
        cfg={"cve_risk": {"osv_advisory_mode": "disabled"}},
    ) == {"source": "osv", "outcome": "disabled"}
    with pytest.raises(ValueError, match="exact PURL and version"):
        osv_external.query_external_osv(
            risk_db,
            "requests",
            "2.30.0",
            cfg={"cve_risk": {"osv_advisory_mode": "external"}},
        )


def test_kev_parser_requires_catalog_provenance_and_complete_rows():
    payload = {
        "catalogVersion": "2026.08.04",
        "dateReleased": "2026-08-04T00:00:00Z",
        "vulnerabilities": [{
            "cveID": "CVE-2026-12345",
            "dateAdded": "2026-08-01",
            "dueDate": "2026-08-22",
            "requiredAction": "Apply mitigations.",
            "knownRansomwareCampaignUse": "Known",
            "vendorProject": "Example",
            "product": "Server",
            "vulnerabilityName": "Example issue",
        }],
    }
    parsed = parse_kev(json.dumps(payload).encode())
    assert parsed.version == "2026.08.04"
    assert parsed.records[0]["kev_due_date"] == "2026-08-22"

    del payload["catalogVersion"]
    with pytest.raises(FeedValidationError, match="catalog version"):
        parse_kev(json.dumps(payload).encode())


def test_bundled_manifest_matches_pinned_compressed_assets():
    root = Path(bootstrap.__file__).resolve().parents[2] / "resources" / "cve_risk"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert {item["source"] for item in manifest["sources"]} == {"epss", "kev"}
    for item in manifest["sources"]:
        payload = (root / item["filename"]).read_bytes()
        assert len(payload) == item["compressed_bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_bundled_baseline_does_not_replace_newer_live_data(risk_db, monkeypatch, tmp_path):
    accepted = _epss_feed("v-live", "2026-08-05", ("CVE-2026-12345", 0.2, 0.9))
    accept_feed(
        risk_db,
        accepted,
        origin="live",
        payload_sha256="live-sha",
        enqueue_changes=False,
    )
    monkeypatch.setattr(bootstrap, "_ASSET_ROOT", tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": 1, "sources": []}))

    assert bootstrap.load_bundled_snapshots(risk_db) == {"loaded": 0, "skipped": 0, "failed": 0}
    row = risk_db.execute("SELECT origin, source_version FROM cve_risk_sources WHERE source = 'epss'").fetchone()
    assert dict(row) == {"origin": "live", "source_version": "v-live:2026-08-05"}


def test_feed_status_marks_old_bundled_data_stale_and_discloses_refresh_state(risk_db):
    accepted = _epss_feed("v-old", "2020-01-01", ("CVE-2026-12345", 0.2, 0.9))
    accept_feed(
        risk_db,
        accepted,
        origin="bundled",
        payload_sha256="old-sha",
        retrieved_at="2020-01-01T00:00:00+00:00",
        enqueue_changes=False,
    )
    status = {item["source"]: item for item in get_feed_status(
        risk_db, stale_after_hours=24, live_refresh_enabled=False
    )}
    assert status["epss"]["status"] == "stale"
    assert status["epss"]["origin"] == "bundled"
    assert status["epss"]["live_refresh_enabled"] is False
    assert status["kev"]["status"] == "unavailable"


def test_disabled_refresh_never_opens_the_network(risk_db, monkeypatch):
    monkeypatch.setattr(
        refresh,
        "_download",
        lambda *_args, **_kwargs: pytest.fail("disabled refresh attempted a download"),
    )
    assert refresh.refresh_source(
        risk_db,
        "epss",
        cfg={"cve_risk": {"refresh_enabled": False}},
    )["outcome"] == "disabled"


def test_conditional_refresh_preserves_snapshot_on_not_modified(risk_db, monkeypatch):
    accept_feed(
        risk_db,
        _epss_feed("v-good", "2026-08-03", ("CVE-2026-12345", 0.2, 0.9)),
        origin="live",
        payload_sha256="good-sha",
        enqueue_changes=False,
        etag='"epss-good"',
        last_modified="Mon, 03 Aug 2026 12:00:00 GMT",
    )
    monkeypatch.setattr(
        refresh,
        "_download",
        lambda *_args, **_kwargs: (
            None,
            '"epss-good"',
            "Mon, 03 Aug 2026 12:00:00 GMT",
        ),
    )

    result = refresh.refresh_source(
        risk_db,
        "epss",
        force=True,
        cfg={"cve_risk": {"allowed_hosts": ["epss.cyentia.com"]}},
    )

    assert result == {"source": "epss", "outcome": "not_modified"}
    row = risk_db.execute(
        "SELECT source_version, checksum_sha256, etag "
        "FROM cve_risk_sources WHERE source = 'epss'"
    ).fetchone()
    assert dict(row) == {
        "source_version": "v-good:2026-08-03",
        "checksum_sha256": "good-sha",
        "etag": '"epss-good"',
    }


def test_failed_refresh_retains_last_known_good_snapshot(risk_db, monkeypatch):
    accept_feed(
        risk_db,
        _epss_feed("v-good", "2026-08-03", ("CVE-2026-12345", 0.2, 0.9)),
        origin="bundled",
        payload_sha256="good-sha",
        enqueue_changes=False,
    )
    monkeypatch.setattr(refresh, "_download", lambda *_args, **_kwargs: (b"not-a-feed", "", ""))
    result = refresh.refresh_source(
        risk_db,
        "epss",
        force=True,
        cfg={"cve_risk": {"max_attempts": 1, "allowed_hosts": ["epss.cyentia.com"]}},
    )
    assert result["outcome"] == "failed"
    row = risk_db.execute(
        "SELECT source_version, checksum_sha256, last_error FROM cve_risk_sources WHERE source = 'epss'"
    ).fetchone()
    assert row["source_version"] == "v-good:2026-08-03"
    assert row["checksum_sha256"] == "good-sha"
    assert row["last_error"]


def test_redirect_validation_rejects_non_https_and_unlisted_hosts():
    settings = {"allowed_hosts": ["epss.cyentia.com"]}
    refresh._validate_response_url("https://epss.cyentia.com/feed.csv.gz", settings)
    with pytest.raises(FeedValidationError, match="redirected outside"):
        refresh._validate_response_url("https://example.invalid/feed.csv.gz", settings)
    with pytest.raises(FeedValidationError, match="redirected outside"):
        refresh._validate_response_url("http://epss.cyentia.com/feed.csv.gz", settings)


def test_risk_enrichment_and_sql_order_share_kev_epss_age_contract(risk_db):
    for finding_id, created in (("finding-old", "2026-01-01"), ("finding-new", "2026-02-01")):
        risk_db.execute(
            "INSERT INTO findings (id, session_id, target_id, title, created) VALUES (?, 's', ?, ?, ?)",
            (finding_id, finding_id, f"CVE-2026-{12345 if finding_id.endswith('old') else 23456}", created),
        )
    risk_db.executemany(
        "INSERT INTO finding_cve_links (finding_id, cve_id, created_at) VALUES (?, ?, '2026-08-04')",
        (("finding-old", "CVE-2026-12345"), ("finding-new", "CVE-2026-23456")),
    )
    risk_db.executemany(
        "INSERT INTO cve_risk_records (cve_id, kev_listed, epss_probability, epss_percentile) "
        "VALUES (?, ?, ?, ?)",
        (("CVE-2026-12345", False, 0.8, 0.99), ("CVE-2026-23456", True, 0.1, 0.7)),
    )
    findings = [{"id": "finding-old", "title": "CVE-2026-12345"}]
    attach_risk_to_findings(findings, conn=risk_db)
    assert findings[0]["risk"]["epss"]["probability"] == 0.8
    assert findings[0]["risk"]["priority_reasons"][0].startswith("EPSS")

    rows = risk_db.execute(
        "SELECT f.id FROM findings f ORDER BY "
        + cve_risk_order_sql("f", age_expression="f.created")
    ).fetchall()
    assert [row["id"] for row in rows] == ["finding-new", "finding-old"]


def test_risk_order_uses_newer_finding_as_final_shared_tie_breaker(risk_db):
    risk_db.execute(
        "INSERT INTO cve_risk_records (cve_id, epss_probability, cvss_score) "
        "VALUES ('CVE-2026-12345', 0.4, 7.5)"
    )
    for finding_id, target_id, created in (
        ("finding-older", "ent_older", "2026-01-01"),
        ("finding-newer", "ent_newer", "2026-02-01"),
    ):
        risk_db.execute(
            "INSERT INTO findings (id, session_id, target_id, title, created) "
            "VALUES (?, 'session-one', ?, 'CVE-2026-12345', ?)",
            (finding_id, target_id, created),
        )
        risk_db.execute(
            "INSERT INTO finding_cve_links (finding_id, cve_id, created_at) "
            "VALUES (?, 'CVE-2026-12345', '2026-08-04')",
            (finding_id,),
        )

    sql_rows = risk_db.execute(
        "SELECT f.id FROM findings f ORDER BY "
        + cve_risk_order_sql("f", age_expression="f.created")
    ).fetchall()
    worklist = build_remediation_worklist([{
        "id": "finding-newer",
        "session_id": "session-one",
        "entity_id": "ent_newer",
        "title": "CVE-2026-12345",
        "created": "2026-02-01",
    }, {
        "id": "finding-older",
        "session_id": "session-one",
        "entity_id": "ent_older",
        "title": "CVE-2026-12345",
        "created": "2026-01-01",
    }], conn=risk_db)

    assert [row["id"] for row in sql_rows] == ["finding-newer", "finding-older"]
    assert [row["representative_finding_id"] for row in worklist] == [
        "finding-newer",
        "finding-older",
    ]


def test_remediation_worklist_collapses_observations_without_losing_context(risk_db):
    risk_db.executemany(
        "INSERT INTO cve_risk_records "
        "(cve_id, kev_listed, epss_probability, epss_percentile, cvss_score) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            ("CVE-2026-12345", True, 0.12, 0.91, 8.8),
            ("CVE-2026-23456", False, 0.82, 0.99, 9.8),
        ),
    )
    findings = [{
        "id": "finding-confirmed",
        "session_id": "session-one",
        "entity_id": "ent_shared",
        "title": "CVE-2026-12345 confirmed",
        "first_seen_at": "2026-08-02",
        "run_id": "run-confirmed",
        "validation_method": "active_confirmation",
        "confidence": "high",
        "target_exposure": "internet",
        "asset_context": {"criticality": "high", "environment": "production"},
    }, {
        "id": "finding-inferred",
        "session_id": "session-one",
        "entity_id": "ent_shared",
        "title": "CVE-2026-12345 inferred",
        "first_seen_at": "2026-08-01",
        "run_id": "run-inferred",
        "validation_method": "version_inference",
        "confidence": "medium",
        "target_exposure": "internet",
        "asset_context": {"criticality": "high", "environment": "production"},
    }, {
        "id": "finding-other-target",
        "session_id": "session-one",
        "entity_id": "ent_other",
        "title": "CVE-2026-12345 on another target",
        "first_seen_at": "2026-08-03",
        "run_id": "run-other",
    }, {
        "id": "finding-high-epss",
        "session_id": "session-one",
        "entity_id": "ent_shared",
        "title": "CVE-2026-23456",
        "first_seen_at": "2026-08-04",
        "run_id": "run-high-epss",
    }, {
        "id": "finding-false-positive",
        "session_id": "session-one",
        "entity_id": "ent_shared",
        "title": "CVE-2026-23456",
        "review_state": "false_positive",
        "run_id": "run-false-positive",
    }]

    worklist = build_remediation_worklist(findings, conn=risk_db)

    assert len(worklist) == 3
    assert [item["vulnerability_id"] for item in worklist] == [
        "CVE-2026-12345",
        "CVE-2026-12345",
        "CVE-2026-23456",
    ]
    shared = next(
        item for item in worklist
        if item["affected_subject"] == "entity:ent_shared"
        and item["vulnerability_id"] == "CVE-2026-12345"
    )
    assert shared["observation_count"] == 2
    assert shared["evidence_count"] == 2
    assert shared["validation_methods"] == ["active_confirmation", "version_inference"]
    assert shared["strongest_validation_method"] == "active_confirmation"
    assert shared["title"] == "CVE-2026-12345 confirmed"
    assert [item["id"] for item in shared["observation_summaries"]] == [
        "finding-confirmed",
        "finding-inferred",
    ]
    assert shared["last_seen_at"] == "2026-08-02"
    assert shared["rule_identity"] == ""
    assert shared["rule_identities"] == [
        "observation:finding-confirmed",
        "observation:finding-inferred",
    ]
    assert shared["priority_context"] == {
        "confidence": ["high", "medium"],
        "exposure": ["internet"],
        "assets": [{"criticality": "high", "environment": "production"}],
    }
    assert shared["risk"]["kev"]["listed"] is True

    risk_db.executemany(
        "INSERT INTO finding_remediation_merge_members "
        "(session_id, team_id, merge_id, affected_subject, identity_kind, identity_value, "
        "vulnerability_id, rule_identity, created_by_session_id, created_at) "
        "VALUES ('session-one', '', 'rmg_explicit', ?, 'vulnerability', "
        "'CVE-2026-12345', 'CVE-2026-12345', ?, 'session-one', '2026-08-05')",
        (
            ("entity:ent_shared", "observation:finding-confirmed"),
            ("entity:ent_other", "observation:finding-other-target"),
        ),
    )

    merged_worklist = build_remediation_worklist(findings, conn=risk_db)

    assert len(merged_worklist) == 2
    merged = next(
        item for item in merged_worklist
        if item["remediation_group_id"] == "rmg_explicit"
    )
    assert merged["remediation_group_merged"] is True
    assert merged["remediation_group_member_count"] == 2
    assert merged["observation_count"] == 3
    assert len(merged["exact_remediation_ids"]) == 2
    assert merged["affected_subjects"] == ["entity:ent_other", "entity:ent_shared"]
    assert merged["vulnerability_ids"] == ["CVE-2026-12345"]


def test_remediation_identity_uses_owner_and_exact_subject_boundaries(risk_db):
    findings = [{
        "id": "personal-one",
        "session_id": "session-one",
        "subject_key": "domain\x1fexample.test",
        "title": "CVE-2026-12345",
    }, {
        "id": "personal-two",
        "session_id": "session-two",
        "subject_key": "domain\x1fexample.test",
        "title": "CVE-2026-12345",
    }, {
        "id": "unresolved-one",
        "session_id": "session-one",
        "title": "CVE-2026-12345",
    }, {
        "id": "unresolved-two",
        "session_id": "session-one",
        "title": "CVE-2026-12345",
    }]

    worklist = build_remediation_worklist(findings, conn=risk_db)

    assert len(worklist) == 4
    assert len({item["remediation_id"] for item in worklist}) == 4
    assert {
        item["affected_subject"] for item in worklist
        if item["affected_subject"].startswith("observation:")
    } == {"observation:unresolved-one", "observation:unresolved-two"}

    team_findings = [{
        "id": "team-one",
        "session_id": "member-one",
        "team_id": "team-shared",
        "entity_id": "ent_team",
        "title": "CVE-2026-12345",
    }, {
        "id": "team-two",
        "session_id": "member-two",
        "team_id": "team-shared",
        "entity_id": "ent_team",
        "title": "CVE-2026-12345",
    }]
    team_worklist = build_remediation_worklist(team_findings, conn=risk_db)
    assert len(team_worklist) == 1
    assert team_worklist[0]["observation_count"] == 2

    rule_observations = [{
        "id": "rule-confirmed",
        "session_id": "session-one",
        "entity_id": "ent_rule",
        "signature_hash": "stable-rule-signature",
        "tool_root": "nuclei",
        "kind": "finding",
        "title": "Original title",
        "severity": "high",
        "validation_method": "active_confirmation",
    }, {
        "id": "rule-inferred",
        "session_id": "session-one",
        "entity_id": "ent_rule",
        "signature_hash": "stable-rule-signature",
        "tool_root": "nuclei",
        "kind": "finding",
        "title": "Different editable title",
        "severity": "critical",
        "validation_method": "version_inference",
    }]
    attach_risk_to_findings(rule_observations, conn=risk_db)
    confirmed_reference = rule_observations[0]["observation_references"][0]
    inferred_reference = rule_observations[1]["observation_references"][0]
    assert confirmed_reference["identity_kind"] == "rule"
    assert confirmed_reference["vulnerability_id"] == ""
    assert confirmed_reference["rule_identity"] == "signature:stable-rule-signature"
    assert confirmed_reference["remediation_id"] == inferred_reference["remediation_id"]
    assert confirmed_reference["observation_id"] != inferred_reference["observation_id"]
    assert confirmed_reference["review_state"] == "new"
    assert confirmed_reference["review_state_source"] == "observation"
    assert rule_observations[0]["observation_id"] == confirmed_reference["observation_id"]
    assert rule_observations[0]["remediation_id"] == confirmed_reference["remediation_id"]
    risk_db.execute(
        "INSERT INTO finding_remediation_dispositions "
        "(session_id, team_id, affected_subject, identity_kind, identity_value, "
        "rule_identity, review_state, created_at, updated_at) "
        "VALUES ('session-one', '', 'entity:ent_rule', 'rule', "
        "'RULE:signature:stable-rule-signature', 'signature:stable-rule-signature', "
        "'reviewed', '2026-08-05', '2026-08-05')"
    )
    attach_risk_to_findings(rule_observations, conn=risk_db)
    assert {
        item["observation_references"][0]["review_state"]
        for item in rule_observations
    } == {"reviewed"}
    assert {
        item["observation_references"][0]["review_state_source"]
        for item in rule_observations
    } == {"remediation_group"}
    rule_worklist = build_remediation_worklist(rule_observations, conn=risk_db)
    assert len(rule_worklist) == 1
    assert rule_worklist[0]["identity_kind"] == "rule"
    assert rule_worklist[0]["vulnerability_id"] == ""
    assert rule_worklist[0]["rule_identity"] == "signature:stable-rule-signature"
    assert rule_worklist[0]["rule_identities"] == ["signature:stable-rule-signature"]
    assert rule_worklist[0]["observation_count"] == 2
    assert rule_worklist[0]["severity"] == "critical"
    assert rule_worklist[0]["severities"] == ["critical", "high"]
    assert rule_worklist[0]["validation_methods"] == [
        "active_confirmation",
        "version_inference",
    ]
    assert rule_worklist[0]["review_state"] == "reviewed"

    uncertain_rules = [{
        "id": finding_id,
        "session_id": "session-one",
        "entity_id": "ent_rule",
        "tool_root": "nuclei",
        "kind": "finding",
        "validation_method": "active_confirmation",
    } for finding_id in ("missing-rule-one", "missing-rule-two")]
    attach_risk_to_findings(uncertain_rules, conn=risk_db)
    assert uncertain_rules[0]["observation_references"][0]["rule_identity"] == (
        "observation:missing-rule-one"
    )
    assert uncertain_rules[1]["observation_references"][0]["rule_identity"] == (
        "observation:missing-rule-two"
    )
    assert uncertain_rules[0]["remediation_id"] != uncertain_rules[1]["remediation_id"]
    assert len(build_remediation_worklist(uncertain_rules, conn=risk_db)) == 2


def test_primary_remediation_reference_tracks_highest_priority_cve(risk_db):
    from services.projects.finding_remediation_merges import _primary_member

    risk_db.executemany(
        "INSERT INTO cve_risk_records (cve_id, kev_listed, epss_probability) VALUES (?, ?, ?)",
        (
            ("CVE-2026-12345", False, 0.9),
            ("CVE-2026-23456", True, 0.1),
        ),
    )
    findings = [{
        "id": "finding-multiple-cves",
        "session_id": "session-one",
        "entity_id": "ent_shared",
        "title": "CVE-2026-12345 and CVE-2026-23456",
    }]

    attach_risk_to_findings(findings, conn=risk_db)

    finding = findings[0]
    assert finding["risk"]["cve_id"] == "CVE-2026-23456"
    assert finding["remediation_id"] == next(
        item["remediation_id"] for item in finding["remediation_groups"]
        if item["vulnerability_id"] == "CVE-2026-23456"
    )
    assert finding["observation_id"] == next(
        item["observation_id"] for item in finding["observation_references"]
        if item["vulnerability_id"] == "CVE-2026-23456"
    )
    assert {
        item["vulnerability_id"] for item in finding["observation_references"]
    } == {"CVE-2026-12345", "CVE-2026-23456"}
    primary_merge_member = _primary_member(finding)
    assert primary_merge_member["remediation_id"] == finding["remediation_id"]
    assert primary_merge_member["vulnerability_id"] == "CVE-2026-23456"
    risk_db.execute(
        "INSERT INTO finding_remediation_dispositions "
        "(session_id, team_id, affected_subject, identity_kind, identity_value, "
        "vulnerability_id, review_state, created_at, updated_at) "
        "VALUES ('session-one', '', 'entity:ent_shared', 'vulnerability', "
        "'CVE-2026-12345', 'CVE-2026-12345', 'important', '2026-08-05', '2026-08-05')"
    )
    finding["status"] = "important"
    attach_risk_to_findings(findings, conn=risk_db)
    review_by_cve = {
        item["vulnerability_id"]: item["review_state"]
        for item in finding["observation_references"]
    }
    assert review_by_cve == {
        "CVE-2026-12345": "important",
        "CVE-2026-23456": "new",
    }
    assert finding["review_state"] == "new"
    legacy_material = "\x1f".join(("", "session-one", "ent_shared", "CVE-2026-23456"))
    assert finding["remediation_id"] == (
        "rmd_" + hashlib.sha256(legacy_material.encode()).hexdigest()[:32]
    )


def test_enrichment_accepts_private_owner_context_without_exposing_it(risk_db):
    finding = {
        "id": "finding-private-owner",
        "entity_id": "ent_private_owner",
        "title": "CVE-2026-12345",
    }

    attach_risk_to_findings(
        [finding],
        conn=risk_db,
        owner_by_finding_id={
            "finding-private-owner": ("member-session", "team-private-owner"),
        },
    )

    assert finding["remediation_id"] == remediation_identity({
        **finding,
        "session_id": "member-session",
        "team_id": "team-private-owner",
    }, "CVE-2026-12345")
    assert "session_id" not in finding
    assert "team_id" not in finding


def test_risk_order_sql_rejects_untrusted_identifier_fragments():
    with pytest.raises(ValueError, match="ordering alias"):
        cve_risk_order_sql("f; DROP TABLE findings", age_expression="f.created")
    with pytest.raises(ValueError, match="age expression"):
        cve_risk_order_sql("f", age_expression="f.created DESC; DROP TABLE findings")


def test_nvd_dataset_normalizes_cvss_cwe_disputed_status_and_safe_cpe_applicability():
    parsed = parse_nvd_dataset(json.dumps({
        "formatVersion": "NVD_CVE",
        "timestamp": "2026-08-04T12:00:00Z",
        "vulnerabilities": [{
            "cve": {
                "id": "CVE-2026-12345",
                "vulnStatus": "Analyzed",
                "cveTags": [{"tags": ["disputed"]}],
                "published": "2026-08-01T00:00:00Z",
                "lastModified": "2026-08-04T00:00:00Z",
                "metrics": {"cvssMetricV31": [{
                    "baseSeverity": "HIGH",
                    "cvssData": {
                        "version": "3.1",
                        "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                        "baseScore": 9.8,
                    },
                }]},
                "weaknesses": [{"description": [
                    {"lang": "en", "value": "CWE-787"},
                    {"lang": "en", "value": "NVD-CWE-noinfo"},
                ]}],
                "configurations": [{"nodes": [{
                    "operator": "OR",
                    "negate": False,
                    "cpeMatch": [{
                        "vulnerable": True,
                        "criteria": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
                        "matchCriteriaId": "00000000-0000-4000-8000-000000000001",
                    }, {
                        "vulnerable": True,
                        "criteria": "cpe:2.3:a:example:server:*:*:*:*:*:*:*:*",
                        "matchCriteriaId": "00000000-0000-4000-8000-000000000002",
                        "versionStartIncluding": "2.4",
                        "versionEndExcluding": "2.6",
                    }, {
                        "vulnerable": True,
                        "criteria": "cpe:2.3:o:example:device:*:*:*:*:*:*:*:*",
                        "matchCriteriaId": "00000000-0000-4000-8000-000000000003",
                    }, {
                        "vulnerable": False,
                        "criteria": "cpe:2.3:h:example:device:*:*:*:*:*:*:*:*",
                        "matchCriteriaId": "00000000-0000-4000-8000-000000000004",
                    }, {
                        "vulnerable": True,
                        "criteria": "cpe:2.3:a:example:invalid:*:*:*:*:*:*:*:*",
                        "matchCriteriaId": "00000000-0000-4000-8000-000000000005",
                        "versionEndExcluding": "2.6-beta",
                    }],
                }]}, {"nodes": [{
                    "operator": "AND",
                    "cpeMatch": [{
                        "vulnerable": True,
                        "criteria": "cpe:2.3:a:example:conditional:*:*:*:*:*:*:*:*",
                        "matchCriteriaId": "00000000-0000-4000-8000-000000000006",
                    }],
                }]}, {"nodes": [{
                    "operator": "OR",
                    "negate": True,
                    "cpeMatch": [{
                        "vulnerable": True,
                        "criteria": "cpe:2.3:a:example:negated:*:*:*:*:*:*:*:*",
                        "matchCriteriaId": "00000000-0000-4000-8000-000000000007",
                    }],
                }]}, {"nodes": [{
                    "operator": "OR",
                    "children": [{"operator": "OR", "cpeMatch": []}],
                    "cpeMatch": [{
                        "vulnerable": True,
                        "criteria": "cpe:2.3:a:example:nested:*:*:*:*:*:*:*:*",
                        "matchCriteriaId": "00000000-0000-4000-8000-000000000009",
                    }],
                }]}, {"operator": "AND", "nodes": [{
                    "operator": "OR",
                    "cpeMatch": [{
                        "vulnerable": True,
                        "criteria": "cpe:2.3:a:example:wrapped:*:*:*:*:*:*:*:*",
                        "matchCriteriaId": "00000000-0000-4000-8000-000000000008",
                    }],
                }]}],
            },
        }],
    }).encode())

    assert parsed.version == "2026-08-04T12:00:00Z"
    cve_id, payload = parsed.records[0]
    assert cve_id == "CVE-2026-12345"
    assert payload["status"] == "disputed"
    assert payload["score"] == 9.8
    assert payload["cvss_version"] == "3.1"
    assert payload["cwes"] == ["CWE-787"]
    assert payload["cpe_matches"] == [{
        "criteria": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
        "matchCriteriaId": "00000000-0000-4000-8000-000000000001",
        "vulnerable": True,
        "applicability_complete": True,
        "negate": False,
    }, {
        "criteria": "cpe:2.3:a:example:server:*:*:*:*:*:*:*:*",
        "matchCriteriaId": "00000000-0000-4000-8000-000000000002",
        "vulnerable": True,
        "applicability_complete": True,
        "negate": False,
        "versionStartIncluding": "2.4",
        "versionEndExcluding": "2.6",
    }, {
        "criteria": "cpe:2.3:o:example:device:*:*:*:*:*:*:*:*",
        "matchCriteriaId": "00000000-0000-4000-8000-000000000003",
        "vulnerable": True,
        "applicability_complete": True,
        "negate": False,
        "all_versions": True,
    }]
    assert normalize_nvd_cpe_matches([{"nodes": []}] * 129) == []
    match = {
        "vulnerable": True,
        "criteria": "cpe:2.3:a:example:oversized:*:*:*:*:*:*:*:*",
        "matchCriteriaId": "00000000-0000-4000-8000-000000000011",
    }
    assert normalize_nvd_cpe_matches([{
        "nodes": [{"operator": "OR", "cpeMatch": [match] * 129}],
    }]) == []
    assert normalize_nvd_cpe_matches([{"nodes": [{
        "operator": "OR",
        "cpeMatch": [{
            "vulnerable": True,
            "criteria": "cpe:2.3:a:example:empty_range:*:*:*:*:*:*:*:*",
            "matchCriteriaId": "00000000-0000-4000-8000-000000000010",
            "versionStartExcluding": "2.4",
            "versionEndIncluding": "2.4.0",
        }],
    }]}]) == []


def test_external_nvd_lookup_persists_positive_and_negative_cache_without_identifiers_in_logs(
    risk_db,
    caplog,
):
    cfg = {"cve_risk": {
        "advisory_mode": "external",
        "advisory_positive_ttl_seconds": 7200,
        "advisory_negative_ttl_seconds": 600,
    }}
    with caplog.at_level("INFO"):
        result = persist_external_nvd_lookup(
            risk_db,
            "CVE-2026-12345",
            {
                "status": "active",
                "published": "2026-08-01T00:00:00Z",
                "last_modified": "2026-08-04T00:00:00Z",
                "severity": "HIGH",
                "score": 8.8,
                "cvss_version": "3.1",
                "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H",
                "cwes": ["CWE-79"],
                "cpe_matches": [{
                    "criteria": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
                    "matchCriteriaId": "00000000-0000-4000-8000-000000000012",
                    "vulnerable": True,
                    "applicability_complete": True,
                    "negate": False,
                }],
            },
            cfg=cfg,
            now=datetime.fromisoformat("2026-08-04T12:00:00+00:00"),
        )
        replacement = persist_external_nvd_lookup(
            risk_db,
            "CVE-2026-12345",
            {
                "status": "active",
                "published": "2026-08-01T00:00:00Z",
                "last_modified": "2026-08-05T00:00:00Z",
                "severity": "HIGH",
                "score": 8.8,
                "cvss_version": "3.1",
                "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H",
                "cwes": ["CWE-79"],
                "cpe_matches": [{
                    "criteria": "cpe:2.3:a:example:server:*:*:*:*:*:*:*:*",
                    "matchCriteriaId": "00000000-0000-4000-8000-000000000013",
                    "vulnerable": True,
                    "applicability_complete": True,
                    "negate": False,
                    "versionStartIncluding": "2.4",
                    "versionEndExcluding": "2.6",
                }, {
                    "criteria": "cpe:2.3:a:example:unsafe:*:*:*:*:*:*:*:*",
                    "matchCriteriaId": "00000000-0000-4000-8000-000000000014",
                    "vulnerable": True,
                    "applicability_complete": False,
                    "negate": False,
                }],
            },
            cfg=cfg,
            now=datetime.fromisoformat("2026-08-05T12:00:00+00:00"),
        )
        negative = persist_external_nvd_lookup(
            risk_db,
            "CVE-2026-99999",
            {"status": "unknown", "score": None, "cwes": [], "references": []},
            cfg=cfg,
            now=datetime.fromisoformat("2026-08-04T12:00:00+00:00"),
        )

    assert result == {"source": "nvd", "outcome": "stored", "record_count": 1}
    assert replacement == {"source": "nvd", "outcome": "stored", "record_count": 1}
    assert negative == {"source": "nvd", "outcome": "negative_cached", "record_count": 0}
    row = risk_db.execute(
        "SELECT advisory_status, cvss_score, cvss_vector, cwe_ids_json, nvd_origin "
        "FROM cve_risk_records WHERE cve_id = 'CVE-2026-12345'"
    ).fetchone()
    assert dict(row) == {
        "advisory_status": "active",
        "cvss_score": 8.8,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H",
        "cwe_ids_json": '["CWE-79"]',
        "nvd_origin": "external",
    }
    applicability_rows = risk_db.execute(
        "SELECT cve_id, match_criteria_id, cpe_part, cpe_vendor, cpe_product, "
        "criteria_version, version_start_including, version_end_excluding, all_versions, "
        "source_version, origin FROM cve_advisory_cpe_matches"
    ).fetchall()
    assert [dict(item) for item in applicability_rows] == [{
        "cve_id": "CVE-2026-12345",
        "match_criteria_id": "00000000-0000-4000-8000-000000000013",
        "cpe_part": "a",
        "cpe_vendor": "example",
        "cpe_product": "server",
        "criteria_version": "*",
        "version_start_including": "2.4",
        "version_end_excluding": "2.6",
        "all_versions": 0,
        "source_version": "2026-08-05T00:00:00Z",
        "origin": "external",
    }]
    observation = {
        "cpe": "cpe:2.3:a:EXAMPLE:SERVER:2.5.1:*:*:*:*:*:*:*",
        "observation_id": "obs-nvd-1",
        "target": "api.example.test",
    }
    changes_before_read = risk_db.total_changes
    correlation = correlate_stored_nvd_cpe_page(
        risk_db,
        observation,
        now=datetime.fromisoformat("2026-08-05T13:00:00+00:00"),
    )
    assert correlation == {
        "source": "nvd",
        "matches": [{
            "vulnerability_id": "CVE-2026-12345",
            "confidence": "high",
            "match_basis": "exact_cpe_nvd_range",
            "observed_identifier": observation["cpe"],
            "observed_version": "2.5.1",
            "affected_range": "NVD: >= 2.4; < 2.6",
            "range_type": "CPE_NUMERIC",
            "advisory_source": "nvd",
            "advisory_source_version": "2026-08-05T00:00:00Z",
            "validation_method": "version_inference",
            "advisory_origin": "external",
            "advisory_expires_at": "2026-08-05T14:00:00+00:00",
            "advisory_source_state": "current",
            "advisory_criteria": "cpe:2.3:a:example:server:*:*:*:*:*:*:*:*",
            "advisory_match_criteria_id": "00000000-0000-4000-8000-000000000013",
        }],
        "limit": 25,
        "offset": 0,
        "candidate_cve_count": 1,
        "rejected_candidate_count": 0,
        "has_more": False,
        "next_offset": None,
    }
    assert risk_db.total_changes == changes_before_read
    nmap_candidate_result = correlate_nmap_xml_with_stored_nvd(
        risk_db,
        """<nmaprun version="7.96"><host><address addr="192.0.2.10" addrtype="ipv4"/>
        <ports><port protocol="tcp" portid="443"><state state="open"/><service name="https">
        <cpe>cpe:/a:example:server:2.5.1</cpe></service></port></ports></host></nmaprun>""",
        source_run_id="run-nmap-xml-1",
        observed_at="2026-08-05T12:30:00+00:00",
        now=datetime.fromisoformat("2026-08-05T13:00:00+00:00"),
    )
    assert nmap_candidate_result["observation_count"] == 1
    assert nmap_candidate_result["candidate_count"] == 1
    nmap_candidate = nmap_candidate_result["observations"][0]["candidates"][0]
    assert nmap_candidate["target"] == "192.0.2.10:443/tcp"
    assert nmap_candidate["vulnerability_id"] == "CVE-2026-12345"
    assert nmap_candidate["source"] == {
        "kind": "run",
        "observation_id": nmap_candidate_result["observations"][0]["observation_id"],
        "observed_at": "2026-08-05T12:30:00+00:00",
        "tool_version": "7.96",
        "run_id": "run-nmap-xml-1",
        "parser_version": "nmap-xml-cpe-v1",
    }
    assert risk_db.total_changes == changes_before_read
    httpx_candidate_result = correlate_httpx_json_with_stored_nvd(
        risk_db,
        {
            "url": "https://api.example.test",
            "timestamp": "2026-08-05T12:30:00Z",
            "tech": ["Server:2.5.1"],
            "cpe": [{
                "product": "server",
                "vendor": "example",
                "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
            }],
        },
        source_run_id="run-httpx-json-1",
        tool_version="httpx 1.10.0",
        now=datetime.fromisoformat("2026-08-05T13:00:00+00:00"),
    )
    assert httpx_candidate_result["observation_count"] == 1
    assert httpx_candidate_result["candidate_count"] == 1
    httpx_candidate = httpx_candidate_result["observations"][0]["candidates"][0]
    assert httpx_candidate["target"] == "https://api.example.test"
    assert httpx_candidate["vulnerability_id"] == "CVE-2026-12345"
    assert httpx_candidate["source"] == {
        "kind": "run",
        "observation_id": httpx_candidate_result["observations"][0]["observation_id"],
        "observed_at": "2026-08-05T12:30:00Z",
        "tool_version": "httpx 1.10.0",
        "run_id": "run-httpx-json-1",
        "parser_version": "httpx-json-cpe-v1",
    }
    cyclonedx_cpe_result = correlate_cyclonedx_json_with_stored_nvd(
        risk_db,
        json.dumps({
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "components": [{
                "type": "application",
                "bom-ref": "component-server-2.5.1",
                "name": "server",
                "version": "2.5.1",
                "purl": "pkg:generic/example/server@2.5.1",
                "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
            }],
        }).encode(),
        source_batch_id="batch-cyclonedx-nvd-1",
        observed_at="2026-08-05T12:30:00Z",
        now=datetime.fromisoformat("2026-08-05T13:00:00+00:00"),
    )
    assert cyclonedx_cpe_result["candidate_count"] == 1
    cyclonedx_cpe_observation = cyclonedx_cpe_result["observations"][0]
    assert cyclonedx_cpe_observation["component_purl"] == "pkg:generic/example/server@2.5.1"
    assert cyclonedx_cpe_observation["candidates"][0]["source"] == {
        "kind": "import",
        "observation_id": cyclonedx_cpe_observation["observation_id"],
        "observed_at": "2026-08-05T12:30:00Z",
        "tool_version": "CycloneDX 1.6",
        "batch_id": "batch-cyclonedx-nvd-1",
        "parser_version": "cyclonedx-cpe-v1",
    }
    assert risk_db.total_changes == changes_before_read
    incomplete_httpx = correlate_httpx_json_with_stored_nvd(
        risk_db,
        {
            "url": "https://api.example.test",
            "timestamp": "2026-08-05T12:30:00Z",
            "tech": ["Server:2.5.1"],
            "cpe": [{
                "product": "server",
                "vendor": "example",
                "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
            }],
        },
        source_run_id="run-httpx-json-1",
        tool_version="",
    )
    assert incomplete_httpx["candidate_count"] == 0
    assert incomplete_httpx["observations"][0]["matched_cve_count"] == 1
    assert incomplete_httpx["observations"][0]["unmaterialized_match_count"] == 1
    assert risk_db.total_changes == changes_before_read
    risk_db.execute(
        "INSERT INTO runs (id, session_id, command, started, finished, exit_code) "
        "VALUES ('run-nmap-xml-1', 'version-owner', 'nmap -sV 192.0.2.10', ?, ?, 0)",
        ("2026-08-05T12:00:00+00:00", "2026-08-05T12:30:00+00:00"),
    )
    risk_db.execute(
        "INSERT INTO entities (id, session_id, type, canonical_value, signature_hash, "
        "first_seen_at, last_seen_at, occurrence_count, created) VALUES "
        "('entity-version-port', 'version-owner', 'port', '192.0.2.10:443/tcp', "
        "'signature-version-port', ?, ?, 1, ?)",
        ("2026-08-05T12:30:00+00:00",) * 3,
    )
    risk_db.execute(
        "INSERT INTO entity_run_links (entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
        "VALUES ('entity-version-port', 'run-nmap-xml-1', ?, ?, 1)",
        ("2026-08-05T12:30:00+00:00",) * 2,
    )
    assert persist_version_inference_candidate(
        risk_db, "other-version-owner", nmap_candidate
    ) is None
    saved_inference = persist_version_inference_candidate(
        risk_db, "version-owner", nmap_candidate
    )
    repeated_inference = persist_version_inference_candidate(
        risk_db, "version-owner", nmap_candidate
    )
    assert saved_inference is not None
    assert saved_inference["created"] is True
    assert saved_inference["source_created"] is True
    assert repeated_inference == {**saved_inference, "created": False, "source_created": False}
    materialized_nmap = materialize_nmap_xml_version_inferences(
        risk_db,
        "version-owner",
        """<nmaprun version="7.96"><host><address addr="192.0.2.10" addrtype="ipv4"/>
        <ports><port protocol="tcp" portid="443"><state state="open"/><service name="https">
        <cpe>cpe:/a:example:server:2.5.1</cpe></service></port></ports></host></nmaprun>""",
        source_run_id="run-nmap-xml-1",
        observed_at="2026-08-05T12:30:00+00:00",
        now=datetime.fromisoformat("2026-08-05T13:00:00+00:00"),
    )
    assert materialized_nmap == {
        "observation_count": 1,
        "candidate_count": 1,
        "attempted_count": 1,
        "materialized_count": 1,
        "finding_created_count": 0,
        "source_created_count": 0,
        "rejected_count": 0,
        "skipped_count": 0,
        "truncated": False,
    }
    risk_db.execute(
        "INSERT INTO runs (id, session_id, command, started, finished, exit_code) "
        "VALUES ('run-httpx-json-1', 'version-owner', 'httpx -u https://api.example.test -json', ?, ?, 0)",
        ("2026-08-05T12:00:00+00:00", "2026-08-05T12:30:00+00:00"),
    )
    risk_db.execute(
        "INSERT INTO entities (id, session_id, type, canonical_value, signature_hash, "
        "first_seen_at, last_seen_at, occurrence_count, created) VALUES "
        "('entity-version-url', 'version-owner', 'url', 'https://api.example.test', "
        "'signature-version-url', ?, ?, 1, ?)",
        ("2026-08-05T12:30:00+00:00",) * 3,
    )
    risk_db.execute(
        "INSERT INTO entity_run_links (entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
        "VALUES ('entity-version-url', 'run-httpx-json-1', ?, ?, 1)",
        ("2026-08-05T12:30:00+00:00",) * 2,
    )
    materialized_httpx = materialize_httpx_json_version_inferences(
        risk_db,
        "version-owner",
        {
            "url": "https://api.example.test",
            "timestamp": "2026-08-05T12:30:00Z",
            "tech": ["Server:2.5.1"],
            "cpe": [{
                "product": "server",
                "vendor": "example",
                "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
            }],
        },
        source_run_id="run-httpx-json-1",
        tool_version="httpx 1.10.0",
        now=datetime.fromisoformat("2026-08-05T13:00:00+00:00"),
    )
    assert materialized_httpx == {
        "observation_count": 1,
        "candidate_count": 1,
        "attempted_count": 1,
        "materialized_count": 1,
        "finding_created_count": 1,
        "source_created_count": 1,
        "rejected_count": 0,
        "skipped_count": 0,
        "truncated": False,
    }
    httpx_finding = risk_db.execute(
        "SELECT origin, validation_method, tool_root, entity_id FROM findings "
        "WHERE entity_id = 'entity-version-url'"
    ).fetchone()
    assert dict(httpx_finding) == {
        "origin": "run",
        "validation_method": "version_inference",
        "tool_root": "httpx",
        "entity_id": "entity-version-url",
    }
    repeated_httpx = materialize_httpx_json_version_inferences(
        risk_db,
        "version-owner",
        {
            "url": "https://api.example.test",
            "timestamp": "2026-08-05T12:30:00Z",
            "tech": ["Server:2.5.1"],
            "cpe": [{
                "product": "server",
                "vendor": "example",
                "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
            }],
        },
        source_run_id="run-httpx-json-1",
        tool_version="httpx 1.10.0",
        now=datetime.fromisoformat("2026-08-05T13:00:00+00:00"),
    )
    assert repeated_httpx["materialized_count"] == 1
    assert repeated_httpx["finding_created_count"] == 0
    assert repeated_httpx["source_created_count"] == 0
    risk_db.execute("UPDATE runs SET exit_code = 1 WHERE id = 'run-httpx-json-1'")
    failed_httpx = materialize_httpx_json_version_inferences(
        risk_db,
        "version-owner",
        {
            "url": "https://api.example.test",
            "timestamp": "2026-08-05T12:30:00Z",
            "tech": ["Server:2.5.1"],
            "cpe": [{
                "product": "server",
                "vendor": "example",
                "cpe": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
            }],
        },
        source_run_id="run-httpx-json-1",
        tool_version="httpx 1.10.0",
        now=datetime.fromisoformat("2026-08-05T13:00:00+00:00"),
    )
    assert failed_httpx["materialized_count"] == 0
    assert failed_httpx["rejected_count"] == 1
    mismatched_httpx = {
        **httpx_candidate,
        "source": {
            **httpx_candidate["source"],
            "run_id": "run-nmap-xml-1",
        },
    }
    assert persist_version_inference_candidate(
        risk_db, "version-owner", mismatched_httpx
    ) is None
    saved_row = risk_db.execute(
        "SELECT origin, validation_method, severity, confidence, cve_ids_json, occurrence_count, "
        "run_id, entity_id FROM findings WHERE id = ?",
        (saved_inference["finding_id"],),
    ).fetchone()
    assert dict(saved_row) == {
        "origin": "run",
        "validation_method": "version_inference",
        "severity": "info",
        "confidence": "high",
        "cve_ids_json": '["CVE-2026-12345"]',
        "occurrence_count": 1,
        "run_id": "run-nmap-xml-1",
        "entity_id": "entity-version-port",
    }
    saved_source = risk_db.execute(
        "SELECT source_kind, source_id, observation_id, observed_identifier, observed_version, "
        "match_basis, advisory_source_version FROM finding_version_inference_sources "
        "WHERE finding_id = ?",
        (saved_inference["finding_id"],),
    ).fetchone()
    assert dict(saved_source) == {
        "source_kind": "run",
        "source_id": "run-nmap-xml-1",
        "observation_id": nmap_candidate["source"]["observation_id"],
        "observed_identifier": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
        "observed_version": "2.5.1",
        "match_basis": "exact_cpe_nvd_range",
        "advisory_source_version": "2026-08-05T00:00:00Z",
    }
    assert risk_db.execute(
        "SELECT link_source FROM finding_cve_links WHERE finding_id = ?",
        (saved_inference["finding_id"],),
    ).fetchone()["link_source"] == "version_inference"
    tampered = {**nmap_candidate, "affected_range": "all versions"}
    assert persist_version_inference_candidate(risk_db, "version-owner", tampered) is None
    assert risk_db.execute(
        "SELECT COUNT(*) FROM finding_version_inference_sources"
    ).fetchone()[0] == 2
    changes_before_read = risk_db.total_changes
    candidate_page = materialize_stored_nvd_cpe_candidate_page(
        risk_db,
        observation,
        source_id="run-nmap-1",
        source_kind="run",
        observed_at="2026-08-05T12:30:00+00:00",
        tool_version="nmap 7.96",
        parser_version="nmap-xml-v2",
        now=datetime.fromisoformat("2026-08-05T13:00:00+00:00"),
    )
    assert candidate_page["matched_cve_count"] == 1
    assert candidate_page["unmaterialized_match_count"] == 0
    assert candidate_page["candidates"] == [{
        "kind": "finding",
        "validation_method": "version_inference",
        "title": "Version may be affected by CVE-2026-12345",
        "vulnerability_id": "CVE-2026-12345",
        "target": "api.example.test",
        "source": {
            "kind": "run",
            "observation_id": "obs-nvd-1",
            "observed_at": "2026-08-05T12:30:00+00:00",
            "tool_version": "nmap 7.96",
            "run_id": "run-nmap-1",
            "parser_version": "nmap-xml-v2",
        },
        "confidence": "high",
        "match_basis": "exact_cpe_nvd_range",
        "observed_identifier": observation["cpe"],
        "observed_version": "2.5.1",
        "affected_range": "NVD: >= 2.4; < 2.6",
        "range_type": "CPE_NUMERIC",
        "advisory_source": "nvd",
        "advisory_source_version": "2026-08-05T00:00:00Z",
        "advisory_origin": "external",
        "advisory_expires_at": "2026-08-05T14:00:00+00:00",
        "advisory_source_state": "current",
        "advisory_criteria": "cpe:2.3:a:example:server:*:*:*:*:*:*:*:*",
        "advisory_match_criteria_id": "00000000-0000-4000-8000-000000000013",
    }]
    assert risk_db.total_changes == changes_before_read
    risk_db.execute(
        "INSERT INTO atlas_import_batches "
        "(id, session_id, source_tool, import_name, created, applied_at, status) "
        "VALUES ('batch-version-import', 'version-owner', 'cyclonedx', 'Version import', ?, ?, 'applied')",
        ("2026-08-05T12:30:00+00:00",) * 2,
    )
    risk_db.execute(
        "INSERT INTO entities (id, session_id, type, canonical_value, signature_hash, "
        "first_seen_at, last_seen_at, occurrence_count, created) VALUES "
        "('entity-version-import', 'version-owner', 'domain', 'api.example.test', "
        "'signature-version-import', ?, ?, 1, ?)",
        ("2026-08-05T12:30:00+00:00",) * 3,
    )
    risk_db.execute(
        "INSERT INTO atlas_entity_import_links "
        "(entity_id, batch_id, first_observed_at, last_observed_at, occurrence_count, created, updated) "
        "VALUES ('entity-version-import', 'batch-version-import', ?, ?, 1, ?, ?)",
        ("2026-08-05T12:30:00+00:00",) * 4,
    )
    import_candidate = {
        **candidate_page["candidates"][0],
        "source": {
            **candidate_page["candidates"][0]["source"],
            "kind": "import",
            "run_id": "",
            "batch_id": "batch-version-import",
            "tool_version": "cyclonedx 1.6",
            "parser_version": "cyclonedx-v1",
        },
    }
    saved_import_inference = persist_version_inference_candidate(
        risk_db, "version-owner", import_candidate
    )
    assert saved_import_inference is not None
    assert saved_import_inference["created"] is True
    import_finding = risk_db.execute(
        "SELECT origin, validation_method, occurrence_count, run_id, entity_id "
        "FROM findings WHERE id = ?",
        (saved_import_inference["finding_id"],),
    ).fetchone()
    assert dict(import_finding) == {
        "origin": "import",
        "validation_method": "version_inference",
        "occurrence_count": 1,
        "run_id": "",
        "entity_id": "entity-version-import",
    }
    incomplete_page = materialize_stored_nvd_cpe_candidate_page(
        risk_db,
        {**observation, "observation_id": ""},
        source_id="run-nmap-1",
        source_kind="run",
        observed_at="2026-08-05T12:30:00+00:00",
        tool_version="nmap 7.96",
        parser_version="nmap-xml-v2",
    )
    assert incomplete_page["matched_cve_count"] == 1
    assert incomplete_page["candidates"] == []
    assert incomplete_page["unmaterialized_match_count"] == 1
    stale = correlate_stored_nvd_cpe_page(
        risk_db,
        observation,
        now=datetime.fromisoformat("2026-08-05T15:00:00+00:00"),
    )
    assert stale["matches"][0]["advisory_source_state"] == "stale"
    assert correlate_stored_nvd_cpe_page(risk_db, {
        "cpe": "cpe:2.3:a:example:server:2.6:*:*:*:*:*:*:*",
    })["matches"] == []
    assert correlate_stored_nvd_cpe_page(risk_db, {"cpe": "example server 2.5.1"})["matches"] == []
    cache_rows = risk_db.execute(
        "SELECT result_state, record_count FROM cve_advisory_lookup_cache ORDER BY result_state"
    ).fetchall()
    assert [dict(item) for item in cache_rows] == [
        {"result_state": "negative", "record_count": 0},
        {"result_state": "positive", "record_count": 1},
    ]
    assert "CVE-2026-12345" not in caplog.text
    assert "CVE-2026-99999" not in caplog.text
    risk_db.execute(
        "INSERT INTO cve_risk_records (cve_id, updated_at) VALUES (?, ?)",
        ("CVE-2026-12346", "2026-08-05T12:00:00+00:00"),
    )
    risk_db.execute(
        "INSERT INTO cve_advisory_cpe_matches ("
        "source, cve_id, match_criteria_id, criteria, cpe_part, cpe_vendor, cpe_product, "
        "criteria_version, version_start_including, version_end_excluding, all_versions, "
        "source_version, origin, fetched_at, expires_at) "
        "SELECT source, ?, ?, criteria, cpe_part, cpe_vendor, cpe_product, criteria_version, "
        "version_start_including, version_end_excluding, all_versions, source_version, origin, "
        "fetched_at, expires_at FROM cve_advisory_cpe_matches WHERE cve_id = ?",
        (
            "CVE-2026-12346",
            "00000000-0000-4000-8000-000000000016",
            "CVE-2026-12345",
        ),
    )
    first_page = correlate_stored_nvd_cpe_page(risk_db, observation, limit=1)
    second_page = correlate_stored_nvd_cpe_page(risk_db, observation, limit=1, offset=1)
    assert [match["vulnerability_id"] for match in first_page["matches"]] == ["CVE-2026-12345"]
    assert first_page["has_more"] is True
    assert first_page["next_offset"] == 1
    assert [match["vulnerability_id"] for match in second_page["matches"]] == ["CVE-2026-12346"]
    assert second_page["has_more"] is False


def test_local_nvd_dataset_replaces_prior_local_snapshot_and_enriches_ranking(risk_db):
    first = parse_nvd_dataset(json.dumps({
        "timestamp": "2026-08-03T00:00:00Z",
        "vulnerabilities": [{"cve": {
            "id": "CVE-2026-12345",
            "vulnStatus": "Analyzed",
            "published": "2026-08-01",
            "lastModified": "2026-08-03",
            "metrics": {"cvssMetricV31": [{
                "baseSeverity": "HIGH",
                "cvssData": {"version": "3.1", "vectorString": "CVSS:3.1/AV:N", "baseScore": 8.1},
            }]},
            "configurations": [{"nodes": [{
                "operator": "OR",
                "cpeMatch": [{
                    "criteria": "cpe:2.3:a:example:server:2.5.1:*:*:*:*:*:*:*",
                    "matchCriteriaId": "00000000-0000-4000-8000-000000000015",
                    "vulnerable": True,
                }],
            }]}],
        }}],
    }).encode())
    accept_local_nvd_dataset(
        risk_db,
        first,
        checksum="local-one",
        cfg={"cve_risk": {"advisory_mode": "local"}},
        now=datetime.fromisoformat("2026-08-04T00:00:00+00:00"),
    )
    risk_db.execute(
        "INSERT INTO findings (id, session_id, title, created) "
        "VALUES ('finding-cvss', 'session-one', 'CVE-2026-12345', '2026-08-04')"
    )
    findings = [{"id": "finding-cvss", "title": "CVE-2026-12345"}]
    attach_risk_to_findings(findings, conn=risk_db)

    assert findings[0]["risk"]["cvss"]["score"] == 8.1
    assert findings[0]["risk"]["cvss"]["vector"] == "CVSS:3.1/AV:N"
    assert "CVSS 8.1" in findings[0]["risk"]["priority_reasons"]
    source = get_advisory_source_status(
        risk_db,
        cfg={"cve_risk": {"advisory_mode": "local"}},
    )
    assert source["origin"] == "local"
    assert source["record_count"] == 1
    assert risk_db.execute(
        "SELECT match_criteria_id FROM cve_advisory_cpe_matches"
    ).fetchone()["match_criteria_id"] == "00000000-0000-4000-8000-000000000015"

    replacement = parse_nvd_dataset(json.dumps({
        "timestamp": "2026-08-05T00:00:00Z",
        "vulnerabilities": [{"cve": {
            "id": "CVE-2026-99999",
            "vulnStatus": "Analyzed",
            "published": "2026-08-05",
            "lastModified": "2026-08-05",
        }}],
    }).encode())
    accept_local_nvd_dataset(
        risk_db,
        replacement,
        checksum="local-two",
        cfg={"cve_risk": {"advisory_mode": "local"}},
        now=datetime.fromisoformat("2026-08-05T12:00:00+00:00"),
    )
    assert risk_db.execute(
        "SELECT COUNT(*) AS count FROM cve_advisory_cpe_matches"
    ).fetchone()["count"] == 0


def test_local_nvd_changes_create_deduplicated_owner_events_with_source_versions(risk_db):
    _insert_project_finding(risk_db, finding_id="finding-nvd", project_id="project-nvd")
    cfg = {"cve_risk": {
        "advisory_mode": "local",
        "advisory_cvss_downgrade_delta": 1.0,
    }}
    baseline = _nvd_dataset("2026-08-01T00:00:00Z", status="Analyzed", score=9.8)
    accept_local_nvd_dataset(risk_db, baseline, checksum="nvd-v1", cfg=cfg)
    assert risk_db.execute(
        "SELECT COUNT(*) AS count FROM cve_risk_work_items WHERE source = 'nvd'"
    ).fetchone()["count"] == 0

    disputed = _nvd_dataset("2026-08-02T00:00:00Z", status="Disputed", score=8.7)
    accept_local_nvd_dataset(risk_db, disputed, checksum="nvd-v2", cfg=cfg)
    work = risk_db.execute(
        "SELECT transition_kind, old_value, new_value, old_source_version, new_source_version "
        "FROM cve_risk_work_items WHERE source = 'nvd' ORDER BY transition_kind"
    ).fetchall()
    assert [dict(row) for row in work] == [{
        "transition_kind": "nvd_cvss_downgraded",
        "old_value": "9.8",
        "new_value": "8.7",
        "old_source_version": "2026-08-01T00:00:00Z",
        "new_source_version": "2026-08-02T00:00:00Z",
    }, {
        "transition_kind": "nvd_disputed",
        "old_value": "active",
        "new_value": "disputed",
        "old_source_version": "2026-08-01T00:00:00Z",
        "new_source_version": "2026-08-02T00:00:00Z",
    }]
    assert process_risk_work(risk_db)["escalations"] == 2

    active = _nvd_dataset("2026-08-03T00:00:00Z", status="Analyzed", score=8.7)
    rejected = _nvd_dataset("2026-08-04T00:00:00Z", status="Rejected", score=8.7)
    active_again = _nvd_dataset("2026-08-05T00:00:00Z", status="Analyzed", score=8.7)
    withdrawn = _nvd_dataset("2026-08-06T00:00:00Z", status="Withdrawn", score=8.7)
    for index, parsed in enumerate((active, rejected, active_again, withdrawn), start=3):
        accept_local_nvd_dataset(risk_db, parsed, checksum=f"nvd-v{index}", cfg=cfg)
        assert process_risk_work(risk_db)["escalations"] == 1

    transitions = risk_db.execute(
        "SELECT transition_kind FROM risk_escalations ORDER BY created_at, transition_kind"
    ).fetchall()
    assert sorted(row["transition_kind"] for row in transitions) == sorted([
        "nvd_cvss_downgraded",
        "nvd_disputed",
        "nvd_reinstated",
        "nvd_reinstated",
        "nvd_rejected",
        "nvd_withdrawn",
    ])
    event = risk_db.execute(
        "SELECT old_source_version, new_source_version, observation_count "
        "FROM risk_escalations WHERE transition_kind = 'nvd_disputed'"
    ).fetchone()
    assert dict(event) == {
        "old_source_version": "2026-08-01T00:00:00Z",
        "new_source_version": "2026-08-02T00:00:00Z",
        "observation_count": 1,
    }
    assert risk_db.execute(
        "SELECT COUNT(*) AS count FROM risk_escalation_projects WHERE project_id = 'project-nvd'"
    ).fetchone()["count"] == 6
    projected = list_project_risk_escalations(risk_db, "project-nvd")
    disputed_event = next(
        row for row in projected if row["transition_kind"] == "nvd_disputed"
    )
    assert disputed_event["old_source_version"] == "2026-08-01T00:00:00Z"
    assert disputed_event["new_source_version"] == "2026-08-02T00:00:00Z"


def test_explicit_external_nvd_refresh_queues_only_a_later_material_change(risk_db):
    _insert_project_finding(risk_db, finding_id="finding-external", project_id="project-external")
    cfg = {"cve_risk": {
        "advisory_mode": "external",
        "advisory_cvss_downgrade_delta": 1.0,
    }}
    first = {
        "status": "active",
        "published": "2026-08-01T00:00:00Z",
        "last_modified": "2026-08-02T00:00:00Z",
        "score": 9.0,
    }
    persist_external_nvd_lookup(risk_db, "CVE-2026-12345", first, cfg=cfg)
    assert risk_db.execute(
        "SELECT COUNT(*) AS count FROM cve_risk_work_items WHERE source = 'nvd'"
    ).fetchone()["count"] == 0

    later = {**first, "last_modified": "2026-08-03T00:00:00Z", "score": 8.4}
    persist_external_nvd_lookup(risk_db, "CVE-2026-12345", later, cfg=cfg)
    assert risk_db.execute(
        "SELECT COUNT(*) AS count FROM cve_risk_work_items WHERE source = 'nvd'"
    ).fetchone()["count"] == 0

    downgraded = {**first, "last_modified": "2026-08-04T00:00:00Z", "score": 7.2}
    persist_external_nvd_lookup(risk_db, "CVE-2026-12345", downgraded, cfg=cfg)
    work = risk_db.execute(
        "SELECT transition_kind, old_value, new_value FROM cve_risk_work_items WHERE source = 'nvd'"
    ).fetchone()
    assert dict(work) == {
        "transition_kind": "nvd_cvss_downgraded",
        "old_value": "8.4",
        "new_value": "7.2",
    }


def test_failed_local_nvd_reload_preserves_last_known_good_dataset(risk_db, tmp_path):
    valid_payload = json.dumps({
        "timestamp": "2026-08-03T00:00:00Z",
        "vulnerabilities": [{"cve": {
            "id": "CVE-2026-12345",
            "vulnStatus": "Analyzed",
            "published": "2026-08-01",
            "lastModified": "2026-08-03",
            "metrics": {"cvssMetricV31": [{
                "baseSeverity": "HIGH",
                "cvssData": {"version": "3.1", "vectorString": "CVSS:3.1/AV:N", "baseScore": 8.1},
            }]},
        }}],
    }).encode()
    parsed = parse_nvd_dataset(valid_payload)
    valid_checksum = hashlib.sha256(valid_payload).hexdigest()
    accept_local_nvd_dataset(
        risk_db,
        parsed,
        checksum=valid_checksum,
        cfg={"cve_risk": {"advisory_mode": "local"}},
        now=datetime.fromisoformat("2026-08-04T00:00:00+00:00"),
    )
    invalid_path = tmp_path / "nvd.json"
    invalid_path.write_text("not json", encoding="utf-8")

    result = load_configured_local_nvd(
        risk_db,
        cfg={"cve_risk": {
            "advisory_mode": "local",
            "nvd_local_path": str(invalid_path),
        }},
    )

    assert result["outcome"] == "failed"
    source = risk_db.execute(
        "SELECT status, source_version, checksum_sha256, record_count, last_error "
        "FROM cve_advisory_sources WHERE source = 'nvd'"
    ).fetchone()
    assert dict(source) == {
        "status": "failed",
        "source_version": "2026-08-03T00:00:00Z",
        "checksum_sha256": valid_checksum,
        "record_count": 1,
        "last_error": "NvdAdvisoryError",
    }
    record = risk_db.execute(
        "SELECT cvss_score, nvd_origin FROM cve_risk_records WHERE cve_id = 'CVE-2026-12345'"
    ).fetchone()
    assert dict(record) == {"cvss_score": 8.1, "nvd_origin": "local"}

    invalid_path.write_bytes(valid_payload)
    restored = load_configured_local_nvd(
        risk_db,
        cfg={"cve_risk": {
            "advisory_mode": "local",
            "nvd_local_path": str(invalid_path),
        }},
    )
    restored_source = risk_db.execute(
        "SELECT status, accepted_at, checksum_sha256, record_count, last_error "
        "FROM cve_advisory_sources WHERE source = 'nvd'"
    ).fetchone()

    assert restored["outcome"] == "unchanged"
    assert restored_source["status"] == "current"
    assert restored_source["accepted_at"] == "2026-08-04T00:00:00+00:00"
    assert restored_source["checksum_sha256"] == valid_checksum
    assert restored_source["record_count"] == 1
    assert restored_source["last_error"] == ""


def test_feed_crossings_use_hysteresis_deduplicate_and_project_once(risk_db):
    _insert_project_finding(risk_db, finding_id="finding-one", project_id="project-one")
    risk_db.execute(
        "INSERT INTO projects (id, session_id, name, slug, created, updated) "
        "VALUES ('project-two', 'session-one', 'Two', 'two', '2026-08-04', '2026-08-04')"
    )
    risk_db.execute(
        "INSERT INTO project_links (id, project_id, entity_type, entity_id, created) "
        "VALUES ('link-two', 'project-two', 'finding', 'finding-one', '2026-08-04')"
    )
    accept_feed(
        risk_db,
        _epss_feed("v1", "2026-08-01", ("CVE-2026-12345", 0.05, 0.4)),
        origin="bundled",
        payload_sha256="v1",
        enqueue_changes=False,
    )
    accept_feed(
        risk_db,
        _epss_feed("v2", "2026-08-02", ("CVE-2026-12345", 0.12, 0.8)),
        origin="live",
        payload_sha256="v2",
        enqueue_changes=True,
    )
    result = process_risk_work(risk_db)
    assert result["escalations"] == 1
    assert process_risk_work(risk_db)["escalations"] == 0
    event = risk_db.execute("SELECT * FROM risk_escalations").fetchone()
    assert event["transition_kind"] == "epss_activated"
    assert risk_db.execute(
        "SELECT COUNT(*) AS count FROM risk_escalation_projects WHERE escalation_id = ?",
        (event["id"],),
    ).fetchone()["count"] == 2

    accept_feed(
        risk_db,
        _epss_feed("v3", "2026-08-03", ("CVE-2026-12345", 0.085, 0.7)),
        origin="live",
        payload_sha256="v3",
        enqueue_changes=True,
    )
    assert process_risk_work(risk_db)["escalations"] == 0
    accept_feed(
        risk_db,
        _epss_feed("v4", "2026-08-04", ("CVE-2026-12345", 0.07, 0.6)),
        origin="live",
        payload_sha256="v4",
        enqueue_changes=True,
    )
    assert process_risk_work(risk_db)["escalations"] == 1
    assert risk_db.execute(
        "SELECT COUNT(*) AS count FROM risk_escalations WHERE transition_kind = 'epss_reset'"
    ).fetchone()["count"] == 1


def test_changed_cve_work_resumes_by_owner_without_starving_later_groups(risk_db):
    _insert_project_finding(risk_db, finding_id="finding-one", project_id="project-one")
    _insert_project_finding(
        risk_db,
        finding_id="finding-two",
        project_id="project-two",
        session_id="session-two",
        target_id="target-two",
    )
    accept_feed(
        risk_db,
        _epss_feed("v1", "2026-08-01", ("CVE-2026-12345", 0.05, 0.4)),
        origin="bundled",
        payload_sha256="v1",
        enqueue_changes=False,
    )
    accept_feed(
        risk_db,
        _epss_feed("v2", "2026-08-02", ("CVE-2026-12345", 0.12, 0.8)),
        origin="live",
        payload_sha256="v2",
        enqueue_changes=True,
    )
    cfg = {"cve_risk": {"owner_batch_size": 1, "work_batch_size": 1}}
    first = process_risk_work(risk_db, cfg=cfg)
    work = risk_db.execute("SELECT status, cursor_owner_key FROM cve_risk_work_items").fetchone()
    assert first == {"processed": 0, "escalations": 1, "remaining": 1}
    assert work["status"] == "pending"
    assert work["cursor_owner_key"]

    risk_db.execute("UPDATE cve_risk_work_items SET next_attempt_at = ''")
    second = process_risk_work(risk_db, cfg=cfg)
    assert second["processed"] == 1
    assert second["escalations"] == 1
    assert risk_db.execute("SELECT COUNT(*) AS count FROM risk_escalations").fetchone()["count"] == 2


def test_failed_work_item_rolls_back_and_retries_without_payload_logging(risk_db, monkeypatch, caplog):
    _insert_project_finding(risk_db, finding_id="finding-one", project_id="project-one")
    accept_feed(
        risk_db,
        _epss_feed("v1", "2026-08-01", ("CVE-2026-12345", 0.05, 0.4)),
        origin="bundled",
        payload_sha256="v1",
        enqueue_changes=False,
    )
    accept_feed(
        risk_db,
        _epss_feed("v2", "2026-08-02", ("CVE-2026-12345", 0.12, 0.8)),
        origin="live",
        payload_sha256="v2",
        enqueue_changes=True,
    )
    original = escalation._process_group
    monkeypatch.setattr(escalation, "_process_group", lambda *_args, **_kwargs: 1 / 0)
    with caplog.at_level("ERROR"):
        result = process_risk_work(risk_db)
    assert result["processed"] == 0
    row = risk_db.execute(
        "SELECT status, attempts, last_error FROM cve_risk_work_items"
    ).fetchone()
    assert dict(row) == {"status": "failed", "attempts": 1, "last_error": "ZeroDivisionError"}
    assert "CVE-2026-12345" not in caplog.text
    assert risk_db.execute("SELECT COUNT(*) AS count FROM risk_escalations").fetchone()["count"] == 0

    monkeypatch.setattr(escalation, "_process_group", original)
    risk_db.execute("UPDATE cve_risk_work_items SET next_attempt_at = ''")
    assert process_risk_work(risk_db)["escalations"] == 1


def test_archived_team_rejects_risk_acknowledgement(risk_db):
    now = "2026-08-04T00:00:00+00:00"
    risk_db.execute(
        "INSERT INTO teams (id, name, slug, status, created_at, updated_at) "
        "VALUES ('team-one', 'Team', 'team', 'archived', ?, ?)",
        (now, now),
    )
    risk_db.execute(
        "INSERT INTO risk_escalations (id, owner_team_id, remediation_id, cve_id, source, "
        "transition_kind, feed_version, created_at, updated_at) "
        "VALUES ('risk-one', 'team-one', 'rem-one', 'CVE-2026-12345', 'kev', "
        "'kev_added', 'v1', ?, ?)",
        (now, now),
    )
    risk_db.execute(
        "INSERT INTO risk_escalation_projects (escalation_id, project_id) "
        "VALUES ('risk-one', 'project-one')"
    )
    with pytest.raises(ValueError, match="archived teams"):
        acknowledge_escalation(
            risk_db,
            "risk-one",
            session_id="session-one",
            team_id="team-one",
            project_id="project-one",
            ack_state="acknowledged",
        )


def test_report_snapshot_captures_selected_records_and_source_provenance(risk_db):
    risk_db.execute(
        "INSERT INTO findings (id, session_id, title, created) "
        "VALUES ('finding-one', 'session-one', 'CVE-2026-12345', '2026-08-04')"
    )
    risk_db.execute(
        "INSERT INTO finding_cve_links (finding_id, cve_id, created_at) "
        "VALUES ('finding-one', 'CVE-2026-12345', '2026-08-04')"
    )
    accept_feed(
        risk_db,
        _epss_feed("v1", "2026-08-04", ("CVE-2026-12345", 0.2, 0.9)),
        origin="bundled",
        payload_sha256="snapshot-sha",
        enqueue_changes=False,
    )
    snapshot = build_cve_risk_snapshot(
        [{"id": "finding-one", "title": "CVE-2026-12345"}], conn=risk_db
    )
    assert snapshot["schema_version"] == 2
    assert snapshot["cve_ids"] == ["CVE-2026-12345"]
    assert snapshot["records"][0]["epss_probability"] == 0.2
    assert isinstance(snapshot["records"][0]["kev_listed"], bool)
    assert snapshot["sources"][0]["checksum_sha256"] == "snapshot-sha"
    assert "do not endorse" in snapshot["non_endorsement"]


def test_reports_explain_priority_and_attribute_public_risk_sources():
    context = {
        "project": {"name": "Example"},
        "draft": {
            "title": "Example",
            "metadata": {},
            "sections": [{
                "type": "findings_by_severity",
                "title": "Findings",
                "enabled": True,
            }],
        },
        "findings_by_severity": [{
            "severity": "high",
            "count": 1,
            "findings": [{
                "title": "Example CVE",
                "severity": "high",
                "review_state": "needs_review",
                "risk": {
                    "priority_reasons": [
                        "Listed in CISA KEV",
                        "EPSS 18.0% probability",
                    ],
                },
            }],
        }],
        "counts": {},
        "runs": [],
        "targets": [],
        "artifacts": [],
        "artifact_warnings": [],
        "cve_risk_snapshot": {
            "sources": [{
                "source": "epss",
                "attribution": "EPSS data provided by FIRST.",
                "source_version": "v-test",
                "published_at": "2026-08-03",
                "retrieved_at": "2026-08-04",
                "status": "current",
            }],
            "non_endorsement": "FIRST and CISA do not endorse this assessment.",
        },
    }

    markdown = render_report_markdown_from_context(context)
    html = render_report_html_from_context(context)

    for rendered in (markdown, html):
        assert "Listed in CISA KEV" in rendered
        assert "EPSS data provided by FIRST" in rendered
        assert "do not endorse this assessment" in rendered
