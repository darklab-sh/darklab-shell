# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed, transport-aware authentication resolution."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import hmac
import re
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

if TYPE_CHECKING:
    from werkzeug.datastructures import Headers

    HeaderValues: TypeAlias = Mapping[str, Any] | Headers
else:
    HeaderValues = Any

from services.storage.transactions import run_read, run_transaction

from .contracts import (
    CREDENTIAL_DIGEST_ALGORITHM,
    CREDENTIAL_SECRET_MAX_LENGTH,
    LAST_USED_WRITE_INTERVAL_SECONDS,
    PAT_SCOPES,
    InvalidIdentityValue,
    timestamp,
    validate_anonymous_uuid,
)
from .verifier_keys import credential_verifier_digest, load_verifier_root


class AuthenticationState(str, Enum):
    NO_CREDENTIAL = "no_credential"
    VALID = "valid"
    MALFORMED_CREDENTIAL = "malformed_credential"
    UNKNOWN_CREDENTIAL = "unknown_credential"
    EXPIRED_CREDENTIAL = "expired_credential"
    REVOKED_CREDENTIAL = "revoked_credential"
    DISABLED_PRINCIPAL = "disabled_principal"


AuthenticationMethod = Literal[
    "anonymous_header",
    "portable_header",
    "pat_bearer",
]


@dataclass(frozen=True)
class AuthenticatedContext:
    principal_id: str
    personal_workspace_id: str
    workspace_storage_key: str
    credential_id: str
    credential_type: Literal["portable", "pat"]
    authentication_method: AuthenticationMethod
    credential_created_at: str = ""
    credential_last_used_at: str | None = None
    credential_expires_at: str | None = None
    selected_team_id: str = ""
    role: str = ""
    capabilities: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AnonymousContext:
    anonymous_id: str
    authentication_method: AuthenticationMethod = "anonymous_header"

    def __post_init__(self) -> None:
        object.__setattr__(self, "anonymous_id", validate_anonymous_uuid(self.anonymous_id))


ResolvedContext = AuthenticatedContext | AnonymousContext


@dataclass(frozen=True)
class AuthenticationResult:
    state: AuthenticationState
    context: ResolvedContext | None = None
    credential_supplied: bool = False
    error_code: str = ""
    message: str = ""

    @property
    def is_valid(self) -> bool:
        return self.state == AuthenticationState.VALID

    @property
    def failed(self) -> bool:
        return self.state not in {AuthenticationState.NO_CREDENTIAL, AuthenticationState.VALID}


@dataclass(frozen=True)
class _ParsedCredential:
    credential_type: Literal["portable", "pat"]
    credential_id: str
    secret_bytes: bytes = field(repr=False)
    method: AuthenticationMethod = "portable_header"


_PORTABLE_SECRET_RE = re.compile(
    r"\Adlc_v1_(?P<id>crd_[0-9a-f]{32})_(?P<secret>[A-Za-z0-9_-]{43})\Z"
)
_PAT_SECRET_RE = re.compile(
    r"\Adlp_v1_(?P<id>pat_[0-9a-f]{32})_(?P<secret>[A-Za-z0-9_-]{43})\Z"
)
def _failure(state: AuthenticationState, code: str, message: str) -> AuthenticationResult:
    return AuthenticationResult(
        state=state,
        credential_supplied=True,
        error_code=code,
        message=message,
    )


def _decode_secret(value: str, *, credential_type: Literal["portable", "pat"], method: AuthenticationMethod) -> _ParsedCredential:
    if not value or len(value) > CREDENTIAL_SECRET_MAX_LENGTH:
        raise InvalidIdentityValue("credential has an invalid format")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise InvalidIdentityValue("credential has an invalid format") from exc
    matcher = _PORTABLE_SECRET_RE if credential_type == "portable" else _PAT_SECRET_RE
    match = matcher.fullmatch(value)
    if match is None:
        raise InvalidIdentityValue("credential has an invalid format")
    encoded = match.group("secret")
    try:
        secret_bytes = base64.urlsafe_b64decode(encoded + "=")
    except (ValueError, binascii.Error) as exc:
        raise InvalidIdentityValue("credential has an invalid format") from exc
    if len(secret_bytes) != 32 or base64.urlsafe_b64encode(secret_bytes).rstrip(b"=").decode("ascii") != encoded:
        raise InvalidIdentityValue("credential has an invalid format")
    return _ParsedCredential(
        credential_type=credential_type,
        credential_id=match.group("id"),
        secret_bytes=secret_bytes,
        method=method,
    )


