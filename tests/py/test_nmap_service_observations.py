# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from services.assessments import nmap_service_observations
from services.assessments.nmap_script_evidence_catalog import (
    INFORMATIONAL_SCRIPT_EVIDENCE,
)
from services.assessments.nmap_service_observations import (
    NMAP_SERVICE_XML_PARSER_VERSION,
    parse_nmap_xml_service_observations,
)


def _document(ports: str, *, finished: str = "1786233600") -> str:
    return f"""<?xml version="1.0"?>
<nmaprun version="7.95">
  <host>
    <address addr="192.0.2.10" addrtype="ipv4"/>
    <ports>{ports}</ports>
  </host>
  <runstats><finished time="{finished}"/></runstats>
</nmaprun>
"""


def _port(scripts: str, *, state: str = "open", port: int = 445) -> str:
    return f"""
<port protocol="tcp" portid="{port}">
  <state state="{state}"/>
  <service name="microsoft-ds"/>
  {scripts}
</port>
"""


def test_structured_nse_service_facts_keep_exact_provenance_and_informational_state():
    payload = _document(_port("""
      <script id="smb2-security-mode" output="private free-form output">
        <table key="account_used"><elem key="name">guest</elem></table>
        <elem key="message_signing">disabled</elem>
      </script>
      <script id="smb-protocols" output="dialects">
        <table key="dialects"><elem key="preferred">3.1.1</elem></table>
      </script>
    """))

    parsed = parse_nmap_xml_service_observations(payload, source_run_id="run-1")

    assert parsed["source"] == "nmap_xml_service_evidence"
    assert parsed["source_run_id"] == "run-1"
    assert parsed["tool_version"] == "7.95"
    assert parsed["parser_version"] == NMAP_SERVICE_XML_PARSER_VERSION
    assert parsed["observed_at"] == "2026-08-09T00:00:00+00:00"
    assert parsed["truncated"] is False
    assert [item["script_id"] for item in parsed["observations"]] == [
        "smb2-security-mode", "smb-protocols",
    ]
    signing = parsed["observations"][0]
    assert signing["target"] == "192.0.2.10:445/tcp"
    assert signing["service"] == "microsoft-ds"
    assert signing["evidence_kind"] == "smb_signing"
    assert signing["classification"] == "informational"
    assert signing["fields"] == [
        {"path": ["account_used", "name"], "value": "guest"},
        {"path": ["message_signing"], "value": "disabled"},
    ]
    assert "private free-form output" not in str(parsed)


def test_parser_abstains_from_vulnerability_unknown_output_only_and_closed_scripts():
    payload = _document(
        _port("""
          <script id="ssl-heartbleed" output="VULNERABLE">
            <elem key="state">VULNERABLE</elem>
          </script>
          <script id="operator-script" output="custom">
            <elem key="value">custom</elem>
          </script>
          <script id="ssh-hostkey" output="output-only evidence"/>
        """, port=443)
        + _port("""
          <script id="smtp-commands" output="commands">
            <elem key="commands">STARTTLS</elem>
          </script>
        """, state="closed", port=25)
    )

    parsed = parse_nmap_xml_service_observations(payload, source_run_id="run-2")

    assert parsed["observations"] == []
    assert parsed["truncated"] is False


def test_structured_fields_are_bounded_without_dropping_the_accepted_observation(monkeypatch):
    monkeypatch.setattr(nmap_service_observations, "NMAP_SERVICE_XML_MAX_FIELDS", 2)
    payload = _document(_port("""
      <script id="ssh2-enum-algos" output="algorithms">
        <table key="kex_algorithms">
          <elem>curve25519-sha256</elem>
          <elem>diffie-hellman-group14-sha256</elem>
          <elem>diffie-hellman-group16-sha512</elem>
        </table>
      </script>
    """, port=22))

    parsed = parse_nmap_xml_service_observations(payload, source_run_id="run-3")

    assert parsed["truncated"] is True
    assert parsed["observations"][0]["fields_truncated"] is True
    assert parsed["observations"][0]["fields"] == [
        {"path": ["kex_algorithms", "0"], "value": "curve25519-sha256"},
        {"path": ["kex_algorithms", "1"], "value": "diffie-hellman-group14-sha256"},
    ]


def test_observation_and_value_limits_report_truncation(monkeypatch):
    monkeypatch.setattr(nmap_service_observations, "NMAP_SERVICE_XML_MAX_OBSERVATIONS", 1)
    monkeypatch.setattr(nmap_service_observations, "NMAP_SERVICE_XML_MAX_VALUE_LENGTH", 8)
    payload = _document(_port("""
      <script id="smb2-security-mode" output="signing">
        <elem key="message_signing">disabled-and-required</elem>
        <elem key="account">guest</elem>
      </script>
      <script id="smb-protocols" output="dialects">
        <elem key="dialect">3.1.1</elem>
      </script>
    """))

    parsed = parse_nmap_xml_service_observations(payload, source_run_id="run-limits")

    assert parsed["truncated"] is True
    assert len(parsed["observations"]) == 1
    assert parsed["observations"][0]["fields_truncated"] is True
    assert parsed["observations"][0]["fields"] == [
        {"path": ["message_signing"], "value": "disabled"},
        {"path": ["account"], "value": "guest"},
    ]


def test_invalid_or_unsafe_xml_and_unqualified_timestamps_fail_closed():
    unsafe = """<!DOCTYPE nmaprun [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<nmaprun version="7.95"><host>&xxe;</host></nmaprun>"""
    missing_zone = _document(_port("""
      <script id="smtp-commands" output="commands">
        <elem key="commands">STARTTLS</elem>
      </script>
    """, port=25), finished="")

    assert parse_nmap_xml_service_observations(unsafe, source_run_id="run-4")["observations"] == []
    assert parse_nmap_xml_service_observations(
        missing_zone,
        source_run_id="run-4",
        observed_at="2026-08-09T00:00:00",
    )["observations"] == []
    assert parse_nmap_xml_service_observations("", source_run_id="run-4")["source_run_id"] == ""


def test_evidence_catalog_covers_only_exact_informational_profile_scripts():
    assert INFORMATIONAL_SCRIPT_EVIDENCE["nfs-showmount"] == "nfs_exports"
    assert INFORMATIONAL_SCRIPT_EVIDENCE["ssl-enum-ciphers"] == "tls_ciphers"
    assert "ssl-heartbleed" not in INFORMATIONAL_SCRIPT_EVIDENCE
    assert "auth" not in INFORMATIONAL_SCRIPT_EVIDENCE
