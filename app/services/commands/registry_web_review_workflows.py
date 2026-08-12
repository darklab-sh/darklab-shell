# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Built-in live web review workflow definitions."""

from __future__ import annotations


def live_web_review_workflow() -> dict[str, object]:
    """Return the maintained screenshot and parameter-inventory workflow."""
    return {
        "version": 2,
        "id": "live_web_review",
        "title": "Live Web Review",
        "description": (
            "Capture a verified screenshot for one live URL, then build a bounded "
            "parameter inventory without sending XSS payloads."
        ),
        "feature_required": "workspace",
        "inputs": [
            {
                "id": "url", "label": "Live URL", "type": "url", "required": True,
                "placeholder": "https://example.com/search?q=one",
                "default": "https://ip.darklab.sh",
                "help": "One approved HTTP or HTTPS URL that is ready for review.",
            },
        ],
        "steps": [
            {
                "id": "capture_screenshot",
                "cmd": (
                    "httpx -u {{url}} -status-code -title -tech-detect -json "
                    "-screenshot -srd live-web-screenshots -silent -threads 1 "
                    "-timeout 10 -retries 1"
                ),
                "note": (
                    "Save the verified screenshot in Files with its URL, status, title, "
                    "and technology metadata."
                ),
                "next": {"success": "inventory_parameters", "failure": "stop"},
            },
            {
                "id": "inventory_parameters",
                "cmd": (
                    "dalfox {{url}} --only-discovery --skip-mining-dict --format jsonl "
                    "--no-color --timeout 10 --scan-timeout 60 --rate-limit 5 "
                    "--workers 2 --max-concurrent-targets 1 --max-targets-per-host 1"
                ),
                "note": (
                    "Save the structured parameter inventory with discovery-only request, "
                    "worker, target, and time limits."
                ),
                "next": {"success": "complete", "failure": "stop"},
            },
        ],
    }
