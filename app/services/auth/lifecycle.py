# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Audited principal and credential lifecycle orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from services.audit.models import AuditEventType, AuditTargetType
from services.audit.recorder import record_event
from services.storage.transactions import run_read, run_transaction
from services.workspace.models import WorkspaceSettings

from . import storage
from .contracts import CredentialMetadata, IssuedCredential, PrincipalBundle, PrincipalRecord, timestamp
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


def list_credential_durable_work(
    context: AuthenticatedContext,
    credential_id: str,
    *,
    connect: Callable[[], Any] | None = None,
) -> Any:
    if context.credential_type == "pat" and credential_id != context.credential_id:
        raise PermissionError("PATs may inspect only themselves")

    def operation(conn: Any) -> Any:
        from .background_authorization import DurableWorkDisposition, durable_work_for_credential  # noqa: PLC0415

        # Reuse the owner-scoped lookup so an id from another principal is
        # indistinguishable from a missing credential.
        storage._credential_row(conn, context.principal_id, credential_id)  # noqa: SLF001
        return DurableWorkDisposition(
            affected=durable_work_for_credential(conn, context.principal_id, credential_id),
        )

    return run_read(operation, connect=connect)


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


def operator_issue(
    principal_id: str,
    *,
    credential_type: str = "portable",
    label: str = "",
    expires_at: str | datetime | None = None,
    scopes: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None = None,
    connect: Callable[[], Any] | None = None,
) -> IssuedCredential:
    """Issue a credential through the local operator boundary."""
    def operation(conn: Any) -> IssuedCredential:
        issued = storage.issue_credential(
            principal_id,
            credential_type=credential_type,
            label=label,
            expires_at=expires_at,
            scopes=scopes,
            conn=conn,
        )
        record_event(
            AuditEventType.CREDENTIAL_CREATE,
            target_type=AuditTargetType.CREDENTIAL,
            target_id=issued.metadata.id,
            details=_credential_details(issued.metadata, source="local_operator"),
            conn=conn,
        )
        return issued

    return run_transaction(operation, connect=connect)


def operator_recover(
    principal_id: str,
    *,
    label: str = "Recovered access",
    connect: Callable[[], Any] | None = None,
) -> IssuedCredential:
    """Revoke existing credentials and return one replacement exactly once."""
    def operation(conn: Any) -> IssuedCredential:
        from .background_authorization import pause_durable_work_for_credential  # noqa: PLC0415

        current = storage.list_credentials(principal_id, conn=conn)
        for credential in current:
            if credential.revoked_at is not None:
                continue
            storage.revoke_credential(
                principal_id,
                credential.id,
                reason="operator recovery",
                allow_lockout=True,
                conn=conn,
            )
            pause_durable_work_for_credential(conn, principal_id, credential.id)
            record_event(
                AuditEventType.CREDENTIAL_REVOKE,
                target_type=AuditTargetType.CREDENTIAL,
                target_id=credential.id,
                details={"credential_type": credential.credential_type, "source": "local_operator_recovery"},
                conn=conn,
            )
        replacement = storage.issue_credential(
            principal_id,
            credential_type="portable",
            label=label,
            conn=conn,
        )
        record_event(
            AuditEventType.CREDENTIAL_CREATE,
            target_type=AuditTargetType.CREDENTIAL,
            target_id=replacement.metadata.id,
            details=_credential_details(replacement.metadata, source="local_operator_recovery"),
            conn=conn,
        )
        return replacement

    return run_transaction(operation, connect=connect)


def operator_summary(
    principal_id: str,
    *,
    connect: Callable[[], Any] | None = None,
) -> tuple[PrincipalRecord, tuple[CredentialMetadata, ...]]:
    """Return non-secret principal and credential metadata to a local operator."""
    def operation(conn: Any) -> tuple[PrincipalRecord, tuple[CredentialMetadata, ...]]:
        return (
            storage.get_principal(principal_id, conn=conn),
            storage.list_credentials(principal_id, conn=conn),
        )

    return run_read(operation, connect=connect)


