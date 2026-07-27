# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Documentation navigation, reference, and executable-contract safeguards."""

import ast
import html
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

_HERE = Path(__file__).parent          # tests/py/
_TESTS_README = _HERE.parent / "README.md"
_REPO_ROOT = _HERE.parent.parent
_CONTRIBUTING = _REPO_ROOT / "CONTRIBUTING.md"
_ARCHITECTURE = _REPO_ROOT / "ARCHITECTURE.md"
_CONFIGURATION = _REPO_ROOT / "CONFIGURATION.md"
_FEATURES = _REPO_ROOT / "FEATURES.md"
_README = _REPO_ROOT / "README.md"
_CONFIG_PY = _REPO_ROOT / "app" / "config.py"
_DEFAULT_CONFIG_YAML = _REPO_ROOT / "app" / "conf" / "config.yaml"
_COMMAND_REGISTRY_YAML = _REPO_ROOT / "app" / "conf" / "commands.yaml"
_ASSET_MANIFEST = _REPO_ROOT / "app" / "static" / "build" / "manifest.json"
_UI_CAPTURE_GUIDE = _REPO_ROOT / "tests" / "ui-capture-scenes.md"
_UI_CAPTURE_DESKTOP = _REPO_ROOT / "tests" / "js" / "e2e" / "ui-capture.desktop.capture.js"
_UI_CAPTURE_MOBILE = _REPO_ROOT / "tests" / "js" / "e2e" / "ui-capture.mobile.capture.js"
_PRODUCTION_COMPOSE = _REPO_ROOT / "deploy" / "compose.yaml"
_PRODUCTION_SETUP = _REPO_ROOT / "deploy" / "setup.sh.in"
_GITLAB_CI = _REPO_ROOT / ".gitlab-ci.yml"
_CHANGELOG = _REPO_ROOT / "CHANGELOG.md"
_LOGGING_GUIDE = _REPO_ROOT / "docs" / "logging.md"
_LOG_EVENT_INVENTORY_HASH = "ef19deee531e521563bc289877bc5be07044d90154a5a74dbd517ad1912a65b9"
_CHANGELOG_ARCHIVES = (
    _REPO_ROOT / "docs" / "changelog" / "2.x.md",
    _REPO_ROOT / "docs" / "changelog" / "1.x.md",
)

_ENVIRONMENT_OWNED_CONFIG_KEYS = frozenset({
    "ai_api_key",
    "ai_api_key_secret_name",
    "ai_base_url",
    "ai_enabled",
    "ai_feature_next_commands",
    "ai_feature_run_suggestions",
    "ai_feature_summary",
    "ai_model",
    "ai_provider",
    "database_backend",
    "database_url",
    "interactive_pty_enabled",
    "prometheus_multiproc_dir",
    "raw_packet_scanning_enabled",
    "restricted_command_input_cidrs",
    "workspace_backend",
    "workspace_enabled",
    "workspace_root",
})

_PUBLISHED_CHANGELOG_HASHES = {
    "2.8.1": "f1d84e7ec2c77cefe754e153180a375b5955d4562f3b7c53786ba449f6424ee7",
    "2.8.0": "44c87ab5e1e7543251459fa8437da43f77778efba7c9c9edbcc1cbd1111e86f2",
    "2.7.0": "5555b59b166f5008245919be88cd11e106f71ecaee60d0d88c10ad303945d69d",
    "2.6.0": "2301b6a3a70e07f14e5536c1b84aa25f5f5ba49fa67ddb8effd14814d6cc6351",
    "2.5.0": "57551c73e61a89420ac3bbc93427f260b177327f03b788c2f1658a362c29a7a8",
    "2.4": "6276e66a1f7dad33ec7e1f1334ced162ccaee30e4fc9d499c34e71d199e6e347",
    "2.3.1": "648441ffa4384a9117e89c42a7cb3b4d4c0c261bbc72f8046c0db46d5aa68231",
    "2.3": "99a990faa2246b6b6ac116102350dc3e75414554f3e90b34fdafa088e7cb3157",
    "2.2": "a7ccea324eac40e12ece94c6cb5fe4c5d7250a027f710ed31e2078752d4366e2",
    "2.1": "74d20197c7b3c94ffaf487b18878adf419f790aa938a69a58db1edd1c26a0f11",
    "2.0": "386ced5db19ad000056af0a70be8f3d7d479739e6fc69244476b28aef8b19d11",
    "1.7": "c3d002edf8440e82a3cf0d9cd1f39c784609e10075df464491effae59354ab92",
    "1.6": "c1b073dc97dcab4c65da05ee1850aab8fbbd09d96a2e6e7993a262a02d0ce0ae",
    "1.5": "4fc73c61fc5cba399570021354e8141cb1942e21f4929ccea0d59257c539f0e9",
    "1.4": "81bd89ecdfae6559fefaf44ba49a7d4aa4e76187e7b8f77a412396dde3af8f23",
    "1.3": "0dd2a5d1fb2fa21b65cf33670a090c9857d84babdf6436bf9ae71746977b01e5",
    "1.2": "2a62f820dea1579ed5fc88abeaefc0f418b0357a4956845c43e38d105ae27024",
    "1.1": "0de878944fff2e15eb357da291110d473d3f4db000104936202ae6771f68731d",
    "1.0": "602ff73346015b8e2b259f9dff77ce62a38c84d09cf610df2de87fcbe6c63114",
}

