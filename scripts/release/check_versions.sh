#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Check pinned dependency versions plus production and CI image versions.

The script reads the production Docker base image from Dockerfile and the CI
runner images from .gitlab-ci.yml so version checks follow the checked-in
runtime configuration instead of a separately maintained list.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import email.utils
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def _repository_root(script_path: pathlib.Path) -> pathlib.Path:
    for candidate in (script_path.resolve().parent, *script_path.resolve().parents):
        if (candidate / "package.json").is_file() and (candidate / "app").is_dir():
            return candidate
    raise RuntimeError("could not locate the darklab_shell repository root")


ROOT = _repository_root(pathlib.Path(__file__))
REQ_FILES = (
    ROOT / "app" / "requirements.txt",
    ROOT / "requirements-dev.txt",
)
PACKAGE_JSON = ROOT / "package.json"
PACKAGE_LOCK = ROOT / "package-lock.json"
DOCKERFILE = ROOT / "Dockerfile"
GITLAB_CI = ROOT / ".gitlab-ci.yml"
APP_CONFIG = ROOT / "app" / "config.py"
DEV_COMPOSE = ROOT / "compose.dev.yaml"
PROD_COMPOSE = ROOT / "deploy" / "compose.yaml"
PROD_ENV_EXAMPLE = ROOT / "deploy" / ".env.example"
OPENAPI_SNAPSHOT = ROOT / "docs" / "api-v1-openapi.json"
CONTAINER_LICENSE_INVENTORY = ROOT / "deploy" / "container-licenses.json"
PRODUCTION_INSTALL_TEST = ROOT / "tests" / "py" / "test_production_install.py"
PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==(.+)$")
NUMERIC_TAG_PATTERN = re.compile(r"^(v?)(\d+)(?:\.(\d+)(?:\.(\d+))?)?$")
SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
BEARER_PARAMETER_PATTERN = re.compile(r'([A-Za-z][A-Za-z0-9_-]*)="([^"\\]*(?:\\.[^"\\]*)*)"')
ARG_PATTERN = re.compile(r"^ARG\s+([A-Za-z_][A-Za-z0-9_]*)=(.+)$")
DOCKER_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
GO_TOOLCHAIN_PATTERN = re.compile(r"go(\d+\.\d+(?:\.\d+)?)\.linux-")
GO_INSTALL_PATTERN = re.compile(
    r'(?:go install(?:\s+-v)?|install-go-tool)\s+"?([^"\s@]+)@([^"\s\\]+)"?'
)
PIP_INSTALL_PATTERN = re.compile(r"pip install(?:\s+--[A-Za-z0-9_.=-]+)*\s+([A-Za-z0-9_.\-\[\]]+)==([^\s\\]+)")
GEM_INSTALL_PATTERN = re.compile(r"gem install\s+([A-Za-z0-9_.-]+)\s+-v\s+([^\s\\]+)")
GITHUB_RELEASE_PATTERN = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/releases/download/([^/\s]+)/")
GITHUB_CLONE_BRANCH_PATTERN = re.compile(
    r"git clone(?:\s+--depth\s+\d+)?\s+--branch\s+\"?([^\"\s]+)\"?\s+https://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?(?:\s|$)"
)
GO_STABLE_TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
CI_IMAGE_VAR_PATTERN = re.compile(r"^\s{2}(CI_[A-Z0-9_]+):\s*[\"']?([^\"'\n#]+)[\"']?\s*(?:#.*)?$")
CI_IMAGE_REF_PATTERN = re.compile(r"^\s*image:\s*\$([A-Z0-9_]+)\s*(?:#.*)?$")
GO_PACKAGE_MODULE_ROOTS = {
    "github.com/VirusTotal/vt-cli/vt": "github.com/VirusTotal/vt-cli",
    "github.com/ipinfo/cli/ipinfo": "github.com/ipinfo/cli",
}
GO_MODULE_GITHUB_RELEASES = {
    "github.com/ipinfo/cli": ("ipinfo", "cli"),
    "github.com/projectdiscovery/tlsx": ("projectdiscovery", "tlsx"),
    "github.com/urlscan/urlscan-cli": ("urlscan", "urlscan-cli"),
}
GO_MODULE_PROXY_LATEST = {
    "github.com/VirusTotal/vt-cli",
}
GITHUB_TAG_REPOSITORIES = {
    ("sqlmapproject", "sqlmap"),
}
DOCKER_REGISTRY_HOST = "registry-1.docker.io"
REGISTRY_TAG_PAGE_SIZE = 10_000
REGISTRY_MAX_TAG_PAGES = 20
REGISTRY_MAX_TAGS = 50_000
REGISTRY_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
REGISTRY_MAX_TOKEN_BYTES = 64 * 1024
REGISTRY_HTTP_ATTEMPTS = 3
REGISTRY_HTTP_TIMEOUT_SECONDS = 10
REGISTRY_MAX_RETRY_DELAY_SECONDS = 10.0
REGISTRY_MANIFEST_ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)


