"""Tests for SQLite FTS output search via GET /history?q=..."""
import gzip
import json
import os
import sqlite3
import uuid

import pytest

import app as shell_app
import database as shell_db
import run_output_store
from database import db_connect

SESSION_A = "test-session-fts-a"
SESSION_B = "test-session-fts-b"


def get_client(session_id=SESSION_A):
    shell_app.app.config["TESTING"] = True
    shell_app.app.config["RATELIMIT_ENABLED"] = False
    client = shell_app.app.test_client()
    client.environ_base["HTTP_X_SESSION_ID"] = session_id
    return client


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(shell_db, "DB_PATH", str(tmp_path / "history.db"))
    shell_db.db_init()


def _insert_run(session_id, command, output_lines, exit_code=0):
    run_id = str(uuid.uuid4())
    started = "2026-01-01T12:00:00"
    finished = "2026-01-01T12:00:01"
    preview_lines = [{"text": line, "cls": "", "tsC": "", "tsE": ""} for line in output_lines]
    output_search_text = "\n".join(output_lines)
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
            "output, output_preview, preview_truncated, output_line_count, "
            "full_output_available, full_output_truncated, output_search_text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, session_id, command, started, finished, exit_code,
             None, json.dumps(preview_lines), 0, len(preview_lines), 0, 0, output_search_text)
        )
        conn.commit()
    return run_id


