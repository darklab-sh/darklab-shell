"""
Higher-value route coverage focused on brokered /runs behaviour,
history isolation, and share JSON roundtrips.

These tests are intentionally closer to "real bug finding" than
the lighter smoke tests in test_routes.py.
"""

import gzip
import json
import json as json_module
import os
import time
import uuid
import unittest.mock as mock
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app as shell_app
import blueprints.run as run_routes
import database as shell_db
import workspace as shell_workspace
from config import PROJECT_README
from database import db_connect
from run_output_store import RUN_OUTPUT_DIR, ensure_run_output_dir

# These tests lean toward end-to-end backend behavior and intentionally exercise
# the real SQLite/artifact flow rather than heavy mocking.

def get_client(*, use_forwarded_for=True):
    shell_app.app.config["TESTING"] = True
    shell_app.app.config["RATELIMIT_ENABLED"] = False
    client = shell_app.app.test_client()
    if use_forwarded_for:
        token = uuid.uuid4().hex
        client.environ_base["HTTP_X_FORWARDED_FOR"] = (
            f"2001:db8:{token[0:4]}:{token[4:8]}:{token[8:12]}:{token[12:16]}:{token[16:20]}:{token[20:24]}"
        )
    return client


@pytest.fixture(autouse=True)
def isolated_history_db(monkeypatch, tmp_path):
    monkeypatch.setattr(shell_db, "DB_PATH", str(tmp_path / "history.db"))
    shell_db.db_init()


# ── Helpers ──────────────────────────────────────────────────────────────────

class _FakeStdout:
    def __init__(self, lines: Sequence[str]):
        self._lines: list[str] = list(lines)
        self.closed = False

    def readline(self) -> str:
        return self._lines.pop(0) if self._lines else ""

    def close(self) -> None:
        self.closed = True


class _FakeProc:
    def __init__(
        self,
        lines: Sequence[str] | None = None,
        pid: int = 4321,
        returncode: int | None = 0,
        wait_returncode: int | None = None,
    ):
        self.pid = pid
        self.returncode: int | None = returncode
        self._wait_returncode: int | None = returncode if wait_returncode is None else wait_returncode
        self.stdout: _FakeStdout | None = _FakeStdout(lines or [])
        self._poll_calls = 0
        self.wait_calls = 0

    def wait(self, timeout: float | None = None) -> int | None:
        self.wait_calls += 1
        self.returncode = self._wait_returncode
        return self.returncode

    def poll(self) -> int | None:
        # Behave like a still-running proc until stdout is exhausted
        self._poll_calls += 1
        if self.stdout and self.stdout._lines:
            return None
        return self.returncode


class _PassthroughWorkspaceFilter:
    def process_output_line(self, line: str) -> str:
        return line


class _BrokerRunResponse:
    def __init__(self, response):
        self._response = response
        self.status_code = response.status_code
        self.data = response.data

    def __getattr__(self, name):
        return getattr(self._response, name)

    def get_data(self, *args, **kwargs):
        body = self._response.get_data(*args, **kwargs)
        if not kwargs.get("as_text") and not (args and args[0] is True):
            return body
        normalized_events = []
        for event in _sse_events(str(body)):
            if event.get("type") not in {"output", "notice"}:
                continue
            if not isinstance(event.get("text"), str):
                continue
            normalized_event = dict(event)
            text = str(normalized_event["text"])
            normalized_event["text"] = text if text.endswith("\n") else f"{text}\n"
            normalized_events.append(json.dumps(normalized_event))
        if not normalized_events:
            return body
        return f"{body}\n" + "\n".join(normalized_events)


def _post_run(client, *, json=None, headers=None, **kwargs):
    """Drive command execution through the brokered /runs start + stream flow."""
    headers = dict(headers or {})
    headers.setdefault("X-Session-ID", "broker-test-session")
    with mock.patch("blueprints.run.broker_available", return_value=True):
        start_resp = client.post("/runs", json=json, headers=headers, **kwargs)
    if start_resp.status_code != 202:
        return start_resp
    data = json_module.loads(start_resp.data)
    stream_resp = client.get(data["stream"], headers=headers)
    for _ in range(10):
        if stream_resp.status_code != 404:
            return _BrokerRunResponse(stream_resp)
        time.sleep(0.01)
        stream_resp = client.get(data["stream"], headers=headers)
    return _BrokerRunResponse(stream_resp)


