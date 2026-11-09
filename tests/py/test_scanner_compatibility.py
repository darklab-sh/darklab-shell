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
from services.assessments.schemathesis_schema import review_local_openapi_json


pytestmark = pytest.mark.skipif(os.environ.get("RUN_SCANNER_COMPATIBILITY") != "1",
                                reason="requires the isolated scanner environment")


@pytest.mark.parametrize("findings", [False, True])
def test_real_scanner_report_obeys_reviewed_command_and_privacy(tmp_path, findings):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            value = parse_qs(urlsplit(self.path).query).get("limit", [""])[0]
            valid = value.isascii() and value.isdecimal() and len(value) < 4 and 1 <= int(value) <= 3
            self.send_response(500 if findings else 200 if valid else 400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"private":"private-response-body"}')

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    response = {"description": "Fixture", "content": {"application/json": {"schema": {"type": "object"}}}}
    source = json.dumps({"openapi": "3.0.3", "info": {"title": "Disposable fixture", "version": "1.0"},
                         "servers": [{"url": base}], "paths": {"/items": {"get": {
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
        assert result.returncode == (1 if findings else 0), result.stdout + result.stderr
        parsed = parse_schemathesis_ndjson(report.read_bytes(), reviewed, profile_key="api", profile_version="1.0")
        assert parsed.complete
        assert parsed.case_count > 0
        assert bool(parsed.failure_count) is findings
        assert "private-response-body" not in repr(parsed)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