def operator_change_expiry(
    principal_id: str,
    credential_id: str,
    expires_at: str | datetime | None,
    *,
    connect: Callable[[], Any] | None = None,
) -> CredentialMetadata:
    """Change credential expiry through the local operator boundary."""
    def operation(conn: Any) -> CredentialMetadata:
        metadata = storage.set_credential_expiry(
            principal_id,
            credential_id,
            expires_at,
            conn=conn,
        )
        record_event(
            AuditEventType.CREDENTIAL_EXPIRY,
            target_id=metadata.id,
            details=_credential_details(
                metadata,
                expires_at=metadata.expires_at or "",
                source="local_operator",
            ),
            conn=conn,
        )
        return metadata

    return run_transaction(operation, connect=connect)


def operator_rotate(
    principal_id: str,
    credential_id: str,
    *,
    label: str | None = None,
    expires_at: str | datetime | None = None,
    connect: Callable[[], Any] | None = None,
) -> IssuedCredential:
    """Rotate a credential through the local operator boundary."""
    def operation(conn: Any) -> IssuedCredential:
        replacement = storage.rotate_credential(
            principal_id,
            credential_id,
            label=label,
            expires_at=expires_at,
            conn=conn,
        )
        record_event(
            AuditEventType.CREDENTIAL_ROTATE,
            target_id=credential_id,
            details=_credential_details(
                replacement.metadata,
                target_id=replacement.metadata.id,
                source="local_operator",
            ),
            conn=conn,
        )
        return replacement

    return run_transaction(operation, connect=connect)


def operator_revoke(
    principal_id: str,
    credential_id: str,
    *,
    reason: str,
    confirm_lockout: bool = False,
    pause_related_work: bool = False,
    connect: Callable[[], Any] | None = None,
) -> tuple[CredentialMetadata, Any]:
    """Revoke a credential and report its durable-work disposition."""
    def operation(conn: Any) -> tuple[CredentialMetadata, Any]:
        from .background_authorization import (  # noqa: PLC0415
            DurableWorkDisposition,
            durable_work_for_credential,
            pause_durable_work_for_credential,
        )

        metadata = storage.revoke_credential(
            principal_id,
            credential_id,
            reason=reason,
            allow_lockout=confirm_lockout,
            conn=conn,
        )
        record_event(
            AuditEventType.CREDENTIAL_REVOKE,
            target_id=metadata.id,
            details=_credential_details(
                metadata,
                reason=metadata.revocation_reason,
                pause_related_work=bool(pause_related_work),
                source="local_operator",
            ),
            conn=conn,
        )
        if pause_related_work:
            disposition = pause_durable_work_for_credential(conn, principal_id, metadata.id)
        else:
            disposition = DurableWorkDisposition(
                affected=durable_work_for_credential(conn, principal_id, metadata.id),
            )
        return metadata, disposition

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
    pause_related_work: bool = False,
    include_durable_work: bool = False,
    request_fields: Mapping[str, Any] | None = None,
    connect: Callable[[], Any] | None = None,
) -> Any:
    if context.credential_type == "pat" and credential_id != context.credential_id:
        raise PermissionError("PATs may revoke only themselves")

    def operation(conn: Any) -> tuple[CredentialMetadata, Any]:
        from .background_authorization import (  # noqa: PLC0415
            DurableWorkDisposition,
            durable_work_for_credential,
            pause_durable_work_for_credential,
        )

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
            details=_credential_details(
                metadata,
                reason=metadata.revocation_reason,
                pause_related_work=bool(pause_related_work),
            ),
            conn=conn,
            **_audit_fields(request_fields),
        )
        if pause_related_work:
            disposition = pause_durable_work_for_credential(conn, context.principal_id, metadata.id)
        else:
            disposition = DurableWorkDisposition(
                affected=durable_work_for_credential(conn, context.principal_id, metadata.id),
            )
        return metadata, disposition

    metadata, disposition = run_transaction(operation, connect=connect)
    return (metadata, disposition) if include_durable_work else metadata


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
        if not enabled:
            from .background_authorization import suspend_principal_background_work  # noqa: PLC0415

            suspend_principal_background_work(conn, principal_id, now=timestamp())
        record_event(
            AuditEventType.PRINCIPAL_ENABLE if enabled else AuditEventType.PRINCIPAL_DISABLE,
            target_id=principal.id,
            details={"reason": reason} if reason else {},
            conn=conn,
            **_audit_fields(request_fields),
        )
        return principal

    principal = run_transaction(operation, connect=connect)
    if not enabled:
        from .background_runtime import stop_principal_active_work  # noqa: PLC0415

        stop_principal_active_work(principal_id)
    return principal


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
