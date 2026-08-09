# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Encrypted, process-private storage for recoverable OAST provider sessions."""

from __future__ import annotations

from base64 import b64decode, b64encode
from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from typing import Any
import uuid

from config import resolve_data_dir
from services.connectors.oast_provider_contracts import OastProviderSession
from services.connectors.oast_provider_crypto import registration_public_key
from services.secrets.vault import decrypt_secret, encrypt_secret


_CORRELATION_ID_RE = re.compile(r"ocr_[0-9a-f]{32}")
_CALLBACK_LABEL_RE = re.compile(r"[a-z0-9]{33}")
_ORIGIN_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SESSION_VERSION = 1
_MAX_SESSION_FILE_BYTES = 8192
_SPOOL_LIMIT = 256


class OastProviderSessionSpoolError(RuntimeError):
    """Raised when private provider session material can't be retained safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _spool_dir(cfg: Mapping[str, Any] | None = None) -> Path:
    path = Path(resolve_data_dir(cfg)) / "oast-provider-sessions"
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path_stat = path.lstat()
        if not stat.S_ISDIR(path_stat.st_mode) or stat.S_ISLNK(path_stat.st_mode):
            raise OSError("session spool is not a private directory")
        os.chmod(path, 0o700)
    except OSError as exc:
        raise OastProviderSessionSpoolError(
            "oast_provider_spool_unavailable",
            "Private OAST session storage is unavailable",
        ) from exc
    return path


def _correlation_identity(correlation: Mapping[str, object]) -> tuple[str, str, str]:
    correlation_id = str(correlation.get("id") or "").strip().lower()
    callback_label = str(correlation.get("callback_label") or "").strip().lower()
    origin_sha256 = str(correlation.get("service_origin_sha256") or "").strip().lower()
    if (
        not _CORRELATION_ID_RE.fullmatch(correlation_id)
        or not _CALLBACK_LABEL_RE.fullmatch(callback_label)
        or not _ORIGIN_SHA256_RE.fullmatch(origin_sha256)
    ):
        raise OastProviderSessionSpoolError(
            "oast_provider_session_invalid",
            "The private OAST provider session identity is invalid",
        )
    return correlation_id, callback_label, origin_sha256


def _session_path(correlation_id: str, cfg: Mapping[str, Any] | None = None) -> Path:
    selected_id = str(correlation_id or "").strip().lower()
    if not _CORRELATION_ID_RE.fullmatch(selected_id):
        raise OastProviderSessionSpoolError(
            "oast_provider_session_invalid",
            "The private OAST provider session identity is invalid",
        )
    return _spool_dir(cfg) / f"{selected_id}.session"


def _associated_data(correlation_id: str, callback_label: str, origin_sha256: str) -> bytes:
    return (
        "darklab_shell/oast-provider-session/v1\0"
        f"{correlation_id}\0{callback_label}\0{origin_sha256}"
    ).encode("ascii")


def _validated_session(session: OastProviderSession, callback_label: str) -> None:
    try:
        secret = uuid.UUID(session.secret_key)
        registration_public_key(session)
    except (TypeError, ValueError, AttributeError, RuntimeError) as exc:
        raise OastProviderSessionSpoolError(
            "oast_provider_session_invalid",
            "The private OAST provider session is invalid",
        ) from exc
    if (
        session.callback_label != callback_label
        or session.correlation_id != callback_label[:20]
        or str(secret) != session.secret_key
    ):
        raise OastProviderSessionSpoolError(
            "oast_provider_session_invalid",
            "The private OAST provider session is invalid",
        )


def store_oast_provider_session(
    correlation: Mapping[str, object],
    session: OastProviderSession,
    cfg: Mapping[str, Any] | None = None,
) -> None:
    """Atomically retain one encrypted provider session outside the database."""
    correlation_id, callback_label, origin_sha256 = _correlation_identity(correlation)
    _validated_session(session, callback_label)
    payload = json.dumps(
        {
            "callback_label": session.callback_label,
            "correlation_id": correlation_id,
            "private_key_pem": session.private_key_pem.decode("ascii"),
            "provider_correlation_id": session.correlation_id,
            "secret_key": session.secret_key,
            "service_origin_sha256": origin_sha256,
            "version": _SESSION_VERSION,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    try:
        ciphertext, nonce = encrypt_secret(
            payload,
            associated_data=_associated_data(correlation_id, callback_label, origin_sha256),
        )
        envelope = json.dumps(
            {
                "ciphertext": b64encode(ciphertext).decode("ascii"),
                "nonce": b64encode(nonce).decode("ascii"),
                "version": _SESSION_VERSION,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        if len(envelope) > _MAX_SESSION_FILE_BYTES:
            raise ValueError("encrypted session is too large")
        destination = _session_path(correlation_id, cfg)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb", delete=False, dir=str(destination.parent)
            ) as handle:
                temporary = Path(handle.name)
                handle.write(envelope)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    except OastProviderSessionSpoolError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        raise OastProviderSessionSpoolError(
            "oast_provider_session_store_failed",
            "The private OAST provider session could not be retained",
        ) from exc


def _load_envelope(path: Path) -> tuple[bytes, bytes]:
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            path_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(path_stat.st_mode):
                raise OSError("session spool is not a regular file")
            os.fchmod(handle.fileno(), 0o600)
            raw = handle.read(_MAX_SESSION_FILE_BYTES + 1)
        envelope = json.loads(raw.decode("ascii"))
        if (
            not raw
            or len(raw) > _MAX_SESSION_FILE_BYTES
            or not isinstance(envelope, dict)
            or set(envelope) != {"ciphertext", "nonce", "version"}
            or envelope.get("version") != _SESSION_VERSION
        ):
            raise ValueError("invalid session envelope")
        ciphertext = b64decode(str(envelope["ciphertext"]), validate=True)
        nonce = b64decode(str(envelope["nonce"]), validate=True)
        if len(nonce) != 12 or len(ciphertext) < 16:
            raise ValueError("invalid encrypted session")
        return ciphertext, nonce
    except (OSError, KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise OastProviderSessionSpoolError(
            "oast_provider_session_unavailable",
            "The private OAST provider session is unavailable",
        ) from exc


def load_oast_provider_session(
    correlation: Mapping[str, object],
    cfg: Mapping[str, Any] | None = None,
) -> OastProviderSession:
    """Decrypt a session only for its exact durable correlation identity."""
    correlation_id, callback_label, origin_sha256 = _correlation_identity(correlation)
    ciphertext, nonce = _load_envelope(_session_path(correlation_id, cfg))
    try:
        plaintext = decrypt_secret(
            ciphertext,
            nonce,
            associated_data=_associated_data(correlation_id, callback_label, origin_sha256),
        )
        payload = json.loads(plaintext)
        expected = {
            "callback_label",
            "correlation_id",
            "private_key_pem",
            "provider_correlation_id",
            "secret_key",
            "service_origin_sha256",
            "version",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("invalid session payload")
        if (
            payload["version"] != _SESSION_VERSION
            or payload["correlation_id"] != correlation_id
            or payload["callback_label"] != callback_label
            or payload["service_origin_sha256"] != origin_sha256
        ):
            raise ValueError("session identity mismatch")
        session = OastProviderSession(
            callback_label=str(payload["callback_label"]),
            correlation_id=str(payload["provider_correlation_id"]),
            secret_key=str(payload["secret_key"]),
            private_key_pem=str(payload["private_key_pem"]).encode("ascii"),
        )
        _validated_session(session, callback_label)
        return session
    except OastProviderSessionSpoolError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise OastProviderSessionSpoolError(
            "oast_provider_session_invalid",
            "The private OAST provider session is invalid",
        ) from exc


def discard_oast_provider_session(
    correlation_id: str,
    cfg: Mapping[str, Any] | None = None,
) -> None:
    """Best-effort removal for terminal or orphaned provider sessions."""
    try:
        _session_path(correlation_id, cfg).unlink(missing_ok=True)
    except (OSError, OastProviderSessionSpoolError):
        return


def stale_oast_provider_session_ids(
    cfg: Mapping[str, Any] | None = None,
    *,
    now: float | None = None,
    grace_seconds: int = 300,
) -> tuple[str, ...]:
    """Return a bounded set of old regular session files for reconciliation."""
    cutoff = (time.time() if now is None else float(now)) - max(60, int(grace_seconds))
    candidates: list[str] = []
    for path in sorted(_spool_dir(cfg).glob("ocr_*.session"))[:_SPOOL_LIMIT]:
        try:
            path_stat = path.lstat()
        except OSError:
            continue
        if (
            not stat.S_ISREG(path_stat.st_mode)
            or stat.S_ISLNK(path_stat.st_mode)
            or path_stat.st_mtime > cutoff
            or not _CORRELATION_ID_RE.fullmatch(path.stem)
        ):
            continue
        candidates.append(path.stem)
    return tuple(candidates)


__all__ = [
    "OastProviderSessionSpoolError",
    "discard_oast_provider_session",
    "load_oast_provider_session",
    "stale_oast_provider_session_ids",
    "store_oast_provider_session",
]
