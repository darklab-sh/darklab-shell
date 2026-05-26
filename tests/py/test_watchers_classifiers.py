import json
import sqlite3

from services.watchers import diff as watcher_diff
from services.watchers.classifiers import registered_classifiers


def _run(run_id: str, command: str, lines: list[str], *, session_id: str = "tok_watchers"):
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


def test_ports_classifier_reports_added_changed_and_removed_ports():
    diff = watcher_diff.diff_runs(
        _run("run_base", "nmap -sV darklab.sh", ["22/tcp open ssh", "80/tcp open http"]),
        _run("run_current", "nmap -sV darklab.sh", ["22/tcp open openssh", "443/tcp open https"]),
    )

    assert diff.kind == "signal"
    assert diff.summary["classifier"] == "ports"
    assert diff.summary["added_port_count"] == 1
    assert diff.summary["removed_port_count"] == 1
    assert diff.summary["changed_port_count"] == 1
    assert diff.summary["changed_ports"][0]["key"] == "22/tcp"


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
    names = [classifier.name for classifier in registered_classifiers()]

    assert names[:4] == ["findings", "ports", "hosts", "tls"]
    assert names[-1] == "textual"
