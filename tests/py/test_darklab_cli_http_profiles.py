# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json
from io import StringIO
from unittest import mock

import pytest
from darklab_cli_test_support import install_cli_harness


@pytest.fixture
def cli_harness(monkeypatch):
    return install_cli_harness(monkeypatch)


def test_darklab_cli_identity_reader(cli_harness, capsys):
    cli_main = cli_harness.cli_main
    assert cli_main.main(["whoami"]) == 0
    assert "token_created" in capsys.readouterr().out


def test_darklab_cli_http_profile_commands(cli_harness, capsys, tmp_path):
    cli_main = cli_harness.cli_main
    http_profile_requests = cli_harness.http_profile_requests
    assert cli_main.main(["http-profile", "list", "cli-project"]) == 0
    profile_list = capsys.readouterr().out
    assert "Authenticated API" in profile_list
    assert '"headers":1' in profile_list
    assert "stored-secret-value" not in profile_list
    assert http_profile_requests[-1] == ("GET", "/projects/prj_cli/http-profiles", None)
    assert cli_main.main([
        "http-profile", "list", "prj_cli", "--format", "json",
    ]) == 0
    listed_profiles = json.loads(capsys.readouterr().out)
    assert listed_profiles["total"] == 1
    assert listed_profiles["profiles"][0]["reference_counts"]["secret_refs"] == 1
    assert cli_main.main([
        "http-profile", "list", "prj_cli", "--format", "ndjson",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "htp_cli"
    assert cli_main.main(["http-profile", "show", "prj_cli", "htp_cli"]) == 0
    profile_text = capsys.readouterr().out
    assert "Authenticated API" in profile_text
    assert "API_TOKEN" not in profile_text
    assert "certs/client.pem" not in profile_text
    assert cli_main.main([
        "http-profile", "show", "prj_cli", "htp_cli", "--format", "json",
    ]) == 0
    shown_profile = json.loads(capsys.readouterr().out)["profile"]
    assert shown_profile["secret_refs"] == {"api_token": "API_TOKEN"}
    assert "stored-secret-value" not in json.dumps(shown_profile)
    assert cli_main.main([
        "http-profile", "show", "prj_cli", "htp_viewer", "--format", "json",
    ]) == 0
    viewer_profile = json.loads(capsys.readouterr().out)["profile"]
    assert viewer_profile["protected_references_visible"] is False
    assert "secret_refs" not in viewer_profile
    assert viewer_profile["reference_counts"]["secret_refs"] == 1
    profile_input = tmp_path / "http-profile-create.json"
    profile_input.write_text(json.dumps({
        "name": "Automation session",
        "role": "authenticated",
        "base_url": "https://api.example.com",
        "headers": [{"name": "Authorization", "secret_name": "API_TOKEN"}],
        "secret_refs": {"bearer_token": "API_TOKEN"},
        "file_refs": {
            "client_certificate": "certs/client.pem",
            "client_key": "certs/client-key.pem",
        },
    }), encoding="utf-8")
    assert cli_main.main([
        "http-profile", "create", "prj_cli", "--input", str(profile_input),
    ]) == 0
    created_profile_text = capsys.readouterr().out
    assert "htp_created" in created_profile_text
    assert "API_TOKEN" not in created_profile_text
    assert "certs/client.pem" not in created_profile_text
    assert http_profile_requests[-1] == (
        "POST",
        "/projects/prj_cli/http-profiles",
        {
            "name": "Automation session",
            "role": "authenticated",
            "base_url": "https://api.example.com",
            "headers": [{"name": "Authorization", "secret_name": "API_TOKEN"}],
            "secret_refs": {"bearer_token": "API_TOKEN"},
            "file_refs": {
                "client_certificate": "certs/client.pem",
                "client_key": "certs/client-key.pem",
            },
        },
    )
    assert cli_main.main([
        "http-profile", "create", "prj_cli", "--input", str(profile_input),
        "--format", "json",
    ]) == 0
    created_profile_json = json.loads(capsys.readouterr().out)["profile"]
    assert created_profile_json["secret_refs"]["bearer_token"]["name"] == "API_TOKEN"
    assert "stored-secret-value" not in json.dumps(created_profile_json)
    profile_update = tmp_path / "http-profile-update.json"
    profile_update.write_text('{"enabled":false}', encoding="utf-8")
    assert cli_main.main([
        "http-profile", "update", "prj_cli", "htp_cli", "--revision", "3",
        "--input", str(profile_update), "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["profile"]["revision"] == 4
    assert http_profile_requests[-1] == (
        "PATCH",
        "/projects/prj_cli/http-profiles/htp_cli",
        {"enabled": False, "revision": 3},
    )
    with mock.patch(
        "darklab_cli.payloads.sys.stdin",
        new=StringIO('{"enabled":true}'),
    ):
        assert cli_main.main([
            "http-profile", "update", "prj_cli", "htp_cli",
            "--revision", "3", "--input", "-", "--format", "json",
        ]) == 0
    assert json.loads(capsys.readouterr().out)["profile"]["enabled"] is True
    assert http_profile_requests[-1][2] == {"enabled": True, "revision": 3}
    assert cli_main.main([
        "http-profile", "update", "prj_cli", "htp_cli", "--revision", "2",
        "--input", str(profile_update),
    ]) == 1
    assert "current --revision" in capsys.readouterr().err
    revision_input = tmp_path / "http-profile-revision.json"
    revision_input.write_text('{"revision":3,"enabled":false}', encoding="utf-8")
    request_count = len(http_profile_requests)
    assert cli_main.main([
        "http-profile", "update", "prj_cli", "htp_cli", "--revision", "3",
        "--input", str(revision_input),
    ]) == 1
    assert "use --revision" in capsys.readouterr().err
    assert len(http_profile_requests) == request_count
    unsafe_input = tmp_path / "http-profile-unsafe.json"
    unsafe_input.write_text(json.dumps({
        "name": "Unsafe profile",
        "base_url": "https://api.example.com",
        "password": "stored-secret-value",
    }), encoding="utf-8")
    assert cli_main.main([
        "http-profile", "create", "prj_cli", "--input", str(unsafe_input),
    ]) == 1
    assert "unsupported fields" in capsys.readouterr().err
    assert len(http_profile_requests) == request_count
    inline_secret_input = tmp_path / "http-profile-inline-secret.json"
    inline_secret_input.write_text(json.dumps({
        "name": "Unsafe header",
        "base_url": "https://api.example.com",
        "headers": [{"name": "Authorization", "secret_name": "storedsecretvalue"}],
    }), encoding="utf-8")
    assert cli_main.main([
        "http-profile", "create", "prj_cli", "--input", str(inline_secret_input),
    ]) == 1
    inline_secret_error = capsys.readouterr().err
    assert "app-managed Secret" in inline_secret_error
    assert "stored-secret-value" not in inline_secret_error
    assert len(http_profile_requests) == request_count
    unsafe_path_input = tmp_path / "http-profile-unsafe-path.json"
    unsafe_path_input.write_text(json.dumps({
        "name": "Unsafe Files path",
        "base_url": "https://api.example.com",
        "file_refs": {
            "client_certificate": "/tmp/client.pem",
            "client_key": "certs/client-key.pem",
        },
    }), encoding="utf-8")
    assert cli_main.main([
        "http-profile", "create", "prj_cli", "--input", str(unsafe_path_input),
    ]) == 1
    assert "relative Files path" in capsys.readouterr().err
    assert len(http_profile_requests) == request_count
    inline_proxy_input = tmp_path / "http-profile-inline-proxy.json"
    inline_proxy_input.write_text(json.dumps({
        "name": "Unsafe proxy",
        "base_url": "https://api.example.com",
        "proxy_url": "https://user:stored-secret-value@proxy.example.com",
    }), encoding="utf-8")
    assert cli_main.main([
        "http-profile", "create", "prj_cli", "--input", str(inline_proxy_input),
    ]) == 1
    inline_proxy_error = capsys.readouterr().err
    assert "must not contain inline credentials" in inline_proxy_error
    assert "stored-secret-value" not in inline_proxy_error
    assert len(http_profile_requests) == request_count
    oversized_profile_input = tmp_path / "http-profile-oversized.json"
    oversized_profile_input.write_text(" " * (1024 * 1024 + 1), encoding="utf-8")
    assert cli_main.main([
        "http-profile", "create", "prj_cli", "--input", str(oversized_profile_input),
    ]) == 1
    assert "structured input exceeds 1048576 bytes" in capsys.readouterr().err
    assert len(http_profile_requests) == request_count
    duplicate_profile_input = tmp_path / "http-profile-duplicate.json"
    duplicate_profile_input.write_text(json.dumps({
        "name": "Duplicate profile",
        "base_url": "https://api.example.com",
    }), encoding="utf-8")
    assert cli_main.main([
        "http-profile", "create", "prj_cli", "--input", str(duplicate_profile_input),
    ]) == 1
    assert "already exists" in capsys.readouterr().err
    forbidden_input = tmp_path / "http-profile-forbidden.json"
    forbidden_input.write_text(json.dumps({
        "name": "Forbidden profile",
        "base_url": "https://api.example.com",
    }), encoding="utf-8")
    assert cli_main.main([
        "http-profile", "create", "prj_cli", "--input", str(forbidden_input),
    ]) == 1
    assert "MANAGE_SECRETS capability" in capsys.readouterr().err
    delete_count = sum(1 for method, _path, _body in http_profile_requests if method == "DELETE")
    assert cli_main.main([
        "http-profile", "delete", "prj_cli", "htp_cli",
    ]) == 0
    delete_preview = capsys.readouterr().out
    assert '"secret_refs":1' in delete_preview
    assert "--confirm" in delete_preview
    assert sum(1 for method, _path, _body in http_profile_requests if method == "DELETE") == delete_count
    assert cli_main.main([
        "http-profile", "delete", "prj_cli", "htp_cli", "--confirm",
        "--format", "json",
    ]) == 0
    deleted_output = capsys.readouterr()
    assert json.loads(deleted_output.out) == {"ok": True, "removed": True}
    assert json.loads(deleted_output.err)["profile"]["id"] == "htp_cli"
    assert http_profile_requests[-1] == (
        "DELETE", "/projects/prj_cli/http-profiles/htp_cli", None,
    )
