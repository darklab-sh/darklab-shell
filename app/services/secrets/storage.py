"""SQLite storage helpers for encrypted per-session secrets."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from core.database import DB_BACKEND, db_connect
from core.database_backend import dialect_for_backend
from services.secrets.vault import decrypt_secret, encrypt_secret
from services.secrets.audit import emit_secret_event

SECRET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class SecretStorageError(ValueError):
    """Base class for storage validation errors."""


class InvalidSecretName(SecretStorageError):
    """Raised when a secret/env name is not accepted."""


class SecretConsumerEnvConflict(SecretStorageError):
    """Raised when an env binding would point at more than one secret."""

    def __init__(self, env_name: str, existing_name: str):
        super().__init__(f"{env_name} is already bound to {existing_name}")
        self.env_name = env_name
        self.existing_name = existing_name


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_secret_name(name: str) -> str:
    normalized = str(name or "").strip().upper()
    if not SECRET_NAME_RE.fullmatch(normalized):
        raise InvalidSecretName("secret names must match [A-Z][A-Z0-9_]{0,63}")
    return normalized


def normalize_consumer_envs(values: Any, *, default_name: str) -> list[str]:
    if values is None:
        raw_values = [default_name]
    elif isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, list):
        raw_values = values
    else:
        raise InvalidSecretName("consumer_envs must be a list of env names")

    envs: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        env = normalize_secret_name(str(value or ""))
        if env in seen:
            continue
        seen.add(env)
        envs.append(env)
    return envs or [default_name]


def _metadata_from_row(row) -> dict[str, str | list[str]]:
    return {
        "name": row["name"],
        "consumer_envs": json.loads(row["consumer_envs"] or "[]"),
        "updated_at": row["updated_at"],
    }


def list_secret_metadata(session_token: str) -> list[dict[str, str | list[str]]]:
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT name, consumer_envs, updated_at FROM secrets "
            "WHERE session_token = ? ORDER BY name",
            (session_token,),
        ).fetchall()
    return [_metadata_from_row(row) for row in rows]


def upsert_secret_with_connection(conn, session_token: str, name: str, value: str, consumer_envs=None) -> tuple[dict, bool]:
    normalized_name = normalize_secret_name(name)
    normalized_envs = normalize_consumer_envs(consumer_envs, default_name=normalized_name)
    ciphertext, nonce = encrypt_secret(value)
    now = _utc_now()
    envs_json = json.dumps(normalized_envs, separators=(",", ":"))

    existing = conn.execute(
        "SELECT created_at FROM secrets WHERE session_token = ? AND name = ?",
        (session_token, normalized_name),
    ).fetchone()
    rows = conn.execute(
        "SELECT name, consumer_envs FROM secrets WHERE session_token = ? AND name <> ? ORDER BY name",
        (session_token, normalized_name),
    ).fetchall()
    requested_envs = set(normalized_envs)
    for row in rows:
        existing_envs = set(json.loads(row["consumer_envs"] or "[]"))
        conflicts = sorted(requested_envs & existing_envs)
        if conflicts:
            raise SecretConsumerEnvConflict(conflicts[0], row["name"])
    created = existing is None
    created_at = now if created else existing["created_at"]
    conn.execute(
        "INSERT INTO secrets "
        "(session_token, name, ciphertext, nonce, consumer_envs, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(session_token, name) DO UPDATE SET "
        "ciphertext = excluded.ciphertext, "
        "nonce = excluded.nonce, "
        "consumer_envs = excluded.consumer_envs, "
        "updated_at = excluded.updated_at",
        (session_token, normalized_name, ciphertext, nonce, envs_json, created_at, now),
    )
    return {
        "name": normalized_name,
        "consumer_envs": normalized_envs,
        "updated_at": now,
    }, created


def emit_secret_upsert_audit(
    session_token: str,
    metadata: dict,
    created: bool,
    *,
    audit_session_id: str = "",
    team_id: str = "",
) -> None:
    emit_secret_event(
        "SECRET_STORED",
        audit_session_id or session_token,
        name=str(metadata["name"]),
        consumer_envs=metadata["consumer_envs"],
        is_new_secret=created,
        team_id=team_id,
    )


def upsert_secret(
    session_token: str,
    name: str,
    value: str,
    consumer_envs=None,
    *,
    audit_session_id: str = "",
    team_id: str = "",
) -> tuple[dict, bool]:
    with db_connect() as conn:
        metadata, created = upsert_secret_with_connection(conn, session_token, name, value, consumer_envs)
        conn.commit()
    emit_secret_upsert_audit(session_token, metadata, created, audit_session_id=audit_session_id, team_id=team_id)
    return metadata, created


def delete_secret(session_token: str, name: str) -> bool:
    normalized_name = normalize_secret_name(name)
    with db_connect() as conn:
        cur = conn.execute(
            "DELETE FROM secrets WHERE session_token = ? AND name = ?",
            (session_token, normalized_name),
        )
        conn.commit()
    return cur.rowcount > 0


def get_secret_value_for_env(
    session_token: str,
    env_name: str,
    *,
    audit_session_id: str = "",
    team_id: str = "",
) -> str | None:
    normalized_env = normalize_secret_name(env_name)
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT ciphertext, nonce, consumer_envs FROM secrets "
            "WHERE session_token = ? ORDER BY updated_at DESC, name ASC",
            (session_token,),
        ).fetchall()
    for row in rows:
        envs = json.loads(row["consumer_envs"] or "[]")
        if normalized_env in envs:
            value = decrypt_secret(row["ciphertext"], row["nonce"])
            emit_secret_event(
                "SECRET_RETRIEVED",
                audit_session_id or session_token,
                consumer_envs=[normalized_env],
                team_id=team_id,
            )
            return value
    return None


def rewrap_session_secrets(session_token: str, *, audit_session_id: str = "", team_id: str = "") -> int:
    """Re-encrypt all secrets for a session under the currently active key."""
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT name, ciphertext, nonce FROM secrets WHERE session_token = ?",
            (session_token,),
        ).fetchall()
        updated = 0
        now = _utc_now()
        for row in rows:
            value = decrypt_secret(row["ciphertext"], row["nonce"])
            ciphertext, nonce = encrypt_secret(value)
            conn.execute(
                "UPDATE secrets SET ciphertext = ?, nonce = ?, updated_at = ? "
                "WHERE session_token = ? AND name = ?",
                (ciphertext, nonce, now, session_token, row["name"]),
            )
            updated += 1
        conn.commit()
    emit_secret_event("VAULT_KEY_ROTATION_COMPLETED", audit_session_id or session_token, count=updated, team_id=team_id)
    return updated


def migrate_session_secrets(conn, from_session_id: str, to_session_id: str) -> int:
    """Move secret rows between session tokens without decrypting values."""
    rows = conn.execute(
        "SELECT name, ciphertext, nonce, consumer_envs, created_at, updated_at "
        "FROM secrets WHERE session_token = ?",
        (from_session_id,),
    ).fetchall()
    migrated = 0
    migrated_names = []
    insert_sql = (
        "INSERT INTO secrets "  # nosec B608
        "(session_token, name, ciphertext, nonce, consumer_envs, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        + dialect_for_backend(DB_BACKEND).insert_or_ignore_clause(("session_token", "name"))
    )
    for row in rows:
        cur = conn.execute(
            insert_sql,
            (
                to_session_id,
                row["name"],
                row["ciphertext"],
                row["nonce"],
                row["consumer_envs"],
                row["created_at"],
                row["updated_at"],
            ),
        )
        if cur.rowcount:
            migrated += 1
            migrated_names.append(str(row["name"]))
    if migrated_names:
        conn.executemany(
            "DELETE FROM secrets WHERE session_token = ? AND name = ?",
            [[from_session_id, name] for name in migrated_names],
        )
    return migrated
