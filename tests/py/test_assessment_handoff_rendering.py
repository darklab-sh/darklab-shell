# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Assessment finding-change handoff rendering coverage."""

from __future__ import annotations

import json

from services.projects.package_rendering import (
    _package_findings_json_bytes,
    _render_package_index_html,
    _render_package_readme,
)
from services.reports.export import _report_manifest_provenance
from services.reports.rendering import (
    render_report_html_from_context,
    render_report_markdown_from_context,
)


def _finding_changes() -> dict:
    return {
        "assessment": {
            "id": "asmt_current",
            "title": "External assessment",
            "profile_key": "external",
            "profile_version": "1.0",
            "status": "completed",
            "started_at": "2026-08-04T00:00:00+00:00",
            "completed_at": "2026-08-05T00:00:00+00:00",
            "updated_at": "2026-08-05T00:00:00+00:00",
        },
        "comparison": {
            "status": "partial",
            "total_checks": 2,
            "comparable_checks": 1,
            "no_baseline_checks": 0,
            "incomparable_checks": 1,
        },
        "rollup": {
            "regressed": 1,
            "new": 0,
            "persistent": 0,
            "not_observed": 0,
            "incomparable": 1,
            "total": 2,
        },
        "items": [{
            "remediation_id": "rmd_example",
            "identity_kind": "vulnerability",
            "vulnerability_id": "CVE-2026-10004",
            "rule_identity": "template:nuclei",
            "affected_subject": "entity:ent_example",
            "state": "incomparable",
            "reasons": ["The prior check used an incompatible profile version."],
            "checks": [],
            "current_observations": [],
            "previous_observations": [],
            "current_evidence_ids": ["run_current"],
            "previous_evidence_ids": ["run_previous"],
            "previous_assessment_ids": ["asmt_previous"],
            "current_findings": [{
                "id": "finding_current",
                "title": "Current CVE evidence",
                "severity": "high",
                "origin": "run",
                "validation_method": "active_confirmation",
                "verification_status": "needs_retest",
            }],
            "previous_findings": [{
                "id": "finding_previous",
                "title": "Earlier CVE evidence",
                "severity": "high",
                "origin": "run",
                "validation_method": "active_confirmation",
                "verification_status": "verified",
            }],
        }],
        "item_limit": 100,
        "truncated": False,
    }


def _assessment_context() -> dict:
    return {
        "schema_version": 1,
        "selection": {
            "mode": "selected",
            "selected_assessment_id": "asmt_current",
        },
        "assessment": _finding_changes()["assessment"],
        "scope": {
            "target_count": 1,
            "check_count": 2,
            "targets": [{"type": "url", "value": "https://example.test"}],
        },
        "rollup": {
            "applicable_checks": 2,
            "covered_checks": 1,
            "checks_awaiting_review": 0,
            "untested_checks": 0,
            "excluded_checks": 1,
            "unavailable_evidence_checks": 1,
        },
        "checks": [{"id": "check_covered"}, {"id": "check_skipped"}],
        "evidence": [{
            "id": "evidence_current",
            "check_id": "check_covered",
            "evidence_type": "run",
            "evidence_id": "run_current",
            "source_run": {
                "tool": "nuclei",
                "tool_versions": ["3.4.8"],
                "started_at": "2026-08-05T00:00:00+00:00",
            },
        }],
        "manual_exclusions": [{
            "check_id": "check_skipped",
            "target_value": "https://example.test",
            "state": "skipped",
            "reason": "Customer excluded this path.",
        }],
        "unavailable_evidence_warnings": [{
            "check_id": "check_covered",
            "reason": "The source run was removed.",
        }],
        "screenshot_warnings": [{
            "artifact_id": "artifact_capture",
            "reason": "Screenshot metadata is included, but its file wasn't selected for this export.",
        }],
        "methodology": {
            "summary": "The frozen profile was applied to two applicable checks.",
            "applicable_denominator": 2,
        },
        "fix_first": {
            "items": [{
                "title": "Patch the exposed service",
                "remediation_id": "rmd_example",
                "observation_count": 1,
                "evidence_count": 2,
                "risk": {"priority_reasons": ["Known exploited vulnerability"]},
            }],
        },
        "finding_changes": _finding_changes(),
        "redaction_boundaries": {
            "excluded": ["secret values and connector credential references"],
            "screenshot_files_require_selection": True,
        },
    }