class ImageReference:
    __slots__ = ("registry", "repository", "tag", "digest")

    def __init__(
        self,
        registry: str,
        repository: str,
        tag: str | None,
        digest: str | None,
    ) -> None:
        self.registry = registry
        self.repository = repository
        self.tag = tag
        self.digest = digest


_REGISTRY_TAG_CACHE: dict[tuple[str, str], tuple[str, ...]] = {}
_REGISTRY_REPOSITORY_TOKENS: dict[tuple[str, str], str] = {}
_REGISTRY_TOKEN_CACHE: dict[tuple[str, str, str], str] = {}


def _escape_go_module_path(path: str) -> str:
    escaped = []
    for char in path:
        if "A" <= char <= "Z":
            escaped.append(f"!{char.lower()}")
        elif char == "!":
            escaped.append("!!")
        else:
            escaped.append(char)
    return "".join(escaped)


def _go_module_root(package: str) -> str:
    override = GO_PACKAGE_MODULE_ROOTS.get(package)
    if override is not None:
        return override
    parts = package.split("/")
    if len(parts) >= 2 and parts[-2] == "cmd":
        return "/".join(parts[:-2])
    return package


def _read_lines(path: pathlib.Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text().splitlines()


def _dockerfile_instructions() -> list[tuple[int, str]]:
    """Return logical Dockerfile instructions with their starting line."""
    instructions: list[tuple[int, str]] = []
    parts: list[str] = []
    start_line = 0
    for lineno, raw in enumerate(_read_lines(DOCKERFILE), start=1):
        stripped = raw.strip()
        if not parts and (not stripped or stripped.startswith("#")):
            continue
        if not parts:
            start_line = lineno
        continued = stripped.endswith("\\")
        parts.append(stripped[:-1].rstrip() if continued else stripped)
        if continued:
            continue
        instructions.append((start_line, " ".join(part for part in parts if part)))
        parts = []
    if parts:
        instructions.append((start_line, " ".join(part for part in parts if part)))
    return instructions


def _latest_python_version(package: str) -> str:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", package],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return "unknown"

    for line in proc.stdout.splitlines():
        if line.lower().startswith("available versions:"):
            versions = [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
            return versions[0] if versions else "unknown"
    return "unknown"


def _latest_npm_version(package: str) -> str:
    try:
        proc = subprocess.run(
            ["npm", "view", package, "version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return "unknown"
    version = proc.stdout.strip().splitlines()[-1].strip() if proc.stdout.strip() else ""
    return version or "unknown"


def _latest_pypi_version(package: str) -> str:
    url = f"https://pypi.org/pypi/{urllib.parse.quote(package, safe='')}/json"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return "unknown"
    version = payload.get("info", {}).get("version")
    return version if isinstance(version, str) and version else "unknown"


def _latest_rubygems_version(gem: str) -> str:
    url = f"https://rubygems.org/api/v1/versions/{urllib.parse.quote(gem, safe='')}.json"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return "unknown"
    if not isinstance(payload, list):
        return "unknown"
    for item in payload:
        if not isinstance(item, dict):
            continue
        version = item.get("number")
        if isinstance(version, str) and version:
            return version
    return "unknown"


def _latest_go_proxy_version(module: str) -> str:
    url = f"https://proxy.golang.org/{_escape_go_module_path(module)}/@latest"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, ValueError):
        return "unknown"
    version = payload.get("Version") if isinstance(payload, dict) else None
    return version if isinstance(version, str) and version else "unknown"


def _latest_golang_version(module: str, debug: bool = False) -> str:
    module_root = _go_module_root(module)
    github_release = GO_MODULE_GITHUB_RELEASES.get(module_root)
    if github_release is not None:
        owner, repo = github_release
        latest = _latest_github_release_version(owner, repo)
        if debug:
            print(f"  debug: go package={module}")
            print(f"  debug: go module={module_root}")
            print(f"  debug: github releases repo={owner}/{repo}")
            print(f"  debug: github releases selected={latest}")
        return latest

    if module_root in GO_MODULE_PROXY_LATEST:
        latest = _latest_go_proxy_version(module_root)
        if debug:
            print(f"  debug: go package={module}")
            print(f"  debug: go module={module_root}")
            print("  debug: go proxy query=@latest")
            print(f"  debug: go proxy selected={latest}")
        return latest

    url = f"https://proxy.golang.org/{_escape_go_module_path(module_root)}/@v/list"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            payload = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError):
        if debug:
            print(f"  debug: go proxy lookup failed: {url}")
        return "unknown"

    best: tuple[int, int, int] | None = None
    best_version = "unknown"
    raw_versions: list[str] = []
    for raw in payload.splitlines():
        version = raw.strip()
        if not version:
            continue
        raw_versions.append(version)
        match = GO_STABLE_TAG_PATTERN.fullmatch(version)
        if not match:
            continue
        key = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if best is None or key > best:
            best = key
            best_version = version
    if debug:
        sample = ", ".join(raw_versions[:8]) if raw_versions else "(none)"
        print(f"  debug: go proxy package={module}")
        print(f"  debug: go proxy module={module_root}")
        print(f"  debug: go proxy url={url}")
        print(f"  debug: go proxy versions={len(raw_versions)} sample={sample}")
        print(f"  debug: go proxy selected={best_version}")
    return best_version


def _latest_go_toolchain_version() -> str:
    try:
        with urllib.request.urlopen("https://go.dev/dl/?mode=json", timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, UnicodeDecodeError):
        return "unknown"
    if not isinstance(payload, list):
        return "unknown"
    for item in payload:
        if not isinstance(item, dict):
            continue
        version = item.get("version")
        if isinstance(version, str) and version.startswith("go"):
            return version.removeprefix("go")
    return "unknown"


def _latest_github_release_version(owner: str, repo: str) -> str:
    url = f"https://api.github.com/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "check_versions.sh"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return "unknown"
    tag = payload.get("tag_name")
    return tag if isinstance(tag, str) and tag else "unknown"


def _latest_github_tag_version(owner: str, repo: str) -> str:
    url = (
        "https://api.github.com/repos/"
        f"{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}/tags"
        "?per_page=100"
    )
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "check_versions.sh"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return "unknown"
    if not isinstance(payload, list):
        return "unknown"

    best: tuple[int, int, int] | None = None
    best_tag = "unknown"
    for item in payload:
        tag = item.get("name") if isinstance(item, dict) else None
        if not isinstance(tag, str):
            continue
        match = NUMERIC_TAG_PATTERN.fullmatch(tag)
        if match is None:
            continue
        key = (
            int(match.group(2)),
            int(match.group(3) or 0),
            int(match.group(4) or 0),
        )
        if best is None or key > best:
            best = key
            best_tag = tag
    return best_tag


def _strip_v(version: str) -> str:
    """Strip leading 'v' for version comparison (e.g. v2.4.1 == 2.4.1)."""
    for prefix in ("openssl-", "go", "v"):
        if version.startswith(prefix):
            return version[len(prefix):]
    return version


def _dockerfile_args() -> dict[str, str]:
    args: dict[str, str] = {}
    if not DOCKERFILE.exists():
        return args
    for raw in _read_lines(DOCKERFILE):
        line = raw.strip()
        match = ARG_PATTERN.match(line)
        if not match:
            continue
        name, value = match.groups()
        args[name] = value.strip().strip('"').strip("'")
    return args


def _expand_docker_vars(value: str, args: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return args.get(name, match.group(0))

    return DOCKER_VAR_PATTERN.sub(replace, value)


def _load_json(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _release_version_values() -> dict[str, str]:
    package = _load_json(PACKAGE_JSON)
    package_lock = _load_json(PACKAGE_LOCK)
    openapi = _load_json(OPENAPI_SNAPSHOT)
    container_licenses = _load_json(CONTAINER_LICENSE_INVENTORY)
    lock_root = package_lock.get("packages", {}).get("", {}) if isinstance(package_lock, dict) else {}

    def _match(path: pathlib.Path, pattern: str) -> str:
        match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
        return match.group(1) if match else "missing"

    return {
        "app/config.py": _match(APP_CONFIG, r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']'),
        "package.json": str(package.get("version", "missing")),
        "package-lock.json": str(package_lock.get("version", "missing")),
        "package-lock.json root": str(lock_root.get("version", "missing")),
        "Dockerfile": _match(DOCKERFILE, r"^ARG APP_VERSION=([^\s]+)"),
        "compose.dev.yaml": _match(
            DEV_COMPOSE,
            r"APP_VERSION:\s*\$\{APP_VERSION:-"
            r"([0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?)-dev\}",
        ),
        "deploy/compose.yaml": _match(
            PROD_COMPOSE,
            r"docker\.io/darklabsh/darklab-shell:"
            r"([0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?)",
        ),
        "deploy/.env.example": _match(
            PROD_ENV_EXAMPLE,
            r"^DARKLAB_IMAGE=docker\.io/darklabsh/darklab-shell:([^\s]+)",
        ),
        "deploy/container-licenses.json": str(
            container_licenses.get("reviewed_for_release", "missing")
        ),
        "docs/api-v1-openapi.json": str(openapi.get("info", {}).get("version", "missing")),
        "tests/py/test_production_install.py": _match(
            PRODUCTION_INSTALL_TEST,
            r'^RELEASE_VERSION\s*=\s*["\']([^"\']+)["\']',
        ),
    }


def _check_release_version(expected: str) -> int:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?", expected):
        print(f"Invalid release version: {expected}", file=sys.stderr)
        return 2
    mismatches = {
        source: actual
        for source, actual in _release_version_values().items()
        if actual != expected
    }
    if mismatches:
        print(f"Release version drift; expected {expected}:", file=sys.stderr)
        for source, actual in mismatches.items():
            print(f"- {source}: {actual}", file=sys.stderr)
        return 1
    print(f"Release version {expected} is consistent across runtime and release files.")
    return 0


def _node_dependencies() -> tuple[dict[str, str], dict[str, str]]:
    payload = _load_json(PACKAGE_JSON)
    if not isinstance(payload, dict):
        return {}, {}

    def _extract(key: str) -> dict[str, str]:
        section = payload.get(key)
        if not isinstance(section, dict):
            return {}
        return {k: v for k, v in section.items() if isinstance(k, str) and isinstance(v, str)}

    return _extract("dependencies"), _extract("devDependencies")


def _package_lock_resolved_version(name: str) -> str:
    payload = _load_json(PACKAGE_LOCK)
    packages = payload.get("packages") if isinstance(payload, dict) else {}
    if not isinstance(packages, dict):
        return "unknown"
    entry = packages.get(f"node_modules/{name}")
    if not isinstance(entry, dict):
        return "unknown"
    version = entry.get("version")
    return version if isinstance(version, str) and version else "unknown"


def _print_node_dependencies() -> None:
    deps, devdeps = _node_dependencies()

    def _print_section(label: str, packages: dict[str, str]) -> None:
        if not packages:
            return
        print(f"\nNode {label}:")
        for name in sorted(packages):
            spec = packages[name]
            locked = _package_lock_resolved_version(name)
            latest = _latest_npm_version(name)
            if latest == "unknown":
                status = "unknown"
            elif locked != "unknown" and locked == latest:
                status = "up-to-date"
            else:
                status = "behind" if latest != "unknown" else "unknown"
            print(f"- {name:24} spec={spec:12} locked={locked:12} latest={latest:12} {status}")

    _print_section("dependencies", deps)
    _print_section("devDependencies", devdeps)


def _parse_image_ref(ref: str) -> ImageReference | None:
    value = ref.strip()
    if not value or any(char.isspace() for char in value):
        return None

    if value.count("@") > 1:
        return None
    name_and_tag, separator, digest = value.partition("@")
    if separator and not digest:
        return None

    last_slash = name_and_tag.rfind("/")
    last_colon = name_and_tag.rfind(":")
    if last_colon > last_slash:
        name = name_and_tag[:last_colon]
        tag = name_and_tag[last_colon + 1 :]
        if not tag:
            return None
    else:
        name = name_and_tag
        tag = None

    parts = name.split("/")
    if not all(parts):
        return None
    first = parts[0].lower()
    has_registry = "." in first or ":" in first or first == "localhost"
    if has_registry:
        if len(parts) < 2:
            return None
        registry = first
        repository = "/".join(parts[1:])
    else:
        registry = DOCKER_REGISTRY_HOST
        repository = name if len(parts) > 1 else f"library/{name}"

    if registry in {"docker.io", "index.docker.io"}:
        registry = DOCKER_REGISTRY_HOST
    if not repository or repository.lower() != repository:
        return None
    return ImageReference(registry, repository, tag, digest or None)


def _numeric_tag_info(tag: str) -> tuple[tuple[int, int, int], int, bool] | None:
    match = NUMERIC_TAG_PATTERN.fullmatch(tag)
    if not match:
        return None
    precision = 1 + int(match.group(3) is not None) + int(match.group(4) is not None)
    key = (
        int(match.group(2)),
        int(match.group(3) or 0),
        int(match.group(4) or 0),
    )
    return key, precision, bool(match.group(1))


def _numeric_tag_key(tag: str) -> tuple[int, int, int] | None:
    info = _numeric_tag_info(tag)
    return info[0] if info is not None else None


def _retry_after_seconds(exc: urllib.error.HTTPError, attempt: int) -> float:
    value = exc.headers.get("Retry-After") if exc.headers is not None else None
    if value:
        try:
            return min(max(float(value), 0.0), REGISTRY_MAX_RETRY_DELAY_SECONDS)
        except ValueError:
            try:
                retry_at = email.utils.parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
                return min(max(delay, 0.0), REGISTRY_MAX_RETRY_DELAY_SECONDS)
            except (TypeError, ValueError, OverflowError):
                pass
    return min(0.25 * (2**attempt), REGISTRY_MAX_RETRY_DELAY_SECONDS)


def _urlopen_with_retries(request: urllib.request.Request):
    for attempt in range(REGISTRY_HTTP_ATTEMPTS):
        try:
            return urllib.request.urlopen(request, timeout=REGISTRY_HTTP_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt + 1 >= REGISTRY_HTTP_ATTEMPTS:
                raise
            retry_delay = _retry_after_seconds(exc, attempt)
            exc.close()
            time.sleep(retry_delay)
        except (urllib.error.URLError, TimeoutError):
            if attempt + 1 >= REGISTRY_HTTP_ATTEMPTS:
                raise
            time.sleep(min(0.25 * (2**attempt), REGISTRY_MAX_RETRY_DELAY_SECONDS))
    raise RuntimeError("registry request retry loop ended unexpectedly")


def _bounded_json_response(response, *, byte_limit: int) -> object:
    data = response.read(byte_limit + 1)
    if len(data) > byte_limit:
        raise ValueError(f"registry response exceeded {byte_limit} bytes")
    return json.loads(data.decode("utf-8"))


def _bearer_challenge_parameters(challenge: str) -> dict[str, str] | None:
    scheme, separator, raw_parameters = challenge.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    parameters = {key.lower(): value for key, value in BEARER_PARAMETER_PATTERN.findall(raw_parameters)}
    return parameters or None


def _registry_bearer_token(
    challenge: str,
    *,
    repository: str,
    force_refresh: bool,
) -> str:
    parameters = _bearer_challenge_parameters(challenge)
    if parameters is None or not parameters.get("realm"):
        raise ValueError("registry returned an unsupported authentication challenge")

    realm = parameters["realm"]
    service = parameters.get("service", "")
    scope = parameters.get("scope") or f"repository:{repository}:pull"
    parsed_realm = urllib.parse.urlsplit(realm)
    if parsed_realm.scheme != "https" or not parsed_realm.netloc:
        raise ValueError("registry authentication realm must use HTTPS")

    cache_key = (realm, service, scope)
    if force_refresh:
        _REGISTRY_TOKEN_CACHE.pop(cache_key, None)
    cached = _REGISTRY_TOKEN_CACHE.get(cache_key)
    if cached:
        return cached

    query = urllib.parse.parse_qsl(parsed_realm.query, keep_blank_values=True)
    if service:
        query.append(("service", service))
    if scope:
        query.append(("scope", scope))
    token_url = urllib.parse.urlunsplit(
        (
            parsed_realm.scheme,
            parsed_realm.netloc,
            parsed_realm.path,
            urllib.parse.urlencode(query),
            "",
        )
    )
    request = urllib.request.Request(
        token_url,
        headers={"Accept": "application/json", "User-Agent": "darklab-check-versions"},
    )
    with _urlopen_with_retries(request) as response:
        payload = _bounded_json_response(response, byte_limit=REGISTRY_MAX_TOKEN_BYTES)
    token = None
    if isinstance(payload, dict):
        candidate = payload.get("token") or payload.get("access_token")
        if isinstance(candidate, str) and candidate:
            token = candidate
    if token is None:
        raise ValueError("registry authentication response did not include a token")
    _REGISTRY_TOKEN_CACHE[cache_key] = token
    return token


def _registry_open(
    reference: ImageReference,
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
):
    repository_key = (reference.registry, reference.repository)
    token = _REGISTRY_REPOSITORY_TOKENS.get(repository_key)
    request_headers = {"User-Agent": "darklab-check-versions", **(headers or {})}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=request_headers, method=method)
    challenge = ""
    try:
        return _urlopen_with_retries(request)
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise
        challenge = exc.headers.get("WWW-Authenticate", "") if exc.headers is not None else ""
        exc.close()

    token = _registry_bearer_token(
        challenge,
        repository=reference.repository,
        force_refresh=token is not None,
    )
    _REGISTRY_REPOSITORY_TOKENS[repository_key] = token
    request_headers["Authorization"] = f"Bearer {token}"
    authenticated_request = urllib.request.Request(url, headers=request_headers, method=method)
    return _urlopen_with_retries(authenticated_request)


def _registry_next_link(
    raw_link: str | None,
    *,
    current_url: str,
    reference: ImageReference,
) -> str | None:
    if not raw_link:
        return None
    next_target = None
    for item in raw_link.split(","):
        target_match = re.search(r"<([^>]+)>", item)
        relation_match = re.search(r'(?:^|;)\s*rel\s*=\s*"?([^";,]+)', item, re.IGNORECASE)
        if target_match and relation_match and "next" in relation_match.group(1).lower().split():
            next_target = target_match.group(1)
            break
    if next_target is None:
        return None

    next_url = urllib.parse.urljoin(current_url, next_target)
    parsed = urllib.parse.urlsplit(next_url)
    expected_path = f"/v2/{urllib.parse.quote(reference.repository, safe='/')}/tags/list"
    if parsed.scheme != "https" or parsed.netloc.lower() != reference.registry or parsed.path != expected_path:
        raise ValueError("registry returned an unsafe pagination link")
    return next_url


def _registry_tags(reference: ImageReference) -> tuple[list[str], str | None]:
    cache_key = (reference.registry, reference.repository)
    cached = _REGISTRY_TAG_CACHE.get(cache_key)
    if cached is not None:
        return list(cached), None

    quoted_repository = urllib.parse.quote(reference.repository, safe="/")
    next_url = (
        f"https://{reference.registry}/v2/{quoted_repository}/tags/list"
        f"?n={REGISTRY_TAG_PAGE_SIZE}"
    )
    visited_urls: set[str] = set()
    tags: list[str] = []
    seen_tags: set[str] = set()
    page_count = 0

    try:
        while next_url is not None:
            if next_url in visited_urls:
                raise ValueError("registry pagination loop detected")
            if page_count >= REGISTRY_MAX_TAG_PAGES:
                raise ValueError(f"registry tag listing exceeded {REGISTRY_MAX_TAG_PAGES} pages")
            visited_urls.add(next_url)
            page_count += 1

            with _registry_open(reference, next_url, headers={"Accept": "application/json"}) as response:
                payload = _bounded_json_response(response, byte_limit=REGISTRY_MAX_RESPONSE_BYTES)
                raw_link = response.headers.get("Link")
            if not isinstance(payload, dict):
                raise ValueError("registry tag response was not an object")
            page_tags = payload.get("tags")
            if page_tags is None:
                page_tags = []
            if not isinstance(page_tags, list) or not all(isinstance(tag, str) and tag for tag in page_tags):
                raise ValueError("registry tag response contained invalid tags")
            for tag in page_tags:
                if tag in seen_tags:
                    continue
                seen_tags.add(tag)
                tags.append(tag)
                if len(tags) > REGISTRY_MAX_TAGS:
                    raise ValueError(f"registry tag listing exceeded {REGISTRY_MAX_TAGS} tags")
            next_url = _registry_next_link(raw_link, current_url=next_url, reference=reference)
    except urllib.error.HTTPError as exc:
        exc.close()
        return [], f"registry returned HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return [], f"registry request failed: {getattr(exc, 'reason', None) or exc}"
    except TimeoutError:
        return [], "registry request timed out"
    except (UnicodeDecodeError, ValueError) as exc:
        return [], str(exc)

    _REGISTRY_TAG_CACHE[cache_key] = tuple(tags)
    return tags, None


def _registry_manifest_digest(reference: ImageReference, tag: str) -> tuple[str | None, str | None]:
    quoted_repository = urllib.parse.quote(reference.repository, safe="/")
    quoted_tag = urllib.parse.quote(tag, safe="")
    url = f"https://{reference.registry}/v2/{quoted_repository}/manifests/{quoted_tag}"
    try:
        with _registry_open(
            reference,
            url,
            method="HEAD",
            headers={"Accept": REGISTRY_MANIFEST_ACCEPT},
        ) as response:
            digest = response.headers.get("Docker-Content-Digest")
    except urllib.error.HTTPError as exc:
        exc.close()
        return None, f"registry returned HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, f"registry request failed: {getattr(exc, 'reason', None) or exc}"
    except TimeoutError:
        return None, "registry request timed out"
    except ValueError as exc:
        return None, str(exc)
    if not isinstance(digest, str) or not SHA256_DIGEST_PATTERN.fullmatch(digest):
        return None, "registry did not return a SHA-256 manifest digest"
    return digest, None


def _split_numeric_image_tag(tag: str) -> tuple[tuple[int, int, int], int, bool, str] | None:
    base_tag, separator, suffix = tag.partition("-")
    info = _numeric_tag_info(base_tag)
    if info is None:
        return None
    key, precision, has_v_prefix = info
    return key, precision, has_v_prefix, suffix if separator else ""


def _latest_docker_tag(current_image: str) -> tuple[str | None, str | None]:
    reference = _parse_image_ref(current_image)
    if reference is None:
        return None, "unparseable image reference"
    if not reference.tag:
        return None, "missing tag"

    current_info = _split_numeric_image_tag(reference.tag)
    if current_info is None:
        return None, f"unsupported tag format: {reference.tag}"
    current_key, current_precision, current_v_prefix, tag_suffix = current_info

    tags, fetch_error = _registry_tags(reference)
    if fetch_error:
        return None, fetch_error
    if not tags:
        return None, "registry returned no tags"

    best_tag = None
    best_key = current_key
    best_shape = (-1, -1, -1)
    for tag in tags:
        candidate_info = _split_numeric_image_tag(tag)
        if candidate_info is None:
            continue
        candidate_key, candidate_precision, candidate_v_prefix, candidate_suffix = candidate_info
        if candidate_suffix != tag_suffix or candidate_key <= current_key:
            continue
        candidate_shape = (
            int(candidate_precision == current_precision),
            int(candidate_v_prefix == current_v_prefix),
            candidate_precision,
        )
        if candidate_key > best_key or (candidate_key == best_key and candidate_shape > best_shape):
            best_key = candidate_key
            best_shape = candidate_shape
            best_tag = tag

    return best_tag, None


def _docker_base_image() -> str | None:
    if not DOCKERFILE.exists():
        return None
    docker_args = _dockerfile_args()
    for raw in _read_lines(DOCKERFILE):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("FROM "):
            ref = line.split(None, 1)[1]
            ref = ref.split(" AS ", 1)[0].split(" as ", 1)[0].strip()
            return _expand_docker_vars(ref, docker_args)
    return None


def _gitlab_ci_ci_images() -> list[tuple[str, str, str]]:
    if not GITLAB_CI.exists():
        return []

    vars_by_name: dict[str, str] = {}
    image_refs: list[tuple[str, str, str]] = []
    current_job = "top-level"

    for raw in _read_lines(GITLAB_CI):
        var_match = CI_IMAGE_VAR_PATTERN.match(raw)
        if var_match:
            name, value = var_match.groups()
            vars_by_name[name] = value.strip()
            continue

        if raw and not raw.startswith(" ") and raw.endswith(":"):
            current_job = raw[:-1].strip()
            continue

        image_match = CI_IMAGE_REF_PATTERN.match(raw)
        if not image_match:
            continue

        var_name = image_match.group(1)
        image = vars_by_name.get(var_name)
        if image:
            owner = "top-level default" if current_job == "variables" else current_job
            image_refs.append((owner, var_name, image))

    return image_refs


def _print_dockerfile_pins(labels: set[str] | None = None, debug: bool = False) -> None:
    if not DOCKERFILE.exists():
        return
    pins: list[tuple[int, str, str, str, str]] = []
    docker_args = _dockerfile_args()
    for lineno, raw in _dockerfile_instructions():
        line = _expand_docker_vars(raw, docker_args)
        if not line or line.startswith("#"):
            continue
        if labels is None or "go-toolchain" in labels:
            go_toolchain_match = GO_TOOLCHAIN_PATTERN.search(line)
            if go_toolchain_match:
                pins.append((lineno, "go-toolchain", "go", go_toolchain_match.group(1), line))
        for label, pattern in (
            ("go", GO_INSTALL_PATTERN),
            ("pip", PIP_INSTALL_PATTERN),
            ("gem", GEM_INSTALL_PATTERN),
            ("github", GITHUB_RELEASE_PATTERN),
            ("github", GITHUB_CLONE_BRANCH_PATTERN),
        ):
            if labels is not None and label not in labels:
                continue
            match = pattern.search(line)
            if match:
                groups = match.groups()
                if pattern == GITHUB_CLONE_BRANCH_PATTERN:
                    version, owner, repo = groups
                    package = f"{owner}/{repo}"
                elif label == "github":
                    owner, repo, version = groups
                    package = f"{owner}/{repo}"
                else:
                    package, version = groups
                version = version.strip("\"'")
                pins.append((lineno, label, package, version, line))
    if not pins:
        return
    print("\nDockerfile tool versions:")
    for lineno, label, package, version, line in pins:
        if label == "go-toolchain":
            latest = _latest_go_toolchain_version()
        elif label == "go":
            latest = _latest_golang_version(package, debug=debug)
        elif label == "pip":
            latest = _latest_pypi_version(package)
        elif label == "gem":
            latest = _latest_rubygems_version(package)
        elif label == "github":
            owner, repo = package.split("/", 1)
            if (owner, repo) in GITHUB_TAG_REPOSITORIES:
                latest = _latest_github_tag_version(owner, repo)
            else:
                latest = _latest_github_release_version(owner, repo)
        else:
            latest = "unknown"
        if latest == "unknown":
            status = "unknown"
        elif _strip_v(latest) == _strip_v(version):
            status = "up-to-date"
        else:
            status = "behind"
        print(f"- line {lineno:3d} [{label:12s}] {package:48} pinned={version:12} latest={latest:12} {status}")


def _print_python_requirements() -> None:
    print("Python requirements:")
    seen: set[tuple[str, str]] = set()
    for path in REQ_FILES:
        if not path.exists():
            continue
        for raw in _read_lines(path):
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith(("-", "--")):
                continue
            match = PIN_PATTERN.match(line)
            if not match:
                continue
            package, pinned = match.groups()
            key = (package, pinned)
            if key in seen:
                continue
            seen.add(key)
            latest = _latest_python_version(package)
            if latest == "unknown":
                status = "unknown"
            elif latest == pinned:
                status = "up-to-date"
            else:
                status = "behind"
            print(f"- {package:24} pinned={pinned:12} latest={latest:12} {status}")


def _print_registry_image_status(image: str) -> None:
    newer, error = _latest_docker_tag(image)
    if newer:
        print(f"  newest: {newer}")
    elif error:
        print(f"  newest: unknown ({error})")
    else:
        print("  newest: none found; current tag appears up to date")

    reference = _parse_image_ref(image)
    if (
        reference is None
        or reference.tag is None
        or reference.digest is None
        or not SHA256_DIGEST_PATTERN.fullmatch(reference.digest)
    ):
        return

    resolved_digest, digest_error = _registry_manifest_digest(reference, reference.tag)
    if digest_error:
        print(f"  pinned digest: unknown ({digest_error})")
    elif resolved_digest == reference.digest:
        print("  pinned digest: verified")
    else:
        print(f"  pinned digest: mismatch (tag resolves to {resolved_digest})")

    if newer:
        newest_digest, newest_digest_error = _registry_manifest_digest(reference, newer)
        if newest_digest_error:
            print(f"  newest digest: unknown ({newest_digest_error})")
        else:
            print(f"  newest digest: {newest_digest}")


def _print_docker_image() -> None:
    image = _docker_base_image()
    if not image:
        print("\nDocker base image: unavailable")
        return
    print("\nDocker base image:")
    print(f"- {image}")
    _print_registry_image_status(image)


def _print_ci_images() -> None:
    refs = _gitlab_ci_ci_images()
    if not refs:
        print("\nCI runner images: unavailable")
        return

    print("\nCI runner images:")
    grouped: dict[tuple[str, str], list[str]] = {}
    for job_name, var_name, image in refs:
        grouped.setdefault((var_name, image), []).append(job_name)

    for (var_name, image), job_names in grouped.items():
        used_by = ", ".join(job_names)
        print(f"- {var_name:20} {image:20} (used by {used_by})")
        _print_registry_image_status(image)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-only", action="store_true", help="Only report Python requirements")
    parser.add_argument("--node-only", action="store_true", help="Only report Node dependencies and devDependencies")
    parser.add_argument(
        "--docker-only",
        action="store_true",
        help="Only report the production Docker base image",
    )
    parser.add_argument("--go-only", action="store_true", help="Only report Go toolchain and Go module pins from Dockerfile")
    parser.add_argument("--pip-only", action="store_true", help="Only report pip tool pins from Dockerfile")
    parser.add_argument("--gem-only", action="store_true", help="Only report gem tool pins from Dockerfile")
    parser.add_argument(
        "--github-only",
        action="store_true",
        help="Only report GitHub release pins from Dockerfile",
    )
    parser.add_argument("--debug", action="store_true", help="Print registry lookup details for Go pins")
    release_group = parser.add_mutually_exclusive_group()
    release_group.add_argument(
        "--release-version",
        help=(
            "Offline check that runtime and release files match this MAJOR.MINOR.PATCH "
            "or MAJOR.MINOR.PATCH-rc.NUMBER version"
        ),
    )
    release_group.add_argument(
        "--check-release-version",
        action="store_true",
        help="Offline check that release files match the version declared in app/config.py",
    )
    args = parser.parse_args()

    if args.release_version:
        return _check_release_version(args.release_version)
    if args.check_release_version:
        return _check_release_version(_release_version_values()["app/config.py"])

    if sum(bool(flag) for flag in (
        args.python_only,
        args.node_only,
        args.docker_only,
        args.go_only,
        args.pip_only,
        args.gem_only,
        args.github_only,
    )) > 1:
        parser.error(
            "--python-only, --node-only, --docker-only, --go-only, --pip-only, "
            "--gem-only, and --github-only are mutually exclusive"
        )

    if not any((
        args.python_only,
        args.node_only,
        args.docker_only,
        args.go_only,
        args.pip_only,
        args.gem_only,
        args.github_only,
    )):
        _print_python_requirements()
        _print_node_dependencies()
        _print_docker_image()
        _print_ci_images()
        _print_dockerfile_pins(debug=args.debug)
    elif args.python_only:
        _print_python_requirements()
    elif args.node_only:
        _print_node_dependencies()
    elif args.docker_only:
        _print_docker_image()
    elif args.go_only:
        _print_dockerfile_pins(labels={"go-toolchain", "go"}, debug=args.debug)
    elif args.pip_only:
        _print_dockerfile_pins(labels={"pip"}, debug=args.debug)
    elif args.gem_only:
        _print_dockerfile_pins(labels={"gem"}, debug=args.debug)
    elif args.github_only:
        _print_dockerfile_pins(labels={"github"}, debug=args.debug)

    print("\nNotes:")
    print(
        "- `pip index versions <package>` requires network access, so unavailable lookups "
        "are reported as unknown."
    )
    print(
        "- The Go check uses go.dev for the toolchain, GitHub Releases for modules that "
        "publish installable CLI tags there, the proxy's canonical latest version for "
        "explicit pseudo-version pins, and stable proxy release tags for other modules."
    )
    print(
        "- The Node check reads package.json/package-lock.json dependencies and "
        "devDependencies and compares them against the npm registry."
    )
    print(
        "- The Docker/runtime check reads the production base image from Dockerfile and CI "
        "runner images from .gitlab-ci.yml, follows registry-v2 pagination, reuses one tag "
        "listing per repository, verifies exact digest pins, and ignores prerelease tags."
    )
    print(
        "- Dockerfile pinned tool versions are checked against upstream: go→go.dev/proxy, "
        "pip→pypi.org, gem→rubygems.org, github→GitHub releases API."
    )
    print("- Version comparisons normalise leading 'v' so v2.4.1 and 2.4.1 are treated as equal.")
    print(
        "- Use --python-only, --node-only, --docker-only, --go-only, --pip-only, "
        "--gem-only, or --github-only to narrow the output; add --debug for Go lookup details."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
