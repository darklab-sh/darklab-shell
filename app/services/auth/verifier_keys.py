# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Versioned verifier roots and keyed credential digests."""

from __future__ import annotations

import base64
from collections.abc import Callable
import hashlib
import hmac
import secrets
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from services.secrets.vault import decrypt_secret, encrypt_secret

from .contracts import (
    CREDENTIAL_WRAP_ALGORITHM,
    VerifierKeyError,
    timestamp,
)


VERIFIER_ROOT_BYTES = 32
VERIFIER_HKDF_SALT = b"darklab_shell/auth/v1/verifier"
_VERIFIER_INFO = {
    "portable": b"access-credential",
    "pat": b"personal-access-token",
}


def verifier_root_associated_data(version: int) -> bytes:
    parsed = int(version)
    if parsed <= 0:
        raise VerifierKeyError("verifier-root version must be positive")
    return f"darklab_shell/auth/verifier-root/v1/{parsed}".encode("ascii")


def _encode_root(root: bytes) -> str:
    if len(root) != VERIFIER_ROOT_BYTES:
        raise VerifierKeyError("verifier root must contain exactly 32 bytes")
    return base64.b64encode(root).decode("ascii")


def _decode_root(value: str) -> bytes:
    try:
        root = base64.b64decode(str(value), validate=True)
    except Exception as exc:
        raise VerifierKeyError("stored verifier root is not valid base64") from exc
    if len(root) != VERIFIER_ROOT_BYTES:
        raise VerifierKeyError("stored verifier root has the wrong length")
    return root


def _row_value(row: Any, key: str, index: int) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _insert_root(conn: Any, version: int, root: bytes, created_at: str) -> None:
    ciphertext, nonce = encrypt_secret(
        _encode_root(root),
        associated_data=verifier_root_associated_data(version),
    )
    conn.execute(
        "INSERT INTO credential_verifier_roots "
        "(version, state, wrapped_root, wrap_nonce, wrap_algorithm, created_at, retired_at) "
        "VALUES (?, 'active', ?, ?, ?, ?, NULL)",
        (version, ciphertext, nonce, CREDENTIAL_WRAP_ALGORITHM, created_at),
    )


def ensure_active_verifier_root(conn: Any) -> tuple[int, bytes]:
    row = conn.execute(
        "SELECT version, wrapped_root, wrap_nonce, wrap_algorithm "
        "FROM credential_verifier_roots WHERE state = 'active'"
    ).fetchone()
    if row is None:
        count_row = conn.execute("SELECT COUNT(*) AS count FROM credentials").fetchone()
        credential_count = _row_value(count_row, "count", 0)
        if int(credential_count or 0) != 0:
            raise VerifierKeyError("credentials exist without an active verifier root")
        version = 1
        root = secrets.token_bytes(VERIFIER_ROOT_BYTES)
        _insert_root(conn, version, root, timestamp())
        return version, root

    version = int(_row_value(row, "version", 0))
    algorithm = str(_row_value(row, "wrap_algorithm", 3))
    if algorithm != CREDENTIAL_WRAP_ALGORITHM:
        raise VerifierKeyError("stored verifier root uses an unsupported wrapping algorithm")
    try:
        plaintext = decrypt_secret(
            bytes(_row_value(row, "wrapped_root", 1)),
            bytes(_row_value(row, "wrap_nonce", 2)),
            associated_data=verifier_root_associated_data(version),
        )
    except Exception as exc:
        raise VerifierKeyError("active verifier root cannot be decrypted") from exc
    return version, _decode_root(plaintext)


def derive_verifier_key(root: bytes, credential_type: str) -> bytes:
    try:
        info = _VERIFIER_INFO[credential_type]
    except KeyError as exc:
        raise VerifierKeyError("unsupported credential type") from exc
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=VERIFIER_HKDF_SALT,
        info=info,
    ).derive(bytes(root))


def credential_verifier_digest(
    root: bytes,
    credential_type: str,
    credential_id: str,
    secret_bytes: bytes,
) -> bytes:
    try:
        credential_id_bytes = credential_id.encode("ascii")
        credential_type_bytes = credential_type.encode("ascii")
    except UnicodeEncodeError as exc:
        raise VerifierKeyError("credential identifiers must be ASCII") from exc
    payload = credential_type_bytes + b"\x00" + credential_id_bytes + b"\x00" + bytes(secret_bytes)
    return hmac.new(
        derive_verifier_key(root, credential_type),
        payload,
        hashlib.sha256,
    ).digest()


def rotate_verifier_root(conn: Any, *, now: str | None = None) -> int:
    active = conn.execute(
        "SELECT version FROM credential_verifier_roots WHERE state = 'active'"
    ).fetchone()
    if active is None:
        version, _ = ensure_active_verifier_root(conn)
        return version
    retired_at = now or timestamp()
    active_version = int(_row_value(active, "version", 0))
    next_row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM credential_verifier_roots"
    ).fetchone()
    next_version = int(_row_value(next_row, "next_version", 0))
    conn.execute(
        "UPDATE credential_verifier_roots SET state = 'retired', retired_at = ? "
        "WHERE version = ? AND state = 'active'",
        (retired_at, active_version),
    )
    _insert_root(conn, next_version, secrets.token_bytes(VERIFIER_ROOT_BYTES), retired_at)
    return next_version


def delete_retired_verifier_root(conn: Any, version: int) -> None:
    parsed = int(version)
    row = conn.execute(
        "SELECT state FROM credential_verifier_roots WHERE version = ?",
        (parsed,),
    ).fetchone()
    if row is None:
        raise VerifierKeyError("verifier-root version was not found")
    if str(_row_value(row, "state", 0)) != "retired":
        raise VerifierKeyError("the active verifier root cannot be deleted")
    reference_row = conn.execute(
        "SELECT COUNT(*) AS count FROM credentials WHERE verifier_root_version = ?",
        (parsed,),
    ).fetchone()
    references = _row_value(reference_row, "count", 0)
    if int(references or 0):
        raise VerifierKeyError("referenced verifier roots cannot be deleted")
    conn.execute("DELETE FROM credential_verifier_roots WHERE version = ?", (parsed,))


def rewrap_verifier_roots(
    conn: Any,
    *,
    decrypt: Callable[..., str] = decrypt_secret,
    encrypt: Callable[..., tuple[bytes, bytes]] = encrypt_secret,
) -> int:
    """Rewrap unchanged roots; callers may supply old/new vault boundaries."""
    rows = conn.execute(
        "SELECT version, wrapped_root, wrap_nonce FROM credential_verifier_roots ORDER BY version"
    ).fetchall()
    rewrapped = 0
    for row in rows:
        version = int(_row_value(row, "version", 0))
        associated_data = verifier_root_associated_data(version)
        plaintext = decrypt(
            bytes(_row_value(row, "wrapped_root", 1)),
            bytes(_row_value(row, "wrap_nonce", 2)),
            associated_data=associated_data,
        )
        _decode_root(plaintext)
        ciphertext, nonce = encrypt(plaintext, associated_data=associated_data)
        conn.execute(
            "UPDATE credential_verifier_roots SET wrapped_root = ?, wrap_nonce = ? "
            "WHERE version = ?",
            (ciphertext, nonce, version),
        )
        rewrapped += 1
    return rewrapped


def compare_verifier_digest(expected: bytes, candidate: bytes) -> bool:
    return hmac.compare_digest(bytes(expected), bytes(candidate))
