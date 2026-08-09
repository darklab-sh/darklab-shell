# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""App content loaders used by the command/content registry."""

from __future__ import annotations

import os
import logging
from typing import TypedDict
import yaml

import config as app_config
from services.commands.registry_assessment_workflows import historical_web_surface_workflow
from services.commands import registry_service_workflows
from services.commands.registry_subdomain_workflows import bounded_subdomain_assessment_workflow
from services.commands.registry_web_review_workflows import live_web_review_workflow
from services.workflows import catalog as workflow_catalog

log = logging.getLogger("shell")

class TourPayload(TypedDict):
    version: int
    chapters: list[dict[str, object]]


_TOUR_ALLOWED_REQUIRES = {"workspace_enabled", "interactive_pty_enabled"}
_TOUR_REQUIRED_STRING_FIELDS = ("id", "title", "summary")
_TOUR_OPTIONAL_STRING_FIELDS = ("sample", "illustration")


def _local_overlay_path(path: str) -> str:
    root, ext = os.path.splitext(path)
    return f"{root}.local{ext}"


def _load_yaml_list(path: str) -> list:
    try:
        with open(path) as f:
            loaded = yaml.safe_load(f) or []
    except FileNotFoundError:
        return []
    except yaml.YAMLError as exc:
        log.warning(
            "COMMAND_REGISTRY_CONTENT_YAML_LOAD_FAILED",
            extra={
                "path": path,
                "overlay": path.endswith(".local.yaml"),
                "error_type": type(exc).__name__,
                "error": str(exc)[:240],
            },
        )
        return []
    return loaded if isinstance(loaded, list) else []


def _load_yaml_list_with_local(path: str, *, local_path: str | None = None) -> list:
    return _load_yaml_list(path) + _load_yaml_list(local_path or _local_overlay_path(path))


