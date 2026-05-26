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
from services.intel.lookup import lookup_entity
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


def refresh_entity_intel(session_id: str, entity_id: str) -> dict[str, Any] | None:
    """Refresh provider intel for one Atlas entity and persist snapshots."""
    with db_connect() as conn:
        entity = conn.execute(
            "SELECT id, type, canonical_value FROM entities WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
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
                "status = excluded.status, summary = excluded.summary, data_json = excluded.data_json, "
                "fetched_at = excluded.fetched_at, expires_at = excluded.expires_at",
                (
                    snapshot_id,
                    session_id,
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
