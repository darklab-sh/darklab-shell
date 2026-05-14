"""AES-GCM wrapping helpers for per-session secrets."""

from __future__ import annotations

import base64
import logging
import os
import secrets
import threading
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config import resolve_data_dir

log = logging.getLogger("shell")

MASTER_KEY_ENV = "SECRETS_MASTER_KEY"
MASTER_KEY_FILENAME = ".secrets_master_key"
MASTER_KEY_BYTES = 32
SECRET_VALUE_MAX_BYTES = 4096
NONCE_BYTES = 12
HKDF_SALT = b"darklab_shell/secrets/v1"
HKDF_INFO = b"vault-wrap"

_master_key_cache: bytes | None = None
_master_key_source: str = ""
_warned_file_ignored = False
_logged_generated = False
_master_key_lock = threading.Lock()


class SecretVaultError(ValueError):
    """Base class for vault validation and crypto errors."""


class MasterKeyError(SecretVaultError):
    """Raised when the deployment master key cannot be loaded."""


class SecretDecryptError(SecretVaultError):
    """Raised when a ciphertext cannot be decrypted with the active key."""


class InvalidSecretValue(SecretVaultError):
    """Raised when a secret value is empty or too large."""


def _key_file_path() -> Path:
    return Path(resolve_data_dir()) / MASTER_KEY_FILENAME


def _ensure_key_file_mode(path: Path) -> None:
    try:
        if path.stat().st_mode & 0o777 != 0o600:
            os.chmod(path, 0o600)
    except OSError as exc:
        raise MasterKeyError(f"could not secure {path}") from exc


def _decode_master_key(raw: str, source: str) -> bytes:
    try:
        key = base64.b64decode(str(raw or "").strip(), validate=True)
    except Exception as exc:
        raise MasterKeyError(f"{source} must be base64-encoded") from exc
    if len(key) != MASTER_KEY_BYTES:
        raise MasterKeyError(f"{source} must decode to exactly {MASTER_KEY_BYTES} bytes")
    return key


def _read_key_file(path: Path) -> bytes | None:
    if not path.exists():
        return None
    _ensure_key_file_mode(path)
    try:
        return _decode_master_key(path.read_text(encoding="utf-8"), str(path))
    except OSError as exc:
        raise MasterKeyError(f"could not read {path}") from exc


def _write_new_key_file(path: Path) -> bytes:
    global _logged_generated
    key = secrets.token_bytes(MASTER_KEY_BYTES)
    encoded = base64.b64encode(key).decode("ascii") + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        existing = _read_key_file(path)
        if existing is None:
            raise MasterKeyError(f"{path} exists but could not be read")
        return existing
    except OSError as exc:
        raise MasterKeyError(f"could not create {path}") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if not _logged_generated:
        log.warning("MASTER_KEY_GENERATED", extra={"path": str(path)})
        _logged_generated = True
    return key


def _load_master_key() -> tuple[bytes, str]:
    global _warned_file_ignored
    env_value = os.environ.get(MASTER_KEY_ENV, "").strip()
    key_path = _key_file_path()
    if env_value:
        if key_path.exists() and not _warned_file_ignored:
            log.warning("MASTER_KEY_FILE_IGNORED", extra={"path": str(key_path)})
            _warned_file_ignored = True
        return _decode_master_key(env_value, MASTER_KEY_ENV), "env"

    existing = _read_key_file(key_path)
    if existing is not None:
        return existing, "file"
    return _write_new_key_file(key_path), "file"


def reset_master_key_cache_for_tests() -> None:
    """Clear cached key state for tests that patch env/data-dir values."""
    global _master_key_cache, _master_key_source, _warned_file_ignored, _logged_generated
    _master_key_cache = None
    _master_key_source = ""
    _warned_file_ignored = False
    _logged_generated = False


def master_key_source() -> str:
    """Return the active master-key source, loading the key on first use."""
    if _master_key_cache is None:
        get_wrapping_key()
    return _master_key_source


def get_wrapping_key() -> bytes:
    """Return the derived AES-GCM key for this deployment."""
    global _master_key_cache, _master_key_source
    if _master_key_cache is None:
        with _master_key_lock:
            if _master_key_cache is None:
                master_key, source = _load_master_key()
                _master_key_cache = HKDF(
                    algorithm=hashes.SHA256(),
                    length=MASTER_KEY_BYTES,
                    salt=HKDF_SALT,
                    info=HKDF_INFO,
                ).derive(master_key)
                _master_key_source = source
    assert _master_key_cache is not None
    return _master_key_cache


def _secret_bytes(value: str) -> bytes:
    text = str(value or "")
    if text == "":
        raise InvalidSecretValue("secret value is required")
    encoded = text.encode("utf-8")
    if len(encoded) > SECRET_VALUE_MAX_BYTES:
        raise InvalidSecretValue(f"secret value must be {SECRET_VALUE_MAX_BYTES} bytes or less")
    return encoded


def encrypt_secret(value: str, *, associated_data: bytes | None = None) -> tuple[bytes, bytes]:
    """Encrypt a UTF-8 secret value and return ``(ciphertext, nonce)``."""
    nonce = secrets.token_bytes(NONCE_BYTES)
    ciphertext = AESGCM(get_wrapping_key()).encrypt(nonce, _secret_bytes(value), associated_data)
    return ciphertext, nonce


def decrypt_secret(ciphertext: bytes, nonce: bytes, *, associated_data: bytes | None = None) -> str:
    """Decrypt a stored secret value with the active wrapping key."""
    try:
        plaintext = AESGCM(get_wrapping_key()).decrypt(bytes(nonce), bytes(ciphertext), associated_data)
    except InvalidTag as exc:
        raise SecretDecryptError("secret could not be decrypted with the active key") from exc
    return plaintext.decode("utf-8")
