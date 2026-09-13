# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OIDC authorization-code sign-in and principal identity binding."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import ssl
import tempfile
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, cast
from urllib.parse import urlsplit

import requests
from authlib.integrations.requests_client import OAuth2Session
from certifi import where as requests_ca_bundle
from joserfc import jwk, jwt

from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.storage.transactions import run_read, run_transaction
from services.workspace.settings import workspace_settings

from .contracts import IdentityStorageError, new_identifier, timestamp
from .workspace_storage import new_workspace_storage_key, validate_workspace_storage_key

FLOW_SECONDS = 300
RECENT_AUTH_SECONDS = 300
OIDC_STATE_COOKIE = "darklab_oidc_state"
_ALGORITHMS = ("RS256", "PS256", "ES256")


class OIDCError(IdentityStorageError):
    """A provider response or identity binding cannot be trusted."""


class OIDCUnavailable(OIDCError):
    """The configured provider could not be reached safely."""


@dataclass(frozen=True)
class OIDCFlow:
    state: str
    nonce: str
    code_verifier: str
    purpose: str
    principal_id: str
    browser_session_id: str
    next_path: str


@dataclass(frozen=True)
class OIDCIdentity:
    id: str
    principal_id: str
    issuer: str
    subject: str


def _row(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def configured(config: Mapping[str, Any]) -> bool:
    return bool(config.get("oidc_issuer") and config.get("oidc_client_id") and config.get("oidc_client_secret"))


def validate_startup_state(config: Mapping[str, Any]) -> None:
    """Reject an OIDC-only deployment with no way to create or use an identity."""
    if config.get("access_profile") != "oidc_required" or config.get("oidc_provisioning") != "disabled":
        return

    def operation(conn: Any) -> bool:
        row = conn.execute(
            "SELECT 1 FROM oidc_identities o JOIN principals p ON p.id = o.principal_id "
            "WHERE o.issuer = ? AND p.status = 'active' LIMIT 1",
            (config["oidc_issuer"],),
        ).fetchone()
        return row is not None

    if not run_read(operation):
        raise OIDCError(
            "oidc_required with disabled provisioning needs an active pre-linked identity; "
            "link one in mixed or token_required first"
        )


def _trust(config: Mapping[str, Any]) -> str | bool:
    value = str(config.get("oidc_ca_bundle") or "").strip()
    if not value:
        return True
    path = Path(value)
    if not path.is_absolute():
        import config as app_config  # noqa: PLC0415

        root = app_config.APP_LOCAL_CONF_DIR or app_config.APP_CONF_DIR
        path = Path(root) / path
    if not path.is_file():
        raise OIDCUnavailable("The configured OIDC CA bundle is unavailable.")
    try:
        stat = path.stat()
        return _combined_trust_bundle(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ssl.SSLError, ValueError) as exc:
        raise OIDCUnavailable("The configured OIDC CA bundle is invalid.") from exc


@lru_cache(maxsize=4)
def _combined_trust_bundle(path: str, mtime_ns: int, size: int) -> str:
    del mtime_ns
    if not 0 < size <= 262_144:
        raise ValueError("OIDC CA bundle size is invalid")
    custom = Path(path).read_bytes()
    if not custom.strip():
        raise ValueError("OIDC CA bundle is empty")
    ssl.create_default_context(cadata=custom.decode("ascii"))
    system = Path(requests_ca_bundle()).read_bytes()
    handle, combined_path = tempfile.mkstemp(prefix="darklab-oidc-trust-", suffix=".pem")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(system.rstrip(b"\n") + b"\n" + custom)
        return combined_path
    except BaseException:
        Path(combined_path).unlink(missing_ok=True)
        raise


def _valid_endpoint(endpoint: str) -> bool:
    selected = urlsplit(endpoint)
    return (
        selected.scheme == "https"
        and bool(selected.netloc)
        and selected.username is None
        and selected.password is None
        and not selected.fragment
    )


def _json_get(url: str, issuer: str, config: Mapping[str, Any]) -> dict[str, Any]:
    if not _valid_endpoint(url):
        raise OIDCError("OIDC metadata contains an invalid HTTPS endpoint.")
    try:
        response = requests.get(url, timeout=5, verify=_trust(config), allow_redirects=False)
        if response.status_code != 200 or len(response.content) > 262_144:
            raise OIDCUnavailable("The OIDC provider returned an unusable response.")
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OIDCUnavailable("The OIDC provider is unavailable.") from exc
    if not isinstance(result, dict):
        raise OIDCUnavailable("The OIDC provider returned invalid metadata.")
    return result


def provider_metadata(config: Mapping[str, Any]) -> dict[str, Any]:
    issuer = str(config["oidc_issuer"])
    metadata = _json_get(f"{issuer}/.well-known/openid-configuration", issuer, config)
    if metadata.get("issuer") != issuer:
        raise OIDCError("The OIDC issuer did not match the configured issuer.")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        value = metadata.get(key)
        if not isinstance(value, str) or not _valid_endpoint(value):
            raise OIDCError(f"The OIDC {key} is invalid.")
    methods = metadata.get("code_challenge_methods_supported", ["S256"])
    if not isinstance(methods, list) or "S256" not in methods:
        raise OIDCError("The OIDC provider does not support PKCE S256.")
    return metadata


def _client(config: Mapping[str, Any]) -> OAuth2Session:
    return OAuth2Session(
        client_id=str(config["oidc_client_id"]),
        client_secret=str(config["oidc_client_secret"]),
        redirect_uri=str(config["oidc_redirect_uri"]),
        scope=" ".join(config["oidc_scopes"]),
        code_challenge_method="S256",
        token_endpoint_auth_method="client_secret_basic",
    )


def start_flow(
    config: Mapping[str, Any], *, purpose: str, principal_id: str = "",
    browser_session_id: str = "", next_path: str = "/",
) -> tuple[str, str]:
    if purpose not in {"sign_in", "link"}:
        raise OIDCError("Unsupported OIDC flow.")
    if purpose == "link" and (not principal_id or not browser_session_id):
        raise OIDCError("A current credential session is required to link OIDC.")
    metadata = provider_metadata(config)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    client = _client(config)
    authorization_url, _state = client.create_authorization_url(
        metadata["authorization_endpoint"],
        state=state,
        code_verifier=verifier,
        nonce=nonce,
        max_age=RECENT_AUTH_SECONDS if purpose == "link" else None,
    )
    created = _now()

    def operation(conn: Any) -> None:
        conn.execute("DELETE FROM oidc_auth_flows WHERE expires_at <= ?", (timestamp(created),))
        conn.execute(
            "INSERT INTO oidc_auth_flows (state_digest, nonce, code_verifier, purpose, "
            "principal_id, browser_session_id, next_path, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (hashlib.sha256(state.encode("ascii")).digest(), nonce, verifier, purpose,
             principal_id or None, browser_session_id or None, next_path, timestamp(created),
             timestamp(created + timedelta(seconds=FLOW_SECONDS))),
        )

    run_transaction(operation)
    return authorization_url, state


