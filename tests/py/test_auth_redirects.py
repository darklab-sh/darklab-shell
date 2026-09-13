# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Sign-in return destinations stay on this deployment after URL normalization."""

import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest

from conftest import copy_pristine_sqlite_database
from core import database
from core.database_access import get_db_connect
from services.auth import storage
from test_oidc_sign_in import LocalProvider, ORIGIN, _app, _callback, _config, _response_cookie


@pytest.mark.parametrize("method", ["credential", "oidc_start", "oidc_callback"])
@pytest.mark.parametrize("destination,expected", [
    ("/", "/"),
    ("/?q=some%20words#output", "/?q=some%20words#output"),
    ("/projects?name=example", "/projects?name=example"),
    ("https://evil.example/", "/"),
    ("//evil.example/", "/"),
    ("///evil.example/", "/"),
    ("/\\evil.example/", "/"),
    ("/\\/evil.example/", "/"),
    ("/%5Cevil.example/", "/"),
    ("/%2Fevil.example/", "/"),
    ("/\t/evil.example/", "/"),
    ("/%09/evil.example/", "/"),
    ("/\r\n/evil.example/", "/"),
    ("/\x00/evil.example/", "/"),
    ("/\x7f/evil.example/", "/"),
    (" /projects", "/"),
    ("/" + "a" * 2048, "/"),
])
def test_sign_in_return_destinations_are_local(tmp_path, monkeypatch, method, destination, expected):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "redirect.db")))
    provider = LocalProvider(monkeypatch)
    client = _app(monkeypatch, _config(profile="mixed")).test_client()
    if method == "credential":
        with get_db_connect()() as conn:
            bundle = storage.create_principal_with_credential(conn=conn)
            conn.commit()
        page = client.get("/auth/sign-in", base_url=ORIGIN)
        response = client.post("/auth/sign-in", base_url=ORIGIN, data={
            "credential": bundle.credential.secret,
            "sign_in_nonce": _response_cookie(page, "darklab_sign_in_nonce"),
            "next": destination,
        })
    else:
        started = client.get("/auth/oidc/start", base_url=ORIGIN, query_string={"next": destination})
        assert started.status_code == 302
        state = parse_qs(urlsplit(started.headers["Location"]).query)["state"][0]
        provider.expect(state)
        with get_db_connect()() as conn:
            digest = hashlib.sha256(state.encode()).digest()
            assert conn.execute(
                "SELECT next_path FROM oidc_auth_flows WHERE state_digest = ?", (digest,),
            ).fetchone()[0] == expected
            if method == "oidc_callback":
                # A flow can have been stored by an earlier application version;
                # the callback must independently validate its destination.
                conn.execute("UPDATE oidc_auth_flows SET next_path = ? WHERE state_digest = ?", (destination, digest))
                conn.commit()
        response = _callback(client, state)
    assert response.status_code == 302
    assert response.headers["Location"] == expected
    assert not urlsplit(response.headers["Location"]).netloc
