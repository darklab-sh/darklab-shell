# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from config_builder import DURATION_BOUNDS, _FORGIVING_INT_DEFAULTS, build_config, ConfigLoadError
from config_inspection import catalog, catalog_errors, inspection_payload, safe_value, schema_fields

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_parity_and_declared_rules():
    assert catalog_errors() == []
    schemas = schema_fields(build_config().config.model_json_schema())
    assert len(catalog()) == len(schemas)


@pytest.mark.parametrize("key,bounds", DURATION_BOUNDS.items())
def test_declared_duration_bounds_match_builder(key, bounds):
    for value in (bounds[0], bounds[1]):
        overlay = {key: value, "browser_session_absolute_hours": 8760}
        if key == "browser_session_absolute_hours":
            overlay[key] = value
        assert build_config([("local", overlay)]).config[key] == value
    for value in (bounds[0] - 1, bounds[1] + 1):
        with pytest.raises(ConfigLoadError):
            build_config([("local", {key: value})])


@pytest.mark.parametrize("key,bounds", _FORGIVING_INT_DEFAULTS.items())
def test_declared_forgiving_minimum_matches_normalization(key, bounds):
    fallback, minimum = bounds
    result = build_config([("local", {key: minimum - 1})])
    assert result.config[key] == minimum
    assert any(warning["key"] == key and warning["reason"] == "below_minimum" for warning in result.warnings)
    result = build_config([("local", {key: "invalid"})])
    assert result.config[key] == fallback


def test_disclosure_is_fail_closed_for_missing_nested_and_unsupported_entries():
    assert safe_value("future_secret", "sensitive")["mode"] == "withheld"
    assert safe_value("ai_model", "sensitive", entries={})["mode"] == "withheld"
    assert safe_value("nested", {"unreviewed": "sensitive"}, entries={
        "nested": {"reviewed": True, "disclosure": "full"}})["mode"] == "withheld"
    assert safe_value("items", [{"secret": "sensitive"}], entries={
        "items": {"reviewed": True, "disclosure": "full"}})["mode"] == "withheld"
    assert safe_value("unknown", ["sensitive"], entries={
        "unknown": {"reviewed": True, "disclosure": "summary", "summary": "hash"}})["mode"] == "withheld"
    assert safe_value("welcome_status_labels", ["https://user:secret@example.test"])["mode"] == "withheld"


def test_summaries_and_defaults_never_disclose_source_material():
    result = build_config([("local YAML", {
        "share_redaction_rules": [{"pattern": "SECRET_RULE", "replacement": "SECRET_REPLACE", "label": "SECRET_LABEL"}],
        "ai_base_url": "https://SECRET_USER:SECRET_PASSWORD@example.test",
        "oidc_allowed_subjects": [],
    })])
    values = result.config.model_dump()
    values["oidc_allowed_subjects"] = ["SECRET_SUBJECT"]
    values["notifications"]["dynamic_secret_identifier"] = "SECRET_DYNAMIC"
    payload = inspection_payload(values, result.provenance)
    serialized = json.dumps(payload)
    for marker in ("SECRET_RULE", "SECRET_REPLACE", "SECRET_LABEL", "SECRET_USER", "SECRET_PASSWORD",
                   "SECRET_SUBJECT", "SECRET_DYNAMIC"):
        assert marker not in serialized
    assert "dynamic_secret_identifier" not in serialized
    rows = {row["key"]: row for row in payload["settings"]}
    assert rows["share_redaction_rules"]["effective"]["value"] == 1
    assert rows["oidc_allowed_subjects"]["effective"]["value"] == 1
    assert rows["ai_base_url"]["effective"]["value"] is True
    assert rows["ai_base_url"]["default"]["value"] is False
    assert rows["ai_api_key"]["effective"]["mode"] == "withheld"


def test_bounded_values_have_explicit_truncation():
    result = safe_value("welcome_status_labels", ["x" * 5000] * 100)
    assert result["truncated"] and len(json.dumps(result["value"])) <= 4096
    assert safe_value("motd", "x" * 5000)["truncated"]
    assert safe_value("share_redaction_rules", ["x"] * 5000)["value"] == 5000


def run_validator(tmp_path, *args):
    environment = {**os.environ, "APP_CONF_DIR": str(tmp_path), "APP_LOCAL_CONF_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, str(ROOT / "scripts/operations/check_instance_config.py"), *args],
                          env=environment, cwd=ROOT, capture_output=True, text=True)


def test_validator_help_and_controlled_errors_under_broken_configuration(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("access_profile: SECRET_BAD_PROFILE\nai_base_url: SECRET_AI_URL\n")
    before = path.read_bytes()
    help_result = run_validator(tmp_path, "--help")
    assert help_result.returncode == 0 and "--local-yaml" in help_result.stdout
    for args in ((), ("--json",)):
        result = run_validator(tmp_path, *args)
        assert result.returncode == 2
        assert "SECRET_" not in result.stdout + result.stderr
        assert result.stderr == ""
        assert "access_profile" in result.stdout
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_validator_candidate_strict_and_json_contract(tmp_path):
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text("app_name: candidate\nfuture_secret: SECRET_NEVER_DISPLAY\n")
    result = run_validator(tmp_path, "--local-yaml", str(candidate), "--json")
    assert result.returncode == 0
    body = json.loads(result.stdout)
    assert body["schema_version"] == 1 and body["valid"] and body["warnings"]
    row = next(row for row in body["settings"] if row["key"] == "app_name")
    assert row["effective"]["value"] == "candidate" and row["source"]["layer"] == "local"
    assert "SECRET_NEVER_DISPLAY" not in result.stdout
    assert run_validator(tmp_path, "--local-yaml", str(candidate), "--strict").returncode == 1
    assert run_validator(tmp_path, "--local-yaml", str(tmp_path / "missing")).returncode == 2


def test_two_real_worker_snapshots_ignore_later_file_and_environment_changes(tmp_path):
    code = '''
import json, os
from pathlib import Path
from config import get_loaded_config_snapshot
before = get_loaded_config_snapshot()
Path(os.environ["APP_LOCAL_CONF_DIR"], "config.local.yaml").write_text("app_name: changed-after-load\\n")
os.environ["APP_NAME"] = "changed-environment"
after = get_loaded_config_snapshot()
assert before == after
print(json.dumps({"pid": after["process_id"], "name": after["values"]["app_name"], "loaded": after["loaded_at"]}))
'''
    processes = []
    for name in ("First worker", "Second worker"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "config.local.yaml").write_text("app_name: " + name + "\n")
        environment = {**os.environ, "APP_CONF_DIR": str(folder), "APP_LOCAL_CONF_DIR": str(folder),
                       "PYTHONPATH": str(ROOT / "app")}
        environment.pop("APP_NAME", None)
        processes.append(subprocess.Popen([sys.executable, "-c", code], env=environment, cwd=ROOT,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    snapshots = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        snapshots.append(json.loads(stdout))
    assert snapshots[0]["pid"] != snapshots[1]["pid"]
    assert [snapshot["name"] for snapshot in snapshots] == ["First worker", "Second worker"]
