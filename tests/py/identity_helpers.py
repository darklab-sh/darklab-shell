# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Production-shaped identities for server-side tests.

Positive tests should use these helpers instead of relying on arbitrary strings
that the application would reject outside ``TESTING`` mode. Deliberately invalid
identifiers should remain literal at the call site so their intent stays clear.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


_TEST_IDENTITY_NAMESPACE = uuid.UUID("321e676e-0860-438d-9ec2-c0bb0e4c588d")


def anonymous_session_id(label: str | None = None) -> str:
    """Return a canonical anonymous UUID, stable when ``label`` is supplied."""
    if label is None:
        return str(uuid.uuid4())
    digest = hashlib.sha256(_TEST_IDENTITY_NAMESPACE.bytes + str(label).encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest[:16], version=4))


def identity_headers(identity: str) -> dict[str, str]:
    """Return production request headers that consistently reuse one identity."""
    return browser_identity_headers(identity)


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


@dataclass(frozen=True)
class PersistedPrincipalFixture:
    """Stable principal/workspace ids for service tests that own their connection."""

    principal_id: str
    personal_workspace_id: str
    storage_key: str


_PRINCIPAL_IDENTITIES_BY_WORKSPACE: dict[str, PrincipalIdentityFixture] = {}


def principal_identity(label: str | None = None) -> PrincipalIdentityFixture:
    """Issue separate production-shaped browser and API credentials."""
    from services.secrets.vault import reset_master_key_cache_for_tests  # noqa: PLC0415
    from services.auth import storage  # noqa: PLC0415
    from services.auth.contracts import PAT_SCOPES  # noqa: PLC0415

    # Some vault tests intentionally replace the deployment key. Always reload
    # the restored test key before issuing a production-shaped credential.
    reset_master_key_cache_for_tests()
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


def principal_owner(label: str | None = None) -> str:
    """Create a principal and return its personal workspace owner id."""
    return principal_identity(label).owner_id


def persisted_principal(conn: Any, label: str) -> PersistedPrincipalFixture:
    """Insert a production-shaped principal and workspace on an explicit connection."""
    normalized = str(label or "test-principal")
    principal_id = "prn_" + hashlib.sha256(f"principal:{normalized}".encode()).hexdigest()[:32]
    workspace_id = "wsp_" + hashlib.sha256(f"workspace:{normalized}".encode()).hexdigest()[:32]
    storage_key = "ws_" + hashlib.sha256(f"storage:{normalized}".encode()).hexdigest()[:32]
    created = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO principals (id, created_at, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (id) DO NOTHING",
        (principal_id, created, created),
    )
    conn.execute(
        "INSERT INTO personal_workspaces (id, principal_id, storage_key, created_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (id) DO NOTHING",
        (workspace_id, principal_id, storage_key, created),
    )
    return PersistedPrincipalFixture(principal_id, workspace_id, storage_key)


def browser_identity_headers(identity: str, *, team_id: str = "") -> dict[str, str]:
    """Use a portable credential for principals and a UUID for anonymous owners."""
    principal = _PRINCIPAL_IDENTITIES_BY_WORKSPACE.get(str(identity))
    if principal is not None:
        return principal.browser_headers(team_id=team_id)
    headers = {"X-Darklab-Anonymous-ID": str(identity)}
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
    return IdentityFixture(principal_owner(label))


def identity_client(client: Any, identity: str | IdentityFixture | None = None) -> IdentityClient:
    value = identity.value if isinstance(identity, IdentityFixture) else identity
    return IdentityClient(client, value or anonymous_session_id())
