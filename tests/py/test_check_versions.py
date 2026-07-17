# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_check_versions_module():
    path = ROOT / "scripts" / "check_versions.sh"
    loader = importlib.machinery.SourceFileLoader("check_versions_script", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_urlscan_cli_uses_github_releases_for_calendar_versions(monkeypatch):
    module = _load_check_versions_module()
    calls: list[tuple[str, str]] = []

    def fake_latest_github_release_version(owner: str, repo: str) -> str:
        calls.append((owner, repo))
        return "v2026.06.12"

    monkeypatch.setattr(module, "_latest_github_release_version", fake_latest_github_release_version)

    assert module._latest_golang_version("github.com/urlscan/urlscan-cli") == "v2026.06.12"
    assert calls == [("urlscan", "urlscan-cli")]


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
