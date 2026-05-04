#!/usr/bin/env python3
"""Check pinned dependency versions plus production and CI image versions.

The script reads the production Docker base image from Dockerfile and the CI
runner images from .gitlab-ci.yml so version checks follow the checked-in
runtime configuration instead of a separately maintained list.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parent.parent
REQ_FILES = (
    ROOT / "app" / "requirements.txt",
    ROOT / "requirements-dev.txt",
)
PACKAGE_JSON = ROOT / "package.json"
PACKAGE_LOCK = ROOT / "package-lock.json"
DOCKERFILE = ROOT / "Dockerfile"
GITLAB_CI = ROOT / ".gitlab-ci.yml"
PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==(.+)$")
IMAGE_PATTERN = re.compile(r"^([A-Za-z0-9./_-]+?)(?::([^@\s]+))?(?:@.+)?$")
NUMERIC_TAG_PATTERN = re.compile(r"^(\d+)(?:\.(\d+)(?:\.(\d+))?)?$")
ARG_PATTERN = re.compile(r"^ARG\s+([A-Za-z_][A-Za-z0-9_]*)=(.+)$")
DOCKER_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
GO_TOOLCHAIN_PATTERN = re.compile(r"go(\d+\.\d+(?:\.\d+)?)\.linux-")
GO_INSTALL_PATTERN = re.compile(r"go install(?:\s+-v)?\s+([^\s@]+)@([^\s\\]+)")
PIP_INSTALL_PATTERN = re.compile(r"pip install(?:\s+--[A-Za-z0-9_.=-]+)*\s+([A-Za-z0-9_.\-\[\]]+)==([^\s\\]+)")
GEM_INSTALL_PATTERN = re.compile(r"gem install\s+([A-Za-z0-9_.-]+)\s+-v\s+([^\s\\]+)")
GITHUB_RELEASE_PATTERN = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/releases/download/([^/\s]+)/")
GITHUB_CLONE_BRANCH_PATTERN = re.compile(
    r"git clone(?:\s+--depth\s+\d+)?\s+--branch\s+\"?([^\"\s]+)\"?\s+https://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?(?:\s|$)"
)
GO_STABLE_TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
CI_IMAGE_VAR_PATTERN = re.compile(r"^\s{2}(CI_[A-Z0-9_]+):\s*[\"']?([^\"'\n#]+)[\"']?\s*(?:#.*)?$")
CI_IMAGE_REF_PATTERN = re.compile(r"^\s*image:\s*\$([A-Z0-9_]+)\s*(?:#.*)?$")


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
    parts = package.split("/")
    if len(parts) >= 2 and parts[-2] == "cmd":
        return "/".join(parts[:-2])
    return package


def _read_lines(path: pathlib.Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text().splitlines()


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


def _latest_golang_version(module: str, debug: bool = False) -> str:
    module_root = _go_module_root(module)
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


def _parse_image_ref(ref: str) -> tuple[str, str | None] | None:
    ref = ref.strip()
    if not ref:
        return None
    match = IMAGE_PATTERN.match(ref)
    if not match:
        return None
    name, tag = match.groups()
    if "/" not in name:
        name = f"library/{name}"
    return name, tag


def _numeric_tag_key(tag: str) -> tuple[int, int, int] | None:
    match = NUMERIC_TAG_PATTERN.fullmatch(tag)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    return major, minor, patch


def _dockerhub_tags(repo: str) -> tuple[list[str], str | None]:
    repo = urllib.parse.quote(repo, safe="/")
    page = 1
    tags: list[str] = []
    while True:
        url = f"https://hub.docker.com/v2/repositories/{repo}/tags/?page_size=100&page={page}"
        last_error = "unknown error"
        payload = None
        for _ in range(3):
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                last_error = ""
                break
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code} on page {page}"
            except urllib.error.URLError as exc:
                reason = getattr(exc, 'reason', None)
                last_error = f"URL error on page {page}: {reason or exc}"
            except TimeoutError:
                last_error = f"timeout on page {page}"
            except ValueError:
                last_error = f"invalid JSON on page {page}"
        if payload is None:
            if tags:
                return tags, f"partial results ({last_error})"
            return [], last_error
        results = payload.get("results") or []
        for item in results:
            name = item.get("name")
            if isinstance(name, str) and name:
                tags.append(name)
        next_page = payload.get("next")
        if not next_page:
            break
        page += 1
    return tags, None


def _latest_docker_tag(current_image: str) -> tuple[str | None, str | None]:
    parsed = _parse_image_ref(current_image)
    if not parsed:
        return None, "unparseable image reference"
    repo, current_tag = parsed
    if not current_tag:
        return None, "missing tag"

    tag_suffix = ""
    base_tag = current_tag
    if "-" in current_tag:
        base_tag, tag_suffix = current_tag.split("-", 1)

    current_key = _numeric_tag_key(base_tag)
    if current_key is None:
        return None, f"unsupported tag format: {current_tag}"

    tags, fetch_error = _dockerhub_tags(repo)
    if not tags:
        return None, fetch_error or "unable to fetch Docker Hub tags"

    best_tag = None
    best_key = current_key
    for tag in tags:
        candidate_base = tag
        candidate_suffix = ""
        if "-" in tag:
            candidate_base, candidate_suffix = tag.split("-", 1)
        if candidate_suffix != tag_suffix:
            continue
        candidate_key = _numeric_tag_key(candidate_base)
        if candidate_key is None:
            continue
        if candidate_key > best_key:
            best_key = candidate_key
            best_tag = tag

    return best_tag, fetch_error


def _docker_base_image() -> str | None:
    if not DOCKERFILE.exists():
        return None
    for raw in _read_lines(DOCKERFILE):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("FROM "):
            ref = line.split(None, 1)[1]
            ref = ref.split(" AS ", 1)[0].split(" as ", 1)[0].strip()
            return ref
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
    for lineno, raw in enumerate(_read_lines(DOCKERFILE), start=1):
        line = _expand_docker_vars(raw.strip(), docker_args)
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


def _print_docker_image() -> None:
    image = _docker_base_image()
    if not image:
        print("\nDocker base image: unavailable")
        return
    print("\nDocker base image:")
    print(f"- {image}")
    newer, error = _latest_docker_tag(image)
    if newer:
        suffix = f" ({error})" if error else ""
        print(f"  newest: {newer}{suffix}")
    elif error:
        print(f"  newest: unknown ({error})")
    else:
        print("  newest: none found; current tag appears up to date")


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
        newer, error = _latest_docker_tag(image)
        if newer:
            suffix = f" ({error})" if error else ""
            print(f"  newest: {newer}{suffix}")
        elif error:
            print(f"  newest: unknown ({error})")
        else:
            print("  newest: none found; current tag appears up to date")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-only", action="store_true", help="Only report Python requirements")
    parser.add_argument("--node-only", action="store_true", help="Only report Node dependencies and devDependencies")
    parser.add_argument("--docker-only", action="store_true", help="Only report the Docker base image")
    parser.add_argument("--go-only", action="store_true", help="Only report Go toolchain and Go module pins from Dockerfile")
    parser.add_argument("--pip-only", action="store_true", help="Only report pip tool pins from Dockerfile")
    parser.add_argument("--gem-only", action="store_true", help="Only report gem tool pins from Dockerfile")
    parser.add_argument(
        "--github-only",
        action="store_true",
        help="Only report GitHub release pins from Dockerfile",
    )
    parser.add_argument("--debug", action="store_true", help="Print registry lookup details for Go pins")
    args = parser.parse_args()

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
        _print_ci_images()
        _print_dockerfile_pins(debug=args.debug)
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
        "- The Go check uses go.dev for the toolchain and the public Go module proxy for "
        "module pins; module checks only consider stable release tags."
    )
    print(
        "- The Node check reads package.json/package-lock.json dependencies and "
        "devDependencies and compares them against the npm registry."
    )
    print(
        "- The Docker/runtime check reads the production base image from Dockerfile and CI "
        "runner images from .gitlab-ci.yml, and ignores prerelease tags like alpha and rc builds."
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
