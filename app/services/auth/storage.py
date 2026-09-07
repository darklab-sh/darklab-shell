# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Database-only lifecycle operations for principals and credentials."""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
from typing import Any, TypeVar

from core.database_access import get_db_backend
from core.database_backend import DatabaseBackend, integrity_error_types
from services.storage.transactions import run_read, run_transaction
from services.workspace.models import WorkspaceSettings
from services.workspace.settings import workspace_settings

from .contracts import (
    CREDENTIAL_DIGEST_ALGORITHM,
    CREDENTIAL_SECRET_MAX_LENGTH,
    CredentialMetadata,
    CredentialNotFound,
    CredentialRevoked,
    GENERATED_ID_ATTEMPTS,
    IdentityStorageError,
    IssuedCredential,
    LAST_USED_WRITE_INTERVAL_SECONDS,
    MAX_CREDENTIAL_LABEL_LENGTH,
    MAX_REASON_LENGTH,
    PersonalWorkspaceRecord,
    PrincipalBundle,
    PrincipalDisabled,
    PrincipalNotFound,
    PrincipalRecord,
    WorkspaceAlreadyAttached,
    WorkspaceStorageError,
    bounded_text,
    new_identifier,
    parse_timestamp,
    timestamp,
    validate_identifier,
)
from .verifier_keys import credential_verifier_digest, ensure_active_verifier_root
from .workspace_storage import (
    anonymous_workspace_storage_key,
    new_workspace_storage_key,
    resolve_workspace_storage_path,
    validate_workspace_storage_key,
)


_T = TypeVar("_T")
_CREDENTIAL_SECRET_PREFIX = {
    "portable": "dlc_v1_",
    "pat": "dlp_v1_",
}


def _run_read(callback: Callable[[Any], _T], *, conn: Any | None, connect: Callable[[], Any] | None) -> _T:
    if conn is not None:
        return callback(conn)
    return run_read(callback, connect=connect)


def _run_transaction(
    callback: Callable[[Any], _T],
    *,
    conn: Any | None,
    connect: Callable[[], Any] | None,
) -> _T:
    if conn is not None:
        _savepoint(conn, "auth_storage_operation")
        try:
            result = callback(conn)
        except BaseException:
            _rollback_savepoint(conn, "auth_storage_operation")
            raise
        _release_savepoint(conn, "auth_storage_operation")
        return result
    return run_transaction(callback, connect=connect)


def _row_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except (TypeError, ValueError) as exc:
        raise IdentityStorageError("database rows must expose named columns") from exc


def _stored_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        active = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return active.astimezone(timezone.utc).isoformat()
    return str(value)


def _principal_record(row: Any) -> PrincipalRecord:
    data = _row_dict(row)
    return PrincipalRecord(
        id=str(data["id"]),
        status=str(data["status"]),
        disabled_reason=str(data.get("disabled_reason") or ""),
        created_at=_stored_timestamp(data["created_at"]) or "",
        updated_at=_stored_timestamp(data["updated_at"]) or "",
        disabled_at=_stored_timestamp(data.get("disabled_at")),
    )


def _workspace_record(row: Any) -> PersonalWorkspaceRecord:
    data = _row_dict(row)
    return PersonalWorkspaceRecord(
        id=str(data["id"]),
        principal_id=str(data["principal_id"]),
        storage_key=str(data["storage_key"]),
        created_at=_stored_timestamp(data["created_at"]) or "",
    )


def _credential_metadata(row: Any) -> CredentialMetadata:
    data = _row_dict(row)
    return CredentialMetadata(
        id=str(data["id"]),
        public_prefix=str(data["public_prefix"]),
        principal_id=str(data["principal_id"]),
        credential_type=str(data["credential_type"]),
        label=str(data.get("label") or ""),
        verifier_root_version=int(data["verifier_root_version"]),
        digest_algorithm=str(data["digest_algorithm"]),
        created_by_credential_id=(str(data["created_by_credential_id"]) if data.get("created_by_credential_id") else None),
        created_at=_stored_timestamp(data["created_at"]) or "",
        updated_at=_stored_timestamp(data["updated_at"]) or "",
        last_used_at=_stored_timestamp(data.get("last_used_at")),
        expires_at=_stored_timestamp(data.get("expires_at")),
        revoked_at=_stored_timestamp(data.get("revoked_at")),
        revocation_reason=str(data.get("revocation_reason") or ""),
    )


