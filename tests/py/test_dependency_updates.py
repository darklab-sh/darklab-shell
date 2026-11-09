# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Dependency preparation keeps mechanical outputs separate from review decisions."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts/release' / f'{name}.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


updates = load_script('dependency_update')
audits = load_script('audit_scanner_environments')


@pytest.fixture
def checkout(tmp_path):
    for name in ('Dockerfile', 'deploy/schemathesis-constraints.txt', 'deploy/sslyze-constraints.txt',
                 'app/services/assessments/schemathesis_report_contracts.py'):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def test_project_contract_accepts_routine_bumps_and_rejects_security_downgrades(checkout):
    target = checkout / 'Dockerfile'
    content = target.read_text()
    pin = updates.defaults(checkout)['GO_X_CRYPTO_VERSION']
    target.write_text(content.replace(f'ARG GO_X_CRYPTO_VERSION={pin}', 'ARG GO_X_CRYPTO_VERSION=v0.99.0'))
    assert updates.inspect_update(checkout, [])['reviewRequired'] == []
    target.write_text(content.replace(f'ARG GO_X_CRYPTO_VERSION={pin}', 'ARG GO_X_CRYPTO_VERSION=v0.51.0'))
    with pytest.raises(ValueError, match='security minimum'):
        updates.inspect_update(checkout, [])


def test_scanner_update_requires_independent_parser_review(checkout):
    version = updates.defaults(checkout)['SCHEMATHESIS_VERSION']
    target = checkout / 'Dockerfile'
    target.write_text(target.read_text().replace(f'ARG SCHEMATHESIS_VERSION={version}', 'ARG SCHEMATHESIS_VERSION=4.99.0'))
    with pytest.raises(ValueError, match='disagree'):
        updates.inspect_update(checkout, [])
    constraints = checkout / 'deploy/schemathesis-constraints.txt'
    constraints.write_text(constraints.read_text().replace(f'schemathesis=={version}', 'schemathesis==4.99.0'))
    report = updates.inspect_update(checkout, [])
    assert any('independent parser pin' in reason for reason in report['reviewRequired'])
    assert updates.reviewed_scanner(checkout) == version


def test_changelog_generation_is_idempotent_and_preserves_published_history(tmp_path):
    target = tmp_path / 'CHANGELOG.md'
    history = '## [1.0.0] - 2026-01-01\n\n### Changed\n\n- Published history.\n'
    target.write_text('# Changelog\n\n## [1.0.1] - Unreleased\n\n### Changed\n\n- Existing entry.\n\n' + history)
    context = [{'package': 'pydantic', 'current': '>=2.14,<3', 'proposed': '>=2.15,<3'}]
    updates.update_changelog(tmp_path, context)
    once = target.read_bytes()
    updates.update_changelog(tmp_path, context)
    assert target.read_bytes() == once
    assert target.read_text().endswith(history)
    assert '`>=2.15,<3`' in target.read_text()
    with pytest.raises(ValueError, match='Unsafe'):
        updates.update_changelog(tmp_path, [{'package': 'bad\nname', 'current': '1', 'proposed': '2'}])


def test_patch_license_and_major_updates_are_review_boundaries(checkout):
    report = updates.inspect_update(checkout, [{'package': package, 'type': 'major'}
                                             for package in ('sslyze', 'wpscan', 'jspdf')])
    reasons = ' '.join(report['reviewRequired'])
    assert all(text in reasons for text in ('source patch', 'WPScan terms', 'browser-package notices', 'major-version'))


def test_audit_reads_installed_versions_without_network_or_host_mounts():
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(stdout='Schemathesis==4.33.1\nclick==8.5.1\n')

    assert audits.installed_requirements('fixture:sha', 'schemathesis', run) == 'Schemathesis==4.33.1\nclick==8.5.1\n'
    argv = calls[0][0]
    assert argv[argv.index('--network') + 1] == 'none'
    assert '--read-only' in argv
    assert '--volume' not in argv and '-v' not in argv
    assert '/opt/schemathesis/bin/python' in argv
    with pytest.raises(ValueError, match='Invalid installed'):
        audits.installed_requirements('fixture:sha', 'sslyze', lambda *a, **k: SimpleNamespace(stdout='--index-url=evil\n'))
    with pytest.raises(ValueError, match='Invalid scanner'):
        audits.installed_requirements('fixture:sha', '../other', run)


def test_both_scanner_audits_run_and_abnormal_exit_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(audits.sys, 'argv', ['audit', 'fixture:sha', '--output', str(tmp_path)])
    monkeypatch.setattr(audits, 'installed_requirements', lambda image, scanner: 'fixture==1.0.0\n')
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=-9 if len(calls) == 1 else 0)

    monkeypatch.setattr(audits.subprocess, 'run', run)
    assert audits.main() == 1
    assert len(calls) == 2
    assert all('--no-deps' in argv and '--disable-pip' in argv for argv in calls)
    assert (tmp_path / 'sslyze.txt').read_text() == 'fixture==1.0.0\n'
    assert (tmp_path / 'schemathesis.txt').read_text() == 'fixture==1.0.0\n'


@pytest.mark.parametrize(('state', 'code', 'expected'), [('created', '0', 1), ('exited', '0', 0), ('exited', '7', 7)])
def test_qualification_requires_a_finished_container_and_preserves_failure(tmp_path, state, code, expected):
    script = tmp_path / 'scripts/release/run_dependency_qualification.sh'
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'scripts/release/run_dependency_qualification.sh', script)
    (tmp_path / 'Dockerfile').write_text('ARG PYTHON_BASE_IMAGE=python:3.14.10-slim\n')
    binary = tmp_path / 'bin'
    binary.mkdir()
    (binary / 'git').write_text('#!/bin/sh\nexit 0\n')
    (binary / 'docker').write_text('''#!/bin/sh
case "$1" in
  create) echo fixture-container ;;
  inspect)
    case "$3" in
      *Status*) echo "$FIXTURE_STATE" ;;
      *ExitCode*) echo "$FIXTURE_CODE" ;;
    esac ;;
  rm) touch "$FIXTURE_CLEANUP" ;;
esac
''')
    for path in binary.iterdir():
        path.chmod(0o755)
    cleanup = tmp_path / 'cleanup'
    result = subprocess.run(['sh', str(script)], check=False, capture_output=True, text=True,
                            env={**os.environ, 'PATH': f'{binary}{os.pathsep}{os.environ["PATH"]}',
                                 'FIXTURE_STATE': state, 'FIXTURE_CODE': code, 'FIXTURE_CLEANUP': str(cleanup)})
    assert result.returncode == expected, result.stderr
    assert cleanup.exists()