_LIVE_TEST_LISTING_COMMANDS = (
    "bash scripts/run_pytest.sh -c .tooling/pytest.ini --rootdir=. --collect-only -q",
    "npx vitest list --config .tooling/vitest.config.js",
    "npx playwright test --config .tooling/playwright.parallel.config.js --list",
    "npx playwright test --config .tooling/playwright.demo.config.js --list",
    "npx playwright test --config .tooling/playwright.demo.mobile.config.js --list",
    "npx playwright test --config .tooling/playwright.capture.desktop.config.js --list",
    "npx playwright test --config .tooling/playwright.capture.mobile.config.js --list",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _config_default_keys() -> list[str]:
    """Return app/config.py load_config() default keys in source order."""
    tree = ast.parse(_CONFIG_PY.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "load_config":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "defaults"
                       for target in child.targets):
                continue
            if not isinstance(child.value, ast.Dict):
                continue
            keys: list[str] = []
            for key_node in child.value.keys:
                if key_node is None:
                    continue
                key = ast.literal_eval(key_node)
                if isinstance(key, str):
                    keys.append(key)
            return keys
    raise AssertionError("Could not find load_config() defaults dict in app/config.py")


def _operator_yaml_default_keys() -> list[str]:
    """Return defaults that operators can set through YAML."""
    return [
        key for key in _config_default_keys()
        if key not in _ENVIRONMENT_OWNED_CONFIG_KEYS
    ]


def _documented_default_config_keys() -> set[str]:
    """Return top-level config keys represented in app/conf/config.yaml."""
    keys = set()
    for line in _DEFAULT_CONFIG_YAML.read_text().splitlines():
        match = re.match(r"^#?\s*([A-Za-z_][A-Za-z0-9_]*):(?:\s|$)", line)
        if match:
            keys.add(match.group(1))
    return keys


def _configuration_reference_table_keys() -> set[str]:
    """Return setting names from the CONFIGURATION.md application YAML table."""
    text = _CONFIGURATION.read_text()
    match = re.search(
        r"^## Application YAML Settings\n(?P<body>.*?)(?:^---\n\n## Files Under app/conf\n)",
        text,
        re.M | re.S,
    )
    assert match, "Could not find CONFIGURATION.md '## Application YAML Settings' table"
    return set(re.findall(r"^\|\s+`([^`]+)`\s+\|", match.group("body"), re.M))


def _project_markdown_docs() -> list[str]:
    return [
        path for path in sorted(set(_git_tracked_files()) | set(_git_untracked_files()))
        if path.endswith(".md")
        and not _is_transient_doc_path(path)
    ]


def _markdown_path_for(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _normalise_doc_link(source_path: Path, href: str) -> str | None:
    target = href.split("#", 1)[0]
    if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target):
        return None
    resolved = (source_path.parent / target).resolve()
    try:
        return resolved.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return None


def _markdown_links_in_body(source_path: Path, body: str) -> list[str]:
    links: list[str] = []
    for href in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body):
        target = _normalise_doc_link(source_path, href)
        if target and target.endswith(".md"):
            _append_unique(links, target)
    return links


def _related_docs_links(source_path: Path) -> list[str] | None:
    text = _markdown_without_fenced_code(source_path.read_text())
    match = re.search(
        r"^## Related Docs\n\n(?P<body>.*?)(?:\n^## |\Z)",
        text,
        re.M | re.S,
    )
    if not match:
        return None
    return _markdown_links_in_body(source_path, match.group("body"))


def _documentation_map_links(source_path: Path) -> list[str]:
    match = re.search(
        r"^## Documentation Map\n\n(?P<body>.*?)(?:\n^---\n|\n^## |\Z)",
        source_path.read_text(),
        re.M | re.S,
    )
    assert match, "Could not find README.md '## Documentation Map' section"
    return _markdown_links_in_body(source_path, match.group("body"))


def _markdown_validation_paths() -> list[Path]:
    paths = set(_git_tracked_files()) | set(_git_untracked_files())
    return [
        _REPO_ROOT / path
        for path in sorted(paths)
        if path.endswith(".md")
    ]


def _markdown_without_fenced_code(text: str) -> str:
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            lines.append("")
            continue
        lines.append("" if fence else line)
    return "\n".join(lines)


def _markdown_link_targets(text: str) -> list[tuple[int, str]]:
    targets: list[tuple[int, str]] = []
    clean = _markdown_without_fenced_code(text)
    inline_re = re.compile(r"!?\[[^\]]*\]\((?P<href><[^>]+>|[^\s)]+)")
    reference_re = re.compile(r"^\s*\[[^\]]+\]:\s*(?P<href><[^>]+>|\S+)")
    for lineno, line in enumerate(clean.splitlines(), start=1):
        line = re.sub(r"`[^`]*`", "", line)
        for match in inline_re.finditer(line):
            targets.append((lineno, match.group("href").strip("<>")))
        match = reference_re.match(line)
        if match:
            targets.append((lineno, match.group("href").strip("<>")))
    return targets


def _github_heading_slug(title: str) -> str:
    title = html.unescape(title)
    title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
    title = re.sub(r"<[^>]+>", "", title)
    title = re.sub(r"[`*_~]", "", title).strip().lower()
    title = re.sub(r"[^\w\- ]", "", title)
    return re.sub(r"\s", "-", title)


