# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Contracts for reusable Project-scoped probe planning services."""

from __future__ import annotations

from copy import deepcopy
import json
import uuid

import pytest

from core.database import db_connect, db_init
from services.assessments.action_plan_payload import digest_plan
from services.assessments.action_plans import build_assessment_action_plan
from services.assessments.base_action_catalog import ACTIONS, base_action_ids
from services.assessments.command_plans import command_plan
from services.assessments.probe_catalog import probe_catalog
from services.assessments.probe_contracts import (
    PROBE_LAUNCH_CAPABILITIES,
    PROBE_PROTECTED_CAPABILITIES,
    PROBE_VIEW_CAPABILITIES,
    ProbeError,
    ProbePlanRequest,
)
from services.assessments.probe_plan_digest import probe_plan_digest
from services.assessments.probe_plans import build_probe_plan, confirm_probe_plan
from services.assessments.probe_targets import resolve_probe_target
from services.nuclei.template_cache import NucleiTemplateCacheSnapshot
from services.projects.crud import create_project, delete_project, update_project
from services.projects.targets import add_project_target


_READY_TEMPLATES = NucleiTemplateCacheSnapshot(
    "ready", "v10.4.3", "sha256:" + "a" * 64, 12,
)
_ACTION_IDS = (
    "curl", "ping", "dnsrecon", "gau", "httpx", "katana", "dalfox",
    "sqlmap", "sslyze", "testssl", "nmap", "nuclei",
)


@pytest.fixture(scope="module", autouse=True)
def _initialize_probe_schema():
    db_init()


@pytest.fixture
def probe_project():
    session_id = "probe-services-" + uuid.uuid4().hex
    project = create_project(session_id, {"name": "Probe services"})
    assert project is not None
    project_id = str(project["id"])
    try:
        yield session_id, project_id
    finally:
        delete_project(session_id, project_id)


def _target(entity_id: str = "ent_probe", target_type: str = "domain") -> dict[str, str]:
    value = "example.test" if target_type != "url" else "https://example.test/path"
    return {"entity_id": entity_id, "type": target_type, "value": value}


def _request(action_id: str, *, target_type: str = "domain", **kwargs) -> ProbePlanRequest:
    del target_type
    return ProbePlanRequest(project_id="prj_probe", action_id=action_id, **kwargs)


def test_base_action_registry_is_complete_and_drives_command_target_compatibility():
    assert base_action_ids() == _ACTION_IDS
    assert tuple(ACTIONS) == _ACTION_IDS
    for action in ACTIONS.values():
        for target_type in action.target_types:
            target_value = (
                "https://example.test/a" if target_type == "url"
                else "192.0.2.10" if target_type == "ip"
                else "example.test"
            )
            plan = command_plan(
                action.action_id,
                target_type,
                target_value,
                allow_intrusive=True,
            )
            assert plan is not None, (action.action_id, target_type)
        assert command_plan(action.action_id, "port", "443") is None


def test_probe_catalog_pins_public_schema_and_excludes_cycle_only_actions():
    catalog = probe_catalog(
        service="microsoft-ds",
        target_type="ip",
        template_snapshot=_READY_TEMPLATES,
    )
    assert set(catalog) == {
        "schema_version", "actions", "nmap_profiles", "nuclei_profiles",
        "service_recommendations", "exclusions",
    }
    assert [item["id"] for item in catalog["actions"]] == list(_ACTION_IDS)
    assert set(catalog["actions"][0]) == {
        "id", "revision", "label", "purpose", "mode", "policy_level",
        "target_types", "required_features", "expected_evidence", "exclusions",
        "compatible_profiles", "availability",
    }
    nmap_action = next(item for item in catalog["actions"] if item["id"] == "nmap")
    assert "ssh" in nmap_action["compatible_profiles"]["nmap"]
    nuclei_action = next(item for item in catalog["actions"] if item["id"] == "nuclei")
    assert nuclei_action["availability"] == {"available": True, "code": "", "reason": ""}
    assert catalog["service_recommendations"][0]["action_id"] == "nmap"
    assert catalog["service_recommendations"][0]["nmap_profile"] == "smb"
    assert catalog["nuclei_profiles"][0]["provenance"] == "managed_local_cache"
    assert catalog["nuclei_profiles"][0]["template_snapshot"]["state"] == "ready"
    assert "version_cve_correlation" in catalog["exclusions"]
    assert not probe_catalog(
        service="version-cve",
        target_type="url",
        template_snapshot=_READY_TEMPLATES,
    )["service_recommendations"]
    assert not probe_catalog(
        service="ssh?",
        target_type="ip",
        template_snapshot=_READY_TEMPLATES,
    )["service_recommendations"]
    assert PROBE_VIEW_CAPABILITIES == frozenset()
    assert PROBE_LAUNCH_CAPABILITIES == frozenset({"run_commands"})
    assert PROBE_PROTECTED_CAPABILITIES == frozenset({"run_commands", "manage_secrets"})