def consume_flow(state: str, cookie_state: str) -> OIDCFlow:
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", state) or not hmac.compare_digest(state, cookie_state):
        raise OIDCError("The OIDC sign-in attempt expired. Please start again.")
    digest = hashlib.sha256(state.encode("utf-8")).digest()

    def operation(conn: Any) -> OIDCFlow:
        row = conn.execute(
            "DELETE FROM oidc_auth_flows WHERE state_digest = ? RETURNING *", (digest,)
        ).fetchone()
        data = _row(row)
        if not data or _as_utc(data["expires_at"]) <= _now():
            raise OIDCError("The OIDC sign-in attempt expired. Please start again.")
        return OIDCFlow(
            state=state,
            nonce=str(data["nonce"]),
            code_verifier=str(data["code_verifier"]),
            purpose=str(data["purpose"]),
            principal_id=str(data.get("principal_id") or ""),
            browser_session_id=str(data.get("browser_session_id") or ""),
            next_path=str(data["next_path"]),
        )

    return run_transaction(operation)


def exchange_code(config: Mapping[str, Any], flow: OIDCFlow, code: str) -> tuple[str, str]:
    if not code or len(code) > 4096:
        raise OIDCError("The OIDC provider did not return an authorization code.")
    metadata = provider_metadata(config)
    client = _client(config)
    try:
        token = client.fetch_token(
            metadata["token_endpoint"], code=code, code_verifier=flow.code_verifier,
            redirect_uri=str(config["oidc_redirect_uri"]),
            allow_redirects=False, timeout=10, verify=_trust(config),
        )
    except Exception as exc:
        raise OIDCUnavailable("The OIDC code exchange failed.") from exc
    id_token = token.get("id_token")
    if not isinstance(id_token, str) or len(id_token) > 32_768:
        raise OIDCError("The OIDC provider did not return a valid ID token.")
    keys = _json_get(metadata["jwks_uri"], str(config["oidc_issuer"]), config)
    try:
        if not isinstance(keys.get("keys"), list):
            raise OIDCError("The OIDC provider returned an invalid signing key set.")
        keyset = jwk.KeySet.import_key_set(cast(jwk.KeySetSerialization, keys))
        verified = jwt.decode(id_token, keyset, algorithms=_ALGORITHMS)
        claims = verified.claims
        now = int(_now().timestamp())
        jwt.JWTClaimsRegistry(
            now=now, leeway=30,
            iss={"essential": True, "value": str(config["oidc_issuer"])},
            sub={"essential": True},
            aud={"essential": True, "value": str(config["oidc_client_id"])},
            exp={"essential": True},
            iat={"essential": True},
            nonce={"essential": True, "value": flow.nonce},
        ).validate(claims)
        audience = claims["aud"]
        if isinstance(audience, list) and len(audience) > 1 and claims.get("azp") != config["oidc_client_id"]:
            raise OIDCError("The OIDC authorized party did not match this client.")
        if claims["iat"] > now + 30:
            raise OIDCError("The OIDC ID token was issued in the future.")
        subject = claims["sub"]
        if not isinstance(subject, str) or not 0 < len(subject) <= 512:
            raise OIDCError("The OIDC subject is invalid.")
        if flow.purpose == "link":
            auth_time = claims.get("auth_time")
            if not isinstance(auth_time, int) or auth_time < now - RECENT_AUTH_SECONDS or auth_time > now + 30:
                raise OIDCError("Recent provider authentication is required to link OIDC.")
    except OIDCError:
        raise
    except Exception as exc:
        raise OIDCError("The OIDC ID token could not be verified.") from exc
    return str(config["oidc_issuer"]), subject


