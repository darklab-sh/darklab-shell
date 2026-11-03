# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Regression checks for container compatibility and security controls."""

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


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
