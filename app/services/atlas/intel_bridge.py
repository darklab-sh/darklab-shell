"""Bridge app-native intel lookups into Atlas snapshots."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from config import CFG
from core.database import DB_BACKEND, db_connect
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.atlas.scope import entity_exists_in_scope, metadata_owner_id
from services.intel.canonical import entity_signature
from services.intel.lookup import IntelLookupResult, lookup_entity
from services.storage.body_store import delete_text_body, inline_threshold_bytes, maybe_store_text_body

log = logging.getLogger("shell")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lookup_value(entity_type: str, canonical_value: str) -> str:
    if entity_type == "hash" and ":" in canonical_value:
        return canonical_value.split(":", 1)[1]
    return canonical_value


def _snapshot_summary(payload: dict[str, Any], fallback: str = "") -> str:
    summary = payload.get("summary") if isinstance(payload, dict) else None
    if isinstance(summary, dict):
        providers = summary.get("providers_with_data")
        if isinstance(providers, list) and providers:
            return "data available"
        if summary.get("has_intel") is False:
            return "no intel reported"
    if fallback:
        return fallback
    return "lookup completed"


def _matching_entity_id(
    conn,
    session_id: str,
    entity_type: str,
    canonical_value: str,
    *,
    team_id: str = "",
) -> str:
    signature_hash = entity_signature(entity_type, canonical_value)
    if team_id:
        row = conn.execute(
            "SELECT id FROM entities WHERE team_id = ? AND type = ? AND signature_hash = ?",
            (team_id, entity_type, signature_hash),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM entities WHERE session_id = ? AND team_id = '' AND type = ? AND signature_hash = ?",
            (session_id, entity_type, signature_hash),
        ).fetchone()
    return str(row["id"] or "") if row else ""


def persist_lookup_for_existing_entity(
    session_id: str,
    lookup: IntelLookupResult,
    *,
    team_id: str = "",
) -> dict[str, Any] | None:
    """Persist lookup provider snapshots when the Atlas entity already exists."""
    with db_connect() as conn:
        entity_id = _matching_entity_id(
            conn,
            session_id,
            lookup.entity_type,
            lookup.canonical_value,
            team_id=team_id,
        )
    if not entity_id:
        log.debug("INTEL_LOOKUP_SNAPSHOT_SKIPPED", extra={
            "session": get_log_session_id(session_id),
            "entity_type": lookup.entity_type,
            "reason": "entity_not_found",
        })
        return None
    return _persist_lookup_snapshots(session_id, entity_id, lookup, team_id=team_id)


def refresh_entity_intel(session_id: str, entity_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    """Refresh provider intel for one Atlas entity and persist snapshots."""
    with db_connect() as conn:
        if not entity_exists_in_scope(conn, session_id, entity_id, team_id=team_id):
            return None
        entity = conn.execute(
            "SELECT id, type, canonical_value FROM entities WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if not entity:
            return None

    lookup = lookup_entity(
        entity["type"],
        _lookup_value(entity["type"], entity["canonical_value"]),
        session_id=session_id,
    )
    if lookup.configured_count == 0:
        log.warning("INTEL_PROVIDERS_DISABLED", extra={
            "session": get_log_session_id(session_id),
            "entity_id": entity_id,
            "entity_type": entity["type"],
        })
    return _persist_lookup_snapshots(session_id, entity_id, lookup, team_id=team_id)


def _persist_lookup_snapshots(
    session_id: str,
    entity_id: str,
    lookup: IntelLookupResult,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    metadata_session = metadata_owner_id(session_id, team_id)
    fetched_at = _now()
    snapshots: list[dict[str, Any]] = []
    replaced_payloads: list[Any] = []
    with db_connect() as conn:
        for provider_lookup in lookup.providers:
            provider = provider_lookup.provider
            status = provider_lookup.status
            payload: dict[str, Any] = {"message": provider_lookup.message}
            summary = provider_lookup.message or status
            if provider_lookup.result is not None:
                provider = provider_lookup.result.provider
                status = "ok"
                payload = provider_lookup.result.payload
                summary = _snapshot_summary(payload)
                log.info("INTEL_PROVIDER_LOOKUP_COMPLETED", extra={
                    "session": get_log_session_id(session_id),
                    "entity_id": entity_id,
                    "provider": provider,
                    "status": status,
                })
            else:
                level = logging.WARNING if status in {"error", "rate_limited", "unreachable"} else logging.DEBUG
                log.log(level, "INTEL_PROVIDER_LOOKUP_SKIPPED", extra={
                    "session": get_log_session_id(session_id),
                    "entity_id": entity_id,
                    "provider": provider,
                    "status": status,
                    "provider_message": provider_lookup.message,
                })
            snapshot_id = "intel_" + uuid.uuid4().hex
            existing = conn.execute(
                "SELECT data_json FROM entity_intel_snapshots WHERE entity_id = ? AND provider = ?",
                (entity_id, provider),
            ).fetchone()
            data_json_text = maybe_store_text_body(
                "intel_payload",
                f"{entity_id}-{provider}",
                json.dumps(payload, sort_keys=True),
                inline_threshold_bytes(CFG.get("intel_payload_inline_max_bytes")),
            )
            data_json = dialect_for_backend(DB_BACKEND).decode_json_dict(data_json_text)
            conn.execute(
                "INSERT INTO entity_intel_snapshots "
                "(id, session_id, entity_id, provider, status, summary, data_json, fetched_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '') "
                "ON CONFLICT(entity_id, provider) DO UPDATE SET "
                "session_id = excluded.session_id, status = excluded.status, summary = excluded.summary, "
                "data_json = excluded.data_json, "
                "fetched_at = excluded.fetched_at, expires_at = excluded.expires_at",
                (
                    snapshot_id,
                    metadata_session,
                    entity_id,
                    provider,
                    status,
                    summary,
                    dialect_for_backend(DB_BACKEND).json_param(data_json),
                    fetched_at,
                ),
            )
            if existing and existing["data_json"] != data_json:
                replaced_payloads.append(existing["data_json"])
            snapshots.append({
                "provider": provider,
                "status": status,
                "summary": summary,
                "fetched_at": fetched_at,
            })
        conn.commit()
    for replaced_payload in replaced_payloads:
        delete_text_body(replaced_payload)
    return {
        "entity_id": entity_id,
        "entity_type": lookup.entity_type,
        "canonical_value": lookup.canonical_value,
        "success_count": lookup.success_count,
        "configured_count": lookup.configured_count,
        "snapshots": snapshots,
    }
