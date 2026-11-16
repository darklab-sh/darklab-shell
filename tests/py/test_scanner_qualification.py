# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Automatic parser promotion requires fresh, complete compatibility evidence."""

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("scanner_qualification", ROOT / "scripts/release/scanner_qualification.py")
assert spec and spec.loader
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "Dockerfile").write_text("ARG SCHEMATHESIS_VERSION=4.33.4\nARG PYTHON_VERSION=3.14.10\n")
    for name, content in {
        qualification.CONTRACT: 'SCHEMATHESIS_REPORT_TOOL_VERSION = "4.33.2"\n',
        qualification.CONSTRAINTS: "schemathesis==4.33.4\njsonschema-rs==0.61.2\n",
        "app/parser.py": "# Unchanged parser rules\n",
        "tests/py/test_fixture.py": "# Qualification tests\n",
    }.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    monkeypatch.setattr(qualification.platform, "python_version", lambda: "3.14.10")
    return root


def passed(*_args):
    return {"tests": {name: 1 for name in qualification.SUITES}, "environments": {"scanner": [], "runner": []}}


def test_promotion_qualifies_proposed_tree_without_git_and_changes_only_pin(candidate, tmp_path, monkeypatch):
    before = {name: (candidate / name).read_bytes() for name in qualification.source_files(candidate)}
    def exercise(snapshot, scratch, output, version):
        assert qualification.versions(snapshot)[:2] == ("4.33.4", "4.33.4")
        assert qualification.versions(candidate)[0] == "4.33.2"
        assert (snapshot / "app/parser.py").read_bytes() == before[Path("app/parser.py")]
        assert not (snapshot / ".git").exists()
        return passed()
    monkeypatch.setattr(qualification, "exercise", exercise)
    output = tmp_path / "evidence"
    receipt = qualification.qualify(candidate, output, promote=True)
    assert qualification.versions(candidate)[0] == "4.33.4"
    assert receipt["previous_version"] == "4.33.2"
    assert json.loads((output / "qualification.json").read_text()) == receipt
    assert qualification.evidence_checks(candidate, receipt)
    for name, content in before.items():
        if str(name) != qualification.CONTRACT:
            assert (candidate / name).read_bytes() == content


@pytest.mark.parametrize("failure", ["test-failure", "source-drift", "snapshot-drift"])
def test_failed_or_changing_input_never_promotes_or_reuses_receipt(candidate, tmp_path, monkeypatch, failure):
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "qualification.json").write_text('{"status":"passed"}')
    def exercise(snapshot, *_args):
        if failure == "test-failure":
            raise qualification.QualificationError("Scanner failed")
        root = candidate if failure == "source-drift" else snapshot
        (root / "app/parser.py").write_text("# Changed during qualification\n")
        return passed()
    monkeypatch.setattr(qualification, "exercise", exercise)
    with pytest.raises(qualification.QualificationError):
        qualification.qualify(candidate, output, promote=True)
    assert qualification.versions(candidate)[0] == "4.33.2"
    assert not (output / "qualification.json").exists()


@pytest.mark.parametrize("version", ["5.0.0", "4.32.0"])
def test_major_and_downgrade_require_manual_review(candidate, tmp_path, monkeypatch, version):
    for name in ("Dockerfile", qualification.CONSTRAINTS):
        path = candidate / name
        path.write_text(path.read_text().replace("4.33.4", version))
    monkeypatch.setattr(qualification, "exercise", lambda *_args: pytest.fail("Must not run an unapproved transition"))
    with pytest.raises(qualification.QualificationError, match="manual parser review"):
        qualification.qualify(candidate, tmp_path / "evidence", promote=True)


def test_ci_requires_matching_pin_and_production_interpreter(candidate, tmp_path, monkeypatch):
    with pytest.raises(qualification.QualificationError, match="versions disagree"):
        qualification.qualify(candidate, tmp_path / "evidence")
    monkeypatch.setattr(qualification.platform, "python_version", lambda: "3.15.2")
    with pytest.raises(qualification.QualificationError, match="production Python"):
        qualification.qualify(candidate, tmp_path / "evidence", promote=True)


@pytest.mark.parametrize("content", ["<testsuites/>", '<testsuites><testcase><skipped/></testcase></testsuites>',
                                    '<testsuites><testcase><failure/></testcase></testsuites>',
                                    '<testsuites><testcase><error/></testcase></testsuites>'])
def test_empty_skipped_and_failed_suites_cannot_qualify(tmp_path, content):
    report = tmp_path / "result.xml"
    report.write_text(content)
    with pytest.raises(qualification.QualificationError, match="without skips"):
        qualification.junit_counts(report)


def test_check_rejects_stale_evidence_after_parser_or_constraints_change(candidate, tmp_path, monkeypatch):
    monkeypatch.setattr(qualification, "exercise", passed)
    receipt = qualification.qualify(candidate, tmp_path / "evidence", promote=True)
    path = candidate / qualification.CONSTRAINTS
    path.write_text(path.read_text().replace("0.61.2", "0.61.3"))
    with pytest.raises(qualification.QualificationError, match="stale"):
        qualification.evidence_checks(candidate, receipt)


def test_source_snapshot_excludes_operator_files_and_rejects_symlinks(candidate, tmp_path):
    original = qualification.fingerprint(candidate)
    local = candidate / "app/conf/config.local.yaml"
    local.parent.mkdir(parents=True)
    local.write_text("private: value\n")
    cache = candidate / 'app/.hypothesis/constants/cache'
    cache.parent.mkdir(parents=True)
    cache.write_text('test-generated cache')
    assert qualification.fingerprint(candidate) == original
    assert local.relative_to(candidate) not in set(qualification.source_files(candidate))
    (candidate / "app/linked.py").symlink_to(tmp_path / "outside.py")
    with pytest.raises(qualification.QualificationError, match="symlinks"):
        list(qualification.source_files(candidate))
