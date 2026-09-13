# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Signed, revocable browser sessions for restricted deployments."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import DatabaseBackend

from services.secrets.vault import decrypt_secret, encrypt_secret
from services.storage.transactions import run_read, run_transaction

from .contracts import CREDENTIAL_WRAP_ALGORITHM, IdentityStorageError, timestamp

BROWSER_SESSION_COOKIE = "darklab_browser_session"
BROWSER_CSRF_COOKIE = "darklab_csrf"
BROWSER_SESSION_KEY_BYTES = 32
BROWSER_SESSION_TOUCH_INTERVAL_SECONDS = 60
_COOKIE_RE = re.compile(
    r"\Adlbs_v1_(?P<id>bws_[0-9a-f]{32})_(?P<version>[1-9][0-9]*)_(?P<signature>[A-Za-z0-9_-]{43})\Z"
)


class BrowserSessionError(IdentityStorageError):
    """Raised when persisted browser-session state is unsafe or invalid."""


@dataclass(frozen=True)
class IssuedBrowserSession:
    id: str
    principal_id: str
    credential_id: str
    oidc_identity_id: str
    signing_key_version: int
    cookie_value: str
    csrf_token: str
    created_at: str
    absolute_expires_at: str


@dataclass(frozen=True)
class ResolvedBrowserSession:
    id: str
    principal_id: str
    personal_workspace_id: str
    workspace_storage_key: str
    credential_id: str
    oidc_identity_id: str
    credential_created_at: str
    credential_last_used_at: str | None
    credential_expires_at: str | None
    absolute_expires_at: str
    authenticated_at: str


