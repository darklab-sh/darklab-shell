# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OIDC cache expiry, key rotation, validation, and private trust-file lifecycle."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
from textwrap import dedent
import threading
from types import SimpleNamespace

from certifi import where as requests_ca_bundle
from joserfc import jwk
import pytest

from services.auth import oidc, oidc_cache
from test_oidc_sign_in import ISSUER, LocalProvider, _config, _Response


@pytest.fixture(autouse=True)
def reset_cache():
    oidc_cache.reset_provider_cache()
    oidc_cache._cleanup_trust_bundle()
    yield
    oidc_cache.reset_provider_cache()
    oidc_cache._cleanup_trust_bundle()


def _flow(provider):
    provider.nonce = "test-nonce"
    provider.verifier = "test-proof"
    return oidc.OIDCFlow("test-state", provider.nonce, provider.verifier, "sign_in", "", "", "/")


def test_discovery_is_cached_without_sharing_mutable_metadata(monkeypatch):
    provider = LocalProvider(monkeypatch)
    first = oidc.provider_metadata(_config())
    first["token_endpoint"] = "https://wrong.example/token"
    first["code_challenge_methods_supported"].clear()
    second = oidc.provider_metadata(_config())
    assert second["token_endpoint"].startswith(ISSUER)
    assert second["code_challenge_methods_supported"] == ["S256"]
    assert len(provider.get_calls) == 1
    provider.available = False
    assert oidc.provider_metadata(_config()) == second


def test_expired_discovery_fails_closed_and_failed_loads_are_not_cached(monkeypatch):
    provider = LocalProvider(monkeypatch)
    now = [1_000.0]
    monkeypatch.setattr(oidc_cache, "time", SimpleNamespace(monotonic=lambda: now[0]))
    oidc.provider_metadata(_config())
    now[0] += oidc_cache.PROVIDER_CACHE_SECONDS
    provider.available = False
    with pytest.raises(oidc.OIDCUnavailable):
        oidc.provider_metadata(_config())
    provider.available = True
    assert oidc.provider_metadata(_config())["issuer"] == ISSUER
    assert len(provider.get_calls) == 3


def test_invalid_discovery_and_changed_issuer_never_reuse_an_accepted_entry(monkeypatch):
    provider = LocalProvider(monkeypatch)
    good = oidc.provider_metadata(_config())
    config = {**_config(), "oidc_issuer": "https://other.example"}
    calls = []

    def wrong_issuer(url, **_kwargs):
        calls.append(url)
        return _Response(good)

    monkeypatch.setattr(oidc.requests, "get", wrong_issuer)
    for _ in range(2):
        with pytest.raises(oidc.OIDCError, match="issuer"):
            oidc.provider_metadata(config)
    assert len(calls) == 2
    assert len(provider.get_calls) == 1


def test_unknown_key_refreshes_once_but_wrong_signature_does_not(monkeypatch):
    provider = LocalProvider(monkeypatch)
    flow = _flow(provider)
    expected = (ISSUER, provider.subject)
    assert oidc.exchange_code(_config(), flow, "local-code") == expected
    assert oidc.exchange_code(_config(), flow, "local-code") == expected
    assert len(provider.get_calls) == 2  # One discovery document and one JWKS.
    provider.private_key = jwk.RSAKey.generate_key(2048, private=True, auto_kid=True)
    provider.signing_key = provider.private_key
    assert oidc.exchange_code(_config(), flow, "local-code") == expected
    assert len(provider.get_calls) == 3
    kid = provider.private_key.kid
    assert kid is not None
    provider.signing_key = jwk.RSAKey.generate_key(2048, {"kid": kid}, private=True)
    with pytest.raises(oidc.OIDCError, match="could not be verified"):
        oidc.exchange_code(_config(), flow, "local-code")
    assert len(provider.get_calls) == 3
    provider.signing_key = jwk.RSAKey.generate_key(2048, private=True, auto_kid=True)
    with pytest.raises(oidc.OIDCError, match="could not be verified"):
        oidc.exchange_code(_config(), flow, "local-code")
    assert len(provider.get_calls) == 4  # An unknown ID gets exactly one refresh.
    provider.available = False
    with pytest.raises(oidc.OIDCUnavailable, match="code exchange"):
        oidc.exchange_code(_config(), flow, "local-code")
    assert len(provider.get_calls) == 4


