# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Production-shaped identities for server-side tests.

Positive tests should use these helpers instead of relying on arbitrary strings
that the application would reject outside ``TESTING`` mode. Deliberately invalid
identifiers should remain literal at the call site so their intent stays clear.
"""

from __future__ import annotations

import secrets
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
    return str(uuid.uuid5(_TEST_IDENTITY_NAMESPACE, str(label)))


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
