# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Explicit compatibility matching for saved assessment evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from core.output_targets import command_root, extract_target
from services.assessments.command_modes import assessment_command_mode
from services.commands.registry import command_project_target_inputs
from services.intel.canonical import (
    CanonicalizationError,
    canonical_domain,
    canonical_ip,
    canonical_port,
    canonical_url,
    parse_canonical_port,
)


_DNS_ROOTS = frozenset({"dig", "dnsrecon", "dnsx"})
_HTTP_ROOTS = frozenset({"curl", "dalfox", "ffuf", "gobuster", "httpx", "katana", "nuclei", "sqlmap"})


@dataclass(frozen=True)
class EvidenceIdentity:
    entity_type: str
    canonical_value: str


@dataclass(frozen=True)
class RunEvidenceFacts:
    run_id: str
    command_root: str
    finished_at: str
    exit_code: int | None
    target_identities: tuple[EvidenceIdentity, ...]
    structured_output_kinds: frozenset[str]
    workflow_actions: frozenset[str]
    finding_count: int
    command_mode: str = ""


def _canonical_identity(value: object, value_type: object = "target") -> EvidenceIdentity | None:
    raw = str(value or "").strip().strip("[](){}<>\"'`,;")
    kind = str(value_type or "target").strip().lower()
    if not raw or kind == "port_set":
        return None
    candidates = (kind,) if kind not in {"host", "target"} else ("url", "ip", "port", "domain")
    for candidate in candidates:
        try:
            if candidate == "url":
                return EvidenceIdentity("url", canonical_url(raw))
            if candidate == "ip":
                return EvidenceIdentity("ip", canonical_ip(raw))
            if candidate == "port":
                return EvidenceIdentity("port", canonical_port(raw))
            if candidate == "domain":
                return EvidenceIdentity("domain", canonical_domain(raw))
        except CanonicalizationError:
            continue
    return None


def canonical_evidence_identity(value: object, value_type: object = "target") -> EvidenceIdentity | None:
    """Return the canonical identity used by assessment evidence matching."""
    return _canonical_identity(value, value_type)


def _command_identities(
    command: str, command_target_inputs_fn: Callable[[str], list[dict[str, str]]]
) -> set[EvidenceIdentity]:
    identities: set[EvidenceIdentity] = set()
    try:
        inputs = command_target_inputs_fn(command)
    except Exception:
        inputs = []
    for item in inputs if isinstance(inputs, list) else []:
        if not isinstance(item, Mapping) or str(item.get("target_list_file") or "") == "1":
            continue
        identity = _canonical_identity(item.get("value"), item.get("value_type"))
        if identity is not None:
            identities.add(identity)
    if identities:
        return identities
    fallback = extract_target(command)
    for value in str(fallback or "").split(","):
        identity = _canonical_identity(value)
        if identity is not None:
            identities.add(identity)
    return identities


def _entity_facts(conn: Any, run_id: str) -> tuple[set[EvidenceIdentity], set[str]]:
    rows = conn.execute(
        "SELECT e.type, e.canonical_value, e.attributes_json "
        "FROM entity_run_links erl JOIN entities e ON e.id = erl.entity_id "
        "WHERE erl.run_id = ?",
        (run_id,),
    ).fetchall()
    identities: set[EvidenceIdentity] = set()
    kinds: set[str] = set()
    dialect = dialect_for_backend(get_db_backend())
    for row in rows:
        identity = _canonical_identity(row["canonical_value"], row["type"])
        if identity is None:
            continue
        identities.add(identity)
        kinds.add("entities")
        if identity.entity_type == "port":
            kinds.add("ports")
            attributes = dialect.decode_json_dict(row["attributes_json"])
            if any(str(attributes.get(key) or "").strip() for key in ("service", "version", "banner")):
                kinds.add("services")
        if identity.entity_type == "url":
            kinds.add("http_responses")
    return identities, kinds


def _scan_observation_identities(conn: Any, run_id: str) -> set[EvidenceIdentity]:
    rows = conn.execute(
        "SELECT entity_type, canonical_value FROM scan_target_observations WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    return {
        identity
        for row in rows
        if (identity := _canonical_identity(row["canonical_value"], row["entity_type"])) is not None
    }


def _workflow_actions(conn: Any, run_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT we.workflow_id, wes.step_id FROM workflow_execution_steps wes "
        "JOIN workflow_executions we ON we.id = wes.execution_id WHERE wes.run_id = ?",
        (run_id,),
    ).fetchall()
    return {
        value
        for row in rows
        for value in (str(row["workflow_id"] or "").strip(), str(row["step_id"] or "").strip())
        if value
    }


def load_run_evidence_facts(
    conn: Any, run_id: str, *,
    command_target_inputs_fn: Callable[[str], list[dict[str, str]]] = command_project_target_inputs,
) -> RunEvidenceFacts | None:
    """Load bounded facts used to test one saved run against profile rules."""
    row = conn.execute(
        "SELECT id, command, finished, exit_code FROM runs WHERE id = ?",
        (str(run_id or "").strip(),),
    ).fetchone()
    if not row:
        return None
    command = str(row["command"] or "")
    root = command_root(command)
    identities = _command_identities(command, command_target_inputs_fn)
    entity_identities, structured_kinds = _entity_facts(conn, str(row["id"]))
    identities.update(entity_identities)
    identities.update(_scan_observation_identities(conn, str(row["id"])))
    finding_row = conn.execute(
        "SELECT COUNT(*) AS count FROM findings WHERE run_id = ?",
        (str(row["id"]),),
    ).fetchone()
    finding_count = int(finding_row["count"] or 0) if finding_row else 0
    if finding_count:
        structured_kinds.add("findings")
    artifact_row = conn.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM run_output_artifacts WHERE run_id = ?) + "
        "(SELECT COUNT(*) FROM run_file_artifacts WHERE run_id = ?) AS count",
        (str(row["id"]), str(row["id"])),
    ).fetchone()
    if artifact_row and int(artifact_row["count"] or 0):
        structured_kinds.add("artifacts")
    if root in _DNS_ROOTS and entity_identities:
        structured_kinds.add("dns_records")
    if root in _HTTP_ROOTS and "entities" in structured_kinds:
        structured_kinds.add("http_responses")
    exit_code = row["exit_code"]
    return RunEvidenceFacts(
        run_id=str(row["id"]),
        command_root=root,
        finished_at=str(row["finished"] or ""),
        exit_code=int(exit_code) if exit_code is not None else None,
        target_identities=tuple(sorted(identities, key=lambda item: (item.entity_type, item.canonical_value))),
        structured_output_kinds=frozenset(structured_kinds),
        workflow_actions=frozenset(_workflow_actions(conn, str(row["id"]))),
        finding_count=finding_count,
        command_mode=assessment_command_mode(command),
    )