def test_probe_plan_is_bounded_and_dalfox_never_reaches_intrusive_xss_mode(monkeypatch):
    monkeypatch.setattr(
        "services.assessments.probe_plans.managed_nuclei_template_snapshot",
        lambda: pytest.fail("non-Nuclei plans must not inspect the template cache"),
    )
    plan = build_probe_plan(_request("dalfox"), _target())
    assert plan["policy_level"] == "standard"
    assert plan["action"]["mode"] == "parameter_discovery"
    assert "--only-discovery" in plan["display_command"]
    assert "--skip-mining-dict" in plan["display_command"]
    assert "--custom-payload" not in plan["display_command"]
    assert "xss_payloads" in ACTIONS["dalfox"].exclusions
    assert plan["bounds"]["target_count"] == plan["bounds"]["fan_out"] == 1


def test_probe_profiles_can_raise_but_never_lower_the_base_policy():
    nmap = build_probe_plan(
        _request("nmap", nmap_profile="safe"),
        _target(target_type="ip"),
    )
    assert nmap["policy_level"] == "standard"
    assert nmap["profile"]["policy_level"] == "safe"
    assert "--script safe" in nmap["display_command"]
    assert "service_metadata" in nmap["expected_evidence"]

    nuclei = build_probe_plan(
        _request("nuclei", nuclei_profile="standard"),
        _target(),
        template_snapshot=_READY_TEMPLATES,
    )
    assert nuclei["policy_level"] == "standard"
    assert nuclei["profile"]["template_snapshot"]["content_digest"].startswith("sha256:")


def test_intrusive_nuclei_requires_the_instance_gate_and_fresh_confirmation():
    request = _request("nuclei", nuclei_profile="intrusive")
    disabled = build_probe_plan(request, _target(), template_snapshot=_READY_TEMPLATES)
    assert disabled["launchable"] is False
    assert disabled["availability"]["code"] == "intrusive_actions_disabled"

    enabled = build_probe_plan(
        request,
        _target(),
        intrusive_actions_enabled=True,
        template_snapshot=_READY_TEMPLATES,
    )
    assert enabled["launchable"] is True
    assert enabled["policy_level"] == "intrusive"
    assert "-headless" in enabled["display_command"]
    assert enabled["requires_confirmation"] is True


def test_probe_plan_fails_closed_for_profiles_features_and_target_types():
    with pytest.raises(ProbeError, match="Nmap profile") as unknown:
        build_probe_plan(_request("nmap", nmap_profile="missing"), _target())
    assert unknown.value.code == "probe_profile_not_found"

    missing_feature = build_probe_plan(
        _request("curl"),
        _target(),
        available_features=(),
    )
    assert missing_feature["availability"]["code"] == "feature_unavailable"
    assert missing_feature["feature_gates"] == ["curl"]

    incompatible = build_probe_plan(
        _request("sqlmap"),
        _target(),
    )
    assert incompatible["availability"]["code"] == "unsupported_target_type"


def test_probe_digest_excludes_presentation_but_covers_execution_fields():
    plan = build_probe_plan(_request("curl"), _target())
    assert set(plan) == {
        "schema_version", "digest_version", "project_id", "action", "target", "profile",
        "profile_details", "http_profile", "policy_level", "required_features",
        "feature_gates", "scope", "bounds", "display_command", "expected_evidence",
        "availability", "launchable", "unavailable_reason", "requires_confirmation",
        "plan_digest",
    }
    presentation_change = deepcopy(plan)
    presentation_change["action"]["label"] = "Localized label"
    presentation_change["action"]["purpose"] = "Localized help"
    presentation_change["profile_details"] = {"label": "Presentation only"}
    presentation_change["availability"]["reason"] = "Friendlier explanation"
    assert probe_plan_digest(presentation_change) == plan["plan_digest"]

    execution_change = deepcopy(plan)
    execution_change["display_command"] += " --changed"
    assert probe_plan_digest(execution_change) != plan["plan_digest"]


def test_probe_confirmation_rebuilds_the_plan_and_rejects_stale_or_extra_fields():
    plan = build_probe_plan(_request("ping"), _target())
    assert confirm_probe_plan(
        {"confirmed": True, "plan_digest": plan["plan_digest"]},
        lambda: plan,
    ) is plan
    with pytest.raises(ProbeError) as stale:
        confirm_probe_plan(
            {"confirmed": True, "plan_digest": "0" * 64},
            lambda: plan,
        )
    assert stale.value.code == "stale_plan"
    assert stale.value.status_code == 409
    with pytest.raises(ProbeError) as unsupported:
        confirm_probe_plan(
            {"confirmed": True, "plan_digest": plan["plan_digest"], "command": "ping"},
            lambda: plan,
        )
    assert unsupported.value.code == "unsupported_fields"


