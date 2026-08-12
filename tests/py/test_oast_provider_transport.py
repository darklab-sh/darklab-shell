# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Private OAST provider transport tests without external network calls."""

from __future__ import annotations

from base64 import b64decode, b64encode
import json
import os
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import pytest

from services.connectors.oast_config import OastConnectorSettings
from services.connectors import oast_provider_http
from services.connectors.oast_interaction_review import review_oast_interaction
from services.connectors.oast_provider_http import request_oast_provider_bytes
from services.connectors.oast_provider_transport import (
    OastProviderTransportError,
    deregister_oast_provider_session,
    new_oast_provider_session,
    poll_oast_provider_session,
    register_oast_provider_session,
)


_LABEL = "abcdefghijklmnopqrstuvwxy01234567"


def _settings() -> OastConnectorSettings:
    return OastConnectorSettings(
        enabled=True,
        base_url="https://interactsh.example.test",
        token_secret_id="DARKLAB_TEST_OAST_TOKEN",
        allowed_domain="callbacks.example.test",
        tls_verify=True,
        callback_retention_seconds=604800,
        privacy_acknowledged=True,
    )


class _FakeResponse:
    def __init__(self, url: str, payload: object, *, status: int = 200):
        self._url = url
        self._body = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self) -> str:
        return self._url

    def getcode(self) -> int:
        return self.status

    def read(self, amount: int) -> bytes:
        return self._body[:amount]


def _install_provider(
    monkeypatch,
    responses: list[object],
    *,
    changed_url: str = "",
):
    requests = []

    def fake_open(request, *, settings, timeout):
        del settings
        assert timeout == 30
        requests.append(request)
        return _FakeResponse(changed_url or request.full_url, responses.pop(0))

    monkeypatch.setattr(oast_provider_http, "_open_oast_request", fake_open)
    return requests


