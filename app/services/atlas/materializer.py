"""Materialize normalized output entities into the Session Entity Atlas."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from core.database_backend import DatabaseBackend, dialect_for_backend, parse_database_backend
from core.helpers import get_log_session_id
from core.output_signals import command_root, extract_target
from core.redaction import REDACTED_ENTITY_SENTINEL
from services.atlas.recalculation import recalculate_atlas_entities
from services.atlas.schema import ATLAS_ENTITY_TYPES
from services.intel.canonical import (
    CanonicalizationError,
    canonical_domain,
    canonical_entity,
    canonical_ip,
    canonical_url,
    entity_signature,
    parse_canonical_port,
)

PORT_SCAN_OBSERVATION_ROOTS = frozenset({"nmap", "masscan", "rustscan", "naabu", "nc"})
log = logging.getLogger("shell")


def _conn_dialect(conn):
    backend = getattr(conn, "database_backend", DatabaseBackend.SQLITE)
    return dialect_for_backend(parse_database_backend(backend))


def _json_param(conn, value: Any) -> Any:
    return _conn_dialect(conn).json_param(_json_dict(value))


def atlas_entity_id(session_id: str, entity_type: str, canonical_value: str, *, team_id: str = "") -> str:
    owner_id = str(team_id or session_id)
    raw = f"{owner_id}\x1f{entity_type}\x1f{canonical_value}".encode("utf-8", errors="replace")
    return "ent_" + hashlib.sha256(raw).hexdigest()[:32]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_entity_type(value: object) -> str:
    entity_type = str(value or "").strip().lower()
    if entity_type == "host":
        return "domain"
    return entity_type


def canonicalize_entity_record(entity: Mapping[str, Any]) -> tuple[str, str] | None:
    entity_type = _normalize_entity_type(entity.get("type"))
    if entity_type not in ATLAS_ENTITY_TYPES:
        return None
    raw_value = str(entity.get("canonical_value") or entity.get("value") or "").strip()
    if not raw_value or raw_value == REDACTED_ENTITY_SENTINEL:
        return None
    try:
        if entity_type == "hash" and ":" in raw_value:
            algorithm, token = raw_value.split(":", 1)
            canonical_value = canonical_entity(entity_type, token, algorithm=algorithm)
        else:
            canonical_value = canonical_entity(entity_type, raw_value)
    except CanonicalizationError:
        return None
    return entity_type, canonical_value


def _log_extra(session_id: str = "", team_id: str = "", run_id: str = "", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if session_id:
        payload["session"] = get_log_session_id(session_id)
    if team_id:
        payload["team_id"] = team_id
    if run_id:
        payload["run_id"] = run_id
    payload.update(extra)
    return payload


def _json_dict(
    value: Any,
    *,
    source: str = "",
    log_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context = dict(log_context or {})
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items() if str(key)}
    if isinstance(value, str):
        try:
            parsed = json.loads(value or "{}")
        except ValueError:
            if source == "stored":
                log.warning("ATLAS_ENTITY_ATTRIBUTES_DECODE_FAILED", extra={
                    **context,
                    "value_type": type(value).__name__,
                    "reason": "invalid_json",
                })
            elif source == "incoming" and value:
                log.debug("ATLAS_ENTITY_ATTRIBUTES_DROPPED", extra={
                    **context,
                    "value_type": type(value).__name__,
                    "reason": "invalid_json",
                })
            return {}
        if isinstance(parsed, Mapping):
            return {str(key): item for key, item in parsed.items() if str(key)}
        if source == "stored":
            log.warning("ATLAS_ENTITY_ATTRIBUTES_DECODE_FAILED", extra={
                **context,
                "value_type": type(parsed).__name__,
                "reason": "non_object_json",
            })
        elif source == "incoming" and value:
            log.debug("ATLAS_ENTITY_ATTRIBUTES_DROPPED", extra={
                **context,
                "value_type": type(parsed).__name__,
                "reason": "non_object_json",
            })
        return {}
    if source == "incoming" and value is not None:
        log.debug("ATLAS_ENTITY_ATTRIBUTES_DROPPED", extra={
            **context,
            "value_type": type(value).__name__,
            "reason": "non_object",
        })
    return {}


def _port_host_entity_id(
    session_id: str,
    canonical_value: str,
    *,
    team_id: str = "",
) -> str:
    try:
        host_type, host_canonical, _, _ = parse_canonical_port(canonical_value)
    except CanonicalizationError:
        return ""
    return atlas_entity_id(session_id, host_type, host_canonical, team_id=team_id)


def _host_identity(value: str) -> tuple[str, str] | None:
    raw = str(value or "").strip().strip("[]")
    if not raw:
        return None
    try:
        return "ip", canonical_ip(raw)
    except CanonicalizationError:
        try:
            return "domain", canonical_domain(raw)
        except CanonicalizationError:
            return None


def url_host_identity(value: str) -> tuple[str, str] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        host = str(parts.hostname or "")
    except ValueError:
        return None
    try:
        canonical_url(raw)
    except CanonicalizationError:
        return None
    return _host_identity(host)


def _merge_attributes(existing: Mapping[str, Any] | None, incoming: Mapping[str, Any] | None) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in dict(incoming or {}).items():
        if not str(key) or value is None or value == "":
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        if isinstance(value, tuple) and not value:
            continue
        if isinstance(value, set) and not value:
            continue
        merged[str(key)] = value
    return merged


def upsert_entity(
    conn,
    session_id: str,
    entity_type: str,
    canonical_value: str,
    *,
    team_id: str = "",
    seen_at: str = "",
    occurrence_count: int = 0,
    host_entity_id: str = "",
    attributes: Mapping[str, Any] | None = None,
) -> str:
    timestamp = str(seen_at or _now())
    team_id = str(team_id or "").strip()
    entity_type = _normalize_entity_type(entity_type)
    signature_hash = entity_signature(entity_type, canonical_value)
    entity_id = atlas_entity_id(session_id, entity_type, canonical_value, team_id=team_id)
    if not host_entity_id and entity_type == "port":
        host_entity_id = _port_host_entity_id(session_id, canonical_value, team_id=team_id)
    if not host_entity_id and entity_type == "url":
        host_identity = url_host_identity(canonical_value)
        if host_identity is None:
            log.debug("ATLAS_URL_HOST_LINK_SKIPPED", extra=_log_extra(
                session_id,
                team_id,
                entity_id=entity_id,
                reason="host_identity_unresolved",
            ))
        else:
            host_type, host_canonical = host_identity
            host_entity_id = upsert_entity(
                conn,
                session_id,
                host_type,
                host_canonical,
                team_id=team_id,
                seen_at=timestamp,
                occurrence_count=max(0, int(occurrence_count or 0)),
            )
    attributes_payload = _json_param(conn, attributes)
    if team_id:
        existing_row = conn.execute(
            "SELECT id, attributes_json FROM entities WHERE team_id = ? AND type = ? AND signature_hash = ?",
            (team_id, entity_type, signature_hash),
        ).fetchone()
    else:
        existing_row = conn.execute(
            "SELECT id, attributes_json FROM entities "
            "WHERE session_id = ? AND team_id = '' AND type = ? AND signature_hash = ?",
            (session_id, entity_type, signature_hash),
        ).fetchone()
    conflict_target = (
        "ON CONFLICT(team_id, type, signature_hash) WHERE team_id != '' DO UPDATE SET "
        if team_id
        else "ON CONFLICT(session_id, type, signature_hash) WHERE team_id = '' DO UPDATE SET "
    )
    conn.execute(
        "INSERT INTO entities "
        "(id, session_id, team_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, "
        "occurrence_count, host_entity_id, attributes_json, created) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        f"{conflict_target}"  # nosec
        "last_seen_at = CASE "
        "WHEN excluded.last_seen_at > entities.last_seen_at THEN excluded.last_seen_at ELSE entities.last_seen_at END, "
        "occurrence_count = entities.occurrence_count + excluded.occurrence_count, "
        "host_entity_id = CASE "
        "WHEN COALESCE(entities.host_entity_id, '') = '' THEN excluded.host_entity_id ELSE entities.host_entity_id END",
        (
            entity_id,
            session_id,
            team_id,
            entity_type,
            canonical_value,
            signature_hash,
            timestamp,
            timestamp,
            max(0, int(occurrence_count or 0)),
            str(host_entity_id or ""),
            attributes_payload,
            timestamp,
        ),
    )
    stored_id = str(existing_row["id"]) if existing_row else entity_id
    if attributes and existing_row:
        merged = _merge_attributes(
            _json_dict(existing_row["attributes_json"], source="stored", log_context=_log_extra(
                session_id,
                team_id,
                entity_id=stored_id,
                entity_type=entity_type,
            )),
            _json_dict(attributes, source="incoming", log_context=_log_extra(
                session_id,
                team_id,
                entity_id=stored_id,
                entity_type=entity_type,
            )),
        )
        conn.execute(
            "UPDATE entities SET attributes_json = ? WHERE id = ?",
            (_json_param(conn, merged), stored_id),
        )
    return stored_id


def _command_target_values(command: str) -> list[str]:
    target = extract_target(command) or ""
    values: list[str] = []
    for item in str(target).split(","):
        normalized = item.strip()
        if normalized and normalized not in values:
            values.append(normalized)
    return values


def _port_host_counts(
    session_id: str,
    counts: Counter[tuple[str, str]],
    *,
    team_id: str = "",
) -> Counter[str]:
    result: Counter[str] = Counter()
    for (entity_type, canonical_value), occurrence_count in counts.items():
        if entity_type != "port":
            continue
        host_entity_id = _port_host_entity_id(session_id, canonical_value, team_id=team_id)
        if host_entity_id:
            result[host_entity_id] += int(occurrence_count or 0)
    return result


def _scan_observation_targets(
    session_id: str,
    command: str,
    counts: Counter[tuple[str, str]],
    *,
    team_id: str = "",
) -> dict[str, tuple[str, str]]:
    root = command_root(command)
    if root not in PORT_SCAN_OBSERVATION_ROOTS:
        return {}
    targets: dict[str, tuple[str, str]] = {}
    for entity_type, canonical_value in counts:
        if entity_type not in {"ip", "domain"}:
            continue
        entity_id = atlas_entity_id(session_id, entity_type, canonical_value, team_id=team_id)
        targets[entity_id] = (entity_type, canonical_value)
    for value in _command_target_values(command):
        identity = _host_identity(value)
        if identity is None:
            continue
        entity_type, canonical_value = identity
        entity_id = atlas_entity_id(session_id, entity_type, canonical_value, team_id=team_id)
        targets[entity_id] = (entity_type, canonical_value)
    return targets


def _record_scan_target_observations(
    conn,
    session_id: str,
    run_id: str,
    command: str,
    counts: Counter[tuple[str, str]],
    *,
    team_id: str = "",
    observed_at: str = "",
) -> int:
    root = command_root(command)
    deleted = conn.execute("DELETE FROM scan_target_observations WHERE run_id = ?", (run_id,))
    deleted_count = max(0, int(deleted.rowcount or 0))
    log_context = _log_extra(
        session_id,
        team_id,
        run_id,
        command_root=root,
        deleted_count=deleted_count,
    )
    if root not in PORT_SCAN_OBSERVATION_ROOTS:
        reason = "missing_command" if not str(command or "").strip() or not root else "unsupported_command_root"
        if deleted_count:
            log.warning("SCAN_TARGET_OBSERVATIONS_DROPPED", extra={
                **log_context,
                "reason": reason,
            })
        else:
            log.debug("SCAN_TARGET_OBSERVATIONS_SKIPPED", extra={
                **log_context,
                "reason": reason,
            })
        return 0
    timestamp = str(observed_at or _now())
    port_counts = _port_host_counts(session_id, counts, team_id=team_id)
    targets = _scan_observation_targets(session_id, command, counts, team_id=team_id)
    if not targets:
        if deleted_count:
            log.warning("SCAN_TARGET_OBSERVATIONS_DROPPED", extra={
                **log_context,
                "reason": "no_scan_targets",
            })
        else:
            log.debug("SCAN_TARGET_OBSERVATIONS_SKIPPED", extra={
                **log_context,
                "reason": "no_scan_targets",
            })
        return 0
    for entity_id, (entity_type, canonical_value) in sorted(targets.items()):
        conn.execute(
            "INSERT INTO scan_target_observations "
            "(session_id, team_id, run_id, entity_id, entity_type, canonical_value, scan_kind, "
            "command_root, observed_at, port_entity_count, created) "
            "VALUES (?, ?, ?, ?, ?, ?, 'port_scan', ?, ?, ?, ?) "
            "ON CONFLICT(run_id, entity_id, scan_kind) DO UPDATE SET "
            "observed_at = excluded.observed_at, "
            "command_root = excluded.command_root, "
            "port_entity_count = excluded.port_entity_count",
            (
                session_id,
                str(team_id or ""),
                run_id,
                entity_id,
                entity_type,
                canonical_value,
                root,
                timestamp,
                int(port_counts.get(entity_id, 0)),
                timestamp,
            ),
        )
    return len(targets)


def recalculate_entities(conn, entity_ids: Iterable[str]) -> None:
    recalculate_atlas_entities(conn, entity_ids)


def _iter_entry_entities(entries: Iterable[object]) -> Iterable[Mapping[str, Any]]:
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        raw_entities = entry.get("entities")
        if not isinstance(raw_entities, list):
            continue
        for raw_entity in raw_entities:
            if isinstance(raw_entity, Mapping):
                yield raw_entity


def materialize_run_entities(
    conn,
    session_id: str,
    run_id: str,
    entries: Iterable[object],
    *,
    team_id: str = "",
    seen_at: str = "",
    command: str = "",
):
    """Store unique normalized entities and run links for a completed run."""
    timestamp = str(seen_at or _now())
    existing_rows = conn.execute(
        "SELECT entity_id FROM entity_run_links WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    existing_entity_ids = [str(row["entity_id"] or "") for row in existing_rows]
    conn.execute("DELETE FROM entity_run_links WHERE run_id = ?", (run_id,))
    recalculate_entities(conn, existing_entity_ids)
    counts: Counter[tuple[str, str]] = Counter()
    attributes_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    url_host_keys: dict[tuple[str, str], tuple[str, str]] = {}
    derived_url_host_counts: Counter[tuple[str, str]] = Counter()
    url_entity_count = 0
    url_host_unresolved_count = 0
    url_host_type_counts: Counter[str] = Counter()
    invalid_entity_count = 0
    for entity in _iter_entry_entities(entries):
        normalized = canonicalize_entity_record(entity)
        if normalized:
            counts[normalized] += 1
            if normalized[0] == "url":
                url_entity_count += 1
                host_identity = url_host_identity(normalized[1])
                if host_identity is not None:
                    url_host_keys[normalized] = host_identity
                    url_host_type_counts[host_identity[0]] += 1
                    derived_url_host_counts[host_identity] += 1
                else:
                    url_host_unresolved_count += 1
            raw_attributes = entity.get("attributes") or entity.get("attributes_json")
            attributes = _json_dict(raw_attributes, source="incoming", log_context=_log_extra(
                session_id,
                team_id,
                run_id,
                entity_type=normalized[0],
            ))
            if attributes:
                attributes_by_key[normalized] = _merge_attributes(attributes_by_key.get(normalized), attributes)
        else:
            invalid_entity_count += 1
    for host_identity, occurrence_count in derived_url_host_counts.items():
        if host_identity not in counts:
            counts[host_identity] += int(occurrence_count or 0)
    scan_observation_count = _record_scan_target_observations(
        conn,
        session_id,
        run_id,
        command,
        counts,
        team_id=team_id,
        observed_at=timestamp,
    )
    log.debug("ATLAS_ENTITY_MATERIALIZATION_SUMMARY", extra=_log_extra(
        session_id,
        team_id,
        run_id,
        command_root=command_root(command),
        entity_count=len(counts),
        total_occurrence_count=sum(int(count or 0) for count in counts.values()),
        invalid_entity_count=invalid_entity_count,
        port_entity_count=sum(int(count or 0) for (kind, _), count in counts.items() if kind == "port"),
        url_entity_count=url_entity_count,
        url_host_link_count=len(url_host_keys),
        url_host_unresolved_count=url_host_unresolved_count,
        url_host_domain_count=url_host_type_counts.get("domain", 0),
        url_host_ip_count=url_host_type_counts.get("ip", 0),
        attribute_entity_count=len(attributes_by_key),
        scan_observation_count=scan_observation_count,
    ))

    materialized = []
    sorted_items = sorted(counts.items(), key=lambda item: (item[0][0] == "port", item[0][0], item[0][1]))
    for (entity_type, canonical_value), occurrence_count in sorted_items:
        host_entity_id = ""
        if entity_type == "url":
            host_identity = url_host_keys.get((entity_type, canonical_value))
            if host_identity is not None:
                host_entity_id = atlas_entity_id(
                    session_id,
                    host_identity[0],
                    host_identity[1],
                    team_id=team_id,
                )
        entity_id = upsert_entity(
            conn,
            session_id,
            entity_type,
            canonical_value,
            team_id=team_id,
            seen_at=timestamp,
            occurrence_count=int(occurrence_count),
            host_entity_id=host_entity_id,
            attributes=attributes_by_key.get((entity_type, canonical_value), {}),
        )
        conn.execute(
            "INSERT INTO entity_run_links "
            "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(entity_id, run_id) DO UPDATE SET "
            "last_seen_at = excluded.last_seen_at, "
            "occurrence_count = entity_run_links.occurrence_count + excluded.occurrence_count",
            (entity_id, run_id, timestamp, timestamp, int(occurrence_count)),
        )
        materialized.append({
            "id": entity_id,
            "type": entity_type,
            "canonical_value": canonical_value,
            "occurrence_count": int(occurrence_count),
        })
    return materialized
