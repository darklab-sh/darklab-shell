# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Declared external report formats accepted by Atlas import."""

SUPPORTED_FORMATS = frozenset({
    "burp_xml",
    "cyclonedx_json",
    "generic_csv",
    "generic_jsonl",
    "greenbone_xml",
    "nessus_xml",
    "nuclei_jsonl",
    "sarif_json",
    "zap_json",
    "zap_xml",
})


__all__ = ["SUPPORTED_FORMATS"]
