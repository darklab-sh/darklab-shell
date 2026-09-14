# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""WHOIS failures and registry metadata must not create investigation targets."""

import pytest

from core.output_signals import OutputSignalClassifier


def _entities(target, transcript):
    classifier = OutputSignalClassifier(f"whois {target}")
    entities = []
    for line in transcript.splitlines():
        detected = classifier.classify_line(line).get("entities", [])
        assert isinstance(detected, list)
        entities.extend(detected)
    return entities


@pytest.mark.parametrize("target,response", [
    ("example.com", "\n\n"),
    ("127.0.0.1", "inetnum: 127.0.0.0 - 127.255.255.255"),
    ("example.invalid", "Domain Name: example.invalid"),
    ("AS13335", "origin: AS13335"),
    ("example.com", 'No match for domain "EXAMPLE.COM".'),
    ("example.com", "No entries found for example.com"),
    ("example.com", "% ERROR: query rate limit exceeded for example.com"),
    ("example.com", "WHOIS lookup for example.com failed: connection timed out"),
    ("example.com", "Domain Name: No match for example.com"),
    ("example.com", "Domain Name: unrelated.com"),
    ("example.com", "Registrar WHOIS Server: whois.example.com\nName Server: ns.example.com"),
    ("example.com", "Domain name:\n\nNo match for example.com\nexample.com"),
    ("164.111.15.52", "% No entries found for 164.111.15.52"),
    ("164.111.15.52", "NetRange: query limit exceeded"),
    ("164.111.15.52", "NetRange: 193.0.0.0 - 193.0.7.255"),
    ("164.111.15.52", "CIDR: 193.0.0.0/21"),
    ("164.111.15.52", "CIDR: 2001:4860::/32"),
    ("164.111.15.52", "inetnum: 164.111.255.255 - 164.111.0.0"),
    ("164.111.15.52", "inetnum: 164.111.0.0 - 2001:4860::"),
    ("164.111.15.52", "Ref: https://rdap.arin.net/registry/ip/164.111.15.52"),
])
def test_failed_or_unrelated_whois_responses_emit_no_entities(target, response):
    assert _entities(target, response) == []


@pytest.mark.parametrize("target,record", [
    ("example.com", "Domain Name: EXAMPLE.COM"),
    ("example.com.", "domain: example.com."),
    ("example.co.uk", "Domain name:\n\n        example.co.uk"),
    ("example.jp", "[Domain Name] EXAMPLE.JP"),
    ("164.111.15.52", "NetRange: 164.111.0.0 - 164.111.255.255"),
    ("164.111.15.52", "inetnum: 164.111.0.0 - 164.111.255.255"),
    ("164.111.15.52", "CIDR: 193.0.0.0/21, 164.111.0.0/16"),
    ("164.111.15.52", "route: 164.111.0.0/16"),
    ("164.111.15.52", "network:IP-Network:164.111.0.0/16"),
    ("2001:4860:4860::8888", "inet6num: 2001:4860::/32"),
    ("2001:4860:4860::8888", "route6: 2001:4860::/32"),
])
def test_whois_waits_for_a_matching_record_then_emits_target_once(target, record):
    transcript = f"% Registry terms at https://registry.example.com/\n\n{record}\n{record}\nName Server: ns.example.com"
    entities = _entities(target, transcript)
    assert len(entities) == 1
    assert entities[0]["canonical_value"] == target.rstrip(".").lower()
    assert entities[0]["source_line"] == 2 + record.count("\n")


def test_unrecognized_output_does_not_consume_a_later_registration_record():
    entities = _entities("example.com", "No match on first server\nDomain Name: EXAMPLE.COM\nRegistrar: example.net")
    assert len(entities) == 1
    assert entities[0]["canonical_value"] == "example.com"
    assert entities[0]["source_line"] == 1
