import json
import sqlite3
from collections.abc import Sequence
from typing import Any

from services.watchers import diff as watcher_diff
from services.diff.classifiers import registered_classifiers as registered_diff_classifiers
from services.watchers.classifiers import registered_classifiers as registered_watcher_classifiers


def _run(run_id: str, command: str, lines: Sequence[str | dict[str, Any]], *, session_id: str = "tok_watchers"):
    return {
        "id": run_id,
        "session_id": session_id,
        "command": command,
        "output_preview": json.dumps(lines),
        "preview_truncated": False,
        "full_output_available": False,
        "full_output_truncated": False,
    }


def _findings_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE findings (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            signature_hash TEXT NOT NULL DEFAULT '',
            fingerprint TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            raw_line TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE findings_occurrences (
            finding_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            line_number INTEGER NOT NULL DEFAULT 0
        )
    """)
    return conn


def _insert_finding(conn, finding_id: str, run_id: str, signature_hash: str, title: str):
    conn.execute(
        "INSERT OR IGNORE INTO findings "
        "(id, session_id, signature_hash, fingerprint, title, raw_line, severity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (finding_id, "tok_watchers", signature_hash, f"fp-{finding_id}", title, title, "medium"),
    )
    conn.execute(
        "INSERT INTO findings_occurrences (finding_id, run_id, line_number) VALUES (?, ?, ?)",
        (finding_id, run_id, 1),
    )


def test_findings_classifier_uses_structured_finding_fingerprints():
    conn = _findings_conn()
    _insert_finding(conn, "fnd_existing", "run_base", "sig-existing", "existing issue")
    _insert_finding(conn, "fnd_existing", "run_current", "sig-existing", "existing issue")
    _insert_finding(conn, "fnd_new", "run_current", "sig-new", "new issue")

    diff = watcher_diff.diff_runs(
        _run("run_base", "nuclei -u https://darklab.sh", ["existing issue"]),
        _run("run_current", "nuclei -u https://darklab.sh", ["existing issue", "new issue"]),
        conn=conn,
    )

    assert diff.kind == "signal"
    assert diff.summary["classifier"] == "findings"
    assert diff.summary["added_finding_count"] == 1
    assert diff.summary["added_findings"][0]["id"] == "fnd_new"


def test_textual_classifier_is_fallback_and_honors_suppress_removals():
    diff = watcher_diff.diff_runs(
        _run("run_base", "curl https://darklab.sh", ["alpha", "removed"]),
        _run("run_current", "curl https://darklab.sh", ["alpha"]),
        options={"suppress_removals": True},
    )

    assert diff.kind == "none"
    assert diff.summary["classifier"] == "textual"
    assert diff.summary["removed_line_count"] == 1
    assert diff.summary["suppressed_removed_line_count"] == 1

    ignored = watcher_diff.diff_runs(
        _run("run_base", "curl https://darklab.sh", ["alpha", "Date: Mon"]),
        _run("run_current", "curl https://darklab.sh", ["alpha", "Date: Tue"]),
        options={"ignore_line_patterns": ["Date:"]},
    )

    assert ignored.kind == "none"
    assert ignored.summary["ignored_line_pattern_count"] == 1
    assert ignored.summary["ignored_line_count"] == 2


def test_ports_classifier_reports_added_changed_and_removed_ports():
    from services.runs import comparison as run_comparison

    left_entries = [
        {"text": "Starting Nmap 7.95", "line_index": 0},
        {"text": "22/tcp open ssh OpenSSH 9.9", "line_index": 1},
        {"text": "Nmap scan report for 192.168.1.5", "line_index": 2},
        {"text": "80/tcp open http", "line_index": 3},
    ]
    right_entries = [
        {"text": "Starting Nmap 7.95", "line_index": 4},
        {"text": "22/tcp open ssh OpenSSH 10.0", "line_index": 5},
        {"text": "443/tcp open https", "line_index": 6},
        {"text": "Nmap done: 1 IP address (1 host up) scanned in 0.42 seconds", "line_index": 7},
    ]
    left_run = _run(
        "run_base",
        "nmap -sV 192.168.1.5",
        left_entries,
    )
    right_run = _run(
        "run_current",
        "nmap -sV 192.168.1.10",
        right_entries,
    )
    diff = watcher_diff.diff_runs(left_run, right_run)

    assert diff.kind == "signal"
    assert diff.summary["classifier"] == "ports"
    assert diff.summary["added_port_count"] == 1
    assert diff.summary["removed_port_count"] == 1
    assert diff.summary["changed_port_count"] == 1
    assert diff.summary["added_ports"][0]["line_index"] == 6
    assert diff.summary["changed_ports"][0]["key"] == "22/tcp"
    assert diff.summary["changed_ports"][0]["before"]["service"] == "ssh"
    assert diff.summary["changed_ports"][0]["after"]["service"] == "ssh"
    assert diff.summary["changed_ports"][0]["before"]["service_text"] == "ssh OpenSSH 9.9"
    assert diff.summary["changed_ports"][0]["after"]["service_text"] == "ssh OpenSSH 10.0"
    compare_changes = run_comparison.compare_derived_changes(
        left_run,
        right_run,
        left_entries,
        right_entries,
    )
    port_group = compare_changes["groups"][0]
    assert port_group["id"] == "nmap_ports"
    assert port_group["added_count"] == diff.summary["added_port_count"]
    assert port_group["removed_count"] == diff.summary["removed_port_count"]
    assert port_group["changed_count"] == diff.summary["changed_port_count"]
    assert port_group["target_ambiguous"] is True
    assert port_group["left_target"] == "192.168.1.5"
    assert port_group["right_target"] == "192.168.1.10"
    assert port_group["added"][0]["key"] == "443/tcp"
    assert port_group["added"][0]["compare_line_index"] == 2
    assert port_group["removed"][0]["key"] == "80/tcp"
    assert port_group["removed"][0]["compare_line_index"] == 3
    assert port_group["changed"][0]["before"]["compare_line_index"] == 1
    assert port_group["changed"][0]["after"]["compare_line_index"] == 1


def test_hosts_classifier_reports_added_hosts_for_subdomain_lists():
    diff = watcher_diff.diff_runs(
        _run("run_base", "subfinder -d darklab.sh", ["www.darklab.sh"]),
        _run("run_current", "subfinder -d darklab.sh", ["www.darklab.sh", "api.darklab.sh"]),
    )

    assert diff.kind == "signal"
    assert diff.summary["classifier"] == "hosts"
    assert diff.summary["added_host_count"] == 1
    assert diff.summary["added_hosts"][0]["host"] == "api.darklab.sh"


def test_tls_classifier_reports_certificate_field_changes():
    diff = watcher_diff.diff_runs(
        _run(
            "run_base",
            "openssl s_client -connect darklab.sh:443",
            ["subject=CN=darklab.sh", "issuer=CN=Old CA", "notAfter=Jan 1 00:00:00 2027 GMT"],
        ),
        _run(
            "run_current",
            "openssl s_client -connect darklab.sh:443",
            ["subject=CN=darklab.sh", "issuer=CN=New CA", "notAfter=Jan 1 00:00:00 2028 GMT"],
        ),
    )

    assert diff.kind == "signal"
    assert diff.summary["classifier"] == "tls"
    assert diff.summary["changed_tls_field_count"] == 2
    assert {item["field"] for item in diff.summary["changed_tls_fields"]} == {"issuer", "not_after"}


def test_classifier_registry_keeps_structured_classifiers_before_textual_fallback():
    names = [classifier.name for classifier in registered_diff_classifiers()]
    compatibility_names = [classifier.name for classifier in registered_watcher_classifiers()]

    assert names[:4] == ["findings", "ports", "hosts", "tls"]
    assert names[-1] == "textual"
    assert compatibility_names == names
