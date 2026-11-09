# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Regression checks for container compatibility and security controls."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

from container_version_helpers import dockerfile_defaults, pinned_version, resolve_version_text
from services.assessments.schemathesis_report_contracts import SCHEMATHESIS_REPORT_TOOL_VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_schemathesis_parser_and_smoke_expectations_match_packaged_version():
    dockerfile = (ROOT / "Dockerfile").read_text()
    defaults = dockerfile_defaults(dockerfile)
    version = pinned_version(defaults, "SCHEMATHESIS_VERSION")
    constraints = (ROOT / "deploy/schemathesis-constraints.txt").read_text().splitlines()
    assert f"schemathesis=={version}" in constraints
    assert SCHEMATHESIS_REPORT_TOOL_VERSION == version, "Schemathesis runtime requires report-format review"
    smoke = json.loads((ROOT / "tests/py/fixtures/container_smoke_test-expectations.json").read_text())
    records = [record for record in smoke["records"] if record["command"] == "schemathesis --version"]
    assert len(records) == 1
    assert records[0]["exit_code"] == 0
    assert records[0]["expected_text"] == ["schemathesis, version ${SCHEMATHESIS_VERSION}"]
    assert resolve_version_text(records[0]["expected_text"][0], defaults) == f"schemathesis, version {version}"


def test_schemathesis_upgrade_still_requires_parser_review(tmp_path, monkeypatch):
    (tmp_path / "Dockerfile").write_text("ARG SCHEMATHESIS_VERSION=4.99.0\n")
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy/schemathesis-constraints.txt").write_text("schemathesis==4.99.0\n")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    with pytest.raises(AssertionError, match="requires report-format review"):
        test_schemathesis_parser_and_smoke_expectations_match_packaged_version()


def load_helper(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/container" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load container helper: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shodan_patch_preserves_plugin_discovery_and_version(monkeypatch):
    helper = load_helper("patch_shodan")
    source = '''import pkg_resources
from pkg_resources import iter_entry_points
plugins = iter_entry_points('shodan.cli.plugins')
version = pkg_resources.get_distribution("shodan").version
'''
    from importlib import metadata

    calls = []
    plugin = SimpleNamespace(load=lambda: "loaded")
    monkeypatch.setattr(metadata, "entry_points", lambda **kw: calls.append(kw) or [plugin])
    monkeypatch.setattr(metadata, "version", lambda name: "1.31.0" if name == "shodan" else None)
    namespace = {}
    exec(helper.patch_source(source), namespace)
    assert calls == [{"group": "shodan.cli.plugins"}]
    assert namespace["plugins"][0].load() == "loaded"
    assert namespace["version"] == "1.31.0"
    with pytest.raises(ValueError, match="no longer matches"):
        helper.patch_source(source.replace("import pkg_resources\n", ""))


def test_system_trust_rejects_compromised_or_empty_store(monkeypatch):
    helper = load_helper("verify_system_trust")
    monkeypatch.setattr(helper, "COMPROMISED_ROOT_SHA256", hashlib.sha256(b"blocked").hexdigest())
    helper.verify_roots([b"safe"])
    with pytest.raises(ValueError, match="compromised"):
        helper.verify_roots([b"safe", b"blocked"])
    with pytest.raises(ValueError, match="empty"):
        helper.verify_roots([])


def test_system_trust_requires_debian_bundle_delegation(tmp_path, monkeypatch):
    helper = load_helper("verify_system_trust")
    bundle = tmp_path / "ca-certificates.crt"
    bundle.write_text("system certificates")
    monkeypatch.setattr(helper, "SYSTEM_BUNDLE", bundle)
    monkeypatch.setitem(sys.modules, "certifi", SimpleNamespace(where=lambda: "/different/bundle"))
    with pytest.raises(ValueError, match="no longer delegates"):
        helper.main()


@pytest.mark.parametrize(("scanner_status", "trust_status"), [(0, 0), (2, 0), (0, 1)])
def test_scan_sbom_preserves_gate_and_status_without_host_mounts(tmp_path, monkeypatch, scanner_status, trust_status):
    policy = yaml.safe_load((ROOT / "deploy/grype.yaml").read_text())
    assert len(policy["ignore"]) == 1
    rule = policy["ignore"][0]
    assert rule["vulnerability"] == "GHSA-6q48-6c7w-9gw2"
    assert rule["namespace"] == "github:language:python"
    assert rule["package"] == {
        "name": "certifi", "version": "2025.1.31", "type": "python",
        "location": "/usr/lib/python3/dist-packages/certifi-2025.1.31.egg-info/*",
    }
    log = tmp_path / "calls"
    docker = tmp_path / "docker"
    docker.write_text(f'''#!/bin/sh
if [ "$1" = run ]; then
  echo run-trust-check >> '{log}'
else
  printf '%s\\n' "$*" >> '{log}'
fi
case "$1" in
  run) exit {trust_status} ;;
  create) echo test-container ;;
  start) cat ;;
  inspect) echo {scanner_status} ;;
esac
''')
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + ":/usr/bin:/bin")
    result = subprocess.run(
        ["sh", str(ROOT / "scripts/release/scan_sbom.sh"), "grype:test", "target:image"],
        input='{"bomFormat":"CycloneDX"}', capture_output=True, text=True, check=False,
    )
    if trust_status:
        assert result.returncode == trust_status
        assert result.stdout == ""
        assert log.read_text().splitlines() == ["run-trust-check"]
        return
    assert result.returncode == scanner_status
    assert result.stdout == '{"bomFormat":"CycloneDX"}'
    calls = log.read_text().splitlines()
    assert calls[0] == "run-trust-check"
    assert calls[1] == "create --interactive grype:test --config /grype.yaml --only-fixed --fail-on critical -o json"
    assert calls[2] == f"cp {ROOT}/deploy/grype.yaml test-container:/grype.yaml"
    assert calls[-1] == "rm --force test-container"