def _create_principal(conn: Any) -> str:
    principal_id = new_identifier("principal")
    workspace_id = new_identifier("workspace")
    storage_key = new_workspace_storage_key()
    validate_workspace_storage_key(storage_key, workspace_settings(), conn=conn)
    created = timestamp()
    conn.execute(
        "INSERT INTO principals (id, status, disabled_reason, created_at, updated_at, disabled_at) "
        "VALUES (?, 'active', '', ?, ?, NULL)", (principal_id, created, created),
    )
    conn.execute(
        "INSERT INTO personal_workspaces (id, principal_id, storage_key, created_at) VALUES (?, ?, ?, ?)",
        (workspace_id, principal_id, storage_key, created),
    )
    record_event(
        AuditEventType.PRINCIPAL_CREATE,
        target_id=principal_id,
        details={"source": "oidc_automatic_provisioning"},
        conn=conn,
    )
    return principal_id


def _identity(data: Mapping[str, Any]) -> OIDCIdentity:
    return OIDCIdentity(
        id=str(data["id"]), principal_id=str(data["principal_id"]),
        issuer=str(data["issuer"]), subject=str(data["subject"]),
    )


def find_identity(principal_id: str, issuer: str) -> OIDCIdentity | None:
    def operation(conn: Any) -> OIDCIdentity | None:
        data = _row(conn.execute(
            "SELECT id, principal_id, issuer, subject FROM oidc_identities "
            "WHERE principal_id = ? AND issuer = ?", (principal_id, issuer),
        ).fetchone())
        return _identity(data) if data else None
    return run_read(operation)


def linked_credential_source(flow: OIDCFlow) -> tuple[str, str]:
    """Return the recently proved credential and its original authentication time."""
    if flow.purpose != "link":
        raise OIDCError("A credential source is required for provider linking.")

    def operation(conn: Any) -> tuple[str, str]:
        data = _row(conn.execute(
            "SELECT credential_id, authenticated_at FROM browser_sessions "
            "WHERE id = ? AND principal_id = ? AND revoked_at IS NULL",
            (flow.browser_session_id, flow.principal_id),
        ).fetchone())
        if not data or not data.get("credential_id"):
            raise OIDCError("The credential session is no longer available.")
        return str(data["credential_id"]), str(data["authenticated_at"])

    return run_read(operation)


