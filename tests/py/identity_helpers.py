# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Production-shaped identities for server-side tests.

Positive tests should use these helpers instead of relying on arbitrary strings
that the application would reject outside ``TESTING`` mode. Deliberately invalid
identifiers should remain literal at the call site so their intent stays clear.
"""

from __future__ import annotations

import secrets
import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


_TEST_IDENTITY_NAMESPACE = uuid.UUID("321e676e-0860-438d-9ec2-c0bb0e4c588d")


def anonymous_session_id(label: str | None = None) -> str:
    """Return a canonical anonymous UUID, stable when ``label`` is supplied."""
    if label is None:
        return str(uuid.uuid4())
    digest = hashlib.sha256(_TEST_IDENTITY_NAMESPACE.bytes + str(label).encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest[:16], version=4))


def identity_headers(identity: str) -> dict[str, str]:
    """Return request headers that consistently reuse one identity."""
    return {"X-Session-ID": identity}


def register_durable_session_token(token: str) -> str:
    """Persist a durable token through the same service used by the application."""
    from services.session.storage import create_session_token, session_token_exists  # noqa: PLC0415

    if not str(token).startswith("tok_"):
        raise ValueError("durable test identities must start with 'tok_'")
    if session_token_exists(token):
        return token
    create_session_token(
        token,
        datetime.now(timezone.utc).isoformat(),
        audit_fields={"session_id": "", "actor_session_id": ""},
        audit_details={"source": "test_fixture"},
        audit_target_id=f"{token[:8]}********",
    )
    return token


def durable_session_token(label: str | None = None) -> str:
    """Create and persist a durable token through the production service."""
    suffix = (
        uuid.uuid5(_TEST_IDENTITY_NAMESPACE, f"durable:{label}").hex
        if label
        else secrets.token_hex(16)
    )
    return register_durable_session_token(f"tok_{suffix}")


@dataclass(frozen=True)
class IdentityFixture:
    """An identity and its reusable request headers."""

    value: str

    @property
    def headers(self) -> dict[str, str]:
        return identity_headers(self.value)


@dataclass(frozen=True)
class PrincipalIdentityFixture:
    """A principal's owner id plus its distinct browser and API credentials."""

    principal_id: str
    personal_workspace_id: str
    portable_secret: str
    pat_secret: str

    @property
    def owner_id(self) -> str:
        return self.personal_workspace_id

    def browser_headers(self, *, team_id: str = "") -> dict[str, str]:
        headers = {"X-Darklab-Credential": self.portable_secret}
        if team_id:
            headers["X-Team-ID"] = team_id
        return headers

    def api_headers(self, *, team_id: str = "") -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.pat_secret}"}
        if team_id:
            headers["X-Team-ID"] = team_id
        return headers


_PRINCIPAL_IDENTITIES_BY_WORKSPACE: dict[str, PrincipalIdentityFixture] = {}


def principal_identity(label: str | None = None) -> PrincipalIdentityFixture:
    """Issue separate production-shaped browser and API credentials."""
    from services.auth import storage  # noqa: PLC0415
    from services.auth.contracts import PAT_SCOPES  # noqa: PLC0415

    bundle = storage.create_principal_with_credential(credential_label=label or "Test browser")
    pat = storage.issue_credential(
        bundle.principal.id,
        credential_type="pat",
        label=f"{label or 'Test'} API",
        scopes=PAT_SCOPES,
        created_by_credential_id=bundle.credential.metadata.id,
    )
    fixture = PrincipalIdentityFixture(
        principal_id=bundle.principal.id,
        personal_workspace_id=bundle.workspace.id,
        portable_secret=bundle.credential.secret,
        pat_secret=pat.secret,
    )
    _PRINCIPAL_IDENTITIES_BY_WORKSPACE[fixture.personal_workspace_id] = fixture
    return fixture


def browser_identity_headers(identity: str, *, team_id: str = "") -> dict[str, str]:
    """Use a portable credential for principals and a UUID for anonymous owners."""
    principal = _PRINCIPAL_IDENTITIES_BY_WORKSPACE.get(str(identity))
    if principal is not None:
        return principal.browser_headers(team_id=team_id)
    headers = identity_headers(identity)
    if team_id:
        headers["X-Team-ID"] = team_id
    return headers


def api_identity_headers(identity: str, *, team_id: str = "") -> dict[str, str]:
    """Use the PAT paired with a registered principal workspace owner."""
    try:
        principal = _PRINCIPAL_IDENTITIES_BY_WORKSPACE[str(identity)]
    except KeyError as exc:
        raise ValueError("API test identities must be created with principal_identity()") from exc
    return principal.api_headers(team_id=team_id)


class IdentityClient:
    """Thin Flask test-client adapter that applies one identity by default."""

    def __init__(self, client: Any, identity: str):
        self._client = client
        self.identity = identity

    def open(self, *args: Any, headers: Mapping[str, str] | None = None, **kwargs: Any):
        request_headers = self.headers(headers)
        return self._client.open(*args, headers=request_headers, **kwargs)

    def headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = identity_headers(self.identity)
        headers.update(dict(extra or {}))
        return headers

    def __getattr__(self, name: str):
        if name not in {"delete", "get", "head", "options", "patch", "post", "put", "trace"}:
            return getattr(self._client, name)

        def request(*args: Any, headers: Mapping[str, str] | None = None, **kwargs: Any):
            return getattr(self._client, name)(*args, headers=self.headers(headers), **kwargs)

        return request


def anonymous_identity(label: str | None = None) -> IdentityFixture:
    return IdentityFixture(anonymous_session_id(label))


def durable_identity(label: str | None = None) -> IdentityFixture:
    return IdentityFixture(durable_session_token(label))


def identity_client(client: Any, identity: str | IdentityFixture | None = None) -> IdentityClient:
    value = identity.value if isinstance(identity, IdentityFixture) else identity
    return IdentityClient(client, value or anonymous_session_id())