def _database_backend(conn: Any) -> DatabaseBackend:
    explicit = getattr(conn, "database_backend", None)
    if explicit is not None:
        return DatabaseBackend(explicit)
    return DatabaseBackend(get_db_backend())


def _is_integrity_error(conn: Any, exc: BaseException) -> bool:
    return isinstance(exc, integrity_error_types(_database_backend(conn)))


def _secret_material(credential_type: str, credential_id: str) -> tuple[str, bytes]:
    try:
        prefix = _CREDENTIAL_SECRET_PREFIX[credential_type]
    except KeyError as exc:
        raise IdentityStorageError("unsupported credential type") from exc
    secret_bytes = secrets.token_bytes(32)
    encoded = base64.urlsafe_b64encode(secret_bytes).rstrip(b"=").decode("ascii")
    secret = f"{prefix}{credential_id}_{encoded}"
    if len(secret) > CREDENTIAL_SECRET_MAX_LENGTH:
        raise IdentityStorageError("generated credential exceeds the format limit")
    return secret, secret_bytes


def _principal_row(conn: Any, principal_id: str) -> Any:
    validated = validate_identifier(principal_id, "principal")
    row = conn.execute("SELECT * FROM principals WHERE id = ?", (validated,)).fetchone()
    if row is None:
        raise PrincipalNotFound("principal was not found")
    return row


def _active_principal_row(conn: Any, principal_id: str) -> Any:
    row = _principal_row(conn, principal_id)
    if str(_row_dict(row).get("status")) != "active":
        raise PrincipalDisabled("principal is disabled")
    return row


def _credential_row(conn: Any, principal_id: str, credential_id: str) -> Any:
    validated_principal = validate_identifier(principal_id, "principal")
    kind = "pat" if str(credential_id).startswith("pat_") else "portable"
    validated_credential = validate_identifier(credential_id, kind)
    row = conn.execute(
        "SELECT * FROM credentials WHERE id = ? AND principal_id = ?",
        (validated_credential, validated_principal),
    ).fetchone()
    if row is None:
        raise CredentialNotFound("credential was not found")
    return row


def _savepoint(conn: Any, name: str) -> None:
    conn.execute(f"SAVEPOINT {name}")  # nosec - static internal names only


def _rollback_savepoint(conn: Any, name: str) -> None:
    conn.execute(f"ROLLBACK TO SAVEPOINT {name}")  # nosec - static internal names only
    conn.execute(f"RELEASE SAVEPOINT {name}")  # nosec - static internal names only


def _release_savepoint(conn: Any, name: str) -> None:
    conn.execute(f"RELEASE SAVEPOINT {name}")  # nosec - static internal names only


def _insert_credential(
    conn: Any,
    *,
    principal_id: str,
    credential_type: str,
    label: str,
    expires_at: str | None,
    created_by_credential_id: str | None,
    created_at: str,
    verifier_root_version: int,
    verifier_root: bytes,
) -> IssuedCredential:
    last_error: BaseException | None = None
    for _attempt in range(GENERATED_ID_ATTEMPTS):
        credential_id = new_identifier(credential_type)
        secret, secret_bytes = _secret_material(credential_type, credential_id)
        digest = credential_verifier_digest(
            verifier_root,
            credential_type,
            credential_id,
            secret_bytes,
        )
        _savepoint(conn, "credential_issue")
        try:
            conn.execute(
                "INSERT INTO credentials "
                "(id, public_prefix, principal_id, credential_type, label, verifier_digest, "
                "verifier_root_version, digest_algorithm, created_by_credential_id, created_at, "
                "updated_at, last_used_at, expires_at, revoked_at, revocation_reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, '')",
                (
                    credential_id,
                    credential_id[:12],
                    principal_id,
                    credential_type,
                    label,
                    digest,
                    verifier_root_version,
                    CREDENTIAL_DIGEST_ALGORITHM,
                    created_by_credential_id,
                    created_at,
                    created_at,
                    expires_at,
                ),
            )
        except BaseException as exc:
            _rollback_savepoint(conn, "credential_issue")
            if not _is_integrity_error(conn, exc):
                raise
            last_error = exc
            continue
        _release_savepoint(conn, "credential_issue")
        row = conn.execute("SELECT * FROM credentials WHERE id = ?", (credential_id,)).fetchone()
        return IssuedCredential(metadata=_credential_metadata(row), secret=secret)
    raise IdentityStorageError("could not allocate a unique credential id") from last_error


