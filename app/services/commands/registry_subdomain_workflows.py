# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Built-in subdomain assessment workflow definitions."""

from __future__ import annotations


def bounded_subdomain_assessment_workflow() -> dict[str, object]:
    """Return the maintained bounded subdomain assessment workflow."""
    continued_fanout = {
        "collection": "subdomains",
        "failure_mode": "continue",
        "retries": 1,
        "max_parallel": 4,
        "max_failures": 16,
    }
    return {
        "version": 3,
        "id": "bounded_subdomain_assessment",
        "title": "Bounded Subdomain Assessment",
        "description": (
            "Discover up to 16 subdomains, then resolve, probe, shallow-crawl, and run "
            "the safe Nuclei exposure profile against each candidate with controlled fan-out."
        ),
        "inputs": [
            {
                "id": "domain", "label": "Domain", "type": "domain", "required": True,
                "placeholder": "example.com", "default": "darklab.sh",
                "help": "The approved root domain to discover and assess.",
            },
        ],
        "steps": [
            {
                "id": "discover_subdomains",
                "cmd": "subfinder -d {{domain}} -silent",
                "note": "Collect up to 16 unique subdomains without creating an intermediate file.",
                "captures": [
                    {
                        "name": "subdomains",
                        "source": "entity",
                        "entity_type": "domain",
                        "kind": "collection",
                        "item_limit": 16,
                        "required": True,
                    },
                ],
                "next": {"success": "resolve_subdomains", "failure": "stop"},
            },
            {
                "id": "resolve_subdomains",
                "cmd": "dnsx -d {{subdomains}} -a -resp -silent",
                "note": "Resolve each captured subdomain and retain its DNS response as a normal run.",
                "for_each": dict(continued_fanout),
                "next": {"success": "probe_subdomains", "failure": "stop"},
            },
            {
                "id": "probe_subdomains",
                "cmd": (
                    "httpx -u {{subdomains}} -status-code -title -tech-detect -silent "
                    "-threads 1 -timeout 10 -retries 1"
                ),
                "note": "Probe each candidate with one HTTPx worker and save its web metadata.",
                "for_each": dict(continued_fanout),
                "next": {"success": "crawl_subdomains", "failure": "stop"},
            },
            {
                "id": "crawl_subdomains",
                "cmd": (
                    "katana -u https://{{subdomains}} -d 1 -ct 5 -c 2 -p 2 -rl 10 -silent "
                    "| head -n 64"
                ),
                "note": "Shallow-crawl each HTTPS candidate with bounded time, rate, and output.",
                "for_each": {
                    **continued_fanout,
                    "retries": 0,
                    "max_parallel": 2,
                },
                "next": {"success": "scan_subdomains", "failure": "stop"},
            },
            {
                "id": "scan_subdomains",
                "cmd": (
                    "nuclei -u https://{{subdomains}} -severity high,critical "
                    "-tags exposure,misconfig,tech,ssl -type http,tcp,ssl "
                    "-exclude-tags auth,brute,dos,exploit,fuzz,intrusive,oast,dast "
                    "-exclude-type code,javascript,file,workflow,whois,headless "
                    "-no-interactsh -disable-redirects -disable-update-check "
                    "-rl 10 -c 2 -timeout 10 -retries 1 -silent"
                ),
                "note": (
                    "Run the maintained safe exposure profile with callbacks, redirects, "
                    "updates, intrusive tags, and local-code protocols disabled."
                ),
                "for_each": {
                    **continued_fanout,
                    "retries": 0,
                    "max_parallel": 2,
                },
                "next": {"success": "complete", "failure": "stop"},
            },
        ],
    }
