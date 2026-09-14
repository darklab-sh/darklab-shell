# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OIDC authorization-code sign-in and principal identity binding."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import ssl
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, cast
from urllib.parse import urlsplit

import requests
from authlib.integrations.requests_client import OAuth2Session
from authlib.integrations.base_client.errors import OAuthError
from joserfc import jwk, jwt
from joserfc.errors import (
    BadSignatureError, ClaimError, ExpiredTokenError, InvalidKeyIdError, JoseError, MissingClaimError,
)

from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.storage.transactions import run_read, run_transaction
from services.workspace.settings import workspace_settings

from .contracts import new_identifier, timestamp
from .oidc_diagnostics import (
    OIDCError, OIDCUnavailable, exception_reason, observe_oidc, oidc_purpose, provider_status,
)
from .lifecycle_logging import LifecycleEvents
from .storage import get_principal
from .workspace_storage import new_workspace_storage_key, validate_workspace_storage_key
from .oidc_cache import cached_provider_value, combined_trust_bundle, trust_cache_key

FLOW_SECONDS = 300
RECENT_AUTH_SECONDS = 300
OIDC_STATE_COOKIE = "darklab_oidc_state"
_ALGORITHMS = ("RS256", "PS256", "ES256")


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
        raise OIDCUnavailable("The configured OIDC CA bundle is unavailable.", reason="ca_bundle_unavailable")
    try:
        stat = path.stat()
        return combined_trust_bundle(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ssl.SSLError, ValueError) as exc:
        raise OIDCUnavailable(
            "The configured OIDC CA bundle is invalid.", reason="ca_bundle_invalid", error_type=type(exc).__name__,
        ) from None


def _valid_endpoint(endpoint: str) -> bool:
    try:
        selected = urlsplit(endpoint)
    except ValueError:
        return False
    return (
        selected.scheme == "https"
        and bool(selected.netloc)
        and selected.username is None
        and selected.password is None
        and not selected.fragment
    )


def _json_get(url: str, issuer: str, config: Mapping[str, Any]) -> dict[str, Any]:
    if not _valid_endpoint(url):
        raise OIDCUnavailable("OIDC metadata contains an invalid HTTPS endpoint.", reason="invalid_endpoint")
    try:
        response = requests.get(url, timeout=5, verify=_trust(config), allow_redirects=False)
    except requests.RequestException as exc:
        raise OIDCUnavailable(
            "The OIDC provider is unavailable.", reason=exception_reason(exc), error_type=type(exc).__name__,
            http_status=provider_status(getattr(getattr(exc, "response", None), "status_code", None)),
        ) from None
    status = provider_status(response.status_code)
    if status != 200:
        raise OIDCUnavailable(
            "The OIDC provider returned an unusable response.",
            reason="provider_http_error", http_status=status
        )
    if len(response.content) > 262_144:
        raise OIDCUnavailable("The OIDC provider returned an unusable response.", reason="response_too_large", http_status=status)
    try:
        result = response.json()
    except ValueError as exc:
        raise OIDCUnavailable(
            "The OIDC provider is unavailable.", reason="invalid_json", error_type=type(exc).__name__, http_status=status,
        ) from None
    if not isinstance(result, dict):
        raise OIDCUnavailable("The OIDC provider returned invalid metadata.", reason="invalid_response_shape", http_status=status)
    return result


def _load_provider_metadata(config: Mapping[str, Any]) -> dict[str, Any]:
    issuer = str(config["oidc_issuer"])
    metadata = _json_get(f"{issuer}/.well-known/openid-configuration", issuer, config)
    if metadata.get("issuer") != issuer:
        raise OIDCUnavailable("The OIDC issuer did not match the configured issuer.", reason="issuer_mismatch", http_status=200)
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        value = metadata.get(key)
        if not isinstance(value, str) or not _valid_endpoint(value):
            raise OIDCUnavailable(f"The OIDC {key} is invalid.", reason="invalid_endpoint", http_status=200)
    methods = metadata.get("code_challenge_methods_supported", ["S256"])
    if not isinstance(methods, list) or "S256" not in methods:
        raise OIDCUnavailable("The OIDC provider does not support PKCE S256.", reason="pkce_unsupported", http_status=200)
    return metadata


@observe_oidc("discovery")
def provider_metadata(config: Mapping[str, Any]) -> dict[str, Any]:
    key = ("metadata", str(config["oidc_issuer"]), *trust_cache_key(_trust(config)))
    # Callers receive a copy so one flow cannot mutate later flows' endpoints.
    from copy import deepcopy  # noqa: PLC0415

    return deepcopy(cached_provider_value(key, lambda: _load_provider_metadata(config)))