def _encrypted_poll_payload(session, interactions: list[dict[str, object]]):
    private_key = serialization.load_pem_private_key(
        session.private_key_pem,
        password=None,
    )
    assert isinstance(private_key, rsa.RSAPrivateKey)
    public_key = private_key.public_key()
    aes_key = os.urandom(32)
    encrypted_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    encrypted = []
    for interaction in interactions:
        iv = os.urandom(16)
        encryptor = Cipher(algorithms.AES(aes_key), modes.CTR(iv)).encryptor()
        plaintext = json.dumps(
            interaction,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encrypted.append(
            b64encode(iv + encryptor.update(plaintext) + encryptor.finalize()).decode()
        )
    return {
        "data": encrypted,
        "extra": ["ignored shared record"],
        "tlddata": ["ignored tld record"],
        "aes_key": b64encode(encrypted_key).decode(),
    }


def test_oast_provider_registers_and_deregisters_with_fixed_contract(monkeypatch):
    requests = _install_provider(
        monkeypatch,
        [
            {"message": "registration successful"},
            {"message": "deregistration successful"},
        ],
    )

    session = register_oast_provider_session(_settings(), "provider-token", _LABEL)
    deregister_oast_provider_session(_settings(), "provider-token", session)

    assert session.callback_label == _LABEL
    assert session.correlation_id == _LABEL[:20]
    assert session.secret_key not in repr(session)
    assert "PRIVATE KEY" not in repr(session)
    register_request, deregister_request = requests
    assert register_request.full_url == "https://interactsh.example.test/register"
    assert register_request.method == "POST"
    assert register_request.get_header("Authorization") == "provider-token"
    assert "provider-token" not in register_request.full_url
    register_body = json.loads(register_request.data)
    assert register_body["correlation-id"] == session.correlation_id
    assert register_body["secret-key"] == session.secret_key
    public_pem = b64decode(register_body["public-key"], validate=True)
    public_key = serialization.load_pem_public_key(public_pem)
    assert isinstance(public_key, rsa.RSAPublicKey)
    assert public_key.key_size == 2048
    assert deregister_request.full_url == "https://interactsh.example.test/deregister"
    assert json.loads(deregister_request.data) == {
        "correlation-id": session.correlation_id,
        "secret-key": session.secret_key,
    }


def test_oast_provider_poll_decrypts_exact_callback_and_redacts_raw_data(monkeypatch):
    session = new_oast_provider_session(_LABEL)
    timestamp = "2026-08-09T12:00:00Z"
    raw_records: list[dict[str, object]] = [
        {
            "protocol": "https",
            "unique-id": _LABEL,
            "timestamp": timestamp,
            "raw-request": (
                "GET /login?token=do-not-retain HTTP/1.1\r\n"
                "Authorization: private-header\r\n\r\nprivate-body"
            ),
            "raw-response": "HTTP/1.1 200 OK\r\nSet-Cookie: private-cookie",
            "remote-address": "192.0.2.20",
        },
        {
            "protocol": "dns",
            "unique-id": _LABEL,
            "full-id": f"{_LABEL}.callbacks.example.test.",
            "q-type": "A",
            "timestamp": timestamp,
        },
        {
            "protocol": "smtp",
            "unique-id": _LABEL,
            "timestamp": timestamp,
            "raw-request": "MAIL FROM:<private@example.test>\r\nRCPT TO:<x@y.test>",
            "smtp-from": "private@example.test",
        },
        {
            "protocol": "ldap",
            "unique-id": _LABEL,
            "timestamp": timestamp,
            "raw-request": "private ldap payload",
        },
        {
            "protocol": "dns",
            "unique-id": "z" * 33,
            "timestamp": timestamp,
        },
    ]
    payload = _encrypted_poll_payload(session, raw_records)
    payload["data"].append("not-valid-base64")
    requests = _install_provider(monkeypatch, [payload])

    batch = poll_oast_provider_session(_settings(), "provider-token", session)

    assert len(batch.interactions) == 4
    assert batch.rejected_count == 2
    assert batch.ignored_shared_count == 2
    poll_request = requests[0]
    split = urlsplit(poll_request.full_url)
    assert split.path == "/poll"
    assert parse_qs(split.query) == {
        "id": [session.correlation_id],
        "secret": [session.secret_key],
    }
    assert poll_request.get_header("Authorization") == "provider-token"
    encoded_batch = json.dumps(batch.interactions, sort_keys=True)
    for private_value in (
        "private-header",
        "private-body",
        "private-cookie",
        "192.0.2.20",
        "private@example.test",
        "private ldap payload",
        "ignored shared record",
        "ignored tld record",
    ):
        assert private_value not in encoded_batch
    reviewed = [review_oast_interaction(item) for item in batch.interactions]
    assert "do-not-retain" not in json.dumps(
        [item.summary for item in reviewed], sort_keys=True
    )
    assert [item.protocol for item in reviewed] == ["http", "dns", "smtp", "ldap"]
    assert reviewed[0].summary == {"method": "GET", "path": "/login"}
    assert reviewed[0].redacted_field_count == 1
    assert reviewed[1].summary == {
        "query_name": f"{_LABEL}.callbacks.example.test",
        "query_type": "A",
    }
    assert reviewed[2].summary == {"command": "MAIL"}
    assert reviewed[3].summary == {}


def test_oast_provider_poll_accepts_default_server_null_empty_scopes(monkeypatch):
    session = new_oast_provider_session(_LABEL)
    requests = _install_provider(
        monkeypatch,
        [{"data": None, "extra": None, "aes_key": "unused"}],
    )

    batch = poll_oast_provider_session(_settings(), "provider-token", session)

    assert batch.interactions == ()
    assert batch.rejected_count == 0
    assert batch.ignored_shared_count == 0
    assert requests[0].method == "GET"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"message": "wrong"}, "oast_provider_registration_rejected"),
        ({"data": [], "unexpected": []}, "oast_provider_response_invalid"),
    ],
)
def test_oast_provider_rejects_unconfirmed_or_extended_responses(
    monkeypatch,
    payload,
    code,
):
    requests = _install_provider(monkeypatch, [payload])
    if "message" in payload:
        call = lambda: register_oast_provider_session(  # noqa: E731
            _settings(), "provider-token", _LABEL
        )
    else:
        session = new_oast_provider_session(_LABEL)
        call = lambda: poll_oast_provider_session(  # noqa: E731
            _settings(), "provider-token", session
        )

    with pytest.raises(OastProviderTransportError) as exc_info:
        call()

    assert exc_info.value.code == code
    assert requests


def test_oast_provider_http_rejects_tokens_endpoints_redirects_and_large_bodies(
    monkeypatch,
):
    settings = _settings()
    with pytest.raises(OastProviderTransportError) as exc_info:
        request_oast_provider_bytes(
            settings,
            "provider-token",
            "/caller-selected",
            method="GET",
            max_bytes=10,
        )
    assert exc_info.value.code == "oast_provider_endpoint_invalid"

    with pytest.raises(OastProviderTransportError) as exc_info:
        request_oast_provider_bytes(
            settings,
            "provider-token\nInjected: true",
            "/poll",
            method="GET",
            max_bytes=10,
        )
    assert exc_info.value.code == "oast_provider_token_invalid"

    _install_provider(
        monkeypatch,
        [{"message": "registration successful"}],
        changed_url="https://redirected.example.test/register",
    )
    with pytest.raises(OastProviderTransportError) as exc_info:
        register_oast_provider_session(settings, "provider-token", _LABEL)
    assert exc_info.value.code == "oast_provider_redirected"

    _install_provider(monkeypatch, [b"123456"])
    with pytest.raises(OastProviderTransportError) as exc_info:
        request_oast_provider_bytes(
            settings,
            "provider-token",
            "/poll",
            method="GET",
            max_bytes=5,
        )
    assert exc_info.value.code == "oast_provider_response_too_large"