@dataclass(frozen=True)
class BrowserSessionResolution:
    state: str
    session: ResolvedBrowserSession | None = None
    error_code: str = ""
    message: str = ""

    @property
    def valid(self) -> bool:
        return self.state == "valid" and self.session is not None


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _as_utc(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _active_now(value: datetime | None) -> datetime:
    active = value or datetime.now(timezone.utc)
    if active.tzinfo is None:
        active = active.replace(tzinfo=timezone.utc)
    return active.astimezone(timezone.utc)


def _database_backend(conn: Any) -> DatabaseBackend:
    explicit = getattr(conn, "database_backend", None)
    if explicit is not None:
        return DatabaseBackend(explicit)
    return DatabaseBackend(get_db_backend())


def _lock_signing_key_rows(conn: Any) -> None:
    if _database_backend(conn) == DatabaseBackend.POSTGRES:
        conn.execute("LOCK TABLE browser_session_signing_keys IN EXCLUSIVE MODE")


def _encode_key(value: bytes) -> str:
    if len(value) != BROWSER_SESSION_KEY_BYTES:
        raise BrowserSessionError("browser-session signing key has the wrong length")
    return base64.b64encode(value).decode("ascii")


def _decode_key(value: str) -> bytes:
    try:
        key = base64.b64decode(str(value), validate=True)
    except Exception as exc:
        raise BrowserSessionError("stored browser-session signing key is invalid") from exc
    if len(key) != BROWSER_SESSION_KEY_BYTES:
        raise BrowserSessionError("stored browser-session signing key has the wrong length")
    return key


def _associated_data(version: int) -> bytes:
    if int(version) <= 0:
        raise BrowserSessionError("browser-session signing-key version must be positive")
    return f"darklab_shell/auth/browser-session-key/v1/{int(version)}".encode("ascii")


def _insert_signing_key(conn: Any, version: int, key: bytes, created_at: str) -> None:
    wrapped, nonce = encrypt_secret(_encode_key(key), associated_data=_associated_data(version))
    conn.execute(
        "INSERT INTO browser_session_signing_keys "
        "(version, state, wrapped_key, wrap_nonce, wrap_algorithm, created_at, retired_at) "
        "VALUES (?, 'active', ?, ?, ?, ?, NULL)",
        (version, wrapped, nonce, CREDENTIAL_WRAP_ALGORITHM, created_at),
    )


def ensure_active_signing_key(conn: Any) -> tuple[int, bytes]:
    _lock_signing_key_rows(conn)
    row = conn.execute(
        "SELECT version, wrapped_key, wrap_nonce, wrap_algorithm "
        "FROM browser_session_signing_keys WHERE state = 'active'"
    ).fetchone()
    if row is None:
        version = 1
        key = secrets.token_bytes(BROWSER_SESSION_KEY_BYTES)
        _insert_signing_key(conn, version, key, timestamp())
        return version, key
    data = _row_dict(row)
    version = int(data["version"])
    if str(data["wrap_algorithm"]) != CREDENTIAL_WRAP_ALGORITHM:
        raise BrowserSessionError("stored browser-session signing key uses an unsupported wrapper")
    try:
        plaintext = decrypt_secret(
            bytes(data["wrapped_key"]),
            bytes(data["wrap_nonce"]),
            associated_data=_associated_data(version),
        )
    except Exception as exc:
        raise BrowserSessionError("active browser-session signing key cannot be decrypted") from exc
    return version, _decode_key(plaintext)


def load_signing_key(conn: Any, version: int) -> bytes:
    row = conn.execute(
        "SELECT wrapped_key, wrap_nonce, wrap_algorithm "
        "FROM browser_session_signing_keys WHERE version = ?",
        (int(version),),
    ).fetchone()
    if row is None:
        raise BrowserSessionError("browser-session signing key was not found")
    data = _row_dict(row)
    if str(data["wrap_algorithm"]) != CREDENTIAL_WRAP_ALGORITHM:
        raise BrowserSessionError("stored browser-session signing key uses an unsupported wrapper")
    try:
        plaintext = decrypt_secret(
            bytes(data["wrapped_key"]),
            bytes(data["wrap_nonce"]),
            associated_data=_associated_data(int(version)),
        )
    except Exception as exc:
        raise BrowserSessionError("browser-session signing key cannot be decrypted") from exc
    return _decode_key(plaintext)


def _signature(key: bytes, session_id: str, version: int) -> str:
    digest = hmac.new(
        key,
        f"dlbs-v1\x00{session_id}\x00{int(version)}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _cookie_value(key: bytes, session_id: str, version: int) -> str:
    return f"dlbs_v1_{session_id}_{int(version)}_{_signature(key, session_id, version)}"


def _csrf_digest(token: str) -> bytes:
    return hashlib.sha256(str(token).encode("ascii")).digest()


def _new_csrf_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def create_browser_session(
    *,
    principal_id: str,
    credential_id: str = "",
    oidc_identity_id: str = "",
    absolute_seconds: int,
    replace_session_id: str = "",
    authenticated_at: str | None = None,
    now: datetime | None = None,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> IssuedBrowserSession:
    active_now = _active_now(now)
    expires_at = active_now + timedelta(seconds=max(1, int(absolute_seconds)))

    def operation(active_conn: Any) -> IssuedBrowserSession:
        if bool(credential_id) == bool(oidc_identity_id):
            raise BrowserSessionError("a browser session needs exactly one identity source")
        if credential_id:
            credential = active_conn.execute(
                "SELECT c.principal_id, c.credential_type, c.revoked_at, c.expires_at, p.status "
                "FROM credentials c JOIN principals p ON p.id = c.principal_id "
                "WHERE c.id = ? AND c.principal_id = ?",
                (credential_id, principal_id),
            ).fetchone()
            data = _row_dict(credential)
            if not data or str(data.get("credential_type")) != "portable":
                raise BrowserSessionError("a portable credential is required for browser sign-in")
            if data.get("revoked_at") is not None or str(data.get("status")) != "active":
                raise BrowserSessionError("the credential is not available for browser sign-in")
            if data.get("expires_at") is not None and _as_utc(data["expires_at"]) <= active_now:
                raise BrowserSessionError("the credential is not available for browser sign-in")
        else:
            identity = active_conn.execute(
                "SELECT p.status FROM oidc_identities o JOIN principals p ON p.id = o.principal_id "
                "WHERE o.id = ? AND o.principal_id = ?",
                (oidc_identity_id, principal_id),
            ).fetchone()
            if not identity or str(_row_dict(identity).get("status")) != "active":
                raise BrowserSessionError("the OIDC identity is not available for browser sign-in")
        version, key = ensure_active_signing_key(active_conn)
        session_id = f"bws_{secrets.token_hex(16)}"
        csrf_token = _new_csrf_token()
        created = timestamp(active_now)
        active_conn.execute(
            "INSERT INTO browser_sessions "
            "(id, principal_id, credential_id, oidc_identity_id, signing_key_version, csrf_digest, created_at, "
            "authenticated_at, last_seen_at, absolute_expires_at, revoked_at, revocation_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, '')",
            (
                session_id,
                principal_id,
                credential_id or None,
                oidc_identity_id or None,
                version,
                _csrf_digest(csrf_token),
                created,
                timestamp(_as_utc(authenticated_at)) if authenticated_at else created,
                created,
                timestamp(expires_at),
            ),
        )
        if replace_session_id:
            active_conn.execute(
                "UPDATE browser_sessions SET revoked_at = ?, revocation_reason = 'session rotation' "
                "WHERE id = ? AND principal_id = ? AND revoked_at IS NULL",
                (created, replace_session_id, principal_id),
            )
        return IssuedBrowserSession(
            id=session_id,
            principal_id=principal_id,
            credential_id=credential_id,
            oidc_identity_id=oidc_identity_id,
            signing_key_version=version,
            cookie_value=_cookie_value(key, session_id, version),
            csrf_token=csrf_token,
            created_at=created,
            absolute_expires_at=timestamp(expires_at),
        )

    if conn is not None:
        return operation(conn)
    return run_transaction(operation, connect=connect)


def _failure(state: str, code: str, message: str) -> BrowserSessionResolution:
    return BrowserSessionResolution(state=state, error_code=code, message=message)


def resolve_browser_session(
    cookie_value: str,
    *,
    idle_seconds: int,
    touch: bool = True,
    now: datetime | None = None,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> BrowserSessionResolution:
    match = _COOKIE_RE.fullmatch(str(cookie_value or ""))
    if match is None:
        return _failure("malformed", "malformed_browser_session", "The browser session is invalid.")
    session_id = match.group("id")
    version = int(match.group("version"))
    supplied_signature = match.group("signature")
    active_now = _active_now(now)

    def operation(active_conn: Any) -> BrowserSessionResolution:
        row = active_conn.execute(
            "SELECT s.*, c.created_at AS credential_created_at, c.last_used_at AS credential_last_used_at, "
            "c.expires_at AS credential_expires_at, c.revoked_at AS credential_revoked_at, "
            "c.credential_type, p.status AS principal_status, w.id AS personal_workspace_id, "
            "w.storage_key AS workspace_storage_key, "
            "o.issuer AS oidc_issuer, o.subject AS oidc_subject, o.principal_id AS oidc_principal_id "
            "FROM browser_sessions s LEFT JOIN credentials c ON c.id = s.credential_id "
            "LEFT JOIN oidc_identities o ON o.id = s.oidc_identity_id "
            "JOIN principals p ON p.id = s.principal_id "
            "JOIN personal_workspaces w ON w.principal_id = s.principal_id "
            "WHERE s.id = ? AND s.signing_key_version = ?",
            (session_id, version),
        ).fetchone()
        if row is None:
            return _failure("unknown", "unknown_browser_session", "The browser session is no longer available.")
        data = _row_dict(row)
        try:
            key = load_signing_key(active_conn, version)
        except BrowserSessionError:
            return _failure("unknown", "unknown_browser_session", "The browser session is no longer available.")
        if not hmac.compare_digest(_signature(key, session_id, version), supplied_signature):
            return _failure("unknown", "unknown_browser_session", "The browser session is no longer available.")
        if data.get("revoked_at") is not None:
            return _failure("revoked", "revoked_browser_session", "The browser session has been revoked.")
        if _as_utc(data["absolute_expires_at"]) <= active_now:
            return _failure("expired", "expired_browser_session", "The browser session has expired.")
        if _as_utc(data["last_seen_at"]) + timedelta(seconds=max(1, int(idle_seconds))) <= active_now:
            return _failure("expired", "idle_browser_session", "The browser session expired after inactivity.")
        if str(data.get("principal_status")) != "active":
            return _failure("revoked", "revoked_browser_session", "The browser session has been revoked.")
        if data.get("oidc_identity_id"):
            if data.get("credential_id") or data.get("oidc_principal_id") != data.get("principal_id"):
                return _failure("revoked", "revoked_browser_session", "The browser session has been revoked.")
        elif (
            not data.get("credential_id")
            or data.get("credential_revoked_at") is not None
            or str(data.get("credential_type")) != "portable"
        ):
            return _failure("revoked", "revoked_browser_session", "The browser session has been revoked.")
        if data.get("credential_expires_at") is not None and _as_utc(data["credential_expires_at"]) <= active_now:
            return _failure("expired", "expired_browser_session", "The browser session has expired.")
        if touch and _as_utc(data["last_seen_at"]) + timedelta(seconds=BROWSER_SESSION_TOUCH_INTERVAL_SECONDS) <= active_now:
            active_conn.execute(
                "UPDATE browser_sessions SET last_seen_at = ? WHERE id = ? AND revoked_at IS NULL",
                (timestamp(active_now), session_id),
            )
        return BrowserSessionResolution(
            state="valid",
            session=ResolvedBrowserSession(
                id=session_id,
                principal_id=str(data["principal_id"]),
                personal_workspace_id=str(data["personal_workspace_id"]),
                workspace_storage_key=str(data["workspace_storage_key"]),
                credential_id=str(data.get("credential_id") or ""),
                oidc_identity_id=str(data.get("oidc_identity_id") or ""),
                credential_created_at=(
                    timestamp(_as_utc(data["credential_created_at"]))
                    if data.get("credential_created_at") is not None else ""
                ),
                credential_last_used_at=(
                    timestamp(_as_utc(data["credential_last_used_at"]))
                    if data.get("credential_last_used_at") is not None else None
                ),
                credential_expires_at=(
                    timestamp(_as_utc(data["credential_expires_at"]))
                    if data.get("credential_expires_at") is not None else None
                ),
                absolute_expires_at=timestamp(_as_utc(data["absolute_expires_at"])),
                authenticated_at=timestamp(_as_utc(data["authenticated_at"])),
            ),
        )

    if conn is not None:
        return operation(conn)
    runner = run_transaction if touch else run_read
    return runner(operation, connect=connect)


def verify_csrf_token(session_id: str, token: str, *, connect: Callable[[], Any] | None = None) -> bool:
    if not re.fullmatch(r"bws_[0-9a-f]{32}", str(session_id or "")):
        return False
    normalized = str(token or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", normalized):
        return False

    def operation(conn: Any) -> bool:
        row = conn.execute(
            "SELECT csrf_digest FROM browser_sessions WHERE id = ? AND revoked_at IS NULL",
            (session_id,),
        ).fetchone()
        return bool(row) and hmac.compare_digest(bytes(_row_dict(row)["csrf_digest"]), _csrf_digest(normalized))

    return run_read(operation, connect=connect)


def revoke_browser_session(session_id: str, *, reason: str = "logout", connect: Callable[[], Any] | None = None) -> int:
    def operation(conn: Any) -> int:
        cursor = conn.execute(
            "UPDATE browser_sessions SET revoked_at = ?, revocation_reason = ? "
            "WHERE id = ? AND revoked_at IS NULL",
            (timestamp(), str(reason or "logout")[:256], session_id),
        )
        return int(cursor.rowcount or 0)

    return run_transaction(operation, connect=connect)


def revoke_principal_browser_sessions(
    principal_id: str,
    *,
    reason: str = "revoke all sessions",
    except_session_id: str = "",
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> int:
    def operation(active_conn: Any) -> int:
        sql = (
            "UPDATE browser_sessions SET revoked_at = ?, revocation_reason = ? "
            "WHERE principal_id = ? AND revoked_at IS NULL"
        )
        params: tuple[Any, ...] = (timestamp(), str(reason or "revoke all sessions")[:256], principal_id)
        if except_session_id:
            sql += " AND id <> ?"
            params = (*params, except_session_id)
        cursor = active_conn.execute(sql, params)
        return int(cursor.rowcount or 0)

    if conn is not None:
        return operation(conn)
    return run_transaction(operation, connect=connect)


def rotate_signing_key(
    *,
    conn: Any | None = None,
    connect: Callable[[], Any] | None = None,
) -> int:
    def operation(conn: Any) -> int:
        _lock_signing_key_rows(conn)
        active = conn.execute(
            "SELECT version FROM browser_session_signing_keys WHERE state = 'active'"
        ).fetchone()
        if active is None:
            version, _key = ensure_active_signing_key(conn)
            return version
        current = int(_row_dict(active)["version"])
        next_row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM browser_session_signing_keys"
        ).fetchone()
        next_version = int(_row_dict(next_row)["next_version"])
        rotated_at = timestamp()
        conn.execute(
            "UPDATE browser_session_signing_keys SET state = 'retired', retired_at = ? "
            "WHERE version = ? AND state = 'active'",
            (rotated_at, current),
        )
        _insert_signing_key(conn, next_version, secrets.token_bytes(BROWSER_SESSION_KEY_BYTES), rotated_at)
        return next_version

    if conn is not None:
        return operation(conn)
    return run_transaction(operation, connect=connect)
