# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Identifiers, safe result models, and validation for principal credentials."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import secrets
from typing import Any
from uuid import UUID


MAX_CREDENTIAL_LABEL_LENGTH = 64
MAX_REASON_LENGTH = 256
LAST_USED_WRITE_INTERVAL_SECONDS = 300
CREDENTIAL_DIGEST_ALGORITHM = "hmac-sha256-v1"
CREDENTIAL_WRAP_ALGORITHM = "aes-gcm-v1"
CREDENTIAL_SECRET_MAX_LENGTH = 128
GENERATED_ID_ATTEMPTS = 3

_IDENTIFIER_PATTERNS = {
    "principal": re.compile(r"\Aprn_[0-9a-f]{32}\Z"),
    "workspace": re.compile(r"\Awsp_[0-9a-f]{32}\Z"),
    "portable": re.compile(r"\Acrd_[0-9a-f]{32}\Z"),
    "pat": re.compile(r"\Apat_[0-9a-f]{32}\Z"),
}


class IdentityStorageError(ValueError):
    """Base class for principal and credential persistence failures."""


class InvalidIdentityValue(IdentityStorageError):
    """Raised when an identifier or bounded metadata value is invalid."""


class PrincipalNotFound(IdentityStorageError):
    """Raised when a principal does not exist."""


class PrincipalDisabled(IdentityStorageError):
    """Raised when a disabled principal cannot perform a lifecycle action."""


class CredentialNotFound(IdentityStorageError):
    """Raised when a credential does not exist for the requested principal."""


class CredentialRevoked(IdentityStorageError):
    """Raised when a lifecycle operation requires a live credential."""


class WorkspaceStorageError(IdentityStorageError):
    """Raised when a persisted workspace storage key is unsafe or unavailable."""


class WorkspaceAlreadyAttached(WorkspaceStorageError):
    """Raised when an anonymous workspace is already owned by a principal."""


class VerifierKeyError(IdentityStorageError):
    """Raised when verifier-root state is missing, invalid, or unsafe to change."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime | None = None) -> str:
    active = value or utc_now()
    if active.tzinfo is None:
        active = active.replace(tzinfo=timezone.utc)
    return active.astimezone(timezone.utc).isoformat()


def parse_timestamp(value: str | datetime | None, *, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError as exc:
            raise InvalidIdentityValue(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise InvalidIdentityValue(f"{field_name} must include a timezone")
    return timestamp(parsed)


def bounded_text(value: Any, *, field_name: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if len(normalized) > maximum:
        raise InvalidIdentityValue(f"{field_name} must be {maximum} characters or fewer")
    return normalized


def validate_identifier(value: str, kind: str) -> str:
    normalized = str(value or "")
    pattern = _IDENTIFIER_PATTERNS.get(kind)
    if pattern is None or pattern.fullmatch(normalized) is None:
        raise InvalidIdentityValue(f"invalid {kind} id")
    return normalized


def new_identifier(kind: str) -> str:
    prefixes = {
        "principal": "prn_",
        "workspace": "wsp_",
        "portable": "crd_",
        "pat": "pat_",
    }
    try:
        prefix = prefixes[kind]
    except KeyError as exc:
        raise InvalidIdentityValue(f"unsupported identity kind: {kind}") from exc
    return f"{prefix}{secrets.token_hex(16)}"


def validate_anonymous_uuid(value: str) -> str:
    normalized = str(value or "")
    try:
        parsed = UUID(normalized)
    except (ValueError, AttributeError) as exc:
        raise InvalidIdentityValue("anonymous id must be a canonical UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != normalized:
        raise InvalidIdentityValue("anonymous id must be a canonical lowercase UUIDv4")
    return normalized


@dataclass(frozen=True)
class PrincipalRecord:
    id: str
    status: str
    disabled_reason: str
    created_at: str
    updated_at: str
    disabled_at: str | None

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "disabled_reason": self.disabled_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "disabled_at": self.disabled_at,
        }


@dataclass(frozen=True)
class PersonalWorkspaceRecord:
    id: str
    principal_id: str
    storage_key: str
    created_at: str

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "principal_id": self.principal_id,
            "storage_key": self.storage_key,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class CredentialMetadata:
    id: str
    public_prefix: str
    principal_id: str
    credential_type: str
    label: str
    verifier_root_version: int
    digest_algorithm: str
    created_by_credential_id: str | None
    created_at: str
    updated_at: str
    last_used_at: str | None
    expires_at: str | None
    revoked_at: str | None
    revocation_reason: str

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_prefix": self.public_prefix,
            "principal_id": self.principal_id,
            "credential_type": self.credential_type,
            "label": self.label,
            "verifier_root_version": self.verifier_root_version,
            "digest_algorithm": self.digest_algorithm,
            "created_by_credential_id": self.created_by_credential_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "revocation_reason": self.revocation_reason,
        }


@dataclass(frozen=True)
class IssuedCredential:
    metadata: CredentialMetadata
    secret: str = field(repr=False)

    def to_safe_dict(self) -> dict[str, Any]:
        return self.metadata.to_safe_dict()


@dataclass(frozen=True)
class PrincipalBundle:
    principal: PrincipalRecord
    workspace: PersonalWorkspaceRecord
    credential: IssuedCredential

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "principal": self.principal.to_safe_dict(),
            "workspace": self.workspace.to_safe_dict(),
            "credential": self.credential.to_safe_dict(),
        }
