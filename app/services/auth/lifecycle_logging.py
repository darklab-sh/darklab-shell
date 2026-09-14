# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Publish safe lifecycle milestones only after their transaction commits."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import logging
from typing import Any, Literal, TypeVar

from flask import has_request_context, request

from core.database_access import get_db_backend
from core.database_backend import DatabaseBackend
from services.storage.transactions import run_transaction

from .contracts import CredentialMetadata, PrincipalRecord
from .observability import _request_value

log = logging.getLogger("shell")
_T = TypeVar("_T")


class LifecycleEvents:
    def __init__(self, source: str, request_fields: Mapping[str, Any] | None = None) -> None:
        request_id = (request_fields or {}).get("request_id")
        if request_id is None and has_request_context():
            request_id = request.environ.get("darklab_request_id")
        self._common = {
            "source": source,
            "request_id": _request_value(request_id, 64),
        }
        self._events: list[tuple[str, dict[str, Any]]] = []

    def principal(
        self, event: Literal["PRINCIPAL_CREATED", "PRINCIPAL_STATUS_CHANGED"], principal: PrincipalRecord,
    ) -> None:
        self._events.append((event, {"principal_id": principal.id, "status": principal.status}))

    def credential(
        self,
        event: Literal["CREDENTIAL_CREATED", "CREDENTIAL_ROTATED", "CREDENTIAL_REVOKED"],
        metadata: CredentialMetadata,
        *,
        previous_credential_id: str = "",
        paused_work_count: int | None = None,
    ) -> None:
        fields: dict[str, Any] = {
            "principal_id": metadata.principal_id,
            "credential_id": metadata.id,
            "credential_type": metadata.credential_type,
            "scope_count": len(metadata.scopes),
        }
        if previous_credential_id:
            fields["previous_credential_id"] = previous_credential_id
        if paused_work_count is not None:
            fields["paused_work_count"] = paused_work_count
        self._events.append((event, fields))

    def run(self, operation: Callable[[Any], _T], *, connect: Callable[[], Any] | None = None) -> _T:
        def transaction(conn: Any) -> _T:
            backend = DatabaseBackend(getattr(conn, "database_backend", None) or get_db_backend())
            if backend == DatabaseBackend.SQLITE and not conn.in_transaction:
                # A top-level SAVEPOINT would commit when released. Reserve the
                # enclosing write transaction before any storage savepoints.
                conn.execute("BEGIN IMMEDIATE")
            return operation(conn)

        result = run_transaction(transaction, connect=connect)
        for event, fields in self._events:
            log.info(event, extra={**self._common, **fields})
        return result