def _sse_events(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for chunk in body.split("\n\n"):
        data_lines: list[str] = []
        event_id = ""
        for line in chunk.splitlines():
            if line.startswith("id: "):
                event_id = line[4:].strip()
            elif line.startswith("data: "):
                data_lines.append(line[6:])
        if not data_lines:
            continue
        event = json.loads("\n".join(data_lines))
        if event_id and "event_id" not in event:
            event["event_id"] = event_id
        events.append(event)
    return events


# ── /runs streaming ───────────────────────────────────────────────────────────

class TestRunStreaming:
    @staticmethod
    def _local_dt_text(value: str) -> str:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _local_clock_text(value: str) -> str:
        return datetime.fromisoformat(value).astimezone().strftime("%H:%M:%S")

    def test_brokered_synthetic_run_publishes_events_and_persists_history(self):
        published = []
        with mock.patch("blueprints.run.publish_run_event", side_effect=lambda *args: published.append(args)), \
             mock.patch("blueprints.run.uuid.uuid4", return_value="run-broker-synthetic"):
            run_id = run_routes._brokered_synthetic_run(
                "help",
                "session-synthetic",
                "203.0.113.10",
                [
                    {"type": "output", "text": "first line", "cls": "notice"},
                    {"type": "clear"},
                    {"type": "output", "text": "second line"},
                ],
                exit_code=3,
            )

        assert run_id == "run-broker-synthetic"
        assert [event_type for _, event_type, _ in published] == [
            "started",
            "output",
            "clear",
            "output",
            "exit",
        ]
        assert published[1][2]["text"] == "first line"
        assert published[1][2]["cls"] == "notice"
        assert published[2][2] == {}
        assert published[3][2]["text"] == "second line"
        assert published[-1][2]["code"] == 3

        with db_connect() as conn:
            row = conn.execute(
                "SELECT command, exit_code, output_preview, output_search_text FROM runs WHERE id = ?",
                ("run-broker-synthetic",),
            ).fetchone()
        assert row is not None
        assert row["command"] == "help"
        assert row["exit_code"] == 3
        assert "first line" in row["output_preview"]
        assert "second line" in row["output_preview"]
        assert row["output_search_text"] == "first line\nsecond line"

    def test_broker_worker_publishes_notices_filtered_output_exit_and_cleans_up(self):
        fake_proc = _FakeProc(lines=["skip this\n", "keep this\n", ""])
        published = []
        capture = run_routes._run_output_capture("run-broker-worker")
        postfilter = run_routes._SyntheticPostFilterProcessor({"kind": "grep", "pattern": "keep"})
        started = datetime.now(timezone.utc).isoformat()

        with mock.patch("blueprints.run.publish_run_event", side_effect=lambda *args: published.append(args)), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True, True]), \
             mock.patch("blueprints.run.pid_pop") as pid_pop, \
             mock.patch("blueprints.run.active_run_remove") as active_remove, \
             mock.patch("blueprints.run._finalize_completed_run", return_value=0.2) as finalize:
            run_routes._brokered_real_run_worker(
                run_id="run-broker-worker",
                proc=fake_proc,
                session_id="session-worker",
                client_ip="203.0.113.10",
                original_command="printf lines | grep keep",
                run_started=started,
                capture=capture,
                signal_classifier=run_routes.OutputSignalClassifier("printf lines", cmd_type="real"),
                postfilter=postfilter,
                workspace_path_filter=_PassthroughWorkspaceFilter(),
                variable_notice="[var] HOST=darklab.sh",
                rewrite_notice="rewritten for safety",
                workspace_notices=["[workspace] writing scan.txt"],
            )
        capture.finalize()

        event_types = [event_type for _, event_type, _ in published]
        assert event_types == ["notice", "notice", "notice", "output", "exit"]
        assert [payload["text"] for _, event_type, payload in published if event_type == "notice"] == [
            "[var] HOST=darklab.sh",
            "[notice] rewritten for safety",
            "[workspace] writing scan.txt",
        ]
        assert [payload["text"] for _, event_type, payload in published if event_type == "output"] == [
            "keep this\n",
        ]
        assert published[-1][2]["code"] == 0
        assert published[-1][2]["output_line_count"] == 4
        finalize.assert_called_once()
        assert fake_proc.stdout is not None
        assert fake_proc.stdout.closed is True
        pid_pop.assert_called_once_with("run-broker-worker")
        active_remove.assert_called_once_with("run-broker-worker")

    def test_broker_worker_times_out_and_publishes_timeout_notice(self):
        fake_proc = _FakeProc(lines=["late output\n"], returncode=None, wait_returncode=-15)
        published = []
        started = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        capture = run_routes._run_output_capture("run-broker-timeout")

        with mock.patch.dict("config.CFG", {"command_timeout_seconds": 1}), \
             mock.patch.dict("blueprints.run.CFG", {"command_timeout_seconds": 1}), \
             mock.patch("blueprints.run.publish_run_event", side_effect=lambda *args: published.append(args)), \
             mock.patch("blueprints.run._terminate_process_group") as terminate, \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run.active_run_remove"), \
             mock.patch("blueprints.run._finalize_completed_run", return_value=1.0):
            run_routes._brokered_real_run_worker(
                run_id="run-broker-timeout",
                proc=fake_proc,
                session_id="session-worker",
                client_ip="203.0.113.10",
                original_command="sleep 10",
                run_started=started,
                capture=capture,
                signal_classifier=run_routes.OutputSignalClassifier("sleep 10", cmd_type="real"),
                postfilter=run_routes._SyntheticPostFilterProcessor(None),
                workspace_path_filter=_PassthroughWorkspaceFilter(),
                variable_notice="",
                rewrite_notice="",
                workspace_notices=[],
            )
        capture.finalize()

        terminate.assert_called_once_with(fake_proc)
        timeout_notices = [
            payload["text"]
            for _, event_type, payload in published
            if event_type == "notice" and payload["text"].startswith("[timeout]")
        ]
        assert timeout_notices == ["[timeout] Command exceeded 1s limit and was killed."]
        assert published[-1][1] == "exit"
        assert published[-1][2]["code"] == -15
        assert fake_proc.stdout is not None
        assert fake_proc.stdout.closed is True
        assert fake_proc.wait_calls >= 1

    def test_broker_worker_publishes_error_and_cleans_up_when_stdout_is_missing(self):
        fake_proc = _FakeProc(lines=[])
        fake_proc.stdout = None
        published = []

        with mock.patch("blueprints.run.publish_run_event", side_effect=lambda *args: published.append(args)), \
             mock.patch("blueprints.run.pid_pop") as pid_pop, \
             mock.patch("blueprints.run.active_run_remove") as active_remove:
            run_routes._brokered_real_run_worker(
                run_id="run-broker-error",
                proc=fake_proc,
                session_id="session-worker",
                client_ip="203.0.113.10",
                original_command="broken",
                run_started=datetime.now(timezone.utc).isoformat(),
                capture=run_routes._run_output_capture("run-broker-error"),
                signal_classifier=run_routes.OutputSignalClassifier("broken", cmd_type="real"),
                postfilter=run_routes._SyntheticPostFilterProcessor(None),
                workspace_path_filter=_PassthroughWorkspaceFilter(),
                variable_notice="",
                rewrite_notice="",
                workspace_notices=[],
            )

        assert published == [("run-broker-error", "error", {"text": "Process stdout pipe was not created"})]
        pid_pop.assert_called_once_with("run-broker-error")
        active_remove.assert_called_once_with("run-broker-error")

    def test_run_emits_started_notice_output_and_exit(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["hello\n", "world\n", ""])

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.rewrite_command", return_value=("echo hello", "rewritten for safety")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
                 True,
             ]):
            resp = _post_run(client, json={"command": "echo hello"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert '"type": "notice"' in body
        assert '"type": "output"' in body
        assert '"type": "exit"' in body
        assert "hello\\n" in body
        assert "world\\n" in body

    def test_run_output_events_include_signal_metadata(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["darklab.sh has address 104.21.4.35\n", ""])

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
             ]):
            resp = _post_run(
                client,
                json={"command": "host darklab.sh"},
                headers={"X-Session-ID": "sess-signal-sse"},
            )
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        output_events = [event for event in _sse_events(body) if event.get("type") == "output"]
        assert output_events
        assert output_events[0]["signals"] == ["findings"]
        assert output_events[0]["line_index"] == 0
        assert output_events[0]["command_root"] == "host"
        assert output_events[0]["target"] == "darklab.sh"

    def test_history_restore_json_preserves_signal_metadata(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["darklab.sh has address 104.21.4.35\n", ""])

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
             ]):
            resp = _post_run(
                client,
                json={"command": "host darklab.sh"},
                headers={"X-Session-ID": "sess-signal-history"},
            )
            resp.get_data(as_text=True)

        assert resp.status_code == 200

        hist = client.get("/history", headers={"X-Session-ID": "sess-signal-history"})
        run_id = json.loads(hist.data)["runs"][0]["id"]
        restored = client.get(f"/history/{run_id}?json&preview=1", headers={"X-Session-ID": "sess-signal-history"})
        data = json.loads(restored.data)
        entry = data["output_entries"][0]

        assert entry["text"] == "darklab.sh has address 104.21.4.35"
        assert entry["signals"] == ["findings"]
        assert entry["line_index"] == 0
        assert entry["command_root"] == "host"
        assert entry["target"] == "darklab.sh"

    def test_nonblocking_stream_reader_preserves_partial_lines_until_finalize(self):
        read_fd, write_fd = os.pipe()
        reader = os.fdopen(read_fd, "r", encoding="utf-8", newline="")
        try:
            state = run_routes._make_nonblocking_stream_reader(reader)
            os.write(write_fd, b"partial output")

            lines, eof = run_routes._read_available_stream_lines(state)

            assert lines == []
            assert eof is False
            assert state["pending"] == "partial output"

            os.close(write_fd)
            write_fd = None

            lines, eof = run_routes._read_available_stream_lines(state, finalize=True)

            assert lines == ["partial output"]
            assert eof is True
            assert state["pending"] == ""
        finally:
            if write_fd is not None:
                os.close(write_fd)
            reader.close()

    def test_nonblocking_stream_reader_logs_when_nonblocking_setup_fails(self):
        read_fd, write_fd = os.pipe()
        reader = os.fdopen(read_fd, "r", encoding="utf-8", newline="")
        try:
            with mock.patch("blueprints.run.os.set_blocking", side_effect=OSError("not supported")), \
                    mock.patch.object(run_routes.log, "warning") as warning:
                state = run_routes._make_nonblocking_stream_reader(reader)

            assert state == {"stream": reader, "fd": None, "decoder": None, "pending": ""}
            warning.assert_called_once()
            args, kwargs = warning.call_args
            assert args == ("RUN_STREAM_NONBLOCKING_UNAVAILABLE",)
            assert kwargs["extra"]["fd"] == read_fd
            assert kwargs["extra"]["error"] == "not supported"
        finally:
            os.close(write_fd)
            reader.close()

    def test_run_returns_500_when_spawn_fails(self):
        client = get_client()

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("boom")):
            resp = _post_run(client, json={"command": "echo hi"})

        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert "error" in data
        assert "boom" in data["error"]

    def test_run_persists_completed_run_to_history(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["saved line\n", ""])

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
             ]):
            resp = _post_run(client, json={"command": "echo saved"}, headers={"X-Session-ID": "sess-save"})
            _ = resp.get_data(as_text=True)

        hist = client.get("/history", headers={"X-Session-ID": "sess-save"})
        data = json.loads(hist.data)
        cmds = [r["command"] for r in data["runs"]]
        assert "echo saved" in cmds

    def test_run_filters_output_through_synthetic_grep(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["ttl=54\n", "time=12ms\n", "ttl=55\n", ""])

        with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
                 True,
                 True,
             ]):
            resp = _post_run(client, json={"command": "ping darklab.sh | grep ttl"}, headers={"X-Session-ID": "sess-grep"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "ttl=54\\n" in body
        assert "ttl=55\\n" in body
        assert "time=12ms\\n" not in body

        hist = client.get("/history", headers={"X-Session-ID": "sess-grep"})
        data = json.loads(hist.data)
        assert data["runs"][0]["command"] == "ping darklab.sh | grep ttl"
        run_id = data["runs"][0]["id"]
        preview_resp = client.get(f"/history/{run_id}?json&preview=1", headers={"X-Session-ID": "sess-grep"})
        preview = json.loads(preview_resp.data)
        texts = [entry["text"] for entry in preview["output_entries"]]
        assert texts == ["ttl=54", "ttl=55"]

    def test_run_supports_invert_match_synthetic_grep(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["ttl=54\n", "time=12ms\n", "ttl=55\n", ""])

        with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
                 True,
                 True,
             ]):
            resp = _post_run(client, json={"command": "ping darklab.sh | grep -v ttl"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "time=12ms\\n" in body
        assert "ttl=54\\n" not in body

    def test_run_filters_output_through_synthetic_head(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["one\n", "two\n", "three\n", ""])

        with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
                 True,
                 True,
             ]):
            resp = _post_run(client, json={"command": "ping darklab.sh | head -n 2"}, headers={"X-Session-ID": "sess-head"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "one\\n" in body
        assert "two\\n" in body
        assert "three\\n" not in body

        hist = client.get("/history", headers={"X-Session-ID": "sess-head"})
        data = json.loads(hist.data)
        run_id = data["runs"][0]["id"]
        preview_resp = client.get(f"/history/{run_id}?json&preview=1", headers={"X-Session-ID": "sess-head"})
        preview = json.loads(preview_resp.data)
        texts = [entry["text"] for entry in preview["output_entries"]]
        assert texts == ["one", "two"]

    def test_run_filters_output_through_synthetic_tail(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["one\n", "two\n", "three\n", ""])

        with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
                 True,
                 True,
             ]):
            resp = _post_run(client, json={"command": "ping darklab.sh | tail -n 2"}, headers={"X-Session-ID": "sess-tail"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "one\\n" not in body
        assert "two\\n" in body
        assert "three\\n" in body

        hist = client.get("/history", headers={"X-Session-ID": "sess-tail"})
        data = json.loads(hist.data)
        run_id = data["runs"][0]["id"]
        preview_resp = client.get(f"/history/{run_id}?json&preview=1", headers={"X-Session-ID": "sess-tail"})
        preview = json.loads(preview_resp.data)
        texts = [entry["text"] for entry in preview["output_entries"]]
        assert texts == ["two", "three"]

    def test_run_filters_output_through_synthetic_wc_line_count(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["one\n", "two\n", "three\n", ""])

        with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
                 True,
                 True,
             ]):
            resp = _post_run(client, json={"command": "ping darklab.sh | wc -l"}, headers={"X-Session-ID": "sess-wc"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "one\\n" not in body
        assert "two\\n" not in body
        assert "three\\n" not in body
        assert '"text": "3"' in body

        hist = client.get("/history", headers={"X-Session-ID": "sess-wc"})
        data = json.loads(hist.data)
        run_id = data["runs"][0]["id"]
        preview_resp = client.get(f"/history/{run_id}?json&preview=1", headers={"X-Session-ID": "sess-wc"})
        preview = json.loads(preview_resp.data)
        texts = [entry["text"] for entry in preview["output_entries"]]
        assert texts == ["3"]

    def test_run_filters_output_through_chained_synthetic_helpers(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["ttl=54\n", "time=12ms\n", "ttl=55\n", ""])

        with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
                 True,
                 True,
             ]):
            resp = _post_run(
                client,
                json={"command": "ping darklab.sh | grep ttl | wc -l"},
                headers={"X-Session-ID": "sess-chain"},
            )
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "ttl=54\\n" not in body
        assert "ttl=55\\n" not in body
        assert "time=12ms\\n" not in body
        assert '"text": "2"' in body

        hist = client.get("/history", headers={"X-Session-ID": "sess-chain"})
        data = json.loads(hist.data)
        run_id = data["runs"][0]["id"]
        preview_resp = client.get(f"/history/{run_id}?json&preview=1", headers={"X-Session-ID": "sess-chain"})
        preview = json.loads(preview_resp.data)
        texts = [entry["text"] for entry in preview["output_entries"]]
        assert texts == ["2"]

    def test_run_rejects_invalid_synthetic_grep_regex(self):
        client = get_client()

        resp = _post_run(client, json={"command": "ping darklab.sh | grep -E '['"})

        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["error"].startswith("Invalid synthetic grep regex:")

    def test_run_emits_timeout_notice_when_command_exceeds_limit(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["still running\n"], returncode=-15)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        finish = start + timedelta(seconds=2)

        class _FakeDateTime:
            _first_now = True

            @staticmethod
            def now(_tz=None):
                if _FakeDateTime._first_now:
                    _FakeDateTime._first_now = False
                    return start
                return finish

            @staticmethod
            def fromisoformat(value):
                return datetime.fromisoformat(value)

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run.datetime", _FakeDateTime), \
             mock.patch("blueprints.run.os.getpgid", return_value=4321), \
             mock.patch("blueprints.run.os.killpg") as killpg, \
             mock.patch.dict("config.CFG", {"command_timeout_seconds": 1}):
            resp = _post_run(client, json={"command": "sleep forever"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "[timeout] Command exceeded 1s limit and was killed." in body
        assert '"type": "notice"' in body
        assert '"type": "exit"' in body
        killpg.assert_called_once_with(4321, shell_app.signal.SIGTERM)

    def test_run_still_exits_when_history_save_fails(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["saved line\n", ""])

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[
                 True,
                 True,
             ]), \
             mock.patch("blueprints.run._run_belongs_to_session", return_value=True), \
             mock.patch("blueprints.run.db_connect", side_effect=Exception("db write failed")):
            resp = _post_run(client, json={"command": "echo saved"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert '"type": "output"' in body
        assert '"type": "exit"' in body

    def test_run_waits_before_emitting_exit_code(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["done\n", ""], returncode=None, wait_returncode=0)

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]):
            resp = _post_run(client, json={"command": "echo done"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "exit"' in body
        assert '"code": 0' in body
        assert fake_proc.wait_calls >= 1

    def test_run_cleans_up_stdout_and_waits_when_streaming_errors(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["hello\n"], returncode=None, wait_returncode=0)

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._run_belongs_to_session", return_value=True), \
             mock.patch("blueprints.run._stdout_ready", side_effect=RuntimeError("boom")):
            resp = _post_run(client, json={"command": "echo hi"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "error"' in body
        assert fake_proc.stdout is not None
        assert fake_proc.stdout.closed is True
        assert fake_proc.wait_calls == 1

    def test_builtin_commands_streams_grouped_catalog_and_persists_history(self):
        client = get_client()

        with mock.patch("builtin_commands.load_commands_registry", return_value={
            "commands": [
                {"root": "ping", "category": "Networking", "policy": {"allow": ["ping"], "deny": []}},
                {"root": "dig", "category": "Networking", "policy": {"allow": ["dig"], "deny": []}},
            ],
            "pipe_helpers": [],
        }):
            resp = _post_run(client, json={"command": "commands"}, headers={"X-Session-ID": "sess-built-in-commands"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert '"type": "output"' in body
        assert "Built-in commands:\\n" in body
        assert "Allowed external commands:\\n" in body
        assert "[Networking]\\n" in body
        assert "ping\\n" in body
        assert "dig\\n" in body
        assert '"type": "exit"' in body

        hist = client.get("/history", headers={"X-Session-ID": "sess-built-in-commands"})
        data = json.loads(hist.data)
        assert [r["command"] for r in data["runs"]] == ["commands"]

    def test_builtin_clear_emits_clear_event_and_persists_history(self):
        client = get_client()

        resp = _post_run(client, json={"command": "clear"}, headers={"X-Session-ID": "sess-clear"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert '"type": "clear"' in body
        assert '"type": "exit"' in body

        hist = client.get("/history", headers={"X-Session-ID": "sess-clear"})
        data = json.loads(hist.data)
        assert [r["command"] for r in data["runs"]] == ["clear"]

    def test_builtin_env_returns_web_environment(self):
        client = get_client()

        resp = _post_run(client, json={"command": "env"}, headers={"X-Session-ID": "sess-env"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert f"APP_NAME={shell_app.CFG['app_name']}\\n" in body
        assert "SESSION_ID=sess-env\\n" in body
        assert "SHELL=/bin/bash\\n" in body
        assert "TERM=xterm-256color\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_help_lists_available_helpers(self):
        client = get_client()

        resp = _post_run(client, json={"command": "help"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Help and discovery:\\n" in body
        assert "Run `commands` to browse built-in and allowed external commands.\\n" in body
        assert "Use `commands --built-in` or `commands --external` to filter that catalog.\\n" in body
        assert "Use `commands info <command>` to see examples, flags, and subcommands for a supported command.\\n" in body
        assert "Run `faq` to browse the configured FAQ entries inside the terminal.\\n" in body
        assert "Run `shortcuts` to see the current keyboard shortcuts.\\n" in body
        assert "README:" in body
        assert "Autocomplete appears as you type; press Tab to accept or cycle suggestions.\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_commands_lists_built_in_and_external_catalogs(self):
        client = get_client()

        with mock.patch("builtin_commands.load_commands_registry", return_value={
            "commands": [
                {"root": "ping", "category": "Networking", "policy": {"allow": ["ping"], "deny": []}},
                {"root": "dig", "category": "Networking", "policy": {"allow": ["dig +short", "dig MX"], "deny": []}},
            ],
            "pipe_helpers": [],
        }):
            resp = _post_run(client, json={"command": "commands"}, headers={"X-Session-ID": "sess-built-in-commands"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Built-in commands:\\n" in body
        assert "commands" in body and "List built-in and allowed external commands." in body
        assert "help" in body and "Show guidance for README, FAQ, shortcuts, and command discovery." in body
        assert "Allowed external commands:\\n" in body
        assert "[Networking]\\n" in body
        assert "ping\\n" in body
        assert "dig\\n" in body
        assert "dig +short\\n" not in body
        assert '"type": "exit"' in body

        hist = client.get("/history", headers={"X-Session-ID": "sess-built-in-commands"})
        data = json.loads(hist.data)
        assert [r["command"] for r in data["runs"]] == ["commands"]

    def test_builtin_commands_supports_built_in_only_filter(self):
        client = get_client()

        resp = _post_run(client, json={"command": "commands --built-in"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Built-in commands:\\n" in body
        assert "Allowed external commands:\\n" not in body

    def test_builtin_commands_supports_external_only_filter(self):
        client = get_client()

        with mock.patch("builtin_commands.load_commands_registry", return_value={
            "commands": [
                {"root": "ping", "category": "Networking", "policy": {"allow": ["ping"], "deny": []}},
                {"root": "curl", "category": "Networking", "policy": {"allow": ["curl -I"], "deny": []}},
            ],
            "pipe_helpers": [],
        }):
            resp = _post_run(client, json={"command": "commands --external"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Built-in commands:\\n" not in body
        assert "Allowed external commands:\\n" in body
        assert "ping\\n" in body
        assert "curl\\n" in body
        assert "curl -I\\n" not in body
        assert '"type": "exit"' in body

    def test_builtin_wordlist_lists_searches_and_prints_paths(self):
        client = get_client()
        catalog = {
            "root": "/usr/share/wordlists/seclists",
            "categories": [{"key": "dns", "label": "DNS", "description": "DNS lists"}],
            "items": [
                {
                    "name": "subdomains-top1million-5000.txt",
                    "category": "dns",
                    "category_label": "DNS",
                    "description": "DNS lists",
                    "path": "/usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt",
                    "relpath": "Discovery/DNS/subdomains-top1million-5000.txt",
                    "aliases": ["subdomains-top1million-5000.txt"],
                }
            ],
            "all_items": None,
        }
        with mock.patch("builtin_commands.load_wordlist_catalog", return_value=catalog):
            listed = _post_run(
                client,
                json={"command": "wordlist list dns"},
                headers={"X-Session-ID": "sess-wordlist"},
            )
            searched = _post_run(
                client,
                json={"command": "wordlist search subdomains"},
                headers={"X-Session-ID": "sess-wordlist"},
            )
            path = _post_run(
                client,
                json={"command": "wordlist path subdomains-top1million-5000.txt"},
                headers={"X-Session-ID": "sess-wordlist"},
            )

        assert "Curated dns wordlists:\\n" in listed.get_data(as_text=True)
        assert "Discovery/DNS/subdomains-top1million-5000.txt" in searched.get_data(as_text=True)
        assert "/usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt" in path.get_data(as_text=True)

    def test_builtin_wordlist_reports_missing_catalog(self):
        client = get_client()
        with mock.patch("builtin_commands.load_wordlist_catalog", return_value={
            "root": "/usr/share/wordlists/seclists",
            "categories": [],
            "items": [],
            "all_items": None,
        }):
            resp = _post_run(
                client,
                json={"command": "wordlist"},
                headers={"X-Session-ID": "sess-wordlist-missing"},
            )

        body = resp.get_data(as_text=True)
        assert "Installed SecLists wordlists were not found.\\n" in body
        assert "Expected path: /usr/share/wordlists/seclists\\n" in body

    def test_builtin_workspace_lists_shows_and_removes_session_files(self, tmp_path):
        client = get_client()
        session = "sess-workspace-command"
        workspace_cfg = {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(tmp_path / "workspaces"),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
            "workspace_inactivity_ttl_hours": 1,
        }

        with mock.patch.dict(shell_app.CFG, workspace_cfg):
            created = client.post(
                "/workspace/files",
                json={"path": "targets.txt", "text": "darklab.sh\nip.darklab.sh\n"},
                headers={"X-Session-ID": session},
            )
            created_report = client.post(
                "/workspace/files",
                json={"path": "reports/amass.txt", "text": "one.darklab.sh\n"},
                headers={"X-Session-ID": session},
            )
            created_nested_report = client.post(
                "/workspace/files",
                json={"path": "reports/nested/httpx.txt", "text": "https://ip.darklab.sh\n"},
                headers={"X-Session-ID": session},
            )
            created_empty_folder = client.post(
                "/workspace/directories",
                json={"path": "empty-folder"},
                headers={"X-Session-ID": session},
            )
            list_resp = _post_run(
                client,
                json={"command": "file list"},
                headers={"X-Session-ID": session},
            )
            list_long_resp = _post_run(
                client,
                json={"command": "file ls -l"},
                headers={"X-Session-ID": session},
            )
            list_recursive_resp = _post_run(
                client,
                json={"command": "file ls -Rl"},
                headers={"X-Session-ID": session},
            )
            show_resp = _post_run(
                client,
                json={"command": "file show targets.txt"},
                headers={"X-Session-ID": session},
            )

        assert created.status_code == 200
        assert created_report.status_code == 200
        assert created_nested_report.status_code == 200
        assert created_empty_folder.status_code == 200
        assert list_resp.status_code == 200
        assert list_long_resp.status_code == 200
        assert list_recursive_resp.status_code == 200
        list_body = list_resp.get_data(as_text=True)
        assert "Session files:\\n" in list_body
        assert "usage" in list_body
        assert "62 B / 1.0 MB\\n" in list_body
        assert "remaining" in list_body
        assert "targets.txt" in list_body
        assert "empty-folder/" in list_body
        assert "reports/" in list_body
        assert "amass.txt" not in list_body
        assert "httpx.txt" not in list_body

        long_body = list_long_resp.get_data(as_text=True)
        assert "\\u001b[4mpath\\u001b[0m  " in long_body
        assert "\\u001b[4msize\\u001b[0m    " in long_body
        assert "\\u001b[4mmodified\\u001b[0m" in long_body
        assert "reports/" in long_body
        assert "targets.txt" in long_body
        assert "amass.txt" not in long_body

        recursive_body = list_recursive_resp.get_data(as_text=True)
        assert "reports/" in recursive_body
        assert "  amass.txt" in recursive_body
        assert "  reports/nested/" in recursive_body
        assert "    httpx.txt" in recursive_body
        assert recursive_body.index("reports/") < recursive_body.index("  amass.txt")
        assert recursive_body.index("  reports/nested/") < recursive_body.index("    httpx.txt")

        assert show_resp.status_code == 200
        show_body = show_resp.get_data(as_text=True)
        assert "file: targets.txt\\n" in show_body
        assert "darklab.sh\\n" in show_body
        assert "ip.darklab.sh\\n" in show_body

    def test_builtin_workspace_aliases_list_and_show_session_files(self, tmp_path):
        client = get_client()
        session = "sess-workspace-aliases"
        workspace_cfg = {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(tmp_path / "workspaces"),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
            "workspace_inactivity_ttl_hours": 1,
        }

        with mock.patch.dict(shell_app.CFG, workspace_cfg):
            created = client.post(
                "/workspace/files",
                json={"path": "urls.txt", "text": "https://ip.darklab.sh\n"},
                headers={"X-Session-ID": session},
            )
            ls_resp = _post_run(
                client,
                json={"command": "ls"},
                headers={"X-Session-ID": session},
            )
            cat_resp = _post_run(
                client,
                json={"command": "cat urls.txt"},
                headers={"X-Session-ID": session},
            )
            help_resp = _post_run(
                client,
                json={"command": "file help"},
                headers={"X-Session-ID": session},
            )

        assert created.status_code == 200
        assert ls_resp.status_code == 200
        assert "Session files:\\n" in ls_resp.get_data(as_text=True)
        assert "urls.txt" in ls_resp.get_data(as_text=True)

        assert cat_resp.status_code == 200
        cat_body = cat_resp.get_data(as_text=True)
        assert "file: urls.txt\\n" in cat_body
        assert "https://ip.darklab.sh\\n" in cat_body

        assert help_resp.status_code == 200
        help_body = help_resp.get_data(as_text=True)
        assert "Session file commands:\\n" in help_body
        assert "file ls [-lR] [folder]\\n" in help_body
        assert "file download <file>\\n" in help_body
        assert "Aliases:\\n" in help_body
        assert "Create targets.txt from the Files panel.\\n" in help_body
        assert "curl -o response.html https://ip.darklab.sh\\n" in help_body

    def test_builtin_workspace_show_reports_binary_files(self, tmp_path):
        client = get_client()
        session = "sess-workspace-binary"
        workspace_cfg = {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(tmp_path / "workspaces"),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
            "workspace_inactivity_ttl_hours": 1,
        }

        with mock.patch.dict(shell_app.CFG, workspace_cfg):
            binary_path = shell_workspace.resolve_workspace_path(
                session,
                "amass/asset.db",
                shell_app.CFG,
                ensure_parent=True,
            )
            binary_path.write_bytes(b"SQLite format 3\x00binary")
            show_resp = _post_run(
                client,
                json={"command": "file show amass/asset.db"},
                headers={"X-Session-ID": session},
            )
            cat_resp = _post_run(
                client,
                json={"command": "cat amass/asset.db"},
                headers={"X-Session-ID": session},
            )

        assert show_resp.status_code == 200
        show_body = show_resp.get_data(as_text=True)
        assert "file: file appears to be binary; download it instead\\n" in show_body
        assert "[server error]" not in show_body
        assert '"type": "exit"' in show_body
        assert '"code": 0' in show_body

        assert cat_resp.status_code == 200
        cat_body = cat_resp.get_data(as_text=True)
        assert "file: file appears to be binary; download it instead\\n" in cat_body
        assert "[server error]" not in cat_body

    def test_builtin_shortcuts_lists_current_shortcuts(self):
        client = get_client()

        resp = _post_run(client, json={"command": "shortcuts"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Terminal:\\n" in body
        assert "Tabs:\\n" in body
        assert "UI:\\n" in body
        # Default (non-Mac) User-Agent renders Alt-prefixed chords.
        assert "Alt+T" in body
        assert "Alt+Shift+C" in body
        assert "Ctrl+D" in body
        assert "Ctrl+U" in body
        assert "Option+" not in body
        assert '"type": "exit"' in body

    def test_builtin_shortcuts_renders_mac_keys_for_mac_user_agent(self):
        client = get_client()
        client.environ_base["HTTP_USER_AGENT"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        )

        resp = _post_run(client, json={"command": "shortcuts"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Option+T" in body
        assert "Option+Shift+C" in body
        assert "Ctrl+D" in body
        assert "Ctrl+U" in body
        assert "Alt+" not in body

    def test_builtin_banner_renders_ascii_art(self):
        client = get_client()

        with mock.patch("builtin_commands.load_ascii_art", return_value="line one\nline two"):
            resp = _post_run(client, json={"command": "banner"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "line one\\n" in body
        assert "line two\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_which_and_type_describe_commands(self):
        client = get_client()

        with mock.patch("builtin_commands.resolve_runtime_command", return_value="/usr/bin/curl"):
            which_resp = _post_run(client, json={"command": "which curl"})
            which_body = which_resp.get_data(as_text=True)
            type_resp = _post_run(client, json={"command": "type history"})
            type_body = type_resp.get_data(as_text=True)

        assert which_resp.status_code == 200
        assert "/usr/bin/curl\\n" in which_body
        assert type_resp.status_code == 200
        assert "history is a built-in command\\n" in type_body

    def test_builtin_limits_and_status_show_configuration(self, tmp_path):
        client = get_client()
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "run-stats-ok",
                    "sess-limits",
                    "nmap ip.darklab.sh",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:03+00:00",
                    0,
                    "[]",
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "run-stats-fail",
                    "sess-limits",
                    "curl https://ip.darklab.sh",
                    "2026-01-01T00:00:05+00:00",
                    "2026-01-01T00:00:07+00:00",
                    1,
                    "[]",
                ),
            )
            conn.commit()

        with mock.patch.dict(shell_app.CFG, {
            "max_tabs": 4,
            "permalink_retention_days": 365,
            "workspace_enabled": True,
            "workspace_quota_mb": 50,
            "workspace_max_file_mb": 5,
            "workspace_max_files": 100,
            "workspace_inactivity_ttl_hours": 90,
            "workspace_root": str(tmp_path / "workspaces"),
        }):
            limits_resp = _post_run(client, json={"command": "limits"}, headers={"X-Session-ID": "sess-limits"})
            limits_body = limits_resp.get_data(as_text=True)
            status_resp = _post_run(client, json={"command": "status"}, headers={"X-Session-ID": "sess-limits"})
            status_body = status_resp.get_data(as_text=True)
            stats_resp = _post_run(client, json={"command": "stats"}, headers={"X-Session-ID": "sess-limits"})
            stats_body = stats_resp.get_data(as_text=True)

        assert limits_resp.status_code == 200
        assert "live preview lines" in limits_body
        assert f"{shell_app.CFG['max_output_lines']}\\n" in limits_body
        assert "files enabled" in limits_body
        assert "\\u001b[32myes\\u001b[0m\\n" in limits_body
        assert "files quota" in limits_body
        assert "50 MB\\n" in limits_body
        assert "files cleanup" in limits_body
        assert "90h (0 = disabled)\\n" in limits_body
        assert status_resp.status_code == 200
        assert "session" in status_body
        assert "sess-lim" in status_body
        assert "sess-limits\\n" not in status_body
        assert "tab limit" in status_body
        assert "4\\n" in status_body
        assert "retention" in status_body
        assert "365\\n" in status_body
        assert "active runs" in status_body
        assert "active jobs" not in status_body
        assert "\\u001b[32monline\\u001b[0m" in status_body
        assert "files" in status_body
        assert "0/100 files, 0 B / 50.0 MB\\n" in status_body
        assert stats_resp.status_code == 200
        assert "Session stats:\\n" in stats_body
        assert "active runs" in stats_body
        assert "active jobs" not in stats_body
        assert "success rate" in stats_body
        assert "\\u001b[32m" in stats_body
        assert "\\u001b[31m" in stats_body
        assert "\\u001b[4mcommand\\u001b[0m" in stats_body
        assert "\\u001b[4mruns\\u001b[0m" in stats_body

    def test_builtin_last_lists_recent_completed_runs(self):
        client = get_client()
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-last-1", "sess-last", "ping darklab.sh", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:03+00:00", 0, "[]")
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "run-last-2", "sess-last", "dig darklab.sh A",
                    "2026-01-01T00:00:05+00:00", "2026-01-01T00:00:06+00:00", 1, "[]",
                )
            )
            conn.commit()

        resp = _post_run(client, json={"command": "last"}, headers={"X-Session-ID": "sess-last"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Recent runs:\\n" in body
        assert (
            f"{self._local_dt_text('2026-01-01T00:00:05+00:00')}  "
            "[\\u001b[31m1\\u001b[0m]  dig darklab.sh A\\n"
        ) in body
        assert (
            f"{self._local_dt_text('2026-01-01T00:00:00+00:00')}  "
            "[\\u001b[32m0\\u001b[0m]  ping darklab.sh\\n"
        ) in body

    def test_builtin_who_tty_groups_and_version_render_shell_identity(self):
        client = get_client()

        who_resp = _post_run(client, json={"command": "who"}, headers={"X-Session-ID": "sess-who"})
        who_body = who_resp.get_data(as_text=True)
        tty_resp = _post_run(client, json={"command": "tty"})
        tty_body = tty_resp.get_data(as_text=True)
        groups_resp = _post_run(client, json={"command": "groups"})
        groups_body = groups_resp.get_data(as_text=True)
        version_resp = _post_run(client, json={"command": "version"})
        version_body = version_resp.get_data(as_text=True)

        assert who_resp.status_code == 200
        assert f"{shell_app.CFG['app_name']}  pts/web  sess-who\\n" in who_body
        assert tty_resp.status_code == 200
        assert "/dev/pts/web\\n" in tty_body
        assert groups_resp.status_code == 200
        assert f"{shell_app.CFG['app_name']} operators\\n" in groups_body
        assert version_resp.status_code == 200
        assert f"{shell_app.CFG['app_name']} web shell\\n" in version_body
        assert f"App {shell_app.APP_VERSION}\\n" in version_body
        assert "Flask " in version_body
        assert "Python " in version_body

    def test_builtin_faq_renders_builtin_and_configured_entries(self):
        client = get_client()

        with mock.patch("builtin_commands.load_all_faq", return_value=[
            {"question": "Built-in question?", "answer": "Built-in answer."},
            {"question": "What is this?", "answer": "A browser-based shell."},
            {"question": "How do I stop a command?", "answer": "Use Kill."},
        ]):
            resp = _post_run(client, json={"command": "faq"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Configured FAQ entries:\\n" in body
        assert "Q  Built-in question?\\n" in body
        assert "A  Built-in answer.\\n" in body
        assert "Q  What is this?\\n" in body
        assert "A  A browser-based shell.\\n" in body
        assert "Q  How do I stop a command?\\n" in body
        assert "A  Use Kill.\\n" in body

    def test_builtin_retention_reports_preview_and_full_output_policy(self):
        client = get_client()

        with mock.patch("builtin_commands.CFG", {
            **shell_app.CFG,
            "permalink_retention_days": 365,
            "persist_full_run_output": True,
            "full_output_max_mb": 5,
        }):
            resp = _post_run(client, json={"command": "retention"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Retention policy:\\n" in body
        assert "run preview retention " in body
        assert "365 days\\n" in body
        assert "full output save" in body
        assert "\\u001b[32myes\\u001b[0m\\n" in body
        assert "full output max" in body
        assert "5 MB\\n" in body

    def test_builtin_fortune_returns_configured_line(self):
        client = get_client()

        with mock.patch("builtin_commands.random.choice", return_value="Trust the output, not the hunch."):
            resp = _post_run(client, json={"command": "fortune"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Trust the output, not the hunch.\\n" in body

    def test_builtin_sudo_reports_web_shell_restriction(self):
        client = get_client()

        resp = _post_run(client, json={"command": "sudo ping darklab.sh"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert (
            "sudo: 'ping darklab.sh' is not listed in the threat model, but still no.\\n" in body
            or "sudo: 'ping darklab.sh' has been forwarded to /dev/null for executive review.\\n" in body
            or "sudo: ran 'ping darklab.sh' through the web shell authorization matrix. verdict: absolutely not.\\n" in body
            or "sudo: 'ping darklab.sh' would require a kernel, a real tty, and a better plan.\\n" in body
            or "sudo: 'ping darklab.sh' has been denied by a bipartisan coalition of guardrails.\\n" in body
            or "sudo: 'ping darklab.sh' would make a great postmortem title.\\n" in body
            or "sudo: 'ping darklab.sh' was intercepted by responsible adults.\\n" in body
            or "sudo: 'ping darklab.sh' has failed the vibe check.\\n" in body
            or "sudo: 'ping darklab.sh' has been denied for the continued health of the infrastructure.\\n" in body
            or "sudo: nice try with 'ping darklab.sh', but no.\\n" in body
            or "sudo: 'ping darklab.sh' was rejected before it could become a plan.\\n" in body
        )

    def test_builtin_sudo_without_arguments_uses_the_snark_pool(self):
        client = get_client()

        resp = _post_run(client, json={"command": "sudo"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert (
            "sudo: i asked the kernel. the kernel said no.\\n" in body
            or "sudo: root is occupied. please leave a message after the 403.\\n" in body
            or "sudo: this is still a shell, not a coup.\\n" in body
            or "sudo: administrative confidence detected; administrative power not found.\\n" in body
            or "sudo: this shell respects your ambition and ignores it completely.\\n" in body
            or "sudo: the stack has reviewed your request and chosen comedy.\\n" in body
            or "sudo: root privileges are currently in another castle.\\n" in body
            or "sudo: kernel says no, browser says also no.\\n" in body
            or "sudo: privilege escalation blocked at layer 8.\\n" in body
            or "sudo: request denied by the web shell's sense of self-preservation.\\n" in body
        )

    def test_builtin_reboot_reports_web_shell_restriction(self):
        client = get_client()

        resp = _post_run(client, json={"command": "reboot"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert (
            "reboot: the uptime counter would like a word.\\n" in body
            or "reboot: that's a 4am pager alert in text form. still no.\\n" in body
            or "reboot: graceful shutdown initiated... just kidding.\\n" in body
            or "reboot: systemd is not listening to you right now.\\n" in body
            or "reboot: denied. the server prefers consciousness.\\n" in body
            or "reboot: if you need closure, may I suggest 'clear'?\\n" in body
            or "reboot: that's one way to hide the evidence, but still no.\\n" in body
            or "reboot: the server is not taking user suggestions for downtime.\\n" in body
            or "reboot: let's not turn a diagnostic console into a blackout.\\n" in body
        )

    @pytest.mark.parametrize("command,prefix", [
        ("poweroff", "poweroff:"),
        ("halt", "poweroff:"),
        ("shutdown now", "poweroff:"),
    ])
    def test_builtin_poweroff_variants_use_poweroff_snark_pool(self, command, prefix):
        client = get_client()

        resp = _post_run(client, json={"command": command})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert prefix in body

    @pytest.mark.parametrize("command,prefix", [
        ("su", "su:"),
        ("sudo su", "sudo:"),
        ("sudo -s", "sudo:"),
    ])
    def test_builtin_su_variants_use_shell_escalation_pool(self, command, prefix):
        client = get_client()

        resp = _post_run(client, json={"command": command})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert prefix in body
        assert (
            "root login is not available" in body
            or "does not come with a root shell" in body
            or "no tty, no pam, no chance" in body
            or "root remains a management problem" in body
            or "continued health of the infrastructure" in body
        )

    @pytest.mark.parametrize("command", [
        "rm -fr /",
        "rm -rf /",
        "rm -r -f /",
        "rm -f -r /",
    ])
    def test_builtin_rm_root_refuses_exact_root_delete_pattern(self, command):
        client = get_client()

        resp = _post_run(client, json={"command": command})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert (
            "rm: no filesystem was harmed in the running of this command.\\n" in body
            or "rm: this is a web shell. the / you're reaching for is a container. the container says no.\\n" in body
            or "rm: truly, a classic. still no.\\n" in body
            or "rm: operation blocked by the 'i like having a root filesystem' policy.\\n" in body
            or "rm: you'll have to cause your own outage the old-fashioned way.\\n" in body
            or "rm: the / would like to remain.\\n" in body
        )

    def test_builtin_date_hostname_and_uptime_render_shell_style_information(self):
        client = get_client()

        date_resp = _post_run(client, json={"command": "date"})
        date_body = date_resp.get_data(as_text=True)
        host_resp = _post_run(client, json={"command": "hostname"})
        host_body = host_resp.get_data(as_text=True)
        uptime_resp = _post_run(client, json={"command": "uptime"})
        uptime_body = uptime_resp.get_data(as_text=True)

        assert date_resp.status_code == 200
        assert '"type": "output"' in date_body
        assert host_resp.status_code == 200
        assert f"{shell_app.CFG['app_name']}\\n" in host_body
        assert uptime_resp.status_code == 200
        assert "up " in uptime_body

    def test_builtin_ip_route_df_and_free_render_shell_style_summaries(self):
        client = get_client()

        ip_resp = _post_run(client, json={"command": "ip a"})
        ip_body = ip_resp.get_data(as_text=True)
        route_resp = _post_run(client, json={"command": "route"})
        route_body = route_resp.get_data(as_text=True)
        df_resp = _post_run(client, json={"command": "df -h"})
        df_body = df_resp.get_data(as_text=True)
        free_resp = _post_run(client, json={"command": "free -h"})
        free_body = free_resp.get_data(as_text=True)

        assert ip_resp.status_code == 200
        assert "1: lo:" in ip_body
        assert "2: eth0:" in ip_body
        assert route_resp.status_code == 200
        assert "Kernel IP routing table\\n" in route_body
        assert "\\u001b[4mDestination\\u001b[0m" in route_body
        assert "0.0.0.0" in route_body
        assert df_resp.status_code == 200
        assert "\\u001b[4mFilesystem\\u001b[0m" in df_body
        assert "\\u001b[4mMounted on\\u001b[0m\\n" in df_body
        assert "overlay" in df_body
        assert free_resp.status_code == 200
        assert "\\u001b[4mtotal\\u001b[0m" in free_body
        assert "\\u001b[4mfree\\u001b[0m" in free_body
        assert "Mem:" in free_body

    def test_builtin_jobs_aliases_runs_metadata(self):
        client = get_client()

        with mock.patch("builtin_commands.active_runs_for_session", return_value=[
            {
                "run_id": "run-abcdef123456",
                "pid": 4242,
                "command": "ping darklab.sh",
                "started": "2026-01-01T00:00:00+00:00",
                "resource_usage": {"cpu_seconds": 12.345, "memory_bytes": 1536, "process_count": 2},
            },
            {
                "run_id": "run-fedcba987654",
                "pid": 0,
                "command": "ffuf -u https://darklab.sh/FUZZ -w words.txt",
                "started": "2026-01-01T00:00:05+00:00",
            },
        ]):
            resp = _post_run(client, json={"command": "jobs"}, headers={"X-Session-ID": "sess-jobs"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Active runs:\\n" in body
        assert "run-abcd" in body
        assert "4242" in body
        assert "0.0%" in body
        assert "1.5 KB" in body
        assert "ping darklab.sh\\n" in body
        assert "run-fedc" in body
        assert "ffuf -u https://darklab.sh/FUZZ -w words.txt\\n" in body
        assert "Tip: click STATUS in the HUD for real-time CPU/MEM monitoring.\\n" in body

    def test_builtin_jobs_alias_reports_when_no_active_runs_exist(self):
        client = get_client()

        with mock.patch("builtin_commands.active_runs_for_session", return_value=[]):
            resp = _post_run(client, json={"command": "jobs"}, headers={"X-Session-ID": "sess-jobs"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "No active runs.\\n" in body

    def test_builtin_runs_lists_active_run_metadata(self):
        client = get_client()

        with mock.patch("builtin_commands.active_runs_for_session", return_value=[
            {
                "run_id": "run-abcdef123456",
                "pid": 4242,
                "command": "ping darklab.sh",
                "started": "2026-01-01T00:00:00+00:00",
                "source": "redis",
                "resource_usage": {"cpu_seconds": 12.345, "memory_bytes": 1536, "process_count": 2},
            },
            {
                "run_id": "run-fedcba987654",
                "pid": 0,
                "command": "ffuf -u https://darklab.sh/FUZZ -w words.txt",
                "started": "2026-01-01T00:00:05+00:00",
                "source": "memory",
            },
        ]):
            resp = _post_run(client, json={"command": "runs"}, headers={"X-Session-ID": "sess-runs"})
            body = resp.get_data(as_text=True)
            verbose_resp = _post_run(client, json={"command": "runs -v"}, headers={"X-Session-ID": "sess-runs"})
            verbose_body = verbose_resp.get_data(as_text=True)
            json_resp = _post_run(client, json={"command": "runs --json"}, headers={"X-Session-ID": "sess-runs"})
            json_body = json_resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Active runs:\\n" in body
        assert "run" in body
        assert "pid" in body
        assert "elapsed" in body
        assert "cpu" in body
        assert "mem" in body
        assert "\\u001b[4mcommand\\u001b[0m\\n" in body
        assert "\\u001b[36mrun-abcd\\u001b[0m" in body
        assert "\\u001b[2m4242\\u001b[0m" in body
        assert "\\u001b[33m0.0%\\u001b[0m" in body
        assert "\\u001b[2m1.5 KB\\u001b[0m" in body
        assert "ping darklab.sh\\n" in body
        assert "\\u001b[36mrun-fedc\\u001b[0m" in body
        assert "\\u001b[2m-\\u001b[0m" in body
        assert "ffuf -u https://darklab.sh/FUZZ -w words.txt\\n" in body
        assert "Tip: click STATUS in the HUD for real-time CPU/MEM monitoring.\\n" in body
        assert verbose_resp.status_code == 200
        assert "\\u001b[36mrun-abcdef123456\\u001b[0m" in verbose_body
        assert "\\u001b[4mcpu\\u001b[0m" in verbose_body
        assert "\\u001b[4mcpu time\\u001b[0m" in verbose_body
        assert "\\u001b[4mmem\\u001b[0m" in verbose_body
        assert "\\u001b[2m12.3s\\u001b[0m" in verbose_body
        assert "\\u001b[4mstarted\\u001b[0m" in verbose_body
        assert "\\u001b[36mredis\\u001b[0m" in verbose_body
        assert json_resp.status_code == 200
        assert '\\"run_id\\": \\"run-abcdef123456\\"' in json_body
        assert '\\"source\\": \\"redis\\"' in json_body
        assert '\\"elapsed\\":' in json_body
        assert '\\"resource_usage\\": {\\"cpu_seconds\\": 12.345, \\"memory_bytes\\": 1536, \\"process_count\\": 2}' in json_body

    def test_builtin_runs_reports_when_no_active_runs_exist(self):
        client = get_client()

        with mock.patch("builtin_commands.active_runs_for_session", return_value=[]):
            resp = _post_run(client, json={"command": "runs"}, headers={"X-Session-ID": "sess-runs"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "No active runs.\\n" in body

    def test_builtin_man_renders_real_page_for_allowed_topic(self):
        client = get_client()

        fake_proc = mock.Mock(returncode=0, stdout="NAME\ncurl - transfer a URL\n", stderr="")
        with mock.patch("builtin_commands.runtime_missing_command_name", side_effect=[None, None]), \
             mock.patch("builtin_commands.resolve_runtime_command", return_value="/usr/bin/man"), \
             mock.patch("builtin_commands.subprocess.run", return_value=fake_proc):
            resp = _post_run(client, json={"command": "man curl"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "NAME\\n" in body
        assert "curl - transfer a URL\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_man_does_not_clip_to_max_output_lines(self):
        client = get_client()
        man_text = "\n".join(f"line {index}" for index in range(1, 6)) + "\n"
        fake_proc = mock.Mock(returncode=0, stdout=man_text, stderr="")
        with mock.patch("builtin_commands.runtime_missing_command_name", side_effect=[None, None]), \
             mock.patch("builtin_commands.resolve_runtime_command", return_value="/usr/bin/man"), \
             mock.patch("builtin_commands.subprocess.run", return_value=fake_proc), \
             mock.patch("builtin_commands.CFG", {**shell_app.CFG, "max_output_lines": 2}):
            resp = _post_run(client, json={"command": "man curl"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "line 5\\n" in body
        assert "man page clipped" not in body
        assert '"type": "exit"' in body

    def test_builtin_man_reports_when_helper_binary_is_unavailable(self):
        client = get_client()

        with mock.patch("builtin_commands.runtime_missing_command_name", return_value="man"):
            resp = _post_run(client, json={"command": "man curl"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Command is not installed on this instance: man\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_man_reports_when_allowlisted_topic_is_missing(self):
        client = get_client()

        with mock.patch("builtin_commands.runtime_missing_command_name", side_effect=[None, "curl"]), \
             mock.patch("builtin_commands.resolve_runtime_command", return_value="/usr/bin/man"), \
             mock.patch("builtin_commands.subprocess.run") as run_cmd:
            resp = _post_run(client, json={"command": "man curl"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Command is not installed on this instance: curl\\n" in body
        assert '"type": "exit"' in body
        run_cmd.assert_not_called()

    def test_builtin_man_rejects_topics_outside_allowlist(self):
        client = get_client()

        resp = _post_run(client, json={"command": "man rm"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "man is only available for allowed commands. Topic not allowed: rm\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_man_for_built_in_topic_returns_shell_help(self):
        client = get_client()

        resp = _post_run(client, json={"command": "man history"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Built-in command:\\n" not in body
        assert "Built-in commands:\\n" in body
        assert "history    List recent commands from this session.\\n" in body

    def test_builtin_man_for_shortcuts_topic_returns_web_shell_help(self):
        client = get_client()

        resp = _post_run(client, json={"command": "man shortcuts"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Built-in commands:\\n" in body
        assert "shortcuts  Show current keyboard shortcuts.\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_history_lists_recent_session_commands(self):
        client = get_client()
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-h1", "sess-history", "ping darklab.sh", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:03+00:00", 0, "[]")
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-h2", "sess-history", "dig darklab.sh A", "2026-01-01T00:00:05+00:00", "2026-01-01T00:00:06+00:00", 0, "[]")
            )
            conn.commit()

        resp = _post_run(client, json={"command": "history"}, headers={"X-Session-ID": "sess-history"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Recent commands:\\n" in body
        assert "1  ping darklab.sh\\n" in body
        assert "2  dig darklab.sh A\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_history_honors_recent_commands_limit(self):
        client = get_client()
        with db_connect() as conn:
            for index in range(1, 6):
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"run-limit-{index}",
                        "sess-history-limit",
                        f"cmd {index}",
                        f"2026-01-01T00:00:0{index}+00:00",
                        f"2026-01-01T00:00:1{index}+00:00",
                        0,
                        "[]",
                    ),
                )
            conn.commit()

        with mock.patch.dict("builtin_commands.CFG", {"recent_commands_limit": 3}):
            resp = _post_run(
                client,
                json={"command": "history"},
                headers={"X-Session-ID": "sess-history-limit"},
            )
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "1  cmd 3\\n" in body
        assert "2  cmd 4\\n" in body
        assert "3  cmd 5\\n" in body
        assert "cmd 1\\n" not in body
        assert "cmd 2\\n" not in body
        assert '"type": "exit"' in body

    def test_builtin_pwd_returns_synthetic_path(self):
        client = get_client()

        with mock.patch("builtin_commands.CFG", {**shell_app.CFG, "workspace_enabled": False}):
            resp = _post_run(client, json={"command": "pwd"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert f"/app/{shell_app.CFG['app_name']}/bin\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_pwd_returns_workspace_root_when_workspace_enabled(self):
        client = get_client()

        with mock.patch("builtin_commands.CFG", {**shell_app.CFG, "workspace_enabled": True}):
            resp = _post_run(client, json={"command": "pwd"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"text": "/\\n"' in body
        assert f"/app/{shell_app.CFG['app_name']}/bin\\n" not in body
        assert '"type": "exit"' in body

    def test_builtin_uname_a_returns_web_shell_environment(self):
        client = get_client()

        resp = _post_run(client, json={"command": "uname -a"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert f"{shell_app.CFG['app_name']} Linux web-terminal x86_64 app-runtime\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_uname_without_flags_returns_kernel_name(self):
        client = get_client()

        resp = _post_run(client, json={"command": "uname"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Linux\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_xyzzy_coffee_and_fork_bomb_easter_eggs(self):
        client = get_client()

        xyzzy_resp = _post_run(client, json={"command": "xyzzy"})
        xyzzy_body = xyzzy_resp.get_data(as_text=True)
        coffee_resp = _post_run(client, json={"command": "coffee"})
        coffee_body = coffee_resp.get_data(as_text=True)
        fork_resp = _post_run(client, json={"command": ":(){ :|:& };:"})
        fork_body = fork_resp.get_data(as_text=True)

        assert xyzzy_resp.status_code == 200
        assert "Nothing happens.\\n" in xyzzy_body
        assert coffee_resp.status_code == 200
        assert "HTTP/1.1 418 I'm a teapot\\n" in coffee_body
        assert "Brewing coffee with a teapot is unsupported.\\n" in coffee_body
        assert fork_resp.status_code == 200
        assert "bash: fork bomb politely declined\\n" in fork_body
        assert "system remains operational\\n" in fork_body

    def test_builtin_id_returns_synthetic_identity(self):
        client = get_client()

        resp = _post_run(client, json={"command": "id"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert (
            f"uid=1000({shell_app.CFG['app_name']}) gid=1000({shell_app.CFG['app_name']}) "
            f"groups=1000({shell_app.CFG['app_name']})\\n"
        ) in body
        assert '"type": "exit"' in body

    def test_builtin_whoami_streams_project_description(self):
        client = get_client()

        resp = _post_run(client, json={"command": "whoami"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert f"{shell_app.CFG['app_name']}\\n" in body
        assert f"README: see the project README at {PROJECT_README}\\n" in body
        assert '"type": "exit"' in body

    def test_builtin_ps_lists_active_session_processes(self):
        client = get_client()

        resp = _post_run(client, json={"command": "ps aux"}, headers={"X-Session-ID": "sess-ps"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "\\u001b[4mPID\\u001b[0m" in body
        assert "\\u001b[4mCMD\\u001b[0m\\n" in body
        assert " 9000 pts/0    R    -        ps aux\\n" in body
        assert '"type": "exit"' in body

    def test_run_reports_missing_allowlisted_command_without_spawning(self):
        client = get_client()

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.rewrite_command", return_value=("nmap -sV darklab.sh", None)), \
             mock.patch("blueprints.run.runtime_missing_command_name", return_value="nmap"), \
             mock.patch("blueprints.run.subprocess.Popen") as popen:
            resp = _post_run(client, json={"command": "nmap -sV darklab.sh"}, headers={"X-Session-ID": "sess-missing"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert "Command is not installed on this instance: nmap\\n" in body
        assert '"type": "exit"' in body
        popen.assert_not_called()

        hist = client.get("/history", headers={"X-Session-ID": "sess-missing"})
        data = json.loads(hist.data)
        assert [r["command"] for r in data["runs"]] == ["nmap -sV darklab.sh"]

    def test_run_checks_missing_binary_after_rewrite(self):
        client = get_client()
        client.environ_base["HTTP_X_FORWARDED_FOR"] = "2001:db8:ffff:eeee:dddd:cccc:bbbb:aaaa"

        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.rewrite_command", return_value=("nmap -sT -sV darklab.sh", None)), \
             mock.patch("blueprints.run.runtime_missing_command_name", return_value="nmap"), \
             mock.patch("blueprints.run.subprocess.Popen") as popen:
            resp = _post_run(client, json={"command": "nmap -sV darklab.sh"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Command is not installed on this instance: nmap\\n" in body
        assert '"type": "exit"' in body
        popen.assert_not_called()

    def test_run_rewrites_workspace_file_flags_and_emits_notices(self, tmp_path):
        client = get_client()
        session_id = "sess-workspace-run"
        fake_proc = _FakeProc(lines=["scan complete\n", ""])
        cfg = {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(tmp_path),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
            "workspace_inactivity_ttl_hours": 1,
        }
        registry = {
            "commands": [
                {
                    "root": "nmap",
                    "category": "Scanning",
                    "policy": {"allow": ["nmap"], "deny": ["nmap -iL", "nmap -oN"]},
                    "workspace_flags": [
                        {"flag": "-iL", "mode": "read", "value": "separate"},
                        {"flag": "-oN", "mode": "write", "value": "separate"},
                    ],
                    "runtime_adaptations": {
                        "inject_flags": [
                            {
                                "flags": ["-sT"],
                                "position": "prepend",
                                "unless_any": ["-h", "--help", "-V", "--version"],
                                "unless_any_regex": ["^-s[AFILMNOSTUWXYZn]"],
                            },
                        ],
                    },
                },
            ],
            "pipe_helpers": [],
        }
        from workspace import session_workspace_name, write_workspace_text_file
        write_workspace_text_file(session_id, "targets.txt", "ip.darklab.sh\n", cfg)
        workspace_dir = tmp_path / session_workspace_name(session_id)

        with mock.patch("config.CFG", {**shell_app.CFG, **cfg}), \
             mock.patch("blueprints.run.CFG", {**shell_app.CFG, **cfg}), \
             mock.patch("commands.load_commands_registry", return_value=registry), \
             mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc) as popen, \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]):
            resp = _post_run(
                client,
                json={"command": "nmap -iL targets.txt -oN scan.txt"},
                headers={"X-Session-ID": session_id},
            )
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        launched = popen.call_args.args[0]
        shell_command = launched[-1]
        assert str(workspace_dir / "targets.txt") in shell_command
        assert str(workspace_dir / "scan.txt") in shell_command
        assert "nmap -sT" in shell_command
        assert "--privileged" not in shell_command
        assert "nmap -iL targets.txt -oN scan.txt" not in shell_command
        assert "[workspace] reading targets.txt" in body
        assert "[workspace] writing scan.txt" in body
        assert "scan complete\\n" in body
        hist = client.get("/history", headers={"X-Session-ID": session_id})
        data = json.loads(hist.data)
        assert data["runs"][0]["command"] == "nmap -iL targets.txt -oN scan.txt"

    def test_run_injects_projectdiscovery_workspace_state_and_surfaces_paths(self, tmp_path):
        client = get_client()
        session_id = "sess-projectdiscovery-run"
        cfg = {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(tmp_path),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
            "workspace_inactivity_ttl_hours": 1,
        }
        from workspace import session_workspace_name
        workspace_dir = tmp_path / session_workspace_name(session_id)
        resume_path = workspace_dir / "katana" / "resume-abcd.cfg"
        fake_proc = _FakeProc(lines=[f"Creating resume file: {resume_path}\n", ""])
        registry = {
            "commands": [
                {
                    "root": "katana",
                    "category": "Network Reconnaissance",
                    "policy": {"allow": ["katana"], "deny": []},
                    "runtime_adaptations": {
                        "inject_flags": [
                            {
                                "flags": ["env", "XDG_CONFIG_HOME={session_workspace}"],
                                "position": "command_prefix",
                                "requires_workspace": True,
                            },
                        ],
                    },
                },
            ],
            "pipe_helpers": [],
        }

        with mock.patch("config.CFG", {**shell_app.CFG, **cfg}), \
             mock.patch("blueprints.run.CFG", {**shell_app.CFG, **cfg}), \
             mock.patch("commands.load_commands_registry", return_value=registry), \
             mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc) as popen, \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]):
            resp = _post_run(
                client,
                json={"command": "katana -u https://ip.darklab.sh -d 1"},
                headers={"X-Session-ID": session_id},
            )
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        launched = popen.call_args.args[0]
        shell_command = launched[-1]
        assert f"XDG_CONFIG_HOME={workspace_dir}" in shell_command
        assert "katana -u https://ip.darklab.sh -d 1" in shell_command
        assert str(workspace_dir) not in body
        assert "Creating resume file: /katana/resume-abcd.cfg" in body

    def test_session_variables_expand_before_validation_and_preserve_typed_history(self):
        client = get_client()
        session_id = "sess-vars-run"
        set_resp = _post_run(
            client,
            json={"command": "var set HOST ip.darklab.sh"},
            headers={"X-Session-ID": session_id},
        )
        assert set_resp.status_code == 200

        fake_proc = _FakeProc(lines=["scan complete\n", ""])
        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.rewrite_command", side_effect=lambda command, **_: (command, None)), \
             mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc) as popen, \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]):
            resp = _post_run(
                client,
                json={"command": "nmap -sV $HOST"},
                headers={"X-Session-ID": session_id},
            )
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "[vars] expanded $HOST: nmap -sV ip.darklab.sh" in body
        assert popen.call_args.args[0][-1] == "nmap -sV ip.darklab.sh"
        hist = client.get("/history", headers={"X-Session-ID": session_id})
        data = json.loads(hist.data)
        assert data["runs"][0]["command"] == "nmap -sV $HOST"

    def test_session_variables_reject_undefined_reference_before_spawn(self):
        client = get_client()
        with mock.patch("blueprints.run.subprocess.Popen") as popen:
            resp = _post_run(
                client,
                json={"command": "nmap -sV $HOST"},
                headers={"X-Session-ID": "sess-undefined-var"},
            )

        assert resp.status_code == 403
        assert resp.get_json()["error"] == "undefined session variable: $HOST"
        popen.assert_not_called()

    def test_session_variables_validate_policy_after_expansion(self):
        client = get_client()
        session_id = "sess-vars-policy"
        _post_run(
            client,
            json={"command": "var set HOST blocked.darklab.sh"},
            headers={"X-Session-ID": session_id},
        )

        def _deny_expanded(command, session_id=None, cfg=None, workspace_cwd=""):  # noqa: ARG001
            assert command == "curl https://blocked.darklab.sh"
            return run_routes.CommandValidationResult(
                False,
                "blocked after expansion",
                display_command=command,
                exec_command=command,
            )

        with mock.patch("blueprints.run.validate_command", side_effect=_deny_expanded), \
             mock.patch("blueprints.run.subprocess.Popen") as popen:
            resp = _post_run(
                client,
                json={"command": "curl https://$HOST"},
                headers={"X-Session-ID": session_id},
            )

        assert resp.status_code == 403
        assert resp.get_json()["error"] == "blocked after expansion"
        popen.assert_not_called()


class TestRunOutputArtifacts:
    def _insert_run_with_artifact(self, run_id, session_id="sess-artifact"):
        ensure_run_output_dir()
        artifact_path = Path(RUN_OUTPUT_DIR) / f"{run_id}.txt.gz"
        with gzip.open(artifact_path, "wt", encoding="utf-8") as handle:
            handle.write("line 1\nline 2\n")

        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, output_preview, preview_truncated, "
                "output_line_count, full_output_available, full_output_truncated) "
                "VALUES (?, ?, ?, datetime('now'), ?, 1, 2, 1, 0)",
                (run_id, session_id, "nmap -sV 10.0.0.1", json.dumps(["line 2"])),
            )
            conn.execute(
                "INSERT INTO run_output_artifacts (run_id, rel_path, compression, byte_size, line_count, truncated, created) "
                "VALUES (?, ?, 'gzip', 14, 2, 0, datetime('now'))",
                (run_id, f"{run_id}.txt.gz"),
            )
            conn.commit()
        return artifact_path

    def test_delete_run_removes_output_artifact(self):
        client = get_client()
        artifact_path = self._insert_run_with_artifact("artifact-delete-run", session_id="sess-delete-artifact")
        assert os.path.exists(artifact_path)

        resp = client.delete("/history/artifact-delete-run", headers={"X-Session-ID": "sess-delete-artifact"})

        assert resp.status_code == 200
        assert not os.path.exists(artifact_path)
        with db_connect() as conn:
            assert (
                conn.execute(
                    "SELECT 1 FROM run_output_artifacts WHERE run_id = ?",
                    ("artifact-delete-run",),
                ).fetchone()
                is None
            )

    def test_clear_history_removes_output_artifacts_for_session(self):
        client = get_client()
        artifact_a = self._insert_run_with_artifact("artifact-clear-a", session_id="sess-clear-artifact")
        artifact_b = self._insert_run_with_artifact("artifact-clear-b", session_id="sess-clear-artifact")
        assert os.path.exists(artifact_a)
        assert os.path.exists(artifact_b)

        resp = client.delete("/history", headers={"X-Session-ID": "sess-clear-artifact"})

        assert resp.status_code == 200
        assert not os.path.exists(artifact_a)
        assert not os.path.exists(artifact_b)
        with db_connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM run_output_artifacts").fetchone()[0] == 0


# ── /history isolation ────────────────────────────────────────────────────────

class TestHistoryIsolation:
    def test_history_only_returns_runs_for_current_session(self):
        client = get_client()
        run_a = f"hist-a-{uuid.uuid4()}"
        run_b = f"hist-b-{uuid.uuid4()}"

        try:
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                    "VALUES (?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
                    (run_a, "session-a", "echo A", 0, "[]")
                )
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                    "VALUES (?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
                    (run_b, "session-b", "echo B", 0, "[]")
                )
                conn.commit()

            resp = client.get("/history", headers={"X-Session-ID": "session-a"})
            data = json.loads(resp.data)
            commands = [r["command"] for r in data["runs"]]

            assert "echo A" in commands
            assert "echo B" not in commands
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id IN (?, ?)", (run_a, run_b))
                conn.commit()

    def test_delete_run_only_deletes_for_matching_session(self):
        client = get_client()
        run_id = f"owned-run-{uuid.uuid4()}"

        try:
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                    "VALUES (?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
                    (run_id, "owner-session", "echo owner", 0, "[]")
                )
                conn.commit()

            # Wrong session should not delete
            resp = client.delete(f"/history/{run_id}", headers={"X-Session-ID": "other-session"})
            assert resp.status_code == 200

            with db_connect() as conn:
                row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
            assert row is not None

            # Correct session should delete
            resp = client.delete(f"/history/{run_id}", headers={"X-Session-ID": "owner-session"})
            assert resp.status_code == 200

            with db_connect() as conn:
                row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
            assert row is None
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()


# ── /share ────────────────────────────────────────────────────────────────────

class TestShareRoundTrip:
    def test_share_json_roundtrip_preserves_structured_content(self):
        client = get_client()
        payload = {
            "label": "test snapshot",
            "content": [
                {"text": "$ echo hi", "cls": "cmd"},
                {
                    "text": "hi",
                    "cls": "out",
                    "signals": ["findings"],
                    "line_index": 0,
                    "command_root": "echo",
                    "target": "darklab.sh",
                },
                {"text": "done", "cls": "notice"},
            ],
        }

        resp = client.post("/share", json=payload, headers={"X-Session-ID": "share-session"})
        assert resp.status_code == 200
        created = json.loads(resp.data)
        assert "id" in created

        fetch = client.get(f"/share/{created['id']}?json")
        assert fetch.status_code == 200
        data = json.loads(fetch.data)

        assert data["label"] == "test snapshot"
        assert data["content"] == payload["content"]
        assert data["session_id"] == "share-session"
