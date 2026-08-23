# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_check_versions_module():
    path = ROOT / "scripts" / "release" / "check_versions.sh"
    loader = importlib.machinery.SourceFileLoader("check_versions_script", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_nonstandard_go_cli_versions_use_explicit_upstream_metadata(monkeypatch):
    module = _load_check_versions_module()
    calls: list[tuple[str, str]] = []
    requested_urls: list[str] = []

    def fake_latest_github_release_version(owner: str, repo: str) -> str:
        calls.append((owner, repo))
        return {
            ("ipinfo", "cli"): "ipinfo-3.3.2",
            ("urlscan", "urlscan-cli"): "v2026.06.12",
        }[(owner, repo)]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return b'{"Version":"v0.0.0-20260707165039-b4cf77c4340f"}'

    def fake_urlopen(url: str, timeout: int):
        requested_urls.append(url)
        return FakeResponse()

    monkeypatch.setattr(module, "_latest_github_release_version", fake_latest_github_release_version)
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    assert module._latest_golang_version("github.com/ipinfo/cli/ipinfo") == "ipinfo-3.3.2"
    assert module._latest_golang_version("github.com/urlscan/urlscan-cli") == "v2026.06.12"
    assert module._latest_golang_version("github.com/VirusTotal/vt-cli/vt") == (
        "v0.0.0-20260707165039-b4cf77c4340f"
    )
    assert calls == [("ipinfo", "cli"), ("urlscan", "urlscan-cli")]
    assert requested_urls == [
        "https://proxy.golang.org/github.com/!virus!total/vt-cli/@latest",
    ]


def test_generic_go_lookup_still_uses_module_proxy(monkeypatch):
    module = _load_check_versions_module()
    helper_install = module.GO_INSTALL_PATTERN.search(
        "RUN install-go-tool github.com/example/tool/cmd/tool@${TOOL_VERSION}"
    )
    assert helper_install is not None
    assert helper_install.groups() == (
        "github.com/example/tool/cmd/tool",
        "${TOOL_VERSION}",
    )
    requested_urls: list[str] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return b"v0.1.0\nv0.2.0\n"

    def fake_urlopen(url: str, timeout: int):
        requested_urls.append(url)
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    latest = module._latest_golang_version("github.com/example/tool/cmd/tool")

    assert latest == "v0.2.0"
    assert requested_urls == ["https://proxy.golang.org/github.com/example/tool/@v/list"]


def test_dockerfile_and_registry_reports_follow_checked_in_sources(monkeypatch, tmp_path, capsys):
    module = _load_check_versions_module()
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "\n".join(
            [
                "ARG NIKTO_VERSION=2.6.0",
                "FROM python:3.14-slim",
                "RUN git clone --depth 1 --branch \"${NIKTO_VERSION}\" \\",
                "    https://github.com/sullo/Nikto.git /out/opt/Nikto",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "DOCKERFILE", dockerfile)
    monkeypatch.setattr(module, "_latest_github_release_version", lambda owner, repo: "2.6.0")

    module._print_dockerfile_pins(labels={"github"})

    output = capsys.readouterr().out
    assert "sullo/Nikto" in output
    assert "pinned=2.6.0" in output

    class RegistryResponse:
        def __init__(self, body: bytes = b"", headers: dict[str, str] | None = None):
            self.body = body
            self.headers = headers or {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size: int = -1) -> bytes:
            return self.body if size < 0 else self.body[:size]

    requests: list[tuple[str, str, str | None]] = []
    pinned_digest = "sha256:" + ("a" * 64)
    newest_digest = "sha256:" + ("b" * 64)

    def unauthorized(url: str, challenge: str):
        raise module.urllib.error.HTTPError(
            url,
            401,
            "unauthorized",
            {"WWW-Authenticate": challenge},
            io.BytesIO(),
        )

    def fake_registry_urlopen(request, timeout: int):
        assert timeout == module.REGISTRY_HTTP_TIMEOUT_SECONDS
        url = request.full_url
        method = request.get_method()
        authorization = request.get_header("Authorization")
        requests.append((method, url, authorization))

        if url.startswith("https://auth.docker.io/token?"):
            return RegistryResponse(b'{"token":"docker-token"}')
        if url.startswith("https://gitlab.com/jwt/auth?"):
            return RegistryResponse(b'{"token":"gitlab-token"}')

        if url == "https://registry-1.docker.io/v2/library/node/tags/list?n=10000":
            if authorization is None:
                return unauthorized(
                    url,
                    'Bearer realm="https://auth.docker.io/token",service="registry.docker.io",'
                    'scope="repository:library/node:pull"',
                )
            return RegistryResponse(
                b'{"name":"library/node","tags":["26.5.0-slim","26.7-slim"]}',
                {"Link": '</v2/library/node/tags/list?n=10000&last=26.7-slim>; rel="next"'},
            )
        if url == "https://registry-1.docker.io/v2/library/node/tags/list?n=10000&last=26.7-slim":
            return RegistryResponse(b'{"name":"library/node","tags":["26.7.0-slim"]}')

        if url == "https://registry-1.docker.io/v2/library/python/tags/list?n=10000":
            if authorization is None:
                return unauthorized(
                    url,
                    'Bearer realm="https://auth.docker.io/token",service="registry.docker.io",'
                    'scope="repository:library/python:pull"',
                )
            return RegistryResponse(
                b'{"name":"library/python","tags":["3.14.6-slim"]}',
                {"Link": '</v2/library/python/tags/list?n=10000&last=3.14.6-slim>; rel="next"'},
            )
        if url.endswith("/v2/library/python/tags/list?n=10000&last=3.14.6-slim"):
            raise module.urllib.error.HTTPError(url, 403, "forbidden", {}, io.BytesIO())

        gitlab_tags_url = "https://registry.gitlab.com/v2/gitlab-org/cli/tags/list?n=10000"
        if url == gitlab_tags_url:
            if authorization is None:
                return unauthorized(
                    url,
                    'Bearer realm="https://gitlab.com/jwt/auth",service="container_registry",'
                    'scope="repository:gitlab-org/cli:pull"',
                )
            return RegistryResponse(
                b'{"name":"gitlab-org/cli","tags":["v1.107.0","v1.114.0","v1.115.0-rc1"]}'
            )
        if method == "HEAD" and url.endswith("/manifests/v1.107.0"):
            return RegistryResponse(headers={"Docker-Content-Digest": pinned_digest})
        if method == "HEAD" and url.endswith("/manifests/v1.114.0"):
            return RegistryResponse(headers={"Docker-Content-Digest": newest_digest})
        raise AssertionError(f"unexpected registry request: {method} {url}")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_registry_urlopen)

    node = module._parse_image_ref("node:26.5.0-slim")
    assert node is not None
    assert (node.registry, node.repository, node.tag, node.digest) == (
        "registry-1.docker.io",
        "library/node",
        "26.5.0-slim",
        None,
    )
    assert module._latest_docker_tag("node:26.5.0-slim") == ("26.7.0-slim", None)
    request_count = len(requests)
    assert module._latest_docker_tag("node:26.5.0-slim") == ("26.7.0-slim", None)
    assert len(requests) == request_count

    newest, error = module._latest_docker_tag("python:3.14.6-slim")
    assert newest is None
    assert error == "registry returned HTTP 403"

    gitlab_image = f"registry.gitlab.com/gitlab-org/cli:v1.107.0@{pinned_digest}"
    gitlab = module._parse_image_ref(gitlab_image)
    assert gitlab is not None
    assert (gitlab.registry, gitlab.repository, gitlab.tag, gitlab.digest) == (
        "registry.gitlab.com",
        "gitlab-org/cli",
        "v1.107.0",
        pinned_digest,
    )
    module._print_registry_image_status(gitlab_image)
    registry_output = capsys.readouterr().out
    assert "newest: v1.114.0" in registry_output
    assert "pinned digest: verified" in registry_output
    assert f"newest digest: {newest_digest}" in registry_output