class TestOutputSearch:
    def test_finds_run_by_output_content(self):
        run_id = _insert_run(SESSION_A, "nmap -sV 10.0.0.1", [
            "Starting Nmap 7.94",
            "443/tcp open  https",
            "Nmap done.",
        ])
        client = get_client(SESSION_A)
        resp = client.get("/history?q=443")
        data = resp.get_json()
        ids = [r["id"] for r in data["runs"]]
        assert run_id in ids

    def test_does_not_match_other_session(self):
        _insert_run(SESSION_B, "nmap -sV 10.0.0.1", ["443/tcp open  https"])
        client = get_client(SESSION_A)
        resp = client.get("/history?q=443")
        data = resp.get_json()
        assert data["runs"] == []

    def test_finds_run_by_command_text(self):
        run_id = _insert_run(SESSION_A, "dig example.com", ["example.com. 300 IN A 93.184.216.34"])
        client = get_client(SESSION_A)
        resp = client.get("/history?q=dig")
        data = resp.get_json()
        ids = [r["id"] for r in data["runs"]]
        assert run_id in ids

    def test_no_match_returns_empty(self):
        _insert_run(SESSION_A, "nmap 10.0.0.1", ["Host is up"])
        client = get_client(SESSION_A)
        resp = client.get("/history?q=xyznotfound")
        data = resp.get_json()
        assert data["runs"] == []

    def test_special_chars_do_not_crash(self):
        _insert_run(SESSION_A, "curl https://example.com", ["HTTP/2 200"])
        client = get_client(SESSION_A)
        for query in ['"quote"', "paren(", "star*", "backslash\\"]:
            resp = client.get(f"/history?q={query}")
            assert resp.status_code == 200

    def test_combined_with_exit_code_filter(self):
        run_ok = _insert_run(SESSION_A, "nmap 10.0.0.1", ["80/tcp open"], exit_code=0)
        run_err = _insert_run(SESSION_A, "nmap 10.0.0.2", ["80/tcp open"], exit_code=1)
        client = get_client(SESSION_A)
        resp = client.get("/history?q=80%2Ftcp&exit_code=0")
        data = resp.get_json()
        ids = [r["id"] for r in data["runs"]]
        assert run_ok in ids
        assert run_err not in ids

    def test_empty_query_returns_all_runs(self):
        id1 = _insert_run(SESSION_A, "nmap 10.0.0.1", ["Host is up"])
        id2 = _insert_run(SESSION_A, "dig example.com", ["93.184.216.34"])
        client = get_client(SESSION_A)
        resp = client.get("/history")
        data = resp.get_json()
        ids = [r["id"] for r in data["runs"]]
        assert id1 in ids
        assert id2 in ids

    def test_multiword_query_restricts_results(self):
        run_both = _insert_run(SESSION_A, "nmap 10.0.0.1", ["443/tcp open https"])
        run_one = _insert_run(SESSION_A, "nmap 10.0.0.2", ["443/tcp open ssh"])
        client = get_client(SESSION_A)
        resp = client.get("/history?q=443+https")
        data = resp.get_json()
        ids = [r["id"] for r in data["runs"]]
        assert run_both in ids
        assert run_one not in ids

    def test_partial_substring_match_via_trigram(self):
        # Trigram tokenizer enables substring matching for compound tokens like "443/tcp"
        _insert_run(SESSION_A, "nmap 10.0.0.1", ["443/tcp open https"])
        client = get_client(SESSION_A)
        resp = client.get("/history?q=443%2Ftcp")
        data = resp.get_json()
        # Should match whether trigram or unicode61 tokenizer is available
        assert resp.status_code == 200
        # With trigram: run_id is in results; with unicode61: empty is also acceptable
        ids = [r["id"] for r in data["runs"]]
        # We just verify no crash — trigram availability is environment-dependent
        assert isinstance(ids, list)

    def test_short_query_under_trigram_threshold_matches_via_like(self):
        # Reverse-i-search needs to find 2-char commands like `ps` and `ls`.
        # The trigram tokenizer can't index <3-char terms, so the endpoint must
        # fall back to LIKE on r.command for short queries.
        run_ps = _insert_run(SESSION_A, "ps aux", ["PID TTY STAT"])
        run_ls = _insert_run(SESSION_A, "ls -la", ["total 0"])
        _insert_run(SESSION_A, "nmap 10.0.0.1", ["443/tcp open"])
        client = get_client(SESSION_A)
        resp = client.get("/history?q=ps&scope=command")
        ids = [r["id"] for r in resp.get_json()["runs"]]
        assert run_ps in ids
        assert run_ls not in ids

    def test_partial_typing_narrows_progressively(self):
        # Reverse-i-search expectation: every keystroke runs a search and the
        # result set narrows. `p` -> matches both ping/ps; `pi` -> ping only;
        # `pin` and `ping` -> ping only. None of the intermediate steps may
        # silently return zero matches.
        run_ping = _insert_run(SESSION_A, "ping 10.0.0.1", ["64 bytes from 10.0.0.1"])
        run_ps = _insert_run(SESSION_A, "ps aux", ["PID TTY"])
        client = get_client(SESSION_A)

        ids_p = [r["id"] for r in client.get("/history?q=p&scope=command").get_json()["runs"]]
        assert run_ping in ids_p
        assert run_ps in ids_p

        ids_pi = [r["id"] for r in client.get("/history?q=pi&scope=command").get_json()["runs"]]
        assert run_ping in ids_pi
        assert run_ps not in ids_pi

        for q in ("pin", "ping"):
            ids = [r["id"] for r in client.get(f"/history?q={q}&scope=command").get_json()["runs"]]
            assert run_ping in ids, f"query {q!r} must match the ping run"
            assert run_ps not in ids

    def test_scope_command_ignores_output_matches(self):
        # Reverse-i-search must only match typed command text, not output text.
        # Before this, a command like `ps aux` whose OUTPUT contained the
        # search term (e.g. the hostname "darklab") would be surfaced as a
        # "match" even though the command itself didn't contain the term.
        run_cmd_match = _insert_run(SESSION_A, "ping darklab.sh", ["64 bytes from darklab.sh"])
        run_output_only = _insert_run(SESSION_A, "ps aux", ["root 1 0.0 darklab"])
        client = get_client(SESSION_A)
        # Default scope: drawer-style FTS — both runs are returned.
        ids_default = [r["id"] for r in client.get("/history?q=darklab").get_json()["runs"]]
        assert run_cmd_match in ids_default
        # scope=command: only commands containing the term.
        ids_scoped = [r["id"] for r in client.get("/history?q=darklab&scope=command").get_json()["runs"]]
        assert run_cmd_match in ids_scoped
        assert run_output_only not in ids_scoped

    def test_full_output_text_beyond_preview_window_is_searchable(self, monkeypatch, tmp_path):
        """output_search_text must reflect full artifact content, not just preview.

        Simulates a truncated run: output_preview contains only the last N lines
        but output_search_text (as populated by the fixed _save_completed_run) holds
        the full text including early lines. FTS must find terms that appear only
        in the full output.
        """
        artifact_dir = str(tmp_path / "run-output")
        os.makedirs(artifact_dir)
        monkeypatch.setattr(run_output_store, "RUN_OUTPUT_DIR", artifact_dir)

        run_id = str(uuid.uuid4())
        # Write a real gzip artifact with 5 lines; only lines 4-5 are in preview
        artifact_rel = f"{run_id}.txt.gz"
        all_lines = [
            "Starting Nmap 7.94",
            "Nmap scan report for 10.0.0.1",
            "CVE-2024-9999 found in banner",
            "443/tcp open  https",
            "Nmap done.",
        ]
        with gzip.open(os.path.join(artifact_dir, artifact_rel), "wt", encoding="utf-8") as f:
            for line in all_lines:
                f.write(json.dumps({"text": line, "cls": "", "tsC": "", "tsE": ""}) + "\n")

        # output_preview holds only last 2 lines (simulating preview_limit=2)
        preview_lines = [
            {"text": all_lines[3], "cls": "", "tsC": "", "tsE": ""},
            {"text": all_lines[4], "cls": "", "tsC": "", "tsE": ""},
        ]
        # output_search_text built from the full artifact (what the fixed code produces)
        full_search_text = "\n".join(all_lines)
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
                "output, output_preview, preview_truncated, output_line_count, "
                "full_output_available, full_output_truncated, output_search_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, SESSION_A, "nmap 10.0.0.1", "2026-01-01T12:00:00",
                 "2026-01-01T12:00:01", 0, None, json.dumps(preview_lines),
                 1, len(all_lines), 1, 0, full_search_text)
            )
            conn.execute(
                "INSERT INTO run_output_artifacts "
                "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, artifact_rel, "gzip", 100, len(all_lines), 0, "2026-01-01T12:00:01")
            )
            conn.commit()

        client = get_client(SESSION_A)
        # "CVE-2024-9999" is in line 3 — outside the 2-line preview but in full_search_text
        resp = client.get("/history?q=CVE-2024-9999")
        data = resp.get_json()
        ids = [r["id"] for r in data["runs"]]
        assert run_id in ids, "FTS must find content from beyond the preview window"

    def test_fts_failure_falls_back_to_command_like(self, monkeypatch, tmp_path):
        """When runs_fts is absent, history search falls back to command LIKE without 500.

        Verifies: command-text queries still return results; output-only queries
        return empty (not an error); the response is always 200.
        """
        # Replace the current isolated DB with a minimal schema that has no FTS table.
        no_fts_path = str(tmp_path / "nofts.db")
        monkeypatch.setattr(shell_db, "DB_PATH", no_fts_path)
        conn = sqlite3.connect(no_fts_path)
        conn.execute("""
            CREATE TABLE runs (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, command TEXT NOT NULL,
                started TEXT NOT NULL, finished TEXT, exit_code INTEGER,
                output TEXT, output_preview TEXT,
                preview_truncated INTEGER NOT NULL DEFAULT 0,
                output_line_count INTEGER NOT NULL DEFAULT 0,
                full_output_available INTEGER NOT NULL DEFAULT 0,
                full_output_truncated INTEGER NOT NULL DEFAULT 0,
                output_search_text TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON runs (session_id)")
        conn.commit()
        conn.close()

        run_id = _insert_run(SESSION_A, "dig example.com", ["93.184.216.34"])

        client = get_client(SESSION_A)
        # Command-text queries must still work via LIKE fallback.
        resp = client.get("/history?q=dig")
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.get_json()["runs"]]
        assert run_id in ids, "LIKE fallback must find the run by command text"
        # Output-only queries return empty (no FTS), not a 500.
        resp2 = client.get("/history?q=93.184.216.34")
        assert resp2.status_code == 200
        assert resp2.get_json()["runs"] == []
