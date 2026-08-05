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
from services.cve_risk import bootstrap, refresh
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
from services.cve_risk.parsers import FeedValidationError, ParsedFeed, parse_epss, parse_kev
from services.cve_risk.ranking import (
    attach_risk_to_findings,
    build_remediation_worklist,
    cve_risk_order_sql,
)
from services.cve_risk.snapshot import build_cve_risk_snapshot
from services.cve_risk.store import accept_feed, get_feed_status
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
    with pytest.raises(ValidationError, match="advisory_cvss_downgrade_delta"):
        CveRiskConfig(advisory_cvss_downgrade_delta=0)


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
    assert shared["priority_context"] == {
        "confidence": ["high", "medium"],
        "exposure": ["internet"],
        "assets": [{"criticality": "high", "environment": "production"}],
    }
    assert shared["risk"]["kev"]["listed"] is True


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
    assert rule_observations[0]["observation_id"] == confirmed_reference["observation_id"]
    assert rule_observations[0]["remediation_id"] == confirmed_reference["remediation_id"]

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


def test_primary_remediation_reference_tracks_highest_priority_cve(risk_db):
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


def test_nvd_dataset_normalizes_cvss_cwe_and_disputed_status():
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
            },
            cfg=cfg,
            now=datetime.fromisoformat("2026-08-04T12:00:00+00:00"),
        )
        negative = persist_external_nvd_lookup(
            risk_db,
            "CVE-2026-99999",
            {"status": "unknown", "score": None, "cwes": [], "references": []},
            cfg=cfg,
            now=datetime.fromisoformat("2026-08-04T12:00:00+00:00"),
        )

    assert result == {"source": "nvd", "outcome": "stored", "record_count": 1}
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
    cache_rows = risk_db.execute(
        "SELECT result_state, record_count FROM cve_advisory_lookup_cache ORDER BY result_state"
    ).fetchall()
    assert [dict(item) for item in cache_rows] == [
        {"result_state": "negative", "record_count": 0},
        {"result_state": "positive", "record_count": 1},
    ]
    assert "CVE-2026-12345" not in caplog.text
    assert "CVE-2026-99999" not in caplog.text


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
