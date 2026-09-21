# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json

import pytest

from config_builder import ConfigLoadError, build_config
from config_inspection import catalog_errors, inspection_payload

LEGACY = "diagnostics_allowed_cidrs"
CANONICAL = "metrics_allowed_cidrs"


@pytest.mark.parametrize("shipped,local,expected,source", [
    ({}, {}, [], "built-in defaults"),
    ({CANONICAL: ["192.0.2.0/24"]}, {}, ["192.0.2.0/24"], "shipped YAML"),
    ({CANONICAL: ["192.0.2.0/24"]}, {CANONICAL: []}, [], "local YAML"),
    ({CANONICAL: []}, {CANONICAL: ["::1/128"]}, ["::1/128"], "local YAML"),
    ({LEGACY: ["192.0.2.0/24"]}, {}, [], "built-in defaults"),
    ({CANONICAL: ["192.0.2.0/24"]}, {LEGACY: []}, ["192.0.2.0/24"], "shipped YAML"),
    ({LEGACY: ["192.0.2.0/24"]}, {CANONICAL: []}, [], "local YAML"),
    ({}, {LEGACY: ["192.0.2.0/24"], CANONICAL: []}, [], "local YAML"),
    ({}, {CANONICAL: ["::1/128"], LEGACY: ["192.0.2.0/24"]}, ["::1/128"], "local YAML"),
    ({LEGACY: []}, {LEGACY: ["::1/128"]}, [], "built-in defaults"),
])
def test_removed_metrics_alias_cannot_override_canonical_layers(shipped, local, expected, source):
    result = build_config([("shipped YAML", shipped), ("local YAML", local)])
    assert result.config.metrics_allowed_cidrs == expected
    assert result.provenance[CANONICAL] == source
    assert LEGACY not in result.config and LEGACY not in result.provenance
    assert catalog_errors() == []
    warnings = [w for w in result.warnings if w.get("key") == LEGACY]
    assert warnings == [
        {"key": LEGACY, "source": layer}
        for layer, values in (("shipped YAML", shipped), ("local YAML", local))
        if LEGACY in values
    ]
    for level, event, extra in result.events:
        assert event != "CONFIG_ALIAS_DEPRECATED"
        if event == "CONFIG_UNKNOWN_KEY_IGNORED":
            assert level == "warning"
            assert extra["key"] == LEGACY
            assert "192.0.2" not in json.dumps(extra) and "::1" not in json.dumps(extra)
    rows = {row["key"]: row for row in inspection_payload(
        result.config.model_dump(), result.provenance, result.warnings,
    )["settings"]}
    assert LEGACY not in rows and rows[CANONICAL]["effective"]["value"] == expected
    assert rows[CANONICAL]["warnings"] == []


def test_runtime_overrides_reject_removed_alias_without_mutating_config():
    initial = build_config([("shipped YAML", {CANONICAL: ["192.0.2.0/24"]})]).config
    with pytest.raises(ConfigLoadError, match=LEGACY):
        initial.with_overrides({LEGACY: []})
    with pytest.raises(ConfigLoadError, match=LEGACY):
        initial[LEGACY] = []
    assert initial.metrics_allowed_cidrs == ["192.0.2.0/24"]
    assert LEGACY not in initial and LEGACY not in initial._provenance
    assert initial.with_overrides({CANONICAL: []}).metrics_allowed_cidrs == []
    initial[CANONICAL] = []
    assert initial.metrics_allowed_cidrs == []


@pytest.mark.parametrize("shipped_text,expected,source", [
    ("metrics_allowed_cidrs: [192.0.2.0/24]\n", ["192.0.2.0/24"], "shipped"),
    ("{}\n", [], "default"),
])
def test_standalone_checker_flags_removed_alias_without_changing_metrics(
    tmp_path, shipped_text, expected, source,
):
    from test_config_inspection import run_validator
    shipped = tmp_path / "config.yaml"
    local = tmp_path / "config.local.yaml"
    shipped.write_text(shipped_text)
    local.write_text("diagnostics_allowed_cidrs: []\n")
    result = run_validator(tmp_path, "--json", "--strict")
    assert result.returncode == 1 and result.stderr == ""
    payload = json.loads(result.stdout)
    rows = {row["key"]: row for row in payload["settings"]}
    assert LEGACY not in rows and rows[CANONICAL]["effective"]["value"] == expected
    assert rows[CANONICAL]["source"]["layer"] == source
    assert rows[CANONICAL]["warnings"] == []
    assert payload["warnings"] == [{
        "key": "unknown input key", "event": "CONFIG_INPUT_WARNING", "reason": "input ignored or normalized",
    }]
    assert payload["valid"] is True
    assert sorted(path.name for path in tmp_path.iterdir()) == ["config.local.yaml", "config.yaml"]