def builtin_workflows() -> list[dict[str, object]]:
    return [{
            "title": "DNS Troubleshooting",
            "description": "Diagnose why a domain isn't resolving or returns unexpected results.",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "dig {{domain}} A", "note": "Does it resolve? Check the ANSWER section."},
                {"cmd": "dig {{domain}} NS", "note": "Which nameservers are authoritative?"},
                {"cmd": "dig @8.8.8.8 {{domain}} A", "note": "Does a public resolver see it differently?"},
                {"cmd": "dig {{domain}} +trace", "note": "Trace delegation step by step from the root."},
                {"cmd": "dig {{domain}} MX", "note": "Check mail exchanger records."},
            ],
        },
        {
            "title": "TLS / HTTPS Check",
            "description": "Verify a domain's certificate, chain, and TLS configuration.",
            "inputs": [
                {
                    "id": "host", "label": "Host", "type": "host", "required": True,
                    "placeholder": "example.com", "default": "ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "curl -Iv https://{{host}}", "note": "Check response headers and certificate details."},
                {"cmd": "openssl s_client -connect {{host}}:443",
                 "note": "Inspect the raw TLS handshake and certificate chain."},
                {"cmd": "testssl {{host}}", "note": "Run a full TLS audit including ciphers and known vulnerabilities."},
            ],
        },
        {
            "title": "HTTP Triage",
            "description": "Investigate what a web server is returning.",
            "inputs": [
                {
                    "id": "url", "label": "URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "curl -sIL {{url}}", "note": "Follow redirects and inspect the final response headers."},
                {"cmd": "curl -sv -o /dev/null {{url}}| head -60",
                 "note": "Verbose output with timing, TLS detail, and headers."},
                {"cmd": "wget -S --spider {{url}}", "note": "Spider check with full server response headers."},
            ],
        },
        {
            "title": "Quick Reachability Check",
            "description": "Confirm a host is up and identify which ports are open.",
            "inputs": [
                {
                    "id": "host", "label": "Host", "type": "host", "required": True,
                    "placeholder": "example.com", "default": "ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "ping -c 4 {{host}}", "note": "Is the host reachable? Check latency and packet loss."},
                {"cmd": "nc -zv {{host}} 443", "note": "Is HTTPS open and accepting connections?"},
                {"cmd": "nmap -F {{host}}", "note": "Fast scan of the 100 most common ports."},
            ],
        },
        {
            "title": "Email Server Check",
            "description": "Verify mail delivery configuration for a domain.",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "dig {{domain}} MX", "note": "Which mail servers handle email for this domain?"},
                {"cmd": "dig {{domain}} TXT", "note": "Check SPF, DKIM policy, and other TXT records."},
                {"cmd": "dig _dmarc.{{domain}} TXT",
                 "note": "Check the DMARC policy published for the domain."},
                {"cmd": "dig @8.8.8.8 {{domain}} MX",
                 "note": (
                     "Confirm a public resolver sees the same MX records. If you want to test "
                     "SMTP ports with nc, target one of the MX hosts returned above rather than "
                     "the apex domain."
                 )},
            ],
        },
        {
            "title": "Domain OSINT / Passive Recon",
            "description": "Gather ownership, delegation, and passive subdomain context before active probing.",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "whois {{domain}}", "note": "Review registration, registrar, and allocation context."},
                {"cmd": "dig {{domain}} NS", "note": "Identify authoritative nameservers for the domain."},
                {"cmd": "subfinder -d {{domain}} -silent", "note": "Find passively observed subdomains."},
                {"cmd": "dnsrecon -d {{domain}}", "note": "Enumerate common DNS records and transfer hints."},
            ],
        },
        {
            "title": "Subdomain Enumeration & Validation",
            "description": "Discover candidate subdomains, resolve them, and probe likely web services.",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                },
                {
                    "id": "url", "label": "Probe URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "subfinder -d {{domain}} -silent", "note": "Collect passive subdomain candidates."},
                {
                    "cmd": (
                        "dnsx -d {{domain}} "
                        "-w /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt -resp"
                    ),
                    "note": "Resolve common subdomains and keep the DNS response context.",
                },
                {
                    "cmd": "httpx -u {{url}} -title -status-code -tech-detect",
                    "note": "Probe HTTPS and collect status, title, and technology hints.",
                },
            ],
        },
        bounded_subdomain_assessment_workflow(),
        live_web_review_workflow(),
        {
            "title": "Subdomain HTTP Triage",
            "description": (
                "Write discovered subdomains to Files, probe them for live HTTP services, "
                "then save a compact HTTP summary for review."
            ),
            "feature_required": "workspace",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                    "help": "The root domain to enumerate and triage.",
                },
            ],
            "steps": [
                {
                    "cmd": "subfinder -d {{domain}} -silent -o subdomains.txt",
                    "note": "Discover subdomains and save one hostname per line to Files.",
                },
                {
                    "cmd": "httpx -l subdomains.txt -silent -o live-urls.txt",
                    "note": "Read the generated subdomain file and save live HTTP(S) URLs.",
                },
                {
                    "cmd": "httpx -l live-urls.txt -status-code -title -tech-detect -o http-summary.txt",
                    "note": "Read live URLs and save status, title, and technology hints.",
                },
            ],
        },
        historical_web_surface_workflow(),
        {
            "title": "Crawl And Scan",
            "description": (
                "Crawl a starting URL into Files, summarize discovered URLs, then run a focused "
                "high/critical nuclei pass against the crawl output."
            ),
            "feature_required": "workspace",
            "inputs": [
                {
                    "id": "url", "label": "URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://ip.darklab.sh",
                    "help": "The HTTP or HTTPS URL to crawl and scan.",
                },
            ],
            "steps": [
                {
                    "cmd": "katana -u {{url}} -d 1 -silent -o crawled-urls.txt",
                    "note": "Crawl one level from the seed URL and save discovered URLs.",
                },
                {
                    "cmd": "httpx -l crawled-urls.txt -status-code -title -o crawled-http.txt",
                    "note": "Read crawled URLs and save HTTP status/title context.",
                },
                {
                    "cmd": "nuclei -l crawled-urls.txt -severity high,critical -o nuclei-findings.txt",
                    "note": "Run focused high/critical templates against the crawl output.",
                },
            ],
        },
        {
            "title": "Web Directory Discovery",
            "description": "Look for common web paths and follow up on interesting responses.",
            "inputs": [
                {
                    "id": "url", "label": "URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://tor-stats.darklab.sh",
                },
            ],
            "steps": [
                {
                    "cmd": (
                        "ffuf -u {{url}}/FUZZ "
                        "-w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt"
                    ),
                    "note": "Fuzz common paths and watch for non-baseline status codes or sizes.",
                },
                {
                    "cmd": (
                        "gobuster dir -u {{url}} "
                        "-w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt"
                    ),
                    "note": "Run a second directory check with a different scanner.",
                },
                {"cmd": "curl -sIL {{url}}/admin",
                 "note": "Inspect redirects and headers for a candidate path."},
            ],
        },
        {
            "title": "SSL / TLS Deep Dive",
            "description": "Inspect certificates, protocol support, cipher exposure, and known TLS weaknesses.",
            "inputs": [
                {
                    "id": "host", "label": "Host", "type": "host", "required": True,
                    "placeholder": "example.com", "default": "ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "sslscan {{host}}", "note": "Enumerate protocols, ciphers, and certificate metadata."},
                {"cmd": "sslyze --certinfo {{host}}", "note": "Validate certificate chain details."},
                {
                    "cmd": "openssl s_client -connect {{host}}:443 -servername {{host}}",
                    "note": "Inspect the raw handshake and served certificate chain.",
                },
                {"cmd": "testssl {{host}}", "note": "Run the broader TLS configuration audit."},
            ],
        },
        {
            "title": "CDN / Edge Behavior Check",
            "description": "Compare DNS, ownership, redirects, headers, and WAF/CDN edge signals.",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                },
                {
                    "id": "url", "label": "Web URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "dig {{domain}} A", "note": "Check the current address records."},
                {"cmd": "whois {{domain}}", "note": "Review ownership and provider hints."},
                {"cmd": "curl -sIL {{url}}", "note": "Inspect redirects, cache headers, and edge headers."},
                {"cmd": "wafw00f https://{{domain}}", "note": "Look for WAF or CDN fingerprints."},
            ],
        },
        {
            "title": "API Recon",
            "description": "Triage API-style endpoints with headers, methods, JSON negotiation, and path fuzzing.",
            "inputs": [
                {
                    "id": "url", "label": "Base URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "curl -sI {{url}}/api", "note": "Check whether the API path responds and how."},
                {
                    "cmd": "curl -sX OPTIONS -I {{url}}/api",
                    "note": "Inspect allowed methods and CORS-style headers.",
                },
                {
                    "cmd": "curl -sH Accept:application/json {{url}}/api",
                    "note": "Ask for JSON explicitly and inspect the response shape.",
                },
                {
                    "cmd": (
                        "ffuf -u {{url}}/FUZZ "
                        "-w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt"
                    ),
                    "note": "Fuzz common API-adjacent paths and versions.",
                },
            ],
        },
        {
            "title": "Network Path Analysis",
            "description": "Diagnose reachability, route shape, latency, and packet-loss symptoms.",
            "inputs": [
                {
                    "id": "host", "label": "Host", "type": "host", "required": True,
                    "placeholder": "example.com", "default": "ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "ping -c 10 {{host}}", "note": "Measure basic reachability, latency, and packet loss."},
                {"cmd": "mtr {{host}}", "note": "Summarize path loss and latency in report mode."},
                {"cmd": "traceroute {{host}}", "note": "Capture a static routed path to the target."},
                {"cmd": "tcptraceroute {{host}} 443", "note": "Trace the TCP path toward HTTPS specifically."},
            ],
        },
        registry_service_workflows.fast_port_discovery_workflow(),
        registry_service_workflows.port_service_review_workflow(),
    ]


def workflow_tokens(value: str) -> set[str]:
    return workflow_catalog.workflow_tokens(value)


def render_workflow_text(value: str, inputs: dict[str, str]) -> str:
    return workflow_catalog.render_workflow_text(value, inputs)


def normalize_workflow_entry(entry):
    """Return a normalized workflow entry or None when the payload is invalid."""
    return workflow_catalog.normalize_workflow_entry(entry)


def load_workflows(path: str, *, local_path: str | None = None) -> list[dict[str, object]]:
    """Read workflows.yaml and return a list of workflow dicts."""
    return workflow_catalog.load_workflows(path, local_path=local_path)


def load_all_workflows(
    path: str, cfg=None, *, suggestion_enabled_for_features, local_path: str | None = None
) -> list[dict[str, object]]:
    """Return the built-in workflows followed by any custom workflow entries."""
    builtins = []
    for idx, entry in enumerate(builtin_workflows()):
        normalized = normalize_workflow_entry(entry)
        if normalized and suggestion_enabled_for_features(normalized, cfg):
            builtins.append(workflow_catalog.workflow_with_catalog_metadata(normalized, "builtin", idx))
    custom = [
        workflow_catalog.workflow_with_catalog_metadata(workflow, "config", idx)
        for idx, workflow in enumerate(load_workflows(path, local_path=local_path))
        if suggestion_enabled_for_features(workflow, cfg)
    ]
    return [*builtins, *custom]


def load_welcome(path: str, *, local_path: str | None = None) -> list[dict[str, object]]:
    """Read welcome.yaml and return startup blocks for the welcome typeout."""
    data = _load_yaml_list_with_local(path, local_path=local_path)
    return [
        {
            "cmd": str(item.get("cmd", "")).strip(),
            "out": str(item.get("out", "")).rstrip() if item.get("out") else "",
            "group": str(item.get("group", "")).strip().lower() if item.get("group") else "",
            "featured": bool(item.get("featured", False)),
        }
        for item in data
        if isinstance(item, dict) and item.get("cmd")
    ]


def _tour_config(cfg=None):
    return app_config.CFG if cfg is None else cfg


def _tour_error(message):
    return ValueError(f"Invalid tour.yaml: {message}")


def _read_tour_payload(path: str):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise _tour_error("top-level value must be a mapping")
    return loaded


def _tour_requires_values(raw, index):
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = raw
    else:
        raise _tour_error(f"chapter {index} requires must be a string or list of strings")
    normalized = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise _tour_error(f"chapter {index} requires must contain non-empty strings")
        key = value.strip()
        if key not in _TOUR_ALLOWED_REQUIRES:
            raise _tour_error(f"chapter {index} has unknown requires key {key!r}")
        normalized.append(key)
    return normalized


def _normalize_tour_chapter(raw, index):
    if not isinstance(raw, dict):
        raise _tour_error(f"chapter {index} must be a mapping")
    chapter = {}
    for field_name in _TOUR_REQUIRED_STRING_FIELDS:
        value = raw.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise _tour_error(f"chapter {index} missing required {field_name!r}")
        chapter[field_name] = value.strip()
    for field_name in _TOUR_OPTIONAL_STRING_FIELDS:
        value = raw.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise _tour_error(f"chapter {index} {field_name!r} must be a string")
        stripped = value.strip()
        if stripped:
            chapter[field_name] = stripped
    requires = _tour_requires_values(raw.get("requires"), index)
    if len(requires) == 1:
        chapter["requires"] = requires[0]
    elif len(requires) > 1:
        chapter["requires"] = requires
    return chapter


def _tour_chapter_requires(chapter):
    requires = chapter.get("requires")
    if not requires:
        return []
    if isinstance(requires, str):
        return [requires]
    return [str(value) for value in requires]


def _tour_chapter_enabled(chapter, cfg=None, mobile=False):
    if mobile and chapter.get("id") == "interactive_pty":
        return False
    active_cfg = _tour_config(cfg)
    return all(bool(active_cfg.get(key, False)) for key in _tour_chapter_requires(chapter))


def load_tour(path: str, cfg=None, *, mobile: bool = False) -> TourPayload:
    """Read tour.yaml and return the visible onboarding tour chapters."""
    payload = _read_tour_payload(path)
    if payload is None:
        return {"version": 0, "chapters": []}
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise _tour_error("version must be a positive integer")
    raw_chapters = payload.get("chapters")
    if not isinstance(raw_chapters, list):
        raise _tour_error("chapters must be a list")
    chapters = [
        _normalize_tour_chapter(item, index)
        for index, item in enumerate(raw_chapters, start=1)
    ]
    active_cfg = _tour_config(cfg)
    if not bool(active_cfg.get("tour_enabled", True)):
        return {"version": version, "chapters": []}
    return {
        "version": version,
        "chapters": [
            chapter for chapter in chapters
            if _tour_chapter_enabled(chapter, active_cfg, mobile=mobile)
        ],
    }


def load_ascii_art(path: str, *, local_path: str | None = None) -> str:
    """Read banner art as plain text, preferring a local overlay."""
    local_path = local_path or _local_overlay_path(path)
    if os.path.exists(local_path):
        with open(local_path) as f:
            return f.read().rstrip()
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        return f.read().rstrip()


def _hint_category_enabled(category, cfg=None):
    active_cfg = app_config.CFG if cfg is None else cfg
    normalized = str(category or "general").strip().lower()
    if normalized in ("", "general"):
        return True
    if normalized == "workspace":
        return bool(active_cfg.get("workspace_enabled", False))
    if normalized in {"interactive_pty", "pty"}:
        return bool(active_cfg.get("interactive_pty_enabled", False))
    return True


def load_scoped_hints(path: str, cfg=None, *, local_path: str | None = None) -> list[str]:
    hints = []
    seen = set()
    for candidate in (path, local_path or _local_overlay_path(path)):
        if not os.path.exists(candidate):
            continue
        category = "general"
        with open(candidate) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    category = line[1:-1].strip().lower() or "general"
                    continue
                if _hint_category_enabled(category, cfg) and line not in seen:
                    hints.append(line)
                    seen.add(line)
    return hints