def _identity_host(identity: EvidenceIdentity) -> tuple[str, str] | None:
    if identity.entity_type in {"domain", "ip"}:
        return identity.entity_type, identity.canonical_value
    if identity.entity_type == "url":
        host = str(urlsplit(identity.canonical_value).hostname or "")
        try:
            return "ip", canonical_ip(host)
        except CanonicalizationError:
            try:
                return "domain", canonical_domain(host)
            except CanonicalizationError:
                return None
    if identity.entity_type == "port":
        try:
            host_type, host, _port, _proto = parse_canonical_port(identity.canonical_value)
        except CanonicalizationError:
            return None
        return host_type, host
    return None


def _domain_matches(candidate: str, target: str) -> bool:
    return candidate == target or candidate.endswith("." + target)


def _url_matches(candidate: EvidenceIdentity, target: EvidenceIdentity) -> bool:
    candidate_parts = urlsplit(candidate.canonical_value)
    target_parts = urlsplit(target.canonical_value)
    if (
        candidate_parts.scheme != target_parts.scheme
        or candidate_parts.netloc != target_parts.netloc
    ):
        return False
    candidate_path = candidate_parts.path.rstrip("/")
    target_path = target_parts.path.rstrip("/")
    if not target_path:
        return True
    return candidate_path == target_path or candidate_path.startswith(target_path + "/")


def target_matches(
    identities: tuple[EvidenceIdentity, ...],
    target_type: str,
    target_value: str,
    match_kind: str,
) -> bool:
    """Return whether explicit source identities satisfy one target rule."""
    if match_kind == "project_scope":
        return True
    target = _canonical_identity(target_value, target_type)
    if target is None:
        return False
    if match_kind == "exact":
        return target in identities
    if match_kind != "host_or_descendant":
        return False
    target_host = _identity_host(target)
    if target_host is None:
        return False
    target_host_type, target_host_value = target_host
    for identity in identities:
        if identity == target:
            return True
        candidate_host = _identity_host(identity)
        if candidate_host is None or candidate_host[0] != target_host_type:
            continue
        if target.entity_type == "url":
            if identity.entity_type == "url" and _url_matches(identity, target):
                return True
            if identity.entity_type in {"domain", "ip"} and candidate_host[1] == target_host_value:
                return True
            continue
        if target_host_type == "ip" and candidate_host[1] == target_host_value:
            return True
        if target_host_type == "domain" and _domain_matches(candidate_host[1], target_host_value):
            return True
    return False


def matching_evidence_rule(
    check_definition: Mapping[str, Any],
    facts: RunEvidenceFacts,
    *,
    evidence_type: str,
    target_type: str,
    target_value: str,
) -> dict[str, Any] | None:
    """Return the first frozen profile rule satisfied by a saved source."""
    normalized_evidence_type = str(evidence_type or "").strip().lower()
    for raw_rule in check_definition.get("evidence_rules", []):
        if not isinstance(raw_rule, Mapping):
            continue
        rule = dict(raw_rule)
        if normalized_evidence_type not in rule.get("evidence_types", []):
            continue
        roots = {str(value or "").strip().lower() for value in rule.get("command_roots", [])}
        actions = {str(value or "").strip() for value in rule.get("workflow_actions", [])}
        if facts.command_root not in roots and not actions.intersection(facts.workflow_actions):
            continue
        if rule.get("command_modes") and facts.command_mode not in rule["command_modes"]:
            continue
        versions = {str(value or "").strip() for value in rule.get("compatible_versions", [])}
        if "*" not in versions:
            continue
        completion = str(rule.get("completion") or "")
        if completion == "succeeded" and (not facts.finished_at or facts.exit_code != 0):
            continue
        if completion == "available" and not facts.finished_at:
            continue
        if completion == "finding_present" and facts.finding_count <= 0:
            continue
        if not target_matches(
            facts.target_identities,
            target_type,
            target_value,
            str(rule.get("target_match") or ""),
        ):
            continue
        required_kinds = {
            str(value or "").strip().lower()
            for value in rule.get("structured_output_kinds", [])
        }
        if (
            required_kinds
            and not required_kinds.intersection(facts.structured_output_kinds)
            and not bool(rule.get("negative_evidence"))
        ):
            continue
        return rule
    return None


def matching_run_rule(
    check_definition: Mapping[str, Any],
    facts: RunEvidenceFacts,
    *,
    target_type: str,
    target_value: str,
) -> dict[str, Any] | None:
    """Return the first explicit profile rule satisfied by a saved run."""
    return matching_evidence_rule(
        check_definition,
        facts,
        evidence_type="run",
        target_type=target_type,
        target_value=target_value,
    )