def _markdown_headings(text: str) -> list[tuple[int, str, str]]:
    headings: list[tuple[int, str, str]] = []
    slug_counts: dict[str, int] = {}
    clean = _markdown_without_fenced_code(text)
    for line in clean.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        base_slug = _github_heading_slug(title)
        seen = slug_counts.get(base_slug, 0)
        slug_counts[base_slug] = seen + 1
        slug = base_slug if seen == 0 else f"{base_slug}-{seen}"
        headings.append((level, title, slug))
    return headings


def _documented_capture_slugs(section_name: str) -> list[str]:
    text = _UI_CAPTURE_GUIDE.read_text()
    match = re.search(
        rf"^## {re.escape(section_name)}\n(?P<body>.*?)(?=^## |\Z)",
        text,
        re.M | re.S,
    )
    assert match, f"Could not find {section_name!r} in tests/ui-capture-scenes.md"
    return re.findall(r"^\|\s*\d+\s*\|\s*`([^`]+)`\s*\|", match.group("body"), re.M)


def _capture_source_slugs(path: Path) -> list[str]:
    text = path.read_text()
    _, marker, scenes_text = text.partition("const scenes = [")
    assert marker, f"Could not find scenes array in {path.relative_to(_REPO_ROOT)}"
    return re.findall(r"^\s+slug:\s*'([^']+)'", scenes_text, re.M)


def _supported_runtime_rows() -> dict[str, str]:
    text = _CONFIGURATION.read_text()
    match = re.search(
        r"^## Supported Runtimes\n(?P<body>.*?)(?=^---\n\n## |^## |\Z)",
        text,
        re.M | re.S,
    )
    assert match, "Could not find CONFIGURATION.md '## Supported Runtimes' section"
    rows = {}
    for name, value in re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", match.group("body"), re.M):
        if name.strip() in {"Runtime surface", "-----------------"}:
            continue
        rows[name.strip()] = value.strip()
    return rows


def _changelog_sections(path: Path) -> list[dict[str, str]]:
    pattern = re.compile(
        r"^## \[(?P<version>[^\]]+)\] (?P<separator>-|—) "
        r"(?P<label>Unreleased|initial release|\d{4}-\d{2}-\d{2})\n"
        r".*?(?=^## \[|\Z)",
        re.M | re.S,
    )
    sections = []
    for match in pattern.finditer(path.read_text()):
        body = re.sub(r"\n---\Z", "", match.group(0).rstrip()).rstrip()
        sections.append({
            "version": match.group("version"),
            "label": match.group("label"),
            "body": body,
        })
    return sections


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _log_event_inventory_body() -> str:
    match = re.search(
        r"^## Log Event Inventory\n(?P<body>.*?)(?=^## Logging Shape Notes)",
        _LOGGING_GUIDE.read_text(),
        re.M | re.S,
    )
    assert match, "Could not find docs/logging.md event inventory"
    return match.group("body")


# ── Stable asset and repository-layout contracts ─────────────────────────────

_TEMPLATE_STATIC_URL_RE = re.compile(r"['\"](/(?:static|vendor)/[^'\"]+)['\"]")


def _asset_source_path(source: str) -> Path:
    if source.startswith("/static/"):
        return _REPO_ROOT / "app" / "static" / source.removeprefix("/static/")
    if source.startswith("/vendor/fonts/"):
        return _REPO_ROOT / "app" / "static" / source.removeprefix("/vendor/")
    if source.startswith("/vendor/"):
        return _REPO_ROOT / "app" / "static" / "js" / "vendor" / source.removeprefix("/vendor/")
    raise AssertionError(f"Unsupported asset source in manifest: {source}")


def _template_static_url_violations() -> list[str]:
    violations: list[str] = []
    templates_root = _REPO_ROOT / "app" / "templates"
    for template in sorted(templates_root.rglob("*.html")):
        rel = template.relative_to(_REPO_ROOT).as_posix()
        for line_no, line in enumerate(template.read_text(encoding="utf-8").splitlines(), start=1):
            if "static_asset(" in line or "asset_bundle(" in line:
                continue
            for match in _TEMPLATE_STATIC_URL_RE.finditer(line):
                violations.append(f"{rel}:{line_no}: {match.group(1)}")
    return violations


def _template_document_frame_violations() -> list[str]:
    templates_root = _REPO_ROOT / "app" / "templates"
    base_template = templates_root / "base.html"
    violations: list[str] = []
    base_text = base_template.read_text(encoding="utf-8")
    for token in ("<!DOCTYPE html>", "<html lang=\"en\">", "<head>", "<body", "</body>", "</html>"):
        if base_text.count(token) != 1:
            violations.append(f"app/templates/base.html: expected one {token!r}")

    for name in ("index.html", "permalink_base.html", "diag.html", "diag_audit.html"):
        template = templates_root / name
        text = template.read_text(encoding="utf-8")
        if '{% extends "base.html" %}' not in text:
            violations.append(f"app/templates/{name}: must extend base.html")
        for label, pattern in (
            ("<!DOCTYPE html>", r"<!DOCTYPE\s+html>"),
            ("<html>", r"<html(?:\s|>)"),
            ("<head>", r"<head(?:\s|>)"),
            ("<body>", r"<body(?:\s|>)"),
            ("</body>", r"</body>"),
            ("</html>", r"</html>"),
        ):
            if re.search(pattern, text, flags=re.I):
                violations.append(f"app/templates/{name}: document frame contains {label!r}")

    for name in ("permalink.html", "permalink_error.html"):
        text = (templates_root / name).read_text(encoding="utf-8")
        if '{% extends "permalink_base.html" %}' not in text:
            violations.append(f"app/templates/{name}: must extend permalink_base.html")
    return violations


