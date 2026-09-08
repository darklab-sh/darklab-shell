# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Audited principal and credential lifecycle orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from services.audit.models import AuditEventType, AuditTargetType
from services.audit.recorder import record_event
from services.storage.transactions import run_transaction
from services.workspace.models import WorkspaceSettings

from . import storage
from .contracts import CredentialMetadata, IssuedCredential, PrincipalBundle, PrincipalRecord
from .resolver import AuthenticatedContext, AuthenticationResult


def _audit_fields(request_fields: Mapping[str, Any] | None) -> dict[str, Any]:
    fields = dict(request_fields or {})
    return {
        key: fields.get(key, "")
        for key in ("request_id", "client_ip", "user_agent")
    }


def _credential_details(metadata: CredentialMetadata, **extra: Any) -> dict[str, Any]:
    return {
        "credential_type": metadata.credential_type,
        "scope_count": len(metadata.scopes),
        **extra,
    }


def create_principal(
    *,
    anonymous_id: str,
    credential_label: str = "",
    settings: WorkspaceSettings | None = None,
    request_fields: Mapping[str, Any] | None = None,
    connect: Callable[[], Any] | None = None,
) -> PrincipalBundle:
    def operation(conn: Any) -> PrincipalBundle:
        bundle = storage.create_principal_with_credential(
            anonymous_id=anonymous_id,
            credential_label=credential_label,
            settings=settings,
            conn=conn,
        )
        record_event(
            AuditEventType.PRINCIPAL_CREATE,
            target_type=AuditTargetType.PRINCIPAL,
            target_id=bundle.principal.id,
            details={"source": "anonymous_upgrade"},
            conn=conn,
            **_audit_fields(request_fields),
        )
        record_event(
            AuditEventType.CREDENTIAL_CREATE,
            target_type=AuditTargetType.CREDENTIAL,
            target_id=bundle.credential.metadata.id,
            details=_credential_details(bundle.credential.metadata, source="anonymous_upgrade"),
            conn=conn,
            **_audit_fields(request_fields),
        )
        return bundle

    return run_transaction(operation, connect=connect)


def list_safe_credentials(
    context: AuthenticatedContext,
    *,
    connect: Callable[[], Any] | None = None,
) -> tuple[CredentialMetadata, ...]:
    return storage.list_credentials(context.principal_id, connect=connect)


def issue(
    context: AuthenticatedContext,
    *,
    credential_type: str = "portable",
    label: str = "",
    expires_at: str | datetime | None = None,
    scopes: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None = None,
    request_fields: Mapping[str, Any] | None = None,
    connect: Callable[[], Any] | None = None,
) -> IssuedCredential:
    if context.credential_type == "pat":
        raise PermissionError("PATs cannot issue credentials")

    def operation(conn: Any) -> IssuedCredential:
        issued = storage.issue_credential(
            context.principal_id,
            credential_type=credential_type,
            label=label,
            expires_at=expires_at,
            scopes=scopes,
            created_by_credential_id=context.credential_id,
            conn=conn,
        )
        record_event(
            AuditEventType.CREDENTIAL_CREATE,
            target_type=AuditTargetType.CREDENTIAL,
            target_id=issued.metadata.id,
            details=_credential_details(issued.metadata, source="self_service"),
            conn=conn,
            **_audit_fields(request_fields),
        )
        return issued

    return run_transaction(operation, connect=connect)


def rename(
    context: AuthenticatedContext,
    credential_id: str,
    label: str,
    *,
    request_fields: Mapping[str, Any] | None = None,
    connect: Callable[[], Any] | None = None,
) -> CredentialMetadata:
    if context.credential_type == "pat":
        raise PermissionError("PATs cannot change credential labels")

    def operation(conn: Any) -> CredentialMetadata:
        metadata = storage.rename_credential(context.principal_id, credential_id, label, conn=conn)
        record_event(
            AuditEventType.CREDENTIAL_LABEL,
            target_id=metadata.id,
            details=_credential_details(metadata),
            conn=conn,
            **_audit_fields(request_fields),
        )
        return metadata

    return run_transaction(operation, connect=connect)