@observe_oidc("signing_keys")
def _provider_keys(config: Mapping[str, Any], metadata: Mapping[str, Any], *, replace: Any = None) -> jwk.KeySet:
    issuer = str(config["oidc_issuer"])
    key = ("keys", issuer, str(metadata["jwks_uri"]), *trust_cache_key(_trust(config)))

    def load() -> jwk.KeySet:
        keys = _json_get(str(metadata["jwks_uri"]), issuer, config)
        if not isinstance(keys.get("keys"), list) or not keys["keys"]:
            raise OIDCUnavailable(
                "The OIDC provider returned an invalid signing key set.",
                reason="invalid_signing_keys", http_status=200
            )
        try:
            keyset = jwk.KeySet.import_key_set(cast(jwk.KeySetSerialization, keys))
        except (JoseError, ValueError, TypeError, KeyError) as exc:
            raise OIDCUnavailable(
                "The OIDC provider returned an invalid signing key set.",
                reason="invalid_signing_keys", error_type=type(exc).__name__, http_status=200,
            ) from None
        if not keyset.keys:
            raise OIDCUnavailable(
                "The OIDC provider returned an invalid signing key set.",
                reason="invalid_signing_keys", http_status=200
            )
        return keyset

    return cached_provider_value(key, load, replace=replace)


def _client(config: Mapping[str, Any]) -> OAuth2Session:
    return OAuth2Session(
        client_id=str(config["oidc_client_id"]),
        client_secret=str(config["oidc_client_secret"]),
        redirect_uri=str(config["oidc_redirect_uri"]),
        scope=" ".join(config["oidc_scopes"]),
        code_challenge_method="S256",
        token_endpoint_auth_method="client_secret_basic",
    )


@observe_oidc("flow_creation")
def start_flow(
    config: Mapping[str, Any], *, purpose: str, principal_id: str = "",
    browser_session_id: str = "", next_path: str = "/",
) -> tuple[str, str]:
    if purpose not in {"sign_in", "link"}:
        raise OIDCError("Unsupported OIDC flow.", reason="invalid_purpose")
    if purpose == "link" and (not principal_id or not browser_session_id):
        raise OIDCError("A current credential session is required to link OIDC.", reason="recent_credential_required")
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


@observe_oidc("flow_validation")
def consume_flow(state: str, cookie_state: str) -> OIDCFlow:
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", state) or not hmac.compare_digest(state, cookie_state):
        raise OIDCError("The OIDC sign-in attempt expired. Please start again.", reason="flow_expired")
    digest = hashlib.sha256(state.encode("utf-8")).digest()

    def operation(conn: Any) -> OIDCFlow:
        row = conn.execute(
            "DELETE FROM oidc_auth_flows WHERE state_digest = ? RETURNING *", (digest,)
        ).fetchone()
        data = _row(row)
        if not data or _as_utc(data["expires_at"]) <= _now():
            raise OIDCError("The OIDC sign-in attempt expired. Please start again.", reason="flow_expired")
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


@observe_oidc("token_exchange")
def _exchange_token(config: Mapping[str, Any], flow: OIDCFlow, code: str, metadata: Mapping[str, Any]) -> str:
    client = _client(config)
    status: int | None = None

    def capture_status(response):
        nonlocal status
        status = provider_status(response.status_code)
        return response

    client.register_compliance_hook("access_token_response", capture_status)
    try:
        token = client.fetch_token(
            metadata["token_endpoint"], code=code, code_verifier=flow.code_verifier,
            redirect_uri=str(config["oidc_redirect_uri"]),
            allow_redirects=False, timeout=10, verify=_trust(config),
        )
    except OIDCError:
        raise
    except OAuthError as exc:
        reason = {
            "invalid_grant": "code_rejected", "access_denied": "provider_denied",
            "invalid_client": "client_authentication_failed", "unauthorized_client": "client_not_authorized",
            "server_error": "provider_unavailable", "temporarily_unavailable": "provider_unavailable",
        }.get(exc.error, "token_exchange_failed")
        error = OIDCError if reason in {"code_rejected", "provider_denied"} else OIDCUnavailable
        raise error("The OIDC code exchange failed.", reason=reason, error_type=type(exc).__name__, http_status=status) from None
    except Exception as exc:
        reason = (
            "invalid_json" if isinstance(exc, requests.exceptions.JSONDecodeError)
            else "invalid_response_shape" if isinstance(exc, (ValueError, TypeError))
            else exception_reason(exc, fallback="token_exchange_failed")
        )
        raise OIDCUnavailable(
            "The OIDC code exchange failed.", reason=reason, error_type=type(exc).__name__, http_status=status,
        ) from None
    if status is not None and status != 200:
        raise OIDCUnavailable("The OIDC code exchange failed.", reason="provider_http_error", http_status=status)
    if not isinstance(token, dict):
        raise OIDCUnavailable(
            "The OIDC provider returned an invalid token response.",
            reason="invalid_response_shape", http_status=status
        )
    id_token = token.get("id_token")
    if not isinstance(id_token, str) or len(id_token) > 32_768:
        raise OIDCUnavailable("The OIDC provider did not return a valid ID token.", reason="id_token_missing", http_status=status)
    return id_token