def create_principal_with_credential(
    *,
    anonymous_id: str | None = None,
    credential_label: str = "",
    settings: WorkspaceSettings | None = None,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> PrincipalBundle:
    """Create a principal, workspace, and first portable credential atomically."""
    label = bounded_text(
        credential_label,
        field_name="credential label",
        maximum=MAX_CREDENTIAL_LABEL_LENGTH,
    )
    active_settings = settings or workspace_settings()
    preserved_key = anonymous_workspace_storage_key(anonymous_id) if anonymous_id is not None else None

    def operation(active_conn: Any) -> PrincipalBundle:
        verifier_version, verifier_root = ensure_active_verifier_root(active_conn)
        last_error: BaseException | None = None
        for _attempt in range(GENERATED_ID_ATTEMPTS):
            principal_id = new_identifier("principal")
            workspace_id = new_identifier("workspace")
            storage_key = preserved_key or new_workspace_storage_key()
            try:
                validate_workspace_storage_key(
                    storage_key,
                    active_settings,
                    conn=active_conn,
                    allow_existing_directory=preserved_key is not None,
                )
            except WorkspaceAlreadyAttached:
                if preserved_key is not None:
                    raise
                continue
            except WorkspaceStorageError:
                if preserved_key is not None:
                    raise
                continue
            created_at = timestamp()
            _savepoint(active_conn, "principal_create")
            try:
                active_conn.execute(
                    "INSERT INTO principals "
                    "(id, status, disabled_reason, created_at, updated_at, disabled_at) "
                    "VALUES (?, 'active', '', ?, ?, NULL)",
                    (principal_id, created_at, created_at),
                )
                active_conn.execute(
                    "INSERT INTO personal_workspaces (id, principal_id, storage_key, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (workspace_id, principal_id, storage_key, created_at),
                )
                issued = _insert_credential(
                    active_conn,
                    principal_id=principal_id,
                    credential_type="portable",
                    label=label,
                    expires_at=None,
                    created_by_credential_id=None,
                    created_at=created_at,
                    verifier_root_version=verifier_version,
                    verifier_root=verifier_root,
                )
            except BaseException as exc:
                _rollback_savepoint(active_conn, "principal_create")
                if not _is_integrity_error(active_conn, exc):
                    raise
                if preserved_key is not None:
                    existing = active_conn.execute(
                        "SELECT id FROM personal_workspaces WHERE storage_key = ?",
                        (preserved_key,),
                    ).fetchone()
                    if existing is not None:
                        raise WorkspaceAlreadyAttached("anonymous workspace is already attached") from exc
                last_error = exc
                continue
            _release_savepoint(active_conn, "principal_create")
            principal_row = active_conn.execute(
                "SELECT * FROM principals WHERE id = ?",
                (principal_id,),
            ).fetchone()
            workspace_row = active_conn.execute(
                "SELECT * FROM personal_workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
            return PrincipalBundle(
                principal=_principal_record(principal_row),
                workspace=_workspace_record(workspace_row),
                credential=issued,
            )
        raise IdentityStorageError("could not allocate unique principal storage") from last_error

    return _run_transaction(operation, conn=conn, connect=connect)


def issue_credential(
    principal_id: str,
    *,
    credential_type: str = "portable",
    label: str = "",
    expires_at: str | datetime | None = None,
    created_by_credential_id: str | None = None,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> IssuedCredential:
    kind = str(credential_type or "")
    if kind not in _CREDENTIAL_SECRET_PREFIX:
        raise IdentityStorageError("unsupported credential type")
    normalized_label = bounded_text(label, field_name="credential label", maximum=MAX_CREDENTIAL_LABEL_LENGTH)
    normalized_expiry = parse_timestamp(expires_at, field_name="credential expiry")

    def operation(active_conn: Any) -> IssuedCredential:
        _active_principal_row(active_conn, principal_id)
        if created_by_credential_id:
            creator = _credential_row(active_conn, principal_id, created_by_credential_id)
            if _row_dict(creator).get("revoked_at") is not None:
                raise CredentialRevoked("creator credential is revoked")
        verifier_version, verifier_root = ensure_active_verifier_root(active_conn)
        return _insert_credential(
            active_conn,
            principal_id=principal_id,
            credential_type=kind,
            label=normalized_label,
            expires_at=normalized_expiry,
            created_by_credential_id=created_by_credential_id,
            created_at=timestamp(),
            verifier_root_version=verifier_version,
            verifier_root=verifier_root,
        )

    return _run_transaction(operation, conn=conn, connect=connect)


def list_credentials(
    principal_id: str,
    *,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> tuple[CredentialMetadata, ...]:
    def operation(active_conn: Any) -> tuple[CredentialMetadata, ...]:
        _principal_row(active_conn, principal_id)
        rows = active_conn.execute(
            "SELECT * FROM credentials WHERE principal_id = ? "
            "ORDER BY created_at DESC, id DESC",
            (principal_id,),
        ).fetchall()
        return tuple(_credential_metadata(row) for row in rows)

    return _run_read(operation, conn=conn, connect=connect)


def rename_credential(
    principal_id: str,
    credential_id: str,
    label: str,
    *,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> CredentialMetadata:
    normalized = bounded_text(label, field_name="credential label", maximum=MAX_CREDENTIAL_LABEL_LENGTH)

    def operation(active_conn: Any) -> CredentialMetadata:
        _active_principal_row(active_conn, principal_id)
        _credential_row(active_conn, principal_id, credential_id)
        active_conn.execute(
            "UPDATE credentials SET label = ?, updated_at = ? WHERE id = ? AND principal_id = ?",
            (normalized, timestamp(), credential_id, principal_id),
        )
        return _credential_metadata(_credential_row(active_conn, principal_id, credential_id))

    return _run_transaction(operation, conn=conn, connect=connect)


def set_credential_expiry(
    principal_id: str,
    credential_id: str,
    expires_at: str | datetime | None,
    *,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> CredentialMetadata:
    normalized = parse_timestamp(expires_at, field_name="credential expiry")

    def operation(active_conn: Any) -> CredentialMetadata:
        _active_principal_row(active_conn, principal_id)
        _credential_row(active_conn, principal_id, credential_id)
        active_conn.execute(
            "UPDATE credentials SET expires_at = ?, updated_at = ? WHERE id = ? AND principal_id = ?",
            (normalized, timestamp(), credential_id, principal_id),
        )
        return _credential_metadata(_credential_row(active_conn, principal_id, credential_id))

    return _run_transaction(operation, conn=conn, connect=connect)


def revoke_credential(
    principal_id: str,
    credential_id: str,
    *,
    reason: str = "",
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> CredentialMetadata:
    normalized_reason = bounded_text(reason, field_name="revocation reason", maximum=MAX_REASON_LENGTH)

    def operation(active_conn: Any) -> CredentialMetadata:
        _principal_row(active_conn, principal_id)
        row = _credential_row(active_conn, principal_id, credential_id)
        if _row_dict(row).get("revoked_at") is None:
            now = timestamp()
            active_conn.execute(
                "UPDATE credentials SET revoked_at = ?, revocation_reason = ?, updated_at = ? "
                "WHERE id = ? AND principal_id = ? AND revoked_at IS NULL",
                (now, normalized_reason, now, credential_id, principal_id),
            )
        return _credential_metadata(_credential_row(active_conn, principal_id, credential_id))

    return _run_transaction(operation, conn=conn, connect=connect)


def rotate_credential(
    principal_id: str,
    credential_id: str,
    *,
    label: str | None = None,
    expires_at: str | datetime | None = None,
    reason: str = "rotated",
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> IssuedCredential:
    normalized_reason = bounded_text(reason, field_name="revocation reason", maximum=MAX_REASON_LENGTH)

    def operation(active_conn: Any) -> IssuedCredential:
        _active_principal_row(active_conn, principal_id)
        current = _credential_metadata(_credential_row(active_conn, principal_id, credential_id))
        if current.revoked_at is not None:
            raise CredentialRevoked("credential is already revoked")
        replacement_label = current.label if label is None else bounded_text(
            label,
            field_name="credential label",
            maximum=MAX_CREDENTIAL_LABEL_LENGTH,
        )
        replacement_expiry = current.expires_at if expires_at is None else parse_timestamp(
            expires_at,
            field_name="credential expiry",
        )
        verifier_version, verifier_root = ensure_active_verifier_root(active_conn)
        replacement = _insert_credential(
            active_conn,
            principal_id=principal_id,
            credential_type=current.credential_type,
            label=replacement_label,
            expires_at=replacement_expiry,
            created_by_credential_id=current.id,
            created_at=timestamp(),
            verifier_root_version=verifier_version,
            verifier_root=verifier_root,
        )
        now = timestamp()
        active_conn.execute(
            "UPDATE credentials SET revoked_at = ?, revocation_reason = ?, updated_at = ? "
            "WHERE id = ? AND principal_id = ? AND revoked_at IS NULL",
            (now, normalized_reason, now, current.id, principal_id),
        )
        return replacement

    return _run_transaction(operation, conn=conn, connect=connect)


def disable_principal(
    principal_id: str,
    *,
    reason: str,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> PrincipalRecord:
    normalized = bounded_text(reason, field_name="disable reason", maximum=MAX_REASON_LENGTH)
    if not normalized:
        raise IdentityStorageError("disable reason is required")

    def operation(active_conn: Any) -> PrincipalRecord:
        _principal_row(active_conn, principal_id)
        now = timestamp()
        active_conn.execute(
            "UPDATE principals SET status = 'disabled', disabled_reason = ?, "
            "disabled_at = ?, updated_at = ? WHERE id = ?",
            (normalized, now, now, principal_id),
        )
        return _principal_record(_principal_row(active_conn, principal_id))

    return _run_transaction(operation, conn=conn, connect=connect)


def enable_principal(
    principal_id: str,
    *,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> PrincipalRecord:
    def operation(active_conn: Any) -> PrincipalRecord:
        _principal_row(active_conn, principal_id)
        active_conn.execute(
            "UPDATE principals SET status = 'active', disabled_reason = '', "
            "disabled_at = NULL, updated_at = ? WHERE id = ?",
            (timestamp(), principal_id),
        )
        return _principal_record(_principal_row(active_conn, principal_id))

    return _run_transaction(operation, conn=conn, connect=connect)


def touch_credential_last_used(
    credential_id: str,
    *,
    used_at: datetime | None = None,
    minimum_interval_seconds: int = LAST_USED_WRITE_INTERVAL_SECONDS,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> bool:
    kind = "pat" if str(credential_id).startswith("pat_") else "portable"
    validated = validate_identifier(credential_id, kind)
    interval = max(0, int(minimum_interval_seconds))
    active = used_at or datetime.now(timezone.utc)
    if active.tzinfo is None:
        active = active.replace(tzinfo=timezone.utc)
    active = active.astimezone(timezone.utc)
    cutoff = active - timedelta(seconds=interval)

    def operation(active_conn: Any) -> bool:
        result = active_conn.execute(
            "UPDATE credentials SET last_used_at = ? "
            "WHERE id = ? AND revoked_at IS NULL "
            "AND (last_used_at IS NULL OR last_used_at <= ?)",
            (timestamp(active), validated, timestamp(cutoff)),
        )
        return int(getattr(result, "rowcount", 0) or 0) > 0

    return _run_transaction(operation, conn=conn, connect=connect)


def get_personal_workspace(
    principal_id: str,
    *,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> PersonalWorkspaceRecord:
    def operation(active_conn: Any) -> PersonalWorkspaceRecord:
        _principal_row(active_conn, principal_id)
        row = active_conn.execute(
            "SELECT * FROM personal_workspaces WHERE principal_id = ?",
            (principal_id,),
        ).fetchone()
        if row is None:
            raise IdentityStorageError("principal has no personal workspace")
        return _workspace_record(row)

    return _run_read(operation, conn=conn, connect=connect)


def get_personal_workspace_path(
    principal_id: str,
    *,
    settings: WorkspaceSettings | None = None,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> Path:
    workspace = get_personal_workspace(principal_id, conn=conn, connect=connect)
    return resolve_workspace_storage_path(workspace.storage_key, settings or workspace_settings())