def test_assessment_adapter_keeps_its_full_payload_digest_contract():
    row = {
        "assessment_id": "asm_digest", "check_id": "ach_digest",
        "check_key": "host_reachability", "target_entity_id": "ent_digest",
        "target_type": "domain", "target_value": "example.test",
        "policy_level": "safe", "recommended_action_key": "command:ping",
        "profile_key": "network", "profile_version": "1.0",
        "profile_snapshot": json.dumps({"checks": [{
            "key": "host_reachability", "policy_level": "safe",
            "recommended_action": "command:ping",
        }]}),
        "assessment_status": "active", "project_status": "active",
    }
    plan = build_assessment_action_plan(row, _target("ent_digest"), "prj_digest")
    expected_payload = {key: value for key, value in plan.items() if key != "plan_digest"}
    assert plan["plan_digest"] == (
        "424b41660fe6651edbbed28deb35d00b59591ba6d5af04abdbbbefb2c40a2d7a"
    )
    assert plan["plan_digest"] == digest_plan(expected_payload)
    presentation_change = deepcopy(expected_payload)
    presentation_change["bounds"]["summary"] = "Changed presentation"
    assert digest_plan(presentation_change) != plan["plan_digest"]


def test_probe_target_resolver_requires_one_confirmed_owner_scoped_project_link(
    probe_project,
):
    session_id, project_id = probe_project
    confirmed = add_project_target(
        session_id,
        project_id,
        {"type": "domain", "value": "resolve.example", "review_state": "confirmed"},
    )
    pending = add_project_target(
        session_id,
        project_id,
        {"type": "domain", "value": "pending.example", "review_state": "pending"},
    )
    assert confirmed and pending
    with db_connect() as conn:
        by_id = resolve_probe_target(
            conn, session_id, "",
            ProbePlanRequest(project_id, "ping", entity_id=str(confirmed["id"])),
        )
        by_value = resolve_probe_target(
            conn, session_id, "",
            ProbePlanRequest(project_id, "ping", target_value="resolve.example"),
        )
        assert by_id == by_value
        assert by_id["entity_id"] == confirmed["id"]
        with pytest.raises(ProbeError) as unconfirmed:
            resolve_probe_target(
                conn, session_id, "",
                ProbePlanRequest(project_id, "ping", entity_id=str(pending["id"])),
            )
        assert unconfirmed.value.code == "probe_target_not_found"
        with pytest.raises(ProbeError) as foreign:
            resolve_probe_target(
                conn, "foreign-session", "",
                ProbePlanRequest(project_id, "ping", entity_id=str(confirmed["id"])),
            )
        assert foreign.value.code == "project_not_found"

    update_project(session_id, project_id, {"status": "archived"})
    with db_connect() as conn, pytest.raises(ProbeError) as archived:
        resolve_probe_target(
            conn, session_id, "",
            ProbePlanRequest(project_id, "ping", entity_id=str(confirmed["id"])),
        )
    assert archived.value.code == "project_archived"


class _AmbiguousTargetConnection:
    def __init__(self):
        self.calls = 0

    def execute(self, _sql, _params):
        self.calls += 1
        rows = [{"status": "active"}] if self.calls == 1 else [
            {"id": "ent_a", "type": "domain", "canonical_value": "same.example"},
            {"id": "ent_b", "type": "domain", "canonical_value": "same.example"},
        ]
        return _Rows(rows)


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def test_probe_target_value_ambiguity_returns_only_safe_entity_identifiers():
    with pytest.raises(ProbeError) as ambiguous:
        resolve_probe_target(
            _AmbiguousTargetConnection(),
            "session",
            "",
            ProbePlanRequest("prj_probe", "ping", target_value="same.example"),
        )
    assert ambiguous.value.code == "probe_target_ambiguous"
    assert ambiguous.value.details == {"candidate_entity_ids": ["ent_a", "ent_b"]}


def test_probe_target_resolver_uses_team_scope_instead_of_the_callers_session():
    creator = "probe-team-owner-" + uuid.uuid4().hex
    team_id = "team-probe-" + uuid.uuid4().hex
    project = create_project(creator, {"name": "Team probes"}, team_id=team_id)
    assert project is not None
    project_id = str(project["id"])
    try:
        target = add_project_target(
            creator,
            project_id,
            {"type": "ip", "value": "192.0.2.25", "review_state": "confirmed"},
            team_id=team_id,
        )
        assert target is not None
        with db_connect() as conn:
            resolved = resolve_probe_target(
                conn,
                "another-team-member",
                team_id,
                ProbePlanRequest(project_id, "nmap", entity_id=str(target["id"])),
            )
        assert resolved == {
            "entity_id": target["id"], "type": "ip", "value": "192.0.2.25",
        }
    finally:
        delete_project(creator, project_id, team_id=team_id)
