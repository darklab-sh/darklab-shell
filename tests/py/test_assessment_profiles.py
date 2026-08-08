# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Assessment-profile catalog contract coverage."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path

import pytest
import yaml

import config_paths
from services.assessments import profiles


KNOWN_COMMANDS = frozenset({"curl", "nmap", "ping"})
KNOWN_WORKFLOWS = frozenset({"custom_web_review"})


def _rule(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "key": "completed_scan",
        "version": "1.0",
        "evidence_types": ["run"],
        "command_roots": ["nmap"],
        "workflow_actions": [],
        "structured_output_kinds": ["ports"],
        "target_match": "exact",
        "completion": "succeeded",
        "compatible_versions": ["*"],
        "negative_evidence": True,
    }
    value.update(overrides)
    return value


def _check(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "key": "service_discovery",
        "version": "1.0",
        "category": "discovery",
        "label": "Service discovery",
        "purpose": "Find reachable services.",
        "target_types": ["domain", "ip"],
        "evidence_rules": [_rule()],
        "policy_level": "standard",
        "recommended_action": "command:nmap",
        "completion_guidance": "Run the approved scan and review the saved result.",
    }
    value.update(overrides)
    return value


def _profile(key: str = "network", **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "key": key,
        "version": "1.0",
        "label": key.title(),
        "purpose": "Assess the approved target.",
        "target_types": ["domain", "ip"],
        "checks": [_check()],
    }
    value.update(overrides)
    return value


def _catalog(*catalog_profiles: dict[str, object]) -> dict[str, object]:
    return {"version": 1, "profiles": list(catalog_profiles or (_profile(),))}


def _normalize(data: object) -> profiles.AssessmentProfileCatalog:
    return profiles.normalize_assessment_profile_catalog(
        data,
        known_command_roots=KNOWN_COMMANDS,
        known_workflow_ids=KNOWN_WORKFLOWS,
    )


def _write_yaml(path: Path, data: object) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    profiles.clear_assessment_profile_catalog_cache()
    yield
    profiles.clear_assessment_profile_catalog_cache()


def test_shipped_assessment_profiles_define_versioned_network_and_web_checks():
    catalog = profiles.load_assessment_profile_catalog()

    by_key = {profile["key"]: profile for profile in catalog.profiles}
    assert list(by_key) == ["network", "web"]
    assert {check["key"] for check in by_key["network"]["checks"]} == {
        "host_reachability",
        "service_discovery",
        "dns_inventory",
    }
    assert {check["key"] for check in by_key["web"]["checks"]} == {
        "http_profile",
        "content_discovery",
        "vulnerability_templates",
        "subdomain_takeover_confirmation",
        "parameter_discovery",
        "sql_injection_detection",
    }
    assert by_key["network"]["version"] == "1.0"
    assert by_key["web"]["version"] == "1.2"
    for profile in catalog.profiles:
        for check in profile["checks"]:
            assert check["recommended_action"].startswith("command:")
            assert check["completion_guidance"]
            assert all(rule["version"] == "1.0" for rule in check["evidence_rules"])
    parameter_check = next(
        check for check in by_key["web"]["checks"] if check["key"] == "parameter_discovery"
    )
    assert parameter_check["recommended_action"] == "command:dalfox"
    assert parameter_check["evidence_rules"][0]["command_roots"] == ["dalfox"]
    sqlmap_check = next(
        check for check in by_key["web"]["checks"] if check["key"] == "sql_injection_detection"
    )
    assert sqlmap_check["recommended_action"] == "command:sqlmap"
    assert sqlmap_check["target_types"] == ["url"]
    takeover_check = next(
        check
        for check in by_key["web"]["checks"]
        if check["key"] == "subdomain_takeover_confirmation"
    )
    assert takeover_check == {
        "key": "subdomain_takeover_confirmation",
        "version": "1.0",
        "category": "validation",
        "label": "Subdomain takeover confirmation",
        "purpose": (
            "Check one approved domain for a reviewed dangling-provider fingerprint "
            "without claiming the resource."
        ),
        "target_types": ["domain"],
        "evidence_rules": [{
            "key": "completed_takeover_confirmation",
            "version": "1.0",
            "evidence_types": ["run"],
            "command_roots": ["nuclei"],
            "workflow_actions": [],
            "structured_output_kinds": [],
            "target_match": "exact",
            "completion": "succeeded",
            "compatible_versions": ["*"],
            "negative_evidence": True,
        }],
        "policy_level": "safe",
        "recommended_action": "command:nuclei",
        "completion_guidance": (
            "Run the reviewed provider fingerprint and compare any match with saved DNS "
            "evidence for the exact hostname. The check never claims a resource or "
            "performs a takeover."
        ),
    }