def _bearer(headers: HeaderValues) -> tuple[str, AuthenticationResult | None]:
    raw = str(headers.get("Authorization") or "")
    if "Authorization" not in headers:
        return "", None
    if raw != raw.strip() or " " not in raw:
        return "", _failure(
            AuthenticationState.MALFORMED_CREDENTIAL,
            "invalid_authorization_header",
            "Authorization must use Bearer syntax.",
        )
    scheme, value = raw.split(" ", 1)
    if scheme.lower() != "bearer" or not value or value != value.strip() or " " in value:
        return "", _failure(
            AuthenticationState.MALFORMED_CREDENTIAL,
            "invalid_authorization_header",
            "Authorization must use Bearer syntax.",
        )
    return value, None


def _parse_transport(
    headers: HeaderValues,
) -> tuple[
    _ParsedCredential | AnonymousContext | None,
    AuthenticationResult | None,
]:
    portable = str(headers.get("X-Darklab-Credential") or "")
    anonymous = str(headers.get("X-Darklab-Anonymous-ID") or "")
    if "X-Session-ID" in headers:
        return None, _failure(
            AuthenticationState.MALFORMED_CREDENTIAL,
            "legacy_identity_removed",
            "X-Session-ID is no longer supported. Use a Darklab anonymous ID or access credential.",
        )
    bearer, bearer_error = _bearer(headers)
    if bearer_error is not None:
        return None, bearer_error
    for name, value in (
        ("X-Darklab-Credential", portable),
        ("X-Darklab-Anonymous-ID", anonymous),
    ):
        if name in headers and not value:
            return None, _failure(
                AuthenticationState.MALFORMED_CREDENTIAL,
                "malformed_credential",
                "The supplied identity or credential is malformed.",
            )
    supplied = sum(bool(value) for value in (portable, anonymous, bearer))
    if supplied > 1:
        return None, _failure(
            AuthenticationState.MALFORMED_CREDENTIAL,
            "multiple_credentials",
            "Supply exactly one identity or credential.",
        )
    try:
        if portable:
            return _decode_secret(portable, credential_type="portable", method="portable_header"), None
        if bearer:
            return _decode_secret(bearer, credential_type="pat", method="pat_bearer"), None
        if anonymous:
            return AnonymousContext(validate_anonymous_uuid(anonymous)), None
    except InvalidIdentityValue:
        return None, _failure(
            AuthenticationState.MALFORMED_CREDENTIAL,
            "malformed_credential",
            "The supplied identity or credential is malformed.",
        )
    return None, None


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _as_utc(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _stored_context_timestamp(value: Any) -> str | None:
    parsed = _as_utc(value)
    return parsed.isoformat() if parsed is not None else None


def _last_used_write_is_due(value: Any, cutoff: datetime) -> bool:
    last_used = _as_utc(value)
    return last_used is None or last_used <= cutoff


def _resolve_credential(conn: Any, parsed: _ParsedCredential, *, now: datetime, touch_last_used: bool) -> AuthenticationResult:
    row = conn.execute(
        "SELECT c.*, p.status AS principal_status, w.id AS personal_workspace_id, "
        "w.storage_key AS workspace_storage_key "
        "FROM credentials c JOIN principals p ON p.id = c.principal_id "
        "JOIN personal_workspaces w ON w.principal_id = p.id WHERE c.id = ?",
        (parsed.credential_id,),
    ).fetchone()
    if row is None:
        return _failure(
            AuthenticationState.UNKNOWN_CREDENTIAL,
            "unknown_credential",
            "The supplied credential is unknown or no longer available.",
        )
    data = _row_dict(row)
    if str(data.get("credential_type")) != parsed.credential_type:
        return _failure(
            AuthenticationState.UNKNOWN_CREDENTIAL,
            "unknown_credential",
            "The supplied credential is unknown or no longer available.",
        )
    if str(data.get("digest_algorithm")) != CREDENTIAL_DIGEST_ALGORITHM:
        return _failure(
            AuthenticationState.UNKNOWN_CREDENTIAL,
            "unknown_credential",
            "The supplied credential is unknown or no longer available.",
        )
    root = load_verifier_root(conn, int(data["verifier_root_version"]))
    expected = credential_verifier_digest(
        root,
        parsed.credential_type,
        parsed.credential_id,
        parsed.secret_bytes,
    )
    stored = bytes(data["verifier_digest"])
    if not hmac.compare_digest(expected, stored):
        return _failure(
            AuthenticationState.UNKNOWN_CREDENTIAL,
            "unknown_credential",
            "The supplied credential is unknown or no longer available.",
        )
    if data.get("revoked_at") is not None:
        return _failure(AuthenticationState.REVOKED_CREDENTIAL, "revoked_credential", "The supplied credential has been revoked.")
    expires_at = _as_utc(data.get("expires_at"))
    if expires_at is not None and expires_at <= now:
        return _failure(AuthenticationState.EXPIRED_CREDENTIAL, "expired_credential", "The supplied credential has expired.")
    if str(data.get("principal_status")) != "active":
        return _failure(AuthenticationState.DISABLED_PRINCIPAL, "disabled_principal", "The principal is disabled.")
    scopes: frozenset[str] = frozenset()
    if parsed.credential_type == "pat":
        scope_rows = conn.execute(
            "SELECT scope FROM credential_scopes WHERE credential_id = ? ORDER BY scope",
            (parsed.credential_id,),
        ).fetchall()
        scopes = frozenset(str(_row_dict(scope).get("scope") or "") for scope in scope_rows)
        if not scopes or not scopes.issubset(PAT_SCOPES):
            return _failure(
                AuthenticationState.MALFORMED_CREDENTIAL,
                "invalid_credential_scopes",
                "The supplied credential has invalid scopes.",
            )
    cutoff = now - timedelta(seconds=LAST_USED_WRITE_INTERVAL_SECONDS)
    context_last_used = _stored_context_timestamp(data.get("last_used_at"))
    if touch_last_used and _last_used_write_is_due(data.get("last_used_at"), cutoff):
        conn.execute(
            "UPDATE credentials SET last_used_at = ? WHERE id = ? AND revoked_at IS NULL "
            "AND (last_used_at IS NULL OR last_used_at <= ?)",
            (timestamp(now), parsed.credential_id, timestamp(cutoff)),
        )
        context_last_used = timestamp(now)
    capabilities = scopes if parsed.credential_type == "pat" else PAT_SCOPES
    return AuthenticationResult(
        state=AuthenticationState.VALID,
        context=AuthenticatedContext(
            principal_id=str(data["principal_id"]),
            personal_workspace_id=str(data["personal_workspace_id"]),
            workspace_storage_key=str(data["workspace_storage_key"]),
            credential_id=parsed.credential_id,
            credential_type=parsed.credential_type,
            authentication_method=parsed.method,
            credential_created_at=_stored_context_timestamp(data.get("created_at")) or "",
            credential_last_used_at=context_last_used,
            credential_expires_at=_stored_context_timestamp(data.get("expires_at")),
            capabilities=frozenset(capabilities),
        ),
        credential_supplied=True,
    )


def resolve_authentication(
    headers: HeaderValues,
    *,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
    now: datetime | None = None,
    touch_last_used: bool = True,
) -> AuthenticationResult:
    """Resolve one request without ever retaining or returning its raw secret."""
    parsed, transport_error = _parse_transport(headers)
    if transport_error is not None:
        return transport_error
    if parsed is None:
        return AuthenticationResult(state=AuthenticationState.NO_CREDENTIAL)
    if isinstance(parsed, AnonymousContext):
        return AuthenticationResult(state=AuthenticationState.NO_CREDENTIAL, context=parsed)
    active_now = now or datetime.now(timezone.utc)
    if active_now.tzinfo is None:
        active_now = active_now.replace(tzinfo=timezone.utc)
    active_now = active_now.astimezone(timezone.utc)

    def operation(active_conn: Any) -> AuthenticationResult:
        return _resolve_credential(active_conn, parsed, now=active_now, touch_last_used=touch_last_used)

    if conn is not None:
        return operation(conn)
    runner = run_transaction if touch_last_used else run_read
    return runner(operation, connect=connect)


def redeem_portable_credential(
    secret: str,
    *,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
    now: datetime | None = None,
) -> AuthenticationResult:
    """Resolve a portable secret submitted to the POST-only redemption route."""
    return resolve_authentication(
        {"X-Darklab-Credential": secret},
        conn=conn,
        connect=connect,
        now=now,
    )


def public_lookup_id_from_headers(headers: HeaderValues) -> str:
    """Return only a syntactically visible public id for an ephemeral rate key."""
    authorization = str(headers.get("Authorization") or "")
    authorization_parts = authorization.split(" ", 1)
    bearer_value = (
        authorization_parts[1]
        if len(authorization_parts) == 2 and authorization_parts[0].lower() == "bearer"
        else ""
    )
    candidates = [
        str(headers.get("X-Darklab-Credential") or ""),
        bearer_value,
    ]
    for candidate in candidates:
        if len(candidate) > CREDENTIAL_SECRET_MAX_LENGTH:
            continue
        match = re.match(r"\Adl[cp]_v1_((?:crd|pat)_[0-9a-f]{32})_", candidate)
        if match is not None:
            return match.group(1)
    return ""
