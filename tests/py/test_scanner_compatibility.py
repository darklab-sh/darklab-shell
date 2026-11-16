# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Opt-in qualification of the real isolated scanner and reviewed report parser."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import shlex
import subprocess
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from services.assessments.schemathesis_command import reviewed_schemathesis_command_plan
from services.assessments.schemathesis_report import parse_schemathesis_ndjson
from services.assessments.schemathesis_report_contracts import SCHEMATHESIS_REPORT_TOOL_VERSION, SchemathesisReportError
from services.assessments.schemathesis_schema import review_local_openapi_json


pytestmark = pytest.mark.skipif(os.environ.get("RUN_SCANNER_COMPATIBILITY") != "1",
                                reason="requires the isolated scanner environment")


@pytest.mark.parametrize("schema_version", ["3.0.3", "3.1.0"])
@pytest.mark.parametrize(("method", "expected_check"), [
    ("get", None), ("get", "not_a_server_error"), ("get", "status_code_conformance"),
    ("get", "content_type_conformance"), ("get", "response_schema_conformance"),
    ("get", "negative_data_rejection"), ("head", None), ("head", "not_a_server_error"),
], ids=["clean", "server-error", "status-code", "content-type", "schema-violation", "invalid-accepted", "head", "head-error"])
def test_real_scanner_report_obeys_reviewed_command_and_privacy(tmp_path, schema_version, method, expected_check):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            value = parse_qs(urlsplit(self.path).query).get("limit", [""])[0]
            valid = value.isascii() and value.isdecimal() and len(value) < 4 and 1 <= int(value) <= 3
            status = {"not_a_server_error": 500, "status_code_conformance": 418, "negative_data_rejection": 200}.get(
                expected_check, 200 if valid else 400)
            self.send_response(status)
            self.send_header("Content-Type", "text/plain" if expected_check == "content_type_conformance" else "application/json")
            self.end_headers()
            ok = "invalid-boolean" if expected_check == "response_schema_conformance" else True
            if self.command != "HEAD":
                self.wfile.write(json.dumps({"ok": ok, "private": "private-response-body"}).encode())

        do_HEAD = do_GET

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    response = {"description": "Fixture", "content": {"application/json": {"schema": {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "private": {"type": "string"}},
        "required": ["ok", "private"],
    }}}}
    source = json.dumps({"openapi": schema_version, "info": {"title": "Disposable fixture", "version": "1.0"},
                         "servers": [{"url": base}], "paths": {"/items": {method: {
                             "parameters": [{"name": "limit", "in": "query", "required": True,
                                             "schema": {"type": "integer", "minimum": 1, "maximum": 3}}],
                             "responses": {"200": response, "400": response},
                         }}}}).encode()
    reviewed = review_local_openapi_json(source, source_artifact_id="rfa_0123456789abcdef", base_url=base)
    folder = tmp_path / "private-http-runs/run-qualification"
    folder.mkdir(parents=True)
    schema, config, report = (folder / name for name in ("schema.json", "schemathesis.toml", "events.ndjson"))
    schema.write_bytes(source)
    config.write_text('[cache]\nenabled = false\n\n[generation]\ndatabase = "none"\n')
    plan = reviewed_schemathesis_command_plan(reviewed, schema_path=schema, config_path=config, report_path=report)
    assert plan is not None
    command = shlex.split(plan.command)
    command[0] = os.environ["SCHEMATHESIS_BINARY"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
        (folder / "scanner.log").write_text(result.stdout + result.stderr)
        assert result.returncode == (1 if expected_check else 0), result.stdout + result.stderr
        raw = report.read_bytes()
        parsed = parse_schemathesis_ndjson(raw, reviewed, profile_key="api", profile_version="1.0")
        assert parsed.complete
        assert parsed.tool_version == SCHEMATHESIS_REPORT_TOOL_VERSION
        assert parsed.expected_operation_count == parsed.observed_operation_count == 1
        assert parsed.missing_operations == ()
        assert parsed.operations[0].operation == f"{method.upper()} /items"
        assert parsed.case_count > 0
        assert bool(parsed.failure_count) is bool(expected_check)
        if expected_check:
            assert any(failure.check_name == expected_check for operation in parsed.operations for failure in operation.failures)
        assert "private-response-body" not in repr(parsed)
        assert "invalid-boolean" not in repr(parsed)
        # Exercise report boundaries with actual emitted events as well as synthetic fixtures.
        with pytest.raises(SchemathesisReportError) as rejected:
            parse_schemathesis_ndjson(b"\n".join(raw.splitlines()[:-1]) + b"\n", reviewed,
                                     profile_key="api", profile_version="1.0")
        assert rejected.value.code == "invalid_report_boundaries"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
