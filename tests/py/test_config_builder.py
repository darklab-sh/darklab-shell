# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Independent characterization of the configuration loader before extraction."""

from unittest.mock import patch

import pytest
import yaml

import config


CASES = [
    ({}, {}, {}, {"access_profile": "open", "output_preview_max_bytes": 1048576}, []),
    ({"app_name": "shipped", "scheduler": {"tick_seconds": 9}},
     {"app_name": "local", "scheduler": {"tick_seconds": 12}}, {},
     {"app_name": "local", "scheduler.tick_seconds": 12}, []),
    ({"workspace_enabled": False}, {"workspace_enabled": False},
     {"WORKSPACE_ENABLED": "yes"}, {"workspace_enabled": True}, []),
    ({"workspace_enabled": True}, {}, {"WORKSPACE_ENABLED": "  "},
     {"workspace_enabled": True}, []),
    ({"database_pool_min": -1, "ai_enabled": "nonsense", "audit_export_max_rows": 200001}, {}, {},
     {"database_pool_min": 0, "ai_enabled": False, "audit_export_max_rows": 200000},
     [("database_pool_min", "below_minimum"), ("ai_enabled", "invalid_bool"),
      ("audit_export_max_rows", "above_maximum")]),
    ({"output_preview_max_mb": "2MB", "full_output_max_bytes": 7340032}, {}, {},
     {"output_preview_max_bytes": 2097152, "full_output_max_mb": 7, "full_output_max_bytes": 7340032}, []),
    ({"future_secret": "never-diagnose-this"}, {}, {}, {}, [("future_secret", "")]),
    ({"database_pool_min": 7, "database_pool_max": 2}, {}, {},
     {"database_pool_max": 7}, [("database_pool_max", "below_database_pool_min")]),
]


def value_at(mapping, path):
    for part in path.split("."):
        mapping = mapping[part]
    return mapping


@pytest.mark.parametrize("shipped,local,env,expected,warnings", CASES)
def test_loader_characterization(tmp_path, shipped, local, env, expected, warnings):
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(shipped))
    (tmp_path / "config.local.yaml").write_text(yaml.safe_dump(local))
    with patch.dict("os.environ", env, clear=True):
        loaded = config.load_config(tmp_path)
    for key, value in expected.items():
        assert value_at(loaded.model_dump(), key) == value
    assert sorted((item["key"], item.get("reason", "")) for item in config.CONFIG_LOAD_WARNINGS) == sorted(warnings)
    assert "future_secret" not in loaded
    assert loaded._provenance["access_profile"] == "built-in defaults"
    for layer, values in (("config.yaml", shipped), ("config.local.yaml", local)):
        for key, value in values.items():
            if key not in loaded or key in {"full_output_max_bytes"}:
                continue
            if layer == "config.yaml" and key in local:
                continue
            source = str(tmp_path / layer)
            if key.upper() in env and env[key.upper()].strip():
                source = key.upper()
            assert loaded._provenance[key] == ("built-in defaults" if isinstance(value, dict) else source)
            if isinstance(value, dict):
                for child in value:
                    assert loaded._provenance[f"{key}.{child}"] == source
    assert loaded._provenance["output_preview_max_bytes"] == loaded._provenance["output_preview_max_mb"]
    for key in env:
        if env[key].strip():
            assert key in config.get_config_load_summary()["env_keys"]


@pytest.mark.parametrize("overlay,message", [
    ({"access_profile": "invalid"}, "access_profile must be"),
    ({"browser_session_idle_minutes": 120, "browser_session_absolute_hours": 1}, "cannot be longer"),
    ({"browser_session_idle_minutes": 0}, "must be an integer"),
    ({"access_profile": "oidc_required"}, "OIDC provider configuration is required"),
    ({"assessment_batches": {"item_limit": 0}}, "Invalid app config"),
])
def test_loader_invalid_characterization(tmp_path, overlay, message):
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(overlay))
    with patch.dict("os.environ", {}, clear=True), pytest.raises(config.ConfigLoadError, match=message):
        config.load_config(tmp_path)