def _git_tracked_files() -> list[str]:
    """Return git-tracked files that still exist in the current checkout."""
    result = subprocess.run(
        ["git", "ls-files", "--cached"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT), check=True,
    )
    return [
        line
        for line in result.stdout.splitlines()
        if line and (_REPO_ROOT / line).exists()
    ]


def _git_untracked_files() -> list[str]:
    """Return untracked files that are not ignored by git."""
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT), check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _repository_layout_paths() -> list[str]:
    match = re.search(
        r"^## Repository Layout\n(?P<body>.*?)(?=^## |\Z)",
        _README.read_text(),
        re.M | re.S,
    )
    assert match, "Could not find README.md '## Repository Layout' section"
    return re.findall(r"^\|\s*`([^`]+/)`\s*\|", match.group("body"), re.M)


def _is_transient_doc_path(path: str) -> bool:
    return (
        path.startswith("docs/release-drafts/")
        or path.endswith("_review.md")
    )


def _documented_architecture_routes() -> set[tuple[str, str]]:
    """Return documented (method, route) pairs from the route inventory."""
    routes: set[tuple[str, str]] = set()
    in_section = False
    for line in _ARCHITECTURE.read_text().splitlines():
        if line == "## HTTP Route Inventory":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        match = re.match(r"^\|\s+`([A-Z]+)`\s+\|\s+`([^`]+)`\s+\|", line)
        if match:
            routes.add((match.group(1), match.group(2)))
    return routes


def _registered_flask_routes() -> set[tuple[str, str]]:
    """Return registered Flask (method, route) pairs, excluding automatic methods."""
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True

    routes: set[tuple[str, str]] = set()
    for rule in app.url_map.iter_rules():
        methods = rule.methods or set()
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            routes.add((method, rule.rule))
    return routes


