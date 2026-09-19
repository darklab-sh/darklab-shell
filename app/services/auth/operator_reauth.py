# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Verified operator step-up rotates a live session without extending its life."""

import logging
from datetime import datetime, timezone

from core.database_access import get_db_backend
from core.database_backend import DatabaseBackend

from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.storage.transactions import run_transaction

from . import browser_sessions, operator_grants
from .contracts import IdentityStorageError, timestamp

log = logging.getLogger("shell")


class OperatorReauthenticationError(IdentityStorageError):
    """Proof no longer belongs to an eligible, live operator session."""


def rotate_verified_session(
    context, config, *, credential_context=None, provider_proof=None, now=None, request_fields=None,
):
    if (context.authentication_method != "browser_cookie" or bool(credential_context) == bool(provider_proof)
            or config["access_profile"] not in {"token_required", "oidc_required", "mixed"}):
        raise OperatorReauthenticationError("verification is unavailable")

    def operation(conn):
        operator_grants.lock_principal(conn, context.principal_id)
        if not operator_grants.has_grant(context.principal_id, conn=conn):
            raise OperatorReauthenticationError("verification is unavailable")
        if credential_context:
            query = ("SELECT id FROM credentials WHERE id = ? FOR UPDATE"
                     if DatabaseBackend(get_db_backend()) == DatabaseBackend.POSTGRES
                     else "SELECT id FROM credentials WHERE id = ?")
            conn.execute(query, (credential_context.credential_id,)).fetchone()
        source = browser_sessions.lock_rotation_source(
            conn, session_id=context.browser_session_id, principal_id=context.principal_id,
            idle_seconds=int(config["browser_session_idle_minutes"]) * 60, now=now,
        )
        active_now = now or datetime.now(timezone.utc)
        if credential_context:
            if (credential_context.principal_id != context.principal_id
                    or credential_context.credential_type != "portable" or config["access_profile"] == "oidc_required"):
                raise OperatorReauthenticationError("verification is unavailable")
            credential_id, identity_id = credential_context.credential_id, ""
            provider_authenticated_at = None
        else:
            if config["access_profile"] not in {"oidc_required", "mixed"} or not source["oidc_identity_id"]:
                raise OperatorReauthenticationError("verification is unavailable")
            if (provider_proof.issuer != source["oidc_issuer"] or provider_proof.subject != source["oidc_subject"]
                    or not provider_proof.authenticated_at):
                raise OperatorReauthenticationError("verification is unavailable")
            credential_id, identity_id = "", source["oidc_identity_id"]
            provider_authenticated_at = provider_proof.authenticated_at
        issued = browser_sessions.create_browser_session(
            principal_id=context.principal_id, credential_id=credential_id, oidc_identity_id=identity_id,
            absolute_seconds=int(config["browser_session_absolute_hours"]) * 3600,
            replace_session_id=context.browser_session_id, authenticated_at=timestamp(active_now),
            provider_authenticated_at=provider_authenticated_at,
            absolute_expires_at=source["absolute_expires_at"], now=active_now, conn=conn,
        )
        fields = request_fields or {}
        record_event(
            AuditEventType.INSTANCE_OPERATOR_REAUTH, target_id=context.principal_id,
            actor_principal_id=context.principal_id, actor_credential_id=credential_id,
            details={"source": "credential" if credential_context else "oidc", "result": "verified"},
            request_id=fields.get("request_id", ""), client_ip=fields.get("client_ip", ""), conn=conn,
        )
        return issued

    result = run_transaction(operation)
    log.info("INSTANCE_OPERATOR_REAUTHENTICATED", extra={
        "principal_id": context.principal_id, "source": "credential" if credential_context else "oidc",
    })
    return result