def test_expired_keys_are_refetched_and_empty_key_sets_are_not_cached(monkeypatch):
    provider = LocalProvider(monkeypatch)
    now = [1_000.0]
    monkeypatch.setattr(oidc_cache, "time", SimpleNamespace(monotonic=lambda: now[0]))
    flow = _flow(provider)
    oidc.exchange_code(_config(), flow, "local-code")
    now[0] += oidc_cache.PROVIDER_CACHE_SECONDS
    original_get = oidc.requests.get

    def empty_keys(url, **kwargs):
        return _Response({"keys": []}) if url.endswith("/certs") else original_get(url, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(oidc.requests, "get", empty_keys)
        with pytest.raises(oidc.OIDCError, match="signing key set"):
            oidc.exchange_code(_config(), flow, "local-code")
    assert oidc.exchange_code(_config(), flow, "local-code") == (ISSUER, provider.subject)
    assert len(provider.get_calls) == 4


def test_concurrent_cache_loads_and_key_refreshes_are_coalesced_and_bounded():
    calls = []
    start = threading.Barrier(4)

    def load():
        result = object()
        calls.append(result)
        return result

    def get(replace=None):
        start.wait(timeout=5)
        return oidc_cache.cached_provider_value(("keys",), load, replace=replace)

    with ThreadPoolExecutor(max_workers=4) as executor:
        initial = list(executor.map(lambda _: get(), range(4)))
        assert len(calls) == 1 and all(value is initial[0] for value in initial)
        refreshed = list(executor.map(lambda _: get(initial[0]), range(4)))
        assert len(calls) == 2 and all(value is refreshed[0] for value in refreshed)
    for index in range(oidc_cache.MAX_PROVIDER_CACHE_ENTRIES):
        oidc_cache.cached_provider_value(("other", index), load)
    latest = oidc_cache.cached_provider_value(("keys",), load)
    assert latest is not refreshed[0]


def test_unrelated_provider_loads_do_not_hold_one_global_network_lock():
    ready = threading.Barrier(2)

    def load(key):
        def loader():
            ready.wait(timeout=5)
            return key
        return oidc_cache.cached_provider_value((key,), loader)

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(load, ("first-provider", "second-provider"))) == ["first-provider", "second-provider"]


def test_ca_changes_replace_one_private_file_and_cleanup_removes_it(tmp_path, monkeypatch):
    provider = LocalProvider(monkeypatch)
    metadata = oidc.provider_metadata(_config())
    system = Path(requests_ca_bundle()).read_bytes()
    certificate = system[system.index(b"-----BEGIN CERTIFICATE-----"):]
    certificate = certificate[:certificate.index(b"-----END CERTIFICATE-----") + len(b"-----END CERTIFICATE-----")]
    source = tmp_path / "private-ca.pem"
    source.write_bytes(certificate + b"\n")
    config = {**_config(), "oidc_ca_bundle": str(source)}
    combined = Path(str(oidc._trust(config)))
    before_key = oidc_cache.trust_cache_key(str(combined))
    assert stat.S_IMODE(combined.stat().st_mode) == 0o600
    assert stat.S_IMODE(combined.parent.stat().st_mode) == 0o700
    assert system.rstrip(b"\n") in combined.read_bytes()

    def discovery(_url, **kwargs):
        assert kwargs["verify"] == str(combined)
        provider.get_calls.append(_url)
        return _Response(metadata)

    monkeypatch.setattr(oidc.requests, "get", discovery)
    oidc.provider_metadata(config)
    assert len(provider.get_calls) == 2  # System-root metadata cannot satisfy custom trust.
    for suffix in (b"\n\n", b"\n\n\n"):
        source.write_bytes(certificate + suffix)
        assert oidc._trust(config) == str(combined)
        assert combined.read_bytes().endswith(certificate + suffix)
        assert list(combined.parent.iterdir()) == [combined]
        oidc.provider_metadata(config)
    assert len(provider.get_calls) == 4
    assert oidc_cache.trust_cache_key(str(combined)) != before_key
    assert oidc._trust(config) == str(combined)
    source.write_bytes(b"not a certificate")
    with pytest.raises(oidc.OIDCUnavailable):
        oidc._trust(config)
    assert combined.is_file()
    directory = combined.parent
    oidc_cache._cleanup_trust_bundle()
    assert not directory.exists()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork lifecycle applies to Unix workers")
def test_child_reset_does_not_remove_parent_trust_directory(tmp_path):
    directory = tmp_path / "parent-trust"
    directory.mkdir()
    # Keep the real fork hook covered without inheriting pytest's live threads.
    script = dedent("""
        import os
        from pathlib import Path
        import sys
        import threading
        import traceback

        from services.auth import oidc_cache

        directory = Path(sys.argv[1])
        oidc_cache._TRUST_DIRECTORY = str(directory)
        assert threading.active_count() == 1
        pid = os.fork()
        if pid == 0:
            try:
                assert oidc_cache._PID == os.getpid()
                assert oidc_cache._TRUST_DIRECTORY is None
                oidc_cache._cleanup_trust_bundle()
            except BaseException:
                traceback.print_exc()
                os._exit(1)
            os._exit(0)
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0, f"Forked child failed: {status}"
        assert directory.is_dir(), "Child cleanup removed the parent's trust directory"
    """)
    with subprocess.Popen(
        [sys.executable, "-W", "error::DeprecationWarning", "-c", script, str(directory)],
        cwd=Path(__file__).resolve().parents[2] / "app",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=30)
        except BaseException:
            # The forked child shares the pipes, even if its parent has exited.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise
    assert process.returncode == 0, stderr or stdout
    assert not directory.exists(), "Parent exit did not clean up its own trust directory"
