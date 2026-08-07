# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Built-in assessment workflow definitions."""

from __future__ import annotations


def historical_web_surface_workflow() -> dict[str, object]:
    """Return the guarded passive-to-active historical web workflow."""
    return {
        "version": 2,
        "id": "historical_web_surface_triage",
        "title": "Historical Web Surface Triage",
        "description": (
            "Collect archived URLs passively, scope and normalize them, confirm live web targets, "
            "then crawl and summarize only the approved live surface."
        ),
        "feature_required": "workspace",
        "inputs": [
            {
                "id": "domain", "label": "Domain", "type": "domain", "required": True,
                "placeholder": "example.com", "default": "darklab.sh",
                "help": "The approved root domain; matching subdomains remain in scope.",
            },
        ],
        "steps": [
            {
                "id": "collect_archives",
                "cmd": (
                    "gau --subs --threads 2 --timeout 10 {{domain}} "
                    "| head -n 1024 > historical-urls.txt"
                ),
                "note": "Collect passive archive results into a bounded Files entry without probing them.",
                "next": {"success": "scope_archives", "failure": "stop"},
            },
            {
                "id": "scope_archives",
                "cmd": "urlscope {{domain}} historical-urls.txt historical-scoped-urls.txt",
                "note": "Normalize, deduplicate, and keep only the approved domain and its subdomains.",
                "next": {"success": "confirm_live", "failure": "stop"},
            },
            {
                "id": "confirm_live",
                "cmd": (
                    "httpx -l historical-scoped-urls.txt -silent -threads 10 -timeout 10 -retries 1 "
                    "| head -n 256 > live-urls.txt"
                ),
                "note": "Probe only scoped archive URLs and keep the live HTTP(S) results.",
                "next": {"success": "scope_live", "failure": "stop"},
            },
            {
                "id": "scope_live",
                "cmd": "urlscope {{domain}} live-urls.txt live-scoped-urls.txt",
                "note": "Recheck scope after live probing before any crawler receives targets.",
                "next": {"success": "crawl_live", "failure": "stop"},
            },
            {
                "id": "crawl_live",
                "cmd": (
                    "katana -list live-scoped-urls.txt -d 1 -ct 5 -timeout 10 -silent "
                    "| head -n 1024 > crawled-urls.txt"
                ),
                "note": "Crawl one level from confirmed live, scoped URLs and keep bounded output.",
                "next": {"success": "scope_crawl", "failure": "stop"},
            },
            {
                "id": "scope_crawl",
                "cmd": "urlscope {{domain}} crawled-urls.txt crawled-scoped-urls.txt",
                "note": "Normalize and re-scope crawler discoveries before the final probe.",
                "next": {"success": "summarize_surface", "failure": "stop"},
            },
            {
                "id": "summarize_surface",
                "cmd": (
                    "httpx -l crawled-scoped-urls.txt -status-code -title -tech-detect "
                    "-threads 10 -timeout 10 -retries 1 | head -n 256 > http-summary.txt"
                ),
                "note": "Save a compact status, title, and technology summary for the reviewed surface.",
                "next": {"success": "complete", "failure": "stop"},
            },
        ],
    }
