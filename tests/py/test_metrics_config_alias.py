# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json

import pytest

from config_builder import build_config
from config_inspection import catalog_errors, inspection_payload

LEGACY = "diagnostics_allowed_cidrs"
CANONICAL = "metrics_allowed_cidrs"


@pytest.mark.parametrize("shipped,local,expected,source", [
    ({}, {}, [], "built-in defaults"),
    ({LEGACY: ["192.0.2.0/24"]}, {}, ["192.0.2.0/24"], "shipped YAML"),
    ({CANONICAL: ["192.0.2.0/24"]}, {LEGACY: []}, [], "local YAML"),
    ({LEGACY: ["192.0.2.0/24"]}, {CANONICAL: []}, [], "local YAML"),
    ({}, {LEGACY: ["192.0.2.0/24"], CANONICAL: []}, [], "local YAML"),
    ({}, {CANONICAL: ["::1/128"], LEGACY: ["192.0.2.0/24"]}, ["::1/128"], "local YAML"),
    ({LEGACY: []}, {LEGACY: ["::1/128"]}, ["::1/128"], "local YAML"),
])
def test_metrics_alias_is_resolved_within_each_layer(shipped, local, expected, source):
    result = build_config([("shipped YAML", shipped), ("local YAML", local)])
    assert result.config.metrics_allowed_cidrs == expected
    assert result.provenance[CANONICAL] == source
    assert LEGACY not in result.config and LEGACY not in result.provenance
    assert catalog_errors() == []
    warnings = [w for w in result.warnings if w.get("event") == "CONFIG_ALIAS_DEPRECATED"]
    assert len(warnings) == int(LEGACY in shipped or LEGACY in local)
    for level, event, extra in result.events:
        if event == "CONFIG_ALIAS_DEPRECATED":
            assert level == "warning"
            assert "192.0.2" not in json.dumps(extra) and "::1" not in json.dumps(extra)
            assert extra["removal_version"] == "3.1.0"
    rows = {row["key"]: row for row in inspection_payload(
        result.config.model_dump(), result.provenance, result.warnings,
    )["settings"]}
    assert LEGACY not in rows and rows[CANONICAL]["effective"]["value"] == expected
    if warnings:
        assert rows[CANONICAL]["warnings"][0]["reason"] == "deprecated_alias"


def test_runtime_overrides_apply_legacy_key_as_a_new_layer():
    initial = build_config([("shipped YAML", {CANONICAL: ["192.0.2.0/24"]})]).config
    assert initial.with_overrides({LEGACY: []}).metrics_allowed_cidrs == []
    assert initial.metrics_allowed_cidrs == ["192.0.2.0/24"]
    initial[LEGACY] = []
    assert initial.metrics_allowed_cidrs == []


def test_standalone_checker_uses_the_runtime_alias_contract(tmp_path):
    from test_config_inspection import run_validator
    shipped = tmp_path / "config.yaml"
    local = tmp_path / "config.local.yaml"
    shipped.write_text("metrics_allowed_cidrs: [192.0.2.0/24]\n")
    local.write_text("diagnostics_allowed_cidrs: []\n")
    result = run_validator(tmp_path, "--json", "--strict")
    assert result.returncode == 1 and result.stderr == ""
    payload = json.loads(result.stdout)
    rows = {row["key"]: row for row in payload["settings"]}
    assert LEGACY not in rows and rows[CANONICAL]["effective"]["value"] == []
    assert rows[CANONICAL]["source"]["layer"] == "local"
    assert rows[CANONICAL]["warnings"] == [{
        "key": CANONICAL, "event": "CONFIG_ALIAS_DEPRECATED", "reason": "deprecated_alias",
    }]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["config.local.yaml", "config.yaml"]