def complete_identity(config: Mapping[str, Any], flow: OIDCFlow, issuer: str, subject: str) -> OIDCIdentity:
    def operation(conn: Any) -> OIDCIdentity:
        existing = _row(conn.execute(
            "SELECT o.id, o.principal_id, o.issuer, o.subject, p.status FROM oidc_identities o "
            "JOIN principals p ON p.id = o.principal_id WHERE o.issuer = ? AND o.subject = ?",
            (issuer, subject),
        ).fetchone())
        if flow.purpose == "link":
            source = _row(conn.execute(
                "SELECT s.principal_id, s.credential_id, s.authenticated_at, s.last_seen_at, s.revoked_at, "
                "s.absolute_expires_at, c.revoked_at AS credential_revoked_at, c.expires_at AS credential_expires_at, "
                "p.status FROM browser_sessions s JOIN credentials c ON c.id = s.credential_id "
                "JOIN principals p ON p.id = s.principal_id WHERE s.id = ?",
                (flow.browser_session_id,),
            ).fetchone())
            cutoff = _now() - timedelta(seconds=RECENT_AUTH_SECONDS)
            if (not source or source["principal_id"] != flow.principal_id or source["revoked_at"] is not None
                    or source["credential_revoked_at"] is not None or source["status"] != "active"
                    or source["credential_id"] is None
                    or _as_utc(source["absolute_expires_at"]) <= _now()
                    or _as_utc(source["last_seen_at"]) + timedelta(
                        minutes=int(config.get("browser_session_idle_minutes", 30))
                    ) <= _now()
                    or _as_utc(source["authenticated_at"]) < cutoff
                    or (source["credential_expires_at"] is not None and _as_utc(source["credential_expires_at"]) <= _now())):
                raise OIDCError("A recent, active credential session is required to link OIDC.")
            if existing and existing["principal_id"] != flow.principal_id:
                raise OIDCError("This provider identity is already linked to another workspace.")
            other = _row(conn.execute(
                "SELECT id, subject FROM oidc_identities WHERE principal_id = ? AND issuer = ?",
                (flow.principal_id, issuer),
            ).fetchone())
            if other and other["subject"] != subject:
                raise OIDCError("This workspace is already linked to a different provider identity.")
            principal_id = flow.principal_id
        else:
            if existing:
                if existing["status"] != "active":
                    raise OIDCError("This workspace is unavailable.")
                return _identity(existing)
            policy = str(config.get("oidc_provisioning") or "disabled")
            if policy == "disabled" or (policy == "allowlist" and subject not in config.get("oidc_allowed_subjects", [])):
                raise OIDCError("This provider identity isn't approved for a workspace.")
            principal_id = _create_principal(conn)
        if existing:
            return _identity(existing)
        identity_id = f"oid_{secrets.token_hex(16)}"
        conn.execute(
            "INSERT INTO oidc_identities (id, principal_id, issuer, subject, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (identity_id, principal_id, issuer, subject, timestamp()),
        )
        record_event(
            AuditEventType.OIDC_IDENTITY_LINK,
            target_id=principal_id,
            details={"source": "credential_link" if flow.purpose == "link" else "provider_provisioning"},
            conn=conn,
        )
        return OIDCIdentity(identity_id, principal_id, issuer, subject)

    return run_transaction(operation)


def unlink_identity(principal_id: str, issuer: str) -> bool:
    def operation(conn: Any) -> bool:
        row = _row(conn.execute(
            "SELECT id FROM oidc_identities WHERE principal_id = ? AND issuer = ?",
            (principal_id, issuer),
        ).fetchone())
        if not row:
            return False
        usable = _row(conn.execute(
            "SELECT COUNT(*) AS count FROM credentials WHERE principal_id = ? AND credential_type = 'portable' "
            "AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > ?)",
            (principal_id, timestamp()),
        ).fetchone())
        if not int(usable.get("count") or 0):
            raise OIDCError("Add an active portable credential before unlinking the only sign-in method.")
        conn.execute("DELETE FROM oidc_identities WHERE id = ?", (row["id"],))
        conn.execute(
            "UPDATE browser_sessions SET revoked_at = ?, revocation_reason = 'OIDC identity unlinked' "
            "WHERE principal_id = ? AND revoked_at IS NULL", (timestamp(), principal_id),
        )
        record_event(
            AuditEventType.OIDC_IDENTITY_UNLINK,
            target_id=principal_id,
            details={"source": "credential_proof"},
            conn=conn,
        )
        return True

    return run_transaction(operation)
