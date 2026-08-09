# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Local session key handling for encrypted private OAST polling."""

from __future__ import annotations

from base64 import b64decode, b64encode
import json
import re
import uuid

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from services.connectors.oast_provider_contracts import (
    OastProviderSession,
    OastProviderTransportError,
)


_CALLBACK_LABEL_RE = re.compile(r"[a-z0-9]{33}")
_MAX_INTERACTION_BYTES = 65536


def new_oast_provider_session(callback_label: str) -> OastProviderSession:
    """Create private Interactsh session material without contacting the provider."""
    label = str(callback_label or "").strip().lower()
    if not _CALLBACK_LABEL_RE.fullmatch(label):
        raise OastProviderTransportError(
            "oast_provider_callback_invalid",
            "The private OAST callback label is incompatible with the provider",
        )
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return OastProviderSession(
        callback_label=label,
        correlation_id=label[:20],
        secret_key=str(uuid.uuid4()),
        private_key_pem=private_key_pem,
    )


def _private_key(session: OastProviderSession) -> rsa.RSAPrivateKey:
    try:
        private_key = serialization.load_pem_private_key(
            session.private_key_pem,
            password=None,
        )
    except (TypeError, ValueError) as exc:
        raise OastProviderTransportError(
            "oast_provider_session_invalid",
            "The private OAST provider session is invalid",
        ) from exc
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise OastProviderTransportError(
            "oast_provider_session_invalid",
            "The private OAST provider session is invalid",
        )
    return private_key


def registration_public_key(session: OastProviderSession) -> str:
    """Return the provider registration key as base64-encoded public PEM."""
    public_pem = (
        _private_key(session)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return b64encode(public_pem).decode("ascii")


def decrypt_poll_key(session: OastProviderSession, value: object) -> bytes:
    """Decrypt and validate one provider poll AES key."""
    try:
        encrypted_key = b64decode(str(value or ""), validate=True)
        key = _private_key(session).decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        algorithms.AES(key)
    except (TypeError, ValueError) as exc:
        raise OastProviderTransportError(
            "oast_provider_encryption_invalid",
            "The private OAST provider returned invalid encrypted data",
        ) from exc
    return key


def decrypt_interaction(key: bytes, value: str) -> dict[str, object]:
    """Decrypt one AES-CTR provider record into an exact JSON object."""
    try:
        ciphertext = b64decode(value, validate=True)
        if len(ciphertext) < 16:
            raise ValueError("ciphertext is too short")
        decryptor = Cipher(algorithms.AES(key), modes.CTR(ciphertext[:16])).decryptor()
        plaintext = decryptor.update(ciphertext[16:]) + decryptor.finalize()
        if len(plaintext) > _MAX_INTERACTION_BYTES:
            raise ValueError("interaction is too large")
        interaction = json.loads(plaintext.decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OastProviderTransportError(
            "oast_provider_interaction_invalid",
            "The private OAST provider returned an invalid interaction",
        ) from exc
    if not isinstance(interaction, dict):
        raise OastProviderTransportError(
            "oast_provider_interaction_invalid",
            "The private OAST provider returned an invalid interaction",
        )
    return interaction


__all__ = [
    "decrypt_interaction",
    "decrypt_poll_key",
    "new_oast_provider_session",
    "registration_public_key",
]