def test_local_catalog_replaces_complete_profiles_and_appends_new_profiles(tmp_path: Path):
    shipped = tmp_path / "assessment_profiles.yaml"
    local = tmp_path / "assessment_profiles.local.yaml"
    _write_yaml(shipped, _catalog(_profile("network"), _profile("web")))
    local_network = _profile("network", version="2.0", label="Operator network")
    local_api = _profile("api", label="Operator API")
    _write_yaml(local, _catalog(local_network, local_api))

    catalog = profiles.load_assessment_profile_catalog(
        shipped_path=shipped,
        local_path=local,
        known_command_roots=KNOWN_COMMANDS,
        known_workflow_ids=KNOWN_WORKFLOWS,
    )

    assert [profile["key"] for profile in catalog.profiles] == ["network", "web", "api"]
    assert catalog.profiles[0]["label"] == "Operator network"
    assert catalog.profiles[0]["version"] == "2.0"
    assert catalog.local_profile_keys == ("network", "api")


def test_catalog_hot_reload_rejects_bad_local_file_without_replacing_last_good(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    shipped = tmp_path / "assessment_profiles.yaml"
    local = tmp_path / "assessment_profiles.local.yaml"
    _write_yaml(shipped, _catalog())
    _write_yaml(local, _catalog(_profile("network", label="First local profile")))
    kwargs = {
        "shipped_path": shipped,
        "local_path": local,
        "known_command_roots": KNOWN_COMMANDS,
        "known_workflow_ids": KNOWN_WORKFLOWS,
    }

    assert profiles.load_assessment_profile_catalog(**kwargs).profiles[0]["label"] == "First local profile"

    local.write_text("version: 1\nprofiles:\n  - key: network\n", encoding="utf-8")
    os.utime(local, ns=(2_000_000_000, 2_000_000_000))
    with caplog.at_level("WARNING"):
        retained = profiles.load_assessment_profile_catalog(**kwargs)

    assert retained.profiles[0]["label"] == "First local profile"
    assert "ASSESSMENT_PROFILE_LOCAL_CATALOG_REJECTED" in caplog.messages

    _write_yaml(local, _catalog(_profile("network", label="Recovered local profile")))
    os.utime(local, ns=(3_000_000_000, 3_000_000_000))
    assert profiles.load_assessment_profile_catalog(**kwargs).profiles[0]["label"] == "Recovered local profile"


def test_invalid_local_catalog_on_first_load_falls_back_atomically_to_shipped(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    shipped = tmp_path / "assessment_profiles.yaml"
    local = tmp_path / "assessment_profiles.local.yaml"
    _write_yaml(shipped, _catalog(_profile("network", label="Shipped network")))
    _write_yaml(local, _catalog(_profile("network", checks=[])))

    with caplog.at_level("WARNING"):
        catalog = profiles.load_assessment_profile_catalog(
            shipped_path=shipped,
            local_path=local,
            known_command_roots=KNOWN_COMMANDS,
            known_workflow_ids=KNOWN_WORKFLOWS,
        )

    assert catalog.profiles[0]["label"] == "Shipped network"
    assert catalog.local_profile_keys == ()
    assert "ASSESSMENT_PROFILE_LOCAL_CATALOG_REJECTED" in caplog.messages


def test_invalid_local_yaml_keeps_the_last_valid_catalog(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    shipped = tmp_path / "assessment_profiles.yaml"
    local = tmp_path / "assessment_profiles.local.yaml"
    _write_yaml(shipped, _catalog(_profile("network", label="Shipped network")))
    local.write_text("version: [\n", encoding="utf-8")

    with caplog.at_level("WARNING"):
        catalog = profiles.load_assessment_profile_catalog(
            shipped_path=shipped,
            local_path=local,
            known_command_roots=KNOWN_COMMANDS,
            known_workflow_ids=KNOWN_WORKFLOWS,
        )

    assert catalog.profiles[0]["label"] == "Shipped network"
    assert "ASSESSMENT_PROFILE_LOCAL_CATALOG_REJECTED" in caplog.messages


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.update({"version": 2}), "version must be 1"),
        (lambda data: data.update({"version": True}), "version must be 1"),
        (lambda data: data["profiles"].append(deepcopy(data["profiles"][0])), "duplicate profile key"),
        (lambda data: data["profiles"][0].update({"target_types": ["cidr"]}), "unsupported value: cidr"),
        (
            lambda data: data["profiles"][0]["checks"].append(
                deepcopy(data["profiles"][0]["checks"][0])
            ),
            "duplicate profile check key",
        ),
        (
            lambda data: data["profiles"][0]["checks"][0].update({"policy_level": "aggressive"}),
            "unsupported policy_level",
        ),
        (
            lambda data: data["profiles"][0]["checks"][0]["evidence_rules"][0].update(
                {"evidence_types": ["transcript"]}
            ),
            "unsupported value: transcript",
        ),
        (
            lambda data: data["profiles"][0]["checks"][0].update(
                {"recommended_action": "command:missing"}
            ),
            "unknown command: missing",
        ),
        (
            lambda data: data["profiles"][0]["checks"][0]["evidence_rules"][0].update(
                {"negative_evidence": "yes"}
            ),
            "must be true or false",
        ),
        (
            lambda data: data["profiles"][0].update(
                {"purpose": "x" * (profiles.ASSESSMENT_PROFILE_PURPOSE_MAX_LEN + 1)}
            ),
            "exceeds 1000 characters",
        ),
        (
            lambda data: data["profiles"][0].update({
                "checks": [
                    _check(key=f"check_{index}")
                    for index in range(profiles.ASSESSMENT_PROFILE_MAX_CHECKS + 1)
                ]
            }),
            "exceeds the check cap",
        ),
    ],
)
def test_catalog_validation_rejects_unsafe_or_ambiguous_contracts(mutate, message: str):
    data = _catalog()
    mutate(data)

    with pytest.raises(profiles.AssessmentProfileCatalogError, match=message):
        _normalize(data)


