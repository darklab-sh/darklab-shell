#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validate the reviewed license inventory for the released container."""

from __future__ import annotations

import glob
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
INVENTORY = ROOT / "deploy" / "container-licenses.json"
NOTICE = ROOT / "deploy" / "THIRD_PARTY_NOTICES.txt"
LICENSE_DIR = ROOT / "deploy" / "third-party-licenses"
NMAP_LICENSE = LICENSE_DIR / "Nmap-7.95-NPSL-0.95.txt"
NMAP_LICENSE_SHA256 = "9d9a9a763c0e6145172cfe7d8483e23b38ce60b6c79a82e4894242917bdae6d3"
WPSCAN_LICENSE = LICENSE_DIR / "WPScan-4.0.1.txt"
WPSCAN_LICENSE_SHA256 = "72eaecf9c3497bb34fb5722eba38a4b3b0ae39235c17378547101b8329b51008"
IMAGE_INVENTORY = Path("/usr/share/doc/darklab-shell/container-licenses.json")
RUBY_GEM_MANIFEST = Path("/usr/share/doc/darklab-shell/wpscan-ruby-gems.json")
NOTICE_NAME_RE = re.compile(r"(?:license|copying|notice|copyright)", re.IGNORECASE)


def _installed_notice_available(path: Path) -> bool:
    if path.is_file():
        return path.stat().st_size > 0
    if not path.is_dir():
        return False
    return any(
        candidate.is_file()
        and candidate.stat().st_size > 0
        and NOTICE_NAME_RE.search(candidate.name)
        for candidate in path.rglob("*")
    )


