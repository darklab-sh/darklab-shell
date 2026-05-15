"""Materialize normalized output entities into the Session Entity Atlas."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from services.intel.canonical import CanonicalizationError, canonical_entity, entity_signature
from services.intel.schema import ENTITY_TYPES


ATLAS_ENTITY_TYPES = frozenset(ENTITY_TYPES)


def atlas_entity_id(session_id: str, entity_type: str, canonical_value: str) -> str:
    raw = f"{session_id}\x1f{entity_type}\x1f{canonical_value}".encode("utf-8", errors="replace")
    return "ent_" + hashlib.sha256(raw).hexdigest()[:32]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_entity_type(value: object) -> str:
    entity_type = str(value or "").strip().lower()
    if entity_type == "host":
        return "domain"
    return entity_type


def _canonicalize_entity(entity: Mapping[str, Any]) -> tuple[str, str] | None:
    entity_type = _normalize_entity_type(entity.get("type"))
    if entity_type not in ATLAS_ENTITY_TYPES:
        return None
    raw_value = str(entity.get("canonical_value") or entity.get("value") or "").strip()
    if not raw_value:
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


def materialize_run_entities(conn, session_id: str, run_id: str, entries: Iterable[object], *, seen_at: str = ""):
    """Store unique normalized entities and run links for a completed run."""
    timestamp = str(seen_at or _now())
    counts: Counter[tuple[str, str]] = Counter()
    for entity in _iter_entry_entities(entries):
        normalized = _canonicalize_entity(entity)
        if normalized:
            counts[normalized] += 1

    materialized = []
    for (entity_type, canonical_value), occurrence_count in sorted(counts.items()):
        signature_hash = entity_signature(entity_type, canonical_value)
        entity_id = atlas_entity_id(session_id, entity_type, canonical_value)
        conn.execute(
            "INSERT INTO entities "
            "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, occurrence_count, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, type, signature_hash) DO UPDATE SET "
            "last_seen_at = excluded.last_seen_at, "
            "occurrence_count = entities.occurrence_count + excluded.occurrence_count",
            (
                entity_id,
                session_id,
                entity_type,
                canonical_value,
                signature_hash,
                timestamp,
                timestamp,
                int(occurrence_count),
                timestamp,
            ),
        )
        row = conn.execute(
            "SELECT id FROM entities WHERE session_id = ? AND type = ? AND signature_hash = ?",
            (session_id, entity_type, signature_hash),
        ).fetchone()
        if not row:
            continue
        entity_id = str(row["id"])
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