def _package_manifest() -> dict:
    return {
        "project": {"id": "prj_example", "name": "Example"},
        "counts": {"runs": 1, "findings": 1, "artifacts": 0, "targets": 0},
        "targets": [],
        "runs": [{
            "id": "run_current",
            "command": "nuclei -u example.test",
            "started": "2026-08-05T00:00:00+00:00",
        }],
        "findings": [{
            "id": "finding_current",
            "title": "Current CVE evidence",
            "run_id": "run_current",
            "severity": "high",
            "review_state": "needs_followup",
            "raw_line": "CVE-2026-10004 matched",
        }],
        "artifacts": [],
        "assessment_context": _assessment_context(),
        "assessment_finding_changes": _finding_changes(),
    }


def test_evidence_package_carries_current_and_earlier_assessment_references():
    manifest = _package_manifest()
    run_pages = {"run_current": "runs/run_current.html"}
    html = _render_package_index_html(
        {"name": "Assessment handoff"},
        manifest,
        "2026-08-05T01:00:00+00:00",
        run_pages,
        {},
        {},
        [],
    )
    readme = _render_package_readme(
        {"name": "Assessment handoff"},
        manifest,
        "2026-08-05T01:00:00+00:00",
        run_pages,
        {},
        {},
        [],
    )
    findings_json = json.loads(
        _package_findings_json_bytes(manifest, "2026-08-05T01:00:00+00:00", run_pages)
    )

    for rendered in (html, readme):
        assert "Assessment Coverage" in rendered
        assert "Customer excluded this path" in rendered
        assert "source run was removed" in rendered
        assert "Screenshot metadata is included" in rendered
        assert "Fix first" in rendered
        assert "Patch the exposed service" in rendered
        assert "Assessment Finding Changes" in rendered
        assert "Current CVE evidence" in rendered
        assert "Earlier CVE evidence" in rendered
        assert "run_current" in rendered
        assert "run_previous" in rendered
        assert "incompatible profile version" in rendered
    assert "1 of 2 applicable checks covered" in html
    assert "Applicable denominator: 2" in readme
    assert findings_json["assessment_finding_changes"]["items"][0]["remediation_id"] == "rmd_example"
    assert findings_json["assessment_context"]["checks"][0]["id"] == "check_covered"
    assert findings_json["assessment_context"]["evidence"][0]["source_run"]["tool_versions"] == [
        "3.4.8"
    ]


def test_report_renders_and_records_assessment_finding_change_provenance():
    context = {
        "project": {"id": "prj_example", "name": "Example"},
        "draft": {
            "title": "Example",
            "metadata": {},
            "sections": [
                {
                    "type": "methodology",
                    "title": "Methodology",
                    "enabled": True,
                },
                {
                    "type": "findings_by_severity",
                    "title": "Findings",
                    "enabled": True,
                },
            ],
            "export": {},
        },
        "counts": {"findings": 1},
        "findings_by_severity": [],
        "assessment_context": _assessment_context(),
        "assessment_finding_changes": _finding_changes(),
    }
    markdown = render_report_markdown_from_context(context)
    html = render_report_html_from_context(context)
    provenance = _report_manifest_provenance(
        context["draft"],
        {"redaction_mode": "raw"},
        project=context["project"],
        context=context,
    )

    for rendered in (markdown, html):
        assert "Assessment coverage" in rendered
        assert "frozen profile was applied" in rendered
        assert "Customer excluded this path" in rendered
        assert "source run was removed" in rendered
        assert "Fix first" in rendered
        assert "Patch the exposed service" in rendered
        assert "Assessment finding changes" in rendered
        assert "Current CVE evidence" in rendered
        assert "Earlier CVE evidence" in rendered
        assert "run_previous" in rendered
        assert "incompatible profile version" in rendered
    assert provenance["sources"]["assessment_finding_changes"]["assessment"]["id"] == "asmt_current"
    assert provenance["sources"]["assessment_context"]["assessment"]["id"] == "asmt_current"