def _ruby_gem_specs() -> dict[str, object]:
    ruby_code = r'''
require "json"
specs = Gem::Specification.to_a.map do |spec|
  {
    "name" => spec.name,
    "version" => spec.version.to_s,
    "licenses" => spec.licenses.map(&:to_s).sort,
    "homepage" => spec.homepage.to_s,
    "default_gem" => spec.default_gem?
  }
end.sort_by { |spec| [spec["name"], spec["version"], spec["default_gem"].to_s] }
puts JSON.generate({"schema_version" => 1, "gems" => specs})
'''
    result = subprocess.run(
        ["ruby", "-e", ruby_code],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"could not inspect installed RubyGems: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("installed RubyGem inventory must be an object")
    return payload


def validate_installed_image() -> int:
    inventory = json.loads(IMAGE_INVENTORY.read_text(encoding="utf-8"))
    components = inventory.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("installed container license inventory has no components")

    for component in components:
        if not isinstance(component, dict):
            raise ValueError("installed container license component must be an object")
        name = str(component.get("name") or "<unnamed>")
        notice_location = component.get("notice_location")
        if not isinstance(notice_location, str) or not notice_location:
            raise ValueError(f"{name} has no installed notice location")
        for pattern in notice_location.split(" and "):
            matches = [Path(candidate) for candidate in glob.glob(pattern)]
            if not matches or not any(_installed_notice_available(path) for path in matches):
                raise ValueError(f"{name} has no usable installed notice at {pattern}")

    recorded_gems = json.loads(RUBY_GEM_MANIFEST.read_text(encoding="utf-8"))
    installed_gems = _ruby_gem_specs()
    if recorded_gems != installed_gems:
        raise ValueError("installed RubyGems differ from the reviewed image manifest")
    gems = recorded_gems.get("gems") if isinstance(recorded_gems, dict) else None
    if not isinstance(gems, list) or not gems:
        raise ValueError("reviewed RubyGem manifest is empty")
    missing_licenses = [
        str(gem.get("name") or "<unnamed>")
        for gem in gems
        if not isinstance(gem, dict) or not gem.get("licenses")
    ]
    if missing_licenses:
        raise ValueError(
            "installed RubyGems lack license metadata: " + ", ".join(missing_licenses)
        )

    print(
        f"Installed image exposes usable notices for {len(components)} component groups "
        f"and records {len(gems)} RubyGems."
    )
    return 0


def _version_args(dockerfile: str) -> set[str]:
    return set(re.findall(r"^ARG ([A-Z0-9_]+_VERSION)=", dockerfile, flags=re.MULTILINE))


def _declared_version_args(components: list[object]) -> set[str]:
    declared: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("every license component must be an object")
        version_arg = component.get("version_arg")
        if isinstance(version_arg, str):
            declared.add(version_arg)
        version_args = component.get("version_args", [])
        if not isinstance(version_args, list) or not all(isinstance(item, str) for item in version_args):
            raise ValueError(f"invalid version_args for {component.get('name', '<unnamed>')}")
        declared.update(version_args)
    return declared


def _dockerfile_install_refs(dockerfile: str) -> set[str]:
    normalized = re.sub(r"\\\s*\n", " ", dockerfile)
    refs: set[str] = set()

    for match in re.finditer(r"\bapt-get\s+install\s+([^\n&]+)", normalized):
        for token in shlex.split(match.group(1)):
            if not token.startswith("-"):
                refs.add(f"apt:{token.split('=', 1)[0]}")

    for match in re.finditer(r"\bpip\s+install\s+([^\n&]+)", normalized):
        skip_next = False
        for token in shlex.split(match.group(1)):
            if skip_next:
                skip_next = False
                continue
            if token in {"-r", "--requirement"}:
                skip_next = True
                continue
            if token.startswith("-"):
                continue
            name = re.split(r"[<>=!~\[]", token, maxsplit=1)[0].strip().lower()
            if name:
                refs.add(f"pip:{name}")

    for match in re.finditer(r"\bgit\s+clone\s+([^\n&]+)", normalized):
        url = next(
            (token for token in shlex.split(match.group(1)) if token.startswith("https://")),
            "",
        )
        if url:
            refs.add(f"git:{url}")
    return refs


def _validate_install_coverage(
    inventory: dict[str, object],
    component_names: set[str],
    dockerfile: str,
) -> None:
    coverage = inventory.get("dockerfile_install_coverage")
    if not isinstance(coverage, dict) or not coverage:
        raise ValueError("container license inventory must map Dockerfile install inputs")
    if not all(isinstance(ref, str) and isinstance(name, str) for ref, name in coverage.items()):
        raise ValueError("Dockerfile install coverage must map strings to component names")

    discovered = _dockerfile_install_refs(dockerfile)
    declared = set(coverage)
    missing = sorted(discovered - declared)
    stale = sorted(declared - discovered)
    unknown_components = sorted({str(name) for name in coverage.values()} - component_names)
    if missing or stale or unknown_components:
        raise ValueError(
            "Dockerfile install coverage drifted; "
            f"missing={missing}, stale={stale}, unknown_components={unknown_components}"
        )


def _validate_nmap_redistribution(
    components: list[object],
    *,
    require_approval: bool,
) -> None:
    nmap_components = [
        component
        for component in components
        if isinstance(component, dict) and component.get("name") == "Debian Nmap package"
    ]
    if len(nmap_components) != 1:
        raise ValueError("container license inventory must contain one Debian Nmap package")
    component = nmap_components[0]
    if component.get("license") != "LicenseRef-Nmap-Public-Source-0.95":
        raise ValueError("Debian Nmap package must declare NPSL 0.95")
    review = component.get("redistribution_review")
    allowed_reviews = {
        "requires-upstream-waiver-oem-or-legal-approval",
        "approved-by-upstream-waiver",
        "approved-by-oem-license",
        "approved-by-qualified-legal-review",
    }
    if review not in allowed_reviews:
        raise ValueError("Debian Nmap package has an invalid redistribution review status")
    if require_approval and not str(review).startswith("approved-by-"):
        raise ValueError(
            "public image publication requires an Nmap upstream waiver, OEM license, "
            "or qualified legal approval"
        )


def main(*, require_redistribution_approval: bool = False) -> int:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    components = inventory.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("container license inventory must contain components")

    app_version_match = re.search(r'^APP_VERSION = "([^"]+)"$', (ROOT / "app" / "config.py").read_text(), re.MULTILINE)
    if app_version_match is None:
        raise ValueError("could not read APP_VERSION from app/config.py")
    reviewed_release = inventory.get("reviewed_for_release")
    if reviewed_release != app_version_match.group(1):
        raise ValueError(
            f"license inventory covers {reviewed_release!r}, not app release {app_version_match.group(1)!r}"
        )

    names: set[str] = set()
    for component in components:
        assert isinstance(component, dict)
        name = component.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError(f"invalid or duplicate component name: {name!r}")
        names.add(name)
        for field in ("source", "license", "notice_location"):
            if not isinstance(component.get(field), str) or not component[field].strip():
                raise ValueError(f"{name} is missing {field}")
        if str(component["license"]).lower() in {"unknown", "noassertion", "pending", "blocked"}:
            raise ValueError(f"{name} has not completed license review")

    _validate_install_coverage(inventory, names, dockerfile)
    _validate_nmap_redistribution(
        components,
        require_approval=require_redistribution_approval,
    )

    docker_version_args = _version_args(dockerfile) - {"APP_VERSION"}
    declared_version_args = _declared_version_args(components)
    missing_args = sorted(docker_version_args - declared_version_args)
    unknown_args = sorted(declared_version_args - docker_version_args)
    if missing_args or unknown_args:
        raise ValueError(
            f"license inventory version args drifted; missing={missing_args}, unknown={unknown_args}"
        )

    required_files = [
        NOTICE,
        NMAP_LICENSE,
        WPSCAN_LICENSE,
        LICENSE_DIR / "frontend-runtime.txt",
        LICENSE_DIR / "OFL-1.1.txt",
    ]
    for path in required_files:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"required third-party notice is missing or empty: {path.relative_to(ROOT)}")
    wpscan_hash = hashlib.sha256(WPSCAN_LICENSE.read_bytes()).hexdigest()
    if wpscan_hash != WPSCAN_LICENSE_SHA256:
        raise ValueError("WPScan v4.0.1 license text differs from the reviewed upstream file")
    nmap_hash = hashlib.sha256(NMAP_LICENSE.read_bytes()).hexdigest()
    if nmap_hash != NMAP_LICENSE_SHA256:
        raise ValueError("Nmap v7.95 NPSL 0.95 text differs from the reviewed upstream file")

    print(
        f"Container license inventory covers {len(components)} component groups "
        f"for darklab_shell {reviewed_release}."
    )
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--installed-image"]:
        raise SystemExit(validate_installed_image())
    if sys.argv[1:] == ["--release"]:
        raise SystemExit(main(require_redistribution_approval=True))
    if sys.argv[1:]:
        raise SystemExit(f"unknown arguments: {' '.join(sys.argv[1:])}")
    raise SystemExit(main())
