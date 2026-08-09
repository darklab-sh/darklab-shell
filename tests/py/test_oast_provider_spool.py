# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Encrypted private OAST provider-session spool tests."""

from __future__ import annotations

from base64 import b64decode, b64encode
import json
import os
from pathlib import Path
import stat

import pytest

from services.connectors.oast_provider_crypto import new_oast_provider_session
from services.connectors.oast_provider_spool import (
    OastProviderSessionSpoolError,
    discard_oast_provider_session,
    load_oast_provider_session,
    oast_provider_session_is_staged,
    stale_oast_provider_session_ids,
    store_oast_provider_session,
)
from services.secrets import vault as secrets_vault


_CORRELATION_ID = "ocr_0123456789abcdef0123456789abcdef"
_LABEL = "abcdefghijklmnopqrstuvwxy01234567"
_ORIGIN_SHA256 = "a" * 64


@pytest.fixture(autouse=True)
def _isolated_master_key(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        secrets_vault.MASTER_KEY_ENV,
        b64encode(b"oast-session-spool-test-key!!!!!").decode("ascii"),
    )
    secrets_vault.reset_master_key_cache_for_tests()
    yield
    secrets_vault.reset_master_key_cache_for_tests()


def _correlation(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": _CORRELATION_ID,
        "callback_label": _LABEL,
        "service_origin_sha256": _ORIGIN_SHA256,
    }
    value.update(changes)
    return value


def _session_path(root: Path) -> Path:
    return root / "oast-provider-sessions" / f"{_CORRELATION_ID}.session"


def test_oast_provider_session_spool_round_trips_encrypted_private_material(tmp_path):
    session = new_oast_provider_session(_LABEL)

    store_oast_provider_session(_correlation(), session)

    path = _session_path(tmp_path)
    assert oast_provider_session_is_staged(_CORRELATION_ID) is True
    raw = path.read_bytes()
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert set(json.loads(raw)) == {"ciphertext", "nonce", "version"}
    assert session.secret_key.encode() not in raw
    assert session.private_key_pem not in raw
    assert b"PRIVATE KEY" not in raw

    loaded = load_oast_provider_session(_correlation())

    assert loaded == session
    assert session.secret_key not in repr(loaded)
    assert "PRIVATE KEY" not in repr(loaded)
    discard_oast_provider_session(_CORRELATION_ID)
    assert not path.exists()
    assert oast_provider_session_is_staged(_CORRELATION_ID) is False


def test_oast_provider_session_spool_rejects_tampering_and_identity_drift(tmp_path):
    session = new_oast_provider_session(_LABEL)
    store_oast_provider_session(_correlation(), session)
    path = _session_path(tmp_path)
    envelope = json.loads(path.read_text(encoding="ascii"))
    ciphertext = bytearray(b64decode(envelope["ciphertext"], validate=True))
    ciphertext[0] ^= 1
    envelope["ciphertext"] = b64encode(ciphertext).decode("ascii")
    path.write_text(json.dumps(envelope), encoding="ascii")

    with pytest.raises(OastProviderSessionSpoolError) as exc_info:
        load_oast_provider_session(_correlation())
    assert exc_info.value.code == "oast_provider_session_invalid"
    assert session.secret_key not in str(exc_info.value)

    store_oast_provider_session(_correlation(), session)
    for changed in (
        {"callback_label": "z" * 33},
        {"service_origin_sha256": "b" * 64},
    ):
        with pytest.raises(OastProviderSessionSpoolError) as exc_info:
            load_oast_provider_session(_correlation(**changed))
        assert exc_info.value.code == "oast_provider_session_invalid"


def test_oast_provider_session_spool_fails_closed_after_master_key_change(monkeypatch):
    session = new_oast_provider_session(_LABEL)
    store_oast_provider_session(_correlation(), session)
    secrets_vault.reset_master_key_cache_for_tests()
    monkeypatch.setenv(
        secrets_vault.MASTER_KEY_ENV,
        b64encode(b"replacement-oast-spool-key!!!!!!").decode("ascii"),
    )

    with pytest.raises(OastProviderSessionSpoolError) as exc_info:
        load_oast_provider_session(_correlation())

    assert exc_info.value.code == "oast_provider_session_invalid"
    assert session.secret_key not in str(exc_info.value)


def test_oast_provider_session_spool_rejects_paths_and_lists_only_old_regular_files(
    tmp_path,
):
    session = new_oast_provider_session(_LABEL)
    with pytest.raises(OastProviderSessionSpoolError) as exc_info:
        store_oast_provider_session(
            _correlation(id="../../outside"),
            session,
        )
    assert exc_info.value.code == "oast_provider_session_invalid"

    store_oast_provider_session(_correlation(), session)
    path = _session_path(tmp_path)
    os.utime(path, (100.0, 100.0))
    fresh_id = "ocr_11111111111111111111111111111111"
    fresh_path = path.parent / f"{fresh_id}.session"
    fresh_path.write_text("not encrypted", encoding="ascii")
    os.utime(fresh_path, (1000.0, 1000.0))
    symlink_id = "ocr_22222222222222222222222222222222"
    (path.parent / f"{symlink_id}.session").symlink_to(path)

    assert stale_oast_provider_session_ids(now=1001.0, grace_seconds=60) == (
        _CORRELATION_ID,
    )

    discard_oast_provider_session(_CORRELATION_ID)
    path.symlink_to(fresh_path)
    with pytest.raises(OastProviderSessionSpoolError) as exc_info:
        load_oast_provider_session(_correlation())
    assert exc_info.value.code == "oast_provider_session_unavailable"