def change_expiry(
    context: AuthenticatedContext,
    credential_id: str,
    expires_at: str | datetime | None,
    *,
    request_fields: Mapping[str, Any] | None = None,
    connect: Callable[[], Any] | None = None,
) -> CredentialMetadata:
    if context.credential_type == "pat":
        raise PermissionError("PATs cannot change credential expiry")

    def operation(conn: Any) -> CredentialMetadata:
        metadata = storage.set_credential_expiry(
            context.principal_id,
            credential_id,
            expires_at,
            conn=conn,
        )
        record_event(
            AuditEventType.CREDENTIAL_EXPIRY,
            target_id=metadata.id,
            details=_credential_details(metadata, expires_at=metadata.expires_at or ""),
            conn=conn,
            **_audit_fields(request_fields),
        )
        return metadata

    return run_transaction(operation, connect=connect)


def rotate(
    context: AuthenticatedContext,
    credential_id: str,
    *,
    label: str | None = None,
    expires_at: str | datetime | None = None,
    request_fields: Mapping[str, Any] | None = None,
    connect: Callable[[], Any] | None = None,
) -> IssuedCredential:
    if context.credential_type == "pat":
        raise PermissionError("PATs cannot rotate credentials")

    def operation(conn: Any) -> IssuedCredential:
        replacement = storage.rotate_credential(
            context.principal_id,
            credential_id,
            label=label,
            expires_at=expires_at,
            conn=conn,
        )
        record_event(
            AuditEventType.CREDENTIAL_ROTATE,
            target_id=credential_id,
            details=_credential_details(replacement.metadata, target_id=replacement.metadata.id),
            conn=conn,
            **_audit_fields(request_fields),
        )
        return replacement

    return run_transaction(operation, connect=connect)


def revoke(
    context: AuthenticatedContext,
    credential_id: str,
    *,
    reason: str = "",
    confirm_lockout: bool = False,
    request_fields: Mapping[str, Any] | None = None,
    connect: Callable[[], Any] | None = None,
) -> CredentialMetadata:
    if context.credential_type == "pat" and credential_id != context.credential_id:
        raise PermissionError("PATs may revoke only themselves")

    def operation(conn: Any) -> CredentialMetadata:
        metadata = storage.revoke_credential(
            context.principal_id,
            credential_id,
            reason=reason,
            allow_lockout=confirm_lockout,
            conn=conn,
        )
        record_event(
            AuditEventType.CREDENTIAL_REVOKE,
            target_id=metadata.id,
            details=_credential_details(metadata, reason=metadata.revocation_reason),
            conn=conn,
            **_audit_fields(request_fields),
        )
        return metadata

    return run_transaction(operation, connect=connect)


def set_principal_enabled(
    principal_id: str,
    *,
    enabled: bool,
    reason: str = "",
    request_fields: Mapping[str, Any] | None = None,
    connect: Callable[[], Any] | None = None,
) -> PrincipalRecord:
    def operation(conn: Any) -> PrincipalRecord:
        principal = (
            storage.enable_principal(principal_id, conn=conn)
            if enabled
            else storage.disable_principal(principal_id, reason=reason, conn=conn)
        )
        record_event(
            AuditEventType.PRINCIPAL_ENABLE if enabled else AuditEventType.PRINCIPAL_DISABLE,
            target_id=principal.id,
            details={"reason": reason} if reason else {},
            conn=conn,
            **_audit_fields(request_fields),
        )
        return principal

    return run_transaction(operation, connect=connect)


def record_redemption(
    context: AuthenticatedContext,
    *,
    request_fields: Mapping[str, Any] | None = None,
    conn: Any | None = None,
) -> None:
    record_event(
        AuditEventType.CREDENTIAL_REDEEM,
        target_id=context.credential_id,
        details={
            "credential_type": context.credential_type,
            "authentication_method": context.authentication_method,
        },
        conn=conn,
        **_audit_fields(request_fields),
    )


def record_authentication_failure(
    result: AuthenticationResult,
    *,
    request_fields: Mapping[str, Any] | None = None,
    conn: Any | None = None,
) -> None:
    """Record only the failure class; never persist the submitted value or a fingerprint."""
    record_event(
        AuditEventType.CREDENTIAL_AUTHENTICATION_FAILURE,
        target_id="",
        details={"authentication_state": result.state.value},
        conn=conn,
        **_audit_fields(request_fields),
    )
