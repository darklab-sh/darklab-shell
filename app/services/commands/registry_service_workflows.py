# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Built-in port and service workflow definitions."""

from __future__ import annotations


def port_service_review_workflow() -> dict[str, object]:
    """Return the maintained single-port service review workflow."""
    return {
        "version": 2,
        "id": "port_service_review",
        "title": "Port Service Review",
        "description": (
            "Fingerprint one approved TCP port, then run Nmap's reviewed default "
            "service scripts with fixed retry and time limits."
        ),
        "inputs": [
            {
                "id": "host", "label": "Host", "type": "host", "required": True,
                "placeholder": "example.com", "default": "ip.darklab.sh",
                "help": "The approved hostname or IP address that owns the port.",
            },
            {
                "id": "port", "label": "TCP port", "type": "port", "required": True,
                "placeholder": "443", "default": "443",
                "help": "One known or suspected open TCP port to review.",
            },
        ],
        "steps": [
            {
                "id": "fingerprint_service",
                "cmd": (
                    "nmap -sT -sV -Pn -p {{port}} --max-retries 2 "
                    "--host-timeout 2m {{host}}"
                ),
                "note": "Identify the service and version on exactly the selected TCP port.",
                "next": {"success": "enumerate_service", "failure": "stop"},
            },
            {
                "id": "enumerate_service",
                "cmd": (
                    "nmap -sT -sV -Pn -p {{port}} --script default "
                    "--script-timeout 30s --max-retries 1 --host-timeout 3m {{host}}"
                ),
                "note": (
                    "Run only Nmap's reviewed default scripts that apply to the detected "
                    "service; use Assessment recommendations for deeper protocol profiles."
                ),
                "next": {"success": "complete", "failure": "stop"},
            },
        ],
    }


def fast_port_discovery_workflow() -> dict[str, object]:
    """Return the legacy multi-tool fast port discovery workflow."""
    return {
        "title": "Fast Port Discovery to Service Fingerprint",
        "description": "Sweep for exposed ports quickly, then fingerprint and validate important services.",
        "inputs": [
            {
                "id": "host", "label": "Host", "type": "host", "required": True,
                "placeholder": "example.com", "default": "ip.darklab.sh",
            },
        ],
        "steps": [
            {
                "cmd": "rustscan -a {{host}} --range 1-1000",
                "note": "Quickly sweep the first thousand ports.",
            },
            {"cmd": "naabu -host {{host}} -silent", "note": "Run a second fast TCP discovery pass."},
            {
                "cmd": "nmap -sV {{host}}",
                "note": "Fingerprint services once you know exposure is present.",
            },
            {"cmd": "nc -zv {{host}} 80", "note": "Validate a specific expected port manually."},
        ],
    }