def test_catalog_accepts_known_workflow_actions_and_returns_defensive_copies(tmp_path: Path):
    check = _check(
        recommended_action="workflow:custom_web_review",
        evidence_rules=[_rule(command_roots=[], workflow_actions=["custom_web_review"])],
    )
    shipped = tmp_path / "assessment_profiles.yaml"
    _write_yaml(shipped, _catalog(_profile(checks=[check])))

    copied = profiles.get_assessment_profile(
        "network",
        shipped_path=shipped,
        known_command_roots=KNOWN_COMMANDS,
        known_workflow_ids=KNOWN_WORKFLOWS,
    )
    assert copied is not None
    copied["label"] = "Changed"
    current = profiles.get_assessment_profile(
        "network",
        shipped_path=shipped,
        known_command_roots=KNOWN_COMMANDS,
        known_workflow_ids=KNOWN_WORKFLOWS,
    )

    assert current is not None
    assert current["label"] == "Network"
    assert current["checks"][0]["recommended_action"] == "workflow:custom_web_review"


def test_assessment_profiles_use_the_shared_external_local_config_root(tmp_path: Path):
    shipped = tmp_path / "shipped"
    local = tmp_path / "local"
    shipped.mkdir()
    local.mkdir()

    paths = config_paths.config_asset_paths(
        "assessment_profiles.yaml",
        shipped_conf_dir=shipped,
        local_conf_dir=local,
    )

    assert paths.shipped == shipped / "assessment_profiles.yaml"
    assert paths.local == local / "assessment_profiles.local.yaml"
    assert Path("assessment_profiles.yaml") in config_paths.supported_overlay_assets(
        shipped_conf_dir=shipped
    )