class TestProjectStructureCoverage:
    """Protect stable asset contracts and the compact repository layout."""

    def test_asset_manifest_source_hashes_match_current_sources(self):
        manifest = json.loads(_ASSET_MANIFEST.read_text(encoding="utf-8"))
        stale = []
        for bundle_name, bundle in sorted((manifest.get("bundles") or {}).items()):
            source_hashes = bundle.get("source_hashes") or {}
            for source, expected_hash in sorted(source_hashes.items()):
                path = _asset_source_path(source)
                actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    stale.append(f"{bundle_name}: {source}")
        assert not stale, (
            "Asset manifest source hashes are stale. Run assets:sync:\n"
            + "\n".join(f"  {item}" for item in stale)
        )

    def test_asset_manifest_esm_bundles_do_not_include_lazy_sources(self):
        manifest = json.loads(_ASSET_MANIFEST.read_text(encoding="utf-8"))
        config = json.loads((_REPO_ROOT / "assets.config.json").read_text(encoding="utf-8"))
        lazy_sources = set(config.get("lazy") or [])
        eager_lazy_sources = []
        for bundle_name, bundle in sorted((manifest.get("bundles") or {}).items()):
            if bundle.get("type") != "esm":
                continue
            for source in sorted(bundle.get("sources") or []):
                if source in lazy_sources:
                    eager_lazy_sources.append(f"{bundle_name}: {source}")
        assert not eager_lazy_sources, (
            "ESM bundles include assets configured as lazy. Run assets:sync "
            "after removing the eager import, or remove the source from "
            "assets.config.json lazy:\n"
            + "\n".join(f"  {item}" for item in eager_lazy_sources)
        )

    def test_pytest_files_do_not_import_legacy_flask_singleton(self):
        offenders: list[str] = []
        for path in sorted(_HERE.glob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            app_aliases: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app":
                            app_aliases.add(alias.asname or alias.name)
                            if alias.asname == "shell_app":
                                offenders.append(f"{path.name}:{node.lineno}: import app as shell_app")
                elif isinstance(node, ast.ImportFrom) and node.module == "app":
                    for alias in node.names:
                        if alias.name == "app":
                            offenders.append(f"{path.name}:{node.lineno}: from app import app")
                elif (
                    isinstance(node, ast.Attribute)
                    and node.attr == "app"
                    and isinstance(node.value, ast.Name)
                    and node.value.id in app_aliases
                ):
                    offenders.append(f"{path.name}:{node.lineno}: {node.value.id}.app")

        assert not offenders, "Tests must build Flask apps through create_app():\n" + "\n".join(offenders)

    @pytest.mark.release_integration
    def test_asset_build_output_does_not_depend_on_cwd(self, tmp_path):
        if shutil.which("node") is None:
            pytest.skip("node is not available")
        if not (_REPO_ROOT / "node_modules" / "esbuild").exists():
            pytest.skip("node dependencies are not installed")

        root_out = tmp_path / "from-root"
        scripts_out = tmp_path / "from-scripts"
        script = _REPO_ROOT / "scripts" / "frontend" / "build_assets.mjs"
        subprocess.run(
            ["node", str(script), "--out-dir", str(root_out), "--no-precompress"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["node", str(script), "--out-dir", str(scripts_out), "--no-precompress"],
            cwd=str(_REPO_ROOT / "scripts" / "frontend"),
            capture_output=True,
            text=True,
            check=True,
        )
        root_files = sorted(path.relative_to(root_out) for path in root_out.rglob("*") if path.is_file())
        scripts_files = sorted(path.relative_to(scripts_out) for path in scripts_out.rglob("*") if path.is_file())
        assert not any(str(path).endswith((".br", ".gz")) for path in root_files + scripts_files)
        changed = [
            str(path)
            for path in root_files
            if path in scripts_files
            and (root_out / path).read_bytes() != (scripts_out / path).read_bytes()
        ]
        assert root_files == scripts_files and not changed, (
            "Asset build output depends on the current working directory:\n"
            + "\n".join(f"  changed: {path}" for path in changed)
            + "\n"
            + "\n".join(f"  root-only: {path}" for path in sorted(set(root_files) - set(scripts_files)))
            + "\n"
            + "\n".join(f"  scripts-only: {path}" for path in sorted(set(scripts_files) - set(root_files)))
        )

    def test_committed_asset_sidecars_roundtrip_to_source_bytes(self):
        if shutil.which("node") is None:
            pytest.skip("node is not available")

        verification = r"""
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const root = process.argv[1];
const extensions = new Set(['.css', '.js', '.json', '.map', '.svg']);
const files = fs.readdirSync(root).filter((name) => {
  const fullPath = path.join(root, name);
  return fs.statSync(fullPath).isFile()
    && extensions.has(path.extname(name))
    && fs.statSync(fullPath).size >= 100
    && name !== 'manifest.json';
});
for (const name of files) {
  const source = fs.readFileSync(path.join(root, name));
  const brPath = path.join(root, `${name}.br`);
  const gzPath = path.join(root, `${name}.gz`);
  if (!fs.existsSync(brPath) || !fs.existsSync(gzPath)) {
    throw new Error(`missing compressed sidecar for ${name}`);
  }
  if (!zlib.brotliDecompressSync(fs.readFileSync(brPath)).equals(source)) {
    throw new Error(`Brotli sidecar does not match ${name}`);
  }
  if (!zlib.gunzipSync(fs.readFileSync(gzPath)).equals(source)) {
    throw new Error(`gzip sidecar does not match ${name}`);
  }
}
if (files.length === 0) throw new Error('no precompressed assets were checked');
"""
        result = subprocess.run(
            ["node", "-e", verification, str(_REPO_ROOT / "app" / "static" / "build")],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr or result.stdout

    def test_asset_build_logs_esm_bundle_failure_context(self):
        script = (
            _REPO_ROOT / "scripts" / "frontend" / "build_assets.mjs"
        ).read_text(encoding="utf-8")
        assert "[assets] ESM bundle failed" in script
        for field in ("bundle:", "entry,", "out_dir:", "check_only:", "message:"):
            assert field in script

    def test_listed_paths_exist_in_git(self):
        """Every named layout directory must contain a tracked file."""
        template_static_url_violations = _template_static_url_violations()
        assert not template_static_url_violations, (
            "Templates must resolve /static/ and /vendor/ URLs through "
            "static_asset() or asset_bundle() so immutable cache headers always "
            "have content-hashed or versioned URLs:\n"
            + "\n".join(f"  {violation}" for violation in template_static_url_violations)
        )
        template_document_frame_violations = _template_document_frame_violations()
        assert not template_document_frame_violations, (
            "base.html must own the document frame while page templates own "
            "only page-specific blocks:\n"
            + "\n".join(f"  {violation}" for violation in template_document_frame_violations)
        )
        listed = _repository_layout_paths()
        tracked = _git_tracked_files()
        unknown = sorted(
            path for path in listed
            if not any(candidate.startswith(path) for candidate in tracked)
        )
        assert not unknown, (
            "README.md '## Repository Layout' lists directories without tracked files:\n"
            + "\n".join(f"  {p}" for p in unknown)
        )


# ── Part 4: ARCHITECTURE.md HTTP route inventory ─────────────────────────────

class TestArchitectureRouteInventory:
    """The architecture route inventory must cover every registered route."""

    def test_route_inventory_matches_flask_url_map(self):
        documented = _documented_architecture_routes()
        actual = _registered_flask_routes()
        missing = sorted(actual - documented)
        extra = sorted(documented - actual)
        assert not missing and not extra, (
            "ARCHITECTURE.md '## HTTP Route Inventory' drift:\n"
            f"  documented={len(documented)}, actual={len(actual)}\n"
            + "\n".join(
                [
                    *(f"  missing: {method} {route}" for method, route in missing),
                    *(f"  extra: {method} {route}" for method, route in extra),
                ]
            )
        )


# ── Part 5: operator configuration docs ──────────────────────────────────────

class TestOperatorConfigurationDocs:
    """Operator-facing YAML defaults must stay represented in both references."""

    def test_config_yaml_represents_app_defaults(self):
        expected = _operator_yaml_default_keys()
        documented = _documented_default_config_keys()
        missing = [key for key in expected if key not in documented]
        assert not missing, (
            "app/conf/config.yaml is missing app/config.py default keys:\n"
            + "\n".join(f"  {key}" for key in missing)
        )

    def test_configuration_reference_represents_app_defaults(self):
        expected = _operator_yaml_default_keys()
        documented = _configuration_reference_table_keys()
        missing = [key for key in expected if key not in documented]
        assert not missing, (
            "CONFIGURATION.md '## Application YAML Settings' table is missing "
            "app/config.py default keys:\n"
            + "\n".join(f"  {key}" for key in missing)
        )


class TestChangelogArchives:
    def test_root_keeps_active_release_and_two_newest_published_releases(self):
        sections = _changelog_sections(_CHANGELOG)
        assert len(sections) == 3
        assert sections[0]["label"] == "Unreleased"
        assert all(section["label"] != "Unreleased" for section in sections[1:])

    def test_archive_coverage_matches_major_release_ranges(self):
        expected = {
            "2.x.md": (
                "2.7.0",
                "2.6.0",
                "2.5.0",
                "2.4",
                "2.3.1",
                "2.3",
                "2.2",
                "2.1",
                "2.0",
            ),
            "1.x.md": ("1.7", "1.6", "1.5", "1.4", "1.3", "1.2", "1.1", "1.0"),
        }
        actual = {
            path.name: tuple(section["version"] for section in _changelog_sections(path))
            for path in _CHANGELOG_ARCHIVES
        }
        assert actual == expected

    def test_release_versions_are_unique_and_newest_first(self):
        seen = []
        for path in (_CHANGELOG, *_CHANGELOG_ARCHIVES):
            versions = [section["version"] for section in _changelog_sections(path)]
            assert versions == sorted(versions, key=_version_key, reverse=True), path
            seen.extend(versions)
        assert len(seen) == len(set(seen)), "Release headings must appear exactly once"

    def test_published_release_bodies_match_the_archival_baseline(self):
        actual = {}
        for path in (_CHANGELOG, *_CHANGELOG_ARCHIVES):
            for section in _changelog_sections(path):
                if section["label"] == "Unreleased":
                    continue
                actual[section["version"]] = hashlib.sha256(
                    section["body"].encode()
                ).hexdigest()
        assert actual == _PUBLISHED_CHANGELOG_HASHES

    def test_root_archive_index_and_documentation_map_cover_archives(self):
        archive_links = {path.relative_to(_REPO_ROOT).as_posix() for path in _CHANGELOG_ARCHIVES}
        root_links = set(_markdown_links_in_body(_CHANGELOG, _CHANGELOG.read_text()))
        map_links = set(_documentation_map_links(_README))
        assert archive_links <= root_links
        assert archive_links <= map_links


class TestLoggingReference:
    def test_event_inventory_was_moved_without_dropping_contracts(self):
        body = _log_event_inventory_body()
        assert hashlib.sha256(body.encode()).hexdigest() == _LOG_EVENT_INVENTORY_HASH
        assert len(re.findall(r"^\| (?:DEBUG|INFO|WARNING|ERROR|CRITICAL) \|", body, re.M)) == 236

    def test_architecture_links_to_the_canonical_logging_reference(self):
        assert "[Logging Reference](docs/logging.md)" in _ARCHITECTURE.read_text()


class TestCanonicalFeatureAndDesignReferences:
    def test_feature_entries_keep_user_contracts_without_file_inventories(self):
        text = _FEATURES.read_text()
        assert "**Related files:**" not in text
        assert not re.search(r"`(?:app/(?!conf/)|tests/)", text)
        sections = re.findall(
            r"^## (?P<title>[^\n]+)\n(?P<body>.*?)(?=^## |\Z)",
            text,
            re.M | re.S,
        )
        missing_purpose = [
            title for title, body in sections
            if title not in {"Contents", "Related Docs"}
            and "**Purpose:**" not in body
        ]
        assert not missing_purpose

    def test_front_end_design_has_one_stable_contributor_anchor(self):
        text = _ARCHITECTURE.read_text()
        assert text.count("## Front End Design\n") == 1
        assert "### Design System Primitives\n" in text
        assert "ARCHITECTURE.md#front-end-design" in _CONTRIBUTING.read_text()


class TestReadmeStartPaths:
    def test_quick_start_keeps_release_install_separate_from_verification_and_development(self):
        text = _README.read_text()
        quick_start = text.split("## Quick Start\n", 1)[1].split("\n## ", 1)[0]
        production = text.split("## Production Deployment\n", 1)[1].split("\n## ", 1)[0]
        development = text.split("## Running in a Development Environment\n", 1)[1].split("\n## ", 1)[0]
        current_deployment_docs = "\n".join(
            path.read_text()
            for path in (
                _README,
                _REPO_ROOT / "CONFIGURATION.md",
                _REPO_ROOT / "FEATURES.md",
                _REPO_ROOT / "THEME.md",
                _REPO_ROOT / "docs" / "logging.md",
                _REPO_ROOT / "docs" / "postgres-migration.md",
            )
        )

        assert text.index("## Quick Start\n") < text.index("## Features\n")
        assert "curl -fsSL" in quick_start and "| sh -s --" in quick_start
        assert 'DARKLAB_INSTALL_DIR="$HOME/darklab-shell"' in quick_start
        assert '--dir "$DARKLAB_INSTALL_DIR"' in quick_start
        assert 'cd "$DARKLAB_INSTALL_DIR"' in quick_start
        assert "#review-and-verify-the-installer" in quick_start
        assert "Option 1" not in text and "Option 2" not in text and "Option 3" not in text
        assert "cosign verify-blob SHA256SUMS" in production
        assert "sha256sum -c setup.sh.sha256" in production
        assert 'DARKLAB_INSTALL_DIR="$HOME/darklab-shell"' in production
        assert '--dir "$DARKLAB_INSTALL_DIR"' in production
        assert 'cd "$DARKLAB_INSTALL_DIR"' in production
        assert '--dir "$HOME/darklab-shell"' not in text
        assert 'cd "$HOME/darklab-shell"' not in text
        assert "git clone https://gitlab.com/darklab.sh/darklab_shell.git" in development
        assert "bash examples/run_local.sh" in development
        assert "docker compose -f compose.dev.yaml up --build" in development
        assert "git clone" not in quick_start and "examples/run_local.sh" not in quick_start
        assert "repository-free" not in current_deployment_docs.lower()
        assert "examples/docker-compose.prod.yml" not in current_deployment_docs
        assert "docker-compose.yml" not in current_deployment_docs
        assert "python scripts/backup_system.py" not in current_deployment_docs
        config_reference = (_REPO_ROOT / "app" / "conf" / "config.yaml").read_text()
        for key in _ENVIRONMENT_OWNED_CONFIG_KEYS:
            assert not re.search(rf"(?m)^\s*#?\s*{re.escape(key)}\s*:", config_reference), key
        assert "workspace_max_file_mb:" in config_reference
        assert "interactive_pty_max_runtime_seconds:" in config_reference
        assert "database_pool_min:" in config_reference
        assert "ai_timeout_seconds:" in config_reference


class TestReadmeInstalledTools:
    def test_table_matches_external_command_registry(self):
        registry_text = _COMMAND_REGISTRY_YAML.read_text()
        commands_body = registry_text.split("commands:\n", 1)[1].split("\npipe_helpers:\n", 1)[0]
        registry_roots = set(re.findall(r"^  - root:\s*(\S+)\s*$", commands_body, re.M))

        readme_body = _README.read_text().split("## Installed Tools\n", 1)[1].split("\n## ", 1)[0]
        tool_cells = re.findall(r"^\|\s*(?P<cell>[^|]+?)\s*\|", readme_body, re.M)
        documented_roots = [
            root
            for cell in tool_cells
            for root in re.findall(r"`([^`]+)`", cell)
        ]

        assert len(documented_roots) == len(set(documented_roots)), (
            "README Installed Tools contains duplicate command names"
        )
        assert set(documented_roots) == registry_roots, (
            "README Installed Tools must match the base external command registry. "
            f"Missing: {sorted(registry_roots - set(documented_roots))}; "
            f"extra: {sorted(set(documented_roots) - registry_roots)}"
        )


# ── Related-doc navigation ───────────────────────────────────────────────────

class TestRelatedDocsNavigation:
    def test_related_docs_sections_are_curated_and_valid(self):
        markdown_docs = _project_markdown_docs()
        markdown_doc_set = set(markdown_docs)
        issues = []
        for path in markdown_docs:
            source_path = _REPO_ROOT / path
            links = _related_docs_links(source_path)
            if links is None:
                continue
            if len(links) > 5:
                issues.append(f"{path} links to {len(links)} documents; keep roughly five or fewer")
            if path in links:
                issues.append(f"{path} links to itself")
            unknown = sorted(set(links) - markdown_doc_set)
            if unknown:
                issues.append(
                    f"{path} links to non-project Markdown files:\n"
                    + "\n".join(f"  {candidate}" for candidate in unknown)
                )
        assert not issues, "\n\n".join(issues)

    def test_readme_documentation_map_lists_project_markdown_files(self):
        expected = set(_project_markdown_docs()) - {"README.md"}
        links = set(_documentation_map_links(_README))
        assert links == expected, (
            "README.md '## Documentation Map' must list every project Markdown "
            "document except README.md itself."
        )


class TestDocumentationDurability:
    def test_pre_commit_uses_canonical_shell_lint_scope(self):
        pre_commit = (_REPO_ROOT / "scripts" / "hooks" / "pre-commit").read_text(
            encoding="utf-8"
        )
        assert (
            'run_check "shellcheck" npm --prefix "$REPO_ROOT" run lint:shell'
            in pre_commit
        )

    def test_python_dependency_audits_cover_runtime_and_development_requirements(self):
        package_scripts = json.loads(
            (_REPO_ROOT / "package.json").read_text(encoding="utf-8")
        )["scripts"]
        audit_commands = {
            "package.json audit:py": package_scripts["audit:py"],
            "pre-commit pip-audit": (
                _REPO_ROOT / "scripts" / "hooks" / "pre-commit"
            ).read_text(encoding="utf-8"),
            "CONTRIBUTING.md Python dep CVEs": _CONTRIBUTING.read_text(
                encoding="utf-8"
            ),
        }
        expected_inputs = ("-r app/requirements.txt", "-r requirements-dev.txt")
        missing = {
            source: [item for item in expected_inputs if item not in command]
            for source, command in audit_commands.items()
            if any(item not in command for item in expected_inputs)
        }
        assert not missing, (
            "Every Python dependency audit path must cover runtime and development "
            f"requirements: {missing}"
        )

    def test_testing_handbook_keeps_live_listing_commands(self):
        text = _TESTS_README.read_text()
        missing = [command for command in _LIVE_TEST_LISTING_COMMANDS if command not in text]
        assert not missing, (
            "tests/README.md must retain lightweight live-suite listing commands:\n"
            + "\n".join(f"  {command}" for command in missing)
        )

    def test_reader_docs_do_not_hardcode_test_totals(self):
        total_re = re.compile(
            r"current totals:"
            r"|\b\d[\d,]*\s+(?:pytest|vitest|playwright)(?:\s+tests?)?\b"
            r"|\b(?:pytest|vitest|playwright)\b[^\n]{0,40}\b\d[\d,]*\s+"
            r"(?:tests?|behavior|meta)\b",
            re.I,
        )
        issues = []
        for path in _markdown_validation_paths():
            relative = _markdown_path_for(path)
            if (
                relative in {"CHANGELOG.md", "TODO.md"}
                or relative.startswith(("docs/changelog/", "docs/release-drafts/"))
                or relative.endswith("_review.md")
            ):
                continue
            for lineno, line in enumerate(
                _markdown_without_fenced_code(path.read_text()).splitlines(),
                start=1,
            ):
                if total_re.search(line):
                    issues.append(f"{relative}:{lineno}: {line.strip()}")
        assert not issues, (
            "Reader-facing docs must use the live runners instead of hardcoded test totals:\n"
            + "\n".join(issues)
        )


# ── Part 8: durable documentation navigation and focused contracts ──────────

class TestMarkdownNavigationIntegrity:
    def test_repository_relative_links_and_fragments_resolve(self):
        issues = []
        headings_by_path: dict[Path, set[str]] = {}
        for source_path in _markdown_validation_paths():
            for lineno, href in _markdown_link_targets(source_path.read_text()):
                href = unquote(href)
                if not href or href.startswith("/") or re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I):
                    continue
                target_text, separator, fragment = href.partition("#")
                target_text = target_text.split("?", 1)[0]
                target_path = source_path if not target_text else (source_path.parent / target_text).resolve()
                try:
                    target_path.relative_to(_REPO_ROOT)
                except ValueError:
                    issues.append(
                        f"{_markdown_path_for(source_path)}:{lineno} escapes the repository: {href}"
                    )
                    continue
                if not target_path.exists():
                    issues.append(
                        f"{_markdown_path_for(source_path)}:{lineno} has a missing local target: {href}"
                    )
                    continue
                if separator and fragment and target_path.suffix.lower() == ".md":
                    if target_path not in headings_by_path:
                        headings_by_path[target_path] = {
                            slug for _, _, slug in _markdown_headings(target_path.read_text())
                        }
                    if fragment not in headings_by_path[target_path]:
                        issues.append(
                            f"{_markdown_path_for(source_path)}:{lineno} has a missing heading fragment: {href}"
                        )
        assert not issues, "\n".join(issues)

    def test_full_tables_of_contents_cover_reader_h2_sections(self):
        issues = []
        for source_path in _markdown_validation_paths():
            text = source_path.read_text()
            clean = _markdown_without_fenced_code(text)
            toc_match = re.search(r"^## (?:Table of Contents|Contents)\s*$", clean, re.M)
            if not toc_match:
                continue
            next_h2 = re.search(r"^## (?!Table of Contents$|Contents$).+$", clean[toc_match.end():], re.M)
            toc_end = toc_match.end() + next_h2.start() if next_h2 else len(clean)
            toc_body = clean[toc_match.end():toc_end]
            toc_fragments = {
                unquote(href[1:])
                for _, href in _markdown_link_targets(toc_body)
                if href.startswith("#")
            }
            missing = [
                (title, slug)
                for level, title, slug in _markdown_headings(clean)
                if level == 2
                and title not in {"Table of Contents", "Contents"}
                and slug not in toc_fragments
            ]
            if missing:
                issues.append(
                    f"{_markdown_path_for(source_path)} is missing TOC entries:\n"
                    + "\n".join(f"  {title} (#{slug})" for title, slug in missing)
                )
        assert not issues, "\n\n".join(issues)


class TestUiCaptureSceneGuide:
    def test_desktop_scene_slugs_and_order_match(self):
        assert _documented_capture_slugs("Desktop pack") == _capture_source_slugs(_UI_CAPTURE_DESKTOP)

    def test_mobile_scene_slugs_and_order_match(self):
        assert _documented_capture_slugs("Mobile pack") == _capture_source_slugs(_UI_CAPTURE_MOBILE)


class TestSupportedRuntimeDocumentation:
    def test_canonical_table_matches_executable_contracts(self):
        rows = _supported_runtime_rows()

        compose_match = re.search(r"^\s*platform:\s*([^\s#]+)", _PRODUCTION_COMPOSE.read_text(), re.M)
        assert compose_match is None, (
            "deploy/compose.yaml must let the verified release index select the native platform"
        )
        assert "AMD64" in rows["Production architecture"]
        assert "ARM64" in rows["Production architecture"]

        compose_versions = set(re.findall(
            r"Docker Compose ([0-9]+(?:\.[0-9]+)+) or newer is required",
            _PRODUCTION_SETUP.read_text(),
        ))
        assert len(compose_versions) == 1, "deploy/setup.sh.in must enforce one Compose minimum"
        compose_version = next(iter(compose_versions))
        assert f"Docker Compose {compose_version} or newer" in rows["Container orchestration"]

        ci_text = _GITLAB_CI.read_text()
        platform_mode = re.search(
            r'^\s*RELEASE_PLATFORM_MODE:\s*"([^"]+)"\s*$', ci_text, re.M
        )
        assert platform_mode and platform_mode.group(1) == "dual"
        assert "supported" in rows["Native ARM64"].lower()
        gate_rows = {
            "SELinux-enforcing Docker": "RELEASE_SELINUX_COMPATIBILITY_ENABLED",
            "Rootless Podman": "RELEASE_ROOTLESS_PODMAN_COMPATIBILITY_ENABLED",
        }
        for row_name, variable in gate_rows.items():
            match = re.search(rf"^\s*{variable}:\s*\"([01])\"\s*$", ci_text, re.M)
            assert match, f".gitlab-ci.yml must declare {variable}"
            if match.group(1) == "0":
                assert "compatibility lane" in rows[row_name].lower()
            else:
                assert "supported" in rows[row_name].lower()