def _token_rejection_reason(exc: BaseException) -> str:
    if isinstance(exc, ExpiredTokenError):
        return "token_expired"
    if isinstance(exc, BadSignatureError):
        return "signature_invalid"
    if isinstance(exc, InvalidKeyIdError):
        return "signing_key_unknown"
    if isinstance(exc, MissingClaimError):
        return "claim_missing"
    if isinstance(exc, ClaimError):
        return {
            "iss": "issuer_mismatch", "aud": "audience_mismatch", "nonce": "nonce_mismatch",
            "sub": "subject_invalid", "iat": "issued_at_invalid",
        }.get(exc.claim, "token_claim_invalid")
    return "token_invalid"


@observe_oidc("token_validation")
def _verify_id_token(
    config: Mapping[str, Any], flow: OIDCFlow, id_token: str, keyset: jwk.KeySet, metadata: Mapping[str, Any],
) -> str:
    try:
        try:
            verified = jwt.decode(id_token, keyset, algorithms=_ALGORITHMS)
        except InvalidKeyIdError:
            keyset = _provider_keys(config, metadata, replace=keyset)
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
            raise OIDCError("The OIDC authorized party did not match this client.", reason="authorized_party_mismatch")
        if claims["iat"] > now + 30:
            raise OIDCError("The OIDC ID token was issued in the future.", reason="issued_at_invalid")
        subject = claims["sub"]
        if not isinstance(subject, str) or not 0 < len(subject) <= 512:
            raise OIDCError("The OIDC subject is invalid.", reason="subject_invalid")
        if flow.purpose == "link":
            auth_time = claims.get("auth_time")
            if not isinstance(auth_time, int) or auth_time < now - RECENT_AUTH_SECONDS or auth_time > now + 30:
                raise OIDCError("Recent provider authentication is required to link OIDC.", reason="recent_provider_required")
    except OIDCError:
        raise
    except (JoseError, ValueError, TypeError, KeyError) as exc:
        raise OIDCError(
            "The OIDC ID token could not be verified.", reason=_token_rejection_reason(exc), error_type=type(exc).__name__,
        ) from None
    return subject


def exchange_code(config: Mapping[str, Any], flow: OIDCFlow, code: str) -> tuple[str, str]:
    with oidc_purpose(flow.purpose):
        if not code or len(code) > 4096:
            raise OIDCError(
                "The OIDC provider did not return an authorization code.", stage="token_exchange", reason="code_missing",
            )
        metadata = provider_metadata(config)
        id_token = _exchange_token(config, flow, code, metadata)
        keyset = _provider_keys(config, metadata)
        return str(config["oidc_issuer"]), _verify_id_token(config, flow, id_token, keyset, metadata)


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


@observe_oidc("identity_binding")
def linked_credential_source(flow: OIDCFlow) -> tuple[str, str, str]:
    """Return the proved credential, authentication time, and absolute deadline."""
    if flow.purpose != "link":
        raise OIDCError("A credential source is required for provider linking.", reason="recent_credential_required")

    def operation(conn: Any) -> tuple[str, str, str]:
        data = _row(conn.execute(
            "SELECT credential_id, authenticated_at, absolute_expires_at FROM browser_sessions "
            "WHERE id = ? AND principal_id = ? AND revoked_at IS NULL",
            (flow.browser_session_id, flow.principal_id),
        ).fetchone())
        if not data or not data.get("credential_id"):
            raise OIDCError("The credential session is no longer available.", reason="credential_session_unavailable")
        return str(data["credential_id"]), str(data["authenticated_at"]), str(data["absolute_expires_at"])

    return run_read(operation)


@observe_oidc("identity_binding")
def complete_identity(config: Mapping[str, Any], flow: OIDCFlow, issuer: str, subject: str) -> OIDCIdentity:
    events = LifecycleEvents("provider_provisioning")

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
                raise OIDCError(
                    "A recent, active credential session is required to link OIDC.",
                    reason="recent_credential_required"
                )
            if existing and existing["principal_id"] != flow.principal_id:
                raise OIDCError(
                    "This provider identity is already linked to another workspace.",
                    reason="identity_already_linked"
                )
            other = _row(conn.execute(
                "SELECT id, subject FROM oidc_identities WHERE principal_id = ? AND issuer = ?",
                (flow.principal_id, issuer),
            ).fetchone())
            if other and other["subject"] != subject:
                raise OIDCError(
                    "This workspace is already linked to a different provider identity.",
                    reason="workspace_already_linked"
                )
            principal_id = flow.principal_id
        else:
            if existing:
                if existing["status"] != "active":
                    raise OIDCError("This workspace is unavailable.", reason="workspace_disabled")
                return _identity(existing)
            policy = str(config.get("oidc_provisioning") or "disabled")
            if policy == "disabled" or (policy == "allowlist" and subject not in config.get("oidc_allowed_subjects", [])):
                raise OIDCError("This provider identity isn't approved for a workspace.", reason="provisioning_denied")
            principal_id = _create_principal(conn)
            events.principal("PRINCIPAL_CREATED", get_principal(principal_id, conn=conn))
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

    return events.run(operation)


@observe_oidc("identity_binding")
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
            raise OIDCError(
                "Add an active portable credential before unlinking the only sign-in method.",
                reason="alternative_credential_required"
            )
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
