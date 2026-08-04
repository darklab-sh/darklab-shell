# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared CVE risk feeds, ranking, snapshots, and escalation contracts."""

from __future__ import annotations

import hashlib
import json
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
from services.cve_risk.escalation import acknowledge_escalation, process_risk_work
from services.cve_risk.parsers import FeedValidationError, ParsedFeed, parse_epss, parse_kev
from services.cve_risk.ranking import attach_risk_to_findings, cve_risk_order_sql
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


def test_risk_order_sql_rejects_untrusted_identifier_fragments():
    with pytest.raises(ValueError, match="ordering alias"):
        cve_risk_order_sql("f; DROP TABLE findings", age_expression="f.created")
    with pytest.raises(ValueError, match="age expression"):
        cve_risk_order_sql("f", age_expression="f.created DESC; DROP TABLE findings")


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
