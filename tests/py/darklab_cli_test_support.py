# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[2]
CLI_SRC = ROOT_DIR / "tools" / "darklab_cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))


def load_cli_main():
    return import_module("darklab_cli.__main__")


def install_cli_harness(monkeypatch):
    cli_main = load_cli_main()
    osv_requests = []
    finding_requests = []
    http_profile_requests = []
    class FakeResponse:
        def __iter__(self):
            yield b'{"type":"schema","event":"schema","v":1,"kind":"line_event"}\n'
            yield b'{"type":"output","event":"output","text":"ok","v":1,"kind":"info","role":"body","event_id":"1-0"}\n'
            yield b'{"type":"exit","code":0,"event_id":"2-0"}\n'

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, stream=False):
            if path == "/advisories/osv/lookup":
                assert method == "POST"
                assert params is None
                assert stream is False
                assert isinstance(body, dict)
                assert set(body) == {"purl", "version"}
                osv_requests.append(body)
                error_code = {
                    "pkg:pypi/forbidden": ("team_forbidden", 403),
                    "pkg:pypi/disabled": ("osv_lookup_disabled", 409),
                    "pkg:pypi/busy": ("osv_lookup_busy", 429),
                    "pkg:pypi/provider-failure": ("osv_lookup_failed", 503),
                }.get(body["purl"])
                if error_code:
                    code, status = error_code
                    raise cli_main.DarklabCliError(
                        f"{code}: rejected",
                        status=status,
                        code=code,
                    )
                return {
                    "ok": True,
                    "source": "osv",
                    "outcome": "negative_cached",
                    "record_count": 0,
                }
            if path == "/whoami":
                return {"token_created": "2026-05-19 00:00:00", "last_seen_at": "2026-05-19 00:00:01"}
            if path == "/projects":
                return {
                    "projects": [{
                        "id": "prj_cli",
                        "name": "CLI Project",
                        "slug": "cli-project",
                        "status": "active",
                    }],
                    "has_more": False,
                }
            if path == "/projects/prj_cli/http-profiles" and method == "POST":
                assert params is None
                assert isinstance(body, dict)
                http_profile_requests.append((method, path, body))
                if body.get("name") == "Forbidden profile":
                    raise cli_main.DarklabCliError(
                        "team_forbidden: denied",
                        status=403,
                        code="team_forbidden",
                    )
                if body.get("name") == "Duplicate profile":
                    raise cli_main.DarklabCliError(
                        "http_profile_conflict: duplicate",
                        status=409,
                        code="http_profile_conflict",
                    )
                secret_refs = {
                    key: {"name": value, "available": True}
                    for key, value in body.get("secret_refs", {}).items()
                }
                return {"ok": True, "profile": {
                    "id": "htp_created",
                    "name": body.get("name"),
                    "role": body.get("role", "anonymous"),
                    "base_url": body.get("base_url"),
                    "enabled": body.get("enabled", True),
                    "revision": 1,
                    "protected_references_visible": True,
                    "headers": body.get("headers", []),
                    "secret_refs": secret_refs,
                    "file_refs": body.get("file_refs", {}),
                    "reference_counts": {
                        "headers": len(body.get("headers", [])),
                        "secret_refs": len(secret_refs),
                        "file_refs": len(body.get("file_refs", {})),
                    },
                }}
            if path == "/projects/prj_cli/http-profiles" and method == "GET":
                assert params is None
                http_profile_requests.append((method, path, body))
                return {
                    "profiles": [{
                        "id": "htp_cli",
                        "name": "Authenticated API",
                        "role": "authenticated",
                        "base_url": "https://api.example.com",
                        "enabled": True,
                        "revision": 3,
                        "protected_references_visible": True,
                        "reference_counts": {
                            "headers": 1,
                            "secret_refs": 1,
                            "file_refs": 1,
                            "scope_roots": 1,
                            "allowed_hosts": 1,
                            "capture_rules": 0,
                        },
                    }],
                    "total": 1,
                }
            if path == "/projects/prj_cli/http-profiles/htp_cli" and method == "GET":
                http_profile_requests.append((method, path, body))
                return {"profile": {
                    "id": "htp_cli",
                    "name": "Authenticated API",
                    "role": "authenticated",
                    "base_url": "https://api.example.com",
                    "enabled": True,
                    "revision": 3,
                    "protected_references_visible": True,
                    "header_names": ["Authorization"],
                    "headers": [{"name": "Authorization", "secret_name": "API_TOKEN"}],
                    "secret_refs": {"api_token": "API_TOKEN"},
                    "file_refs": {"client_cert": "certs/client.pem"},
                    "reference_counts": {
                        "headers": 1,
                        "secret_refs": 1,
                        "file_refs": 1,
                        "scope_roots": 1,
                        "allowed_hosts": 1,
                        "capture_rules": 0,
                    },
                }}
            if path == "/projects/prj_cli/http-profiles/htp_viewer" and method == "GET":
                http_profile_requests.append((method, path, body))
                return {"profile": {
                    "id": "htp_viewer",
                    "name": "Viewer-safe API",
                    "role": "authenticated",
                    "base_url": "https://api.example.com",
                    "enabled": True,
                    "revision": 3,
                    "protected_references_visible": False,
                    "header_names": ["Authorization"],
                    "credential_use": ["headers", "secret_refs", "file_refs"],
                    "reference_counts": {"headers": 1, "secret_refs": 1, "file_refs": 1},
                }}
            if path == "/projects/prj_cli/http-profiles/htp_cli" and method == "PATCH":
                assert isinstance(body, dict)
                http_profile_requests.append((method, path, body))
                if body.get("revision") == 2:
                    raise cli_main.DarklabCliError(
                        "http_profile_conflict: stale revision",
                        status=409,
                        code="http_profile_conflict",
                    )
                return {"ok": True, "profile": {
                    "id": "htp_cli",
                    "name": "Authenticated API",
                    "role": "authenticated",
                    "base_url": "https://api.example.com",
                    "enabled": body.get("enabled", True),
                    "revision": 4,
                    "protected_references_visible": True,
                    "reference_counts": {"headers": 1, "secret_refs": 1, "file_refs": 1},
                }}
            if path == "/projects/prj_cli/http-profiles/htp_cli" and method == "DELETE":
                http_profile_requests.append((method, path, body))
                return {"ok": True, "removed": True}
            if path == "/history":
                if params and params.get("run_kind"):
                    assert params == {
                        "project_id": None,
                        "since": None,
                        "until": None,
                        "limit": 50,
                        "offset": 0,
                        "run_kind": "external",
                    }
                    return {
                        "runs": [{
                            "id": "run_external",
                            "status": "succeeded",
                            "exit_code": 0,
                            "finished": "2026-05-19T00:00:03+00:00",
                            "command": "nmap darklab.sh",
                        }],
                    }
                assert params == {
                    "project_id": None,
                    "since": None,
                    "until": None,
                    "limit": 50,
                    "offset": 0,
                }
                return {
                    "runs": [
                        {
                            "id": "run_cli",
                            "status": "succeeded",
                            "exit_code": 0,
                            "finished": "2026-05-19T00:00:02+00:00",
                            "command": "echo ok",
                        },
                        {
                            "id": "run_old",
                            "status": "succeeded",
                            "exit_code": 0,
                            "finished": "2026-05-19T00:00:01+00:00",
                            "command": "date",
                        },
                    ],
                }
            if path == "/history/search":
                assert params == {
                    "project_id": None,
                    "since": None,
                    "until": None,
                    "limit": 50,
                    "offset": 0,
                    "q": "needle",
                    "context": 1,
                }
                return {
                    "matches": [
                        {
                            "run_id": "run_cli",
                            "command": "echo needle",
                            "line_number": 2,
                            "line": "needle here",
                            "context_before": ["before"],
                            "context_after": ["after"],
                        }
                    ],
                    "total": 1,
                    "limit": 50,
                    "offset": 0,
                    "has_more": False,
                    "query": "needle",
                    "context": 1,
                }
            if path == "/runs/run_cli/output":
                assert params == {"format": "text", "range": None}
                return "ok\n"
            if path == "/runs/run_cli/stream" and stream:
                assert params == {"format": "ndjson", "after": "1-0"}
                return FakeResponse()
            if path == "/runs/run_cli/service-evidence":
                assert params == {"limit": 25, "offset": 5}
                return {
                    "observations": [{
                        "id": "nse_cli",
                        "target": "104.161.46.133:443/tcp",
                        "service": "https",
                        "script_id": "ssl-cert",
                        "evidence_kind": "certificate",
                        "fields": [{"path": ["subject", "common_name"], "value": "darklab.sh"}],
                        "observed_at": "2026-05-19T00:00:04+00:00",
                    }],
                    "total": 1,
                    "limit": 25,
                    "offset": 5,
                    "has_more": False,
                }
            if path == "/runs/run_empty/service-evidence":
                assert params == {"limit": 50, "offset": 0}
                return {
                    "observations": [],
                    "total": 0,
                    "limit": 50,
                    "offset": 0,
                    "has_more": False,
                }
            if path == "/projects/prj_cli/findings" and method == "POST":
                assert params is None
                assert isinstance(body, dict)
                finding_requests.append((method, path, body))
                if body.get("title") == "Forbidden finding":
                    raise cli_main.DarklabCliError(
                        "team_forbidden: denied",
                        status=403,
                        code="team_forbidden",
                    )
                if body.get("title") == "Possible duplicate" and not body.get(
                    "allow_duplicate"
                ):
                    raise cli_main.DarklabCliError(
                        "possible_duplicate",
                        status=409,
                        code="possible_duplicate",
                        details={"duplicates": [{"id": "fnd_existing"}]},
                    )
                return {
                    "ok": True,
                    "created": True,
                    "duplicate_override": bool(body.get("allow_duplicate")),
                    "finding": {
                        "id": "fnd_manual_cli",
                        "manual_revision": 1,
                        "severity": body.get("severity"),
                        "title": body.get("title"),
                        "target_id": body.get("target_id"),
                    },
                }
            if path == "/projects/prj_cli/findings/fnd_manual_cli" and method == "PATCH":
                assert params is None
                assert isinstance(body, dict)
                finding_requests.append((method, path, body))
                if body.get("expected_revision") == 0:
                    raise cli_main.DarklabCliError(
                        "stale_revision",
                        status=409,
                        code="stale_revision",
                        details={"current_revision": 2},
                    )
                return {
                    "ok": True,
                    "updated": True,
                    "duplicate_override": False,
                    "changed_fields": ["summary"],
                    "finding": {
                        "id": "fnd_manual_cli",
                        "manual_revision": 2,
                        "severity": "high",
                        "title": "Manual CLI finding",
                        "target_id": "ent_cli",
                    },
                }
            evidence_path = "/projects/prj_cli/findings/fnd_manual_cli/evidence"
            if path == evidence_path and method == "GET":
                return {
                    "evidence": [{
                        "id": "fev_cli",
                        "evidence_type": "run",
                        "evidence_id": "run_cli",
                        "line_number": -1,
                        "source_state": "available",
                        "label": "echo ok",
                    }],
                    "total": 1,
                    "verification": {},
                }
            if path == evidence_path and method == "POST":
                assert isinstance(body, dict)
                finding_requests.append((method, path, body))
                if body.get("evidence_id") == "run_forbidden":
                    raise cli_main.DarklabCliError(
                        "team_forbidden: denied",
                        status=403,
                        code="team_forbidden",
                    )
                created = body.get("evidence_id") != "run_cli"
                return {
                    "ok": True,
                    "created": created,
                    "evidence": {
                        "id": "fev_new" if created else "fev_cli",
                        "evidence_type": body.get("evidence_type"),
                        "evidence_id": body.get("evidence_id"),
                        "line_number": body.get("line_number", -1),
                        "source_state": "available",
                        "label": body.get("snippet") or "saved source",
                    },
                }
            if path == evidence_path + "/fev_cli" and method == "DELETE":
                finding_requests.append((method, path, body))
                return {
                    "ok": True,
                    "evidence": {
                        "id": "fev_cli",
                        "evidence_type": "run",
                        "evidence_id": "run_cli",
                        "line_number": -1,
                        "source_state": "unavailable",
                        "label": "run_cli",
                    },
                }
            if path == "/risk/feeds":
                assert method == "GET"
                assert params is None
                return {
                    "feeds": [
                        {
                            "source": "epss",
                            "status": "stale",
                            "origin": "bundled",
                            "source_version": "v-old:2020-01-01",
                            "model_version": "v-old",
                            "published_at": "2020-01-01T00:00:00Z",
                            "retrieved_at": "2020-01-01T00:00:00Z",
                            "accepted_at": "2020-01-01T00:00:00Z",
                            "age_hours": 58000.0,
                            "record_count": 1,
                            "last_attempt_at": "",
                            "last_error": "",
                            "source_url": "https://epss.cyentia.com/epss_scores-current.csv.gz",
                            "attribution": "FIRST EPSS",
                            "terms_url": "https://www.first.org/epss/model",
                            "live_refresh_enabled": False,
                        },
                        {
                            "source": "kev",
                            "status": "unavailable",
                            "origin": "unavailable",
                            "source_version": "",
                            "model_version": "",
                            "published_at": "",
                            "retrieved_at": "",
                            "accepted_at": "",
                            "age_hours": None,
                            "record_count": 0,
                            "last_attempt_at": "",
                            "last_error": "",
                            "source_url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
                            "attribution": "CISA KEV",
                            "terms_url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                            "live_refresh_enabled": False,
                        },
                    ],
                    "total": 2,
                }
            if path == "/runs" and method == "GET":
                return {
                    "runs": [
                        {
                            "id": "run_active",
                            "started": "2026-05-19T00:00:03+00:00",
                            "status": "running",
                            "run_kind": "external",
                            "command": "sleep 30",
                        }
                    ],
                    "total": 1,
                }
            if path == "/runs" and method == "POST":
                if body == {"command": "echo linked", "project_id": "prj_cli"}:
                    return {"id": "run_wait", "status": "running"}
                assert body == {"command": "echo ok", "project_id": None}
                return {"id": "run_cli", "status": "running"}
            if path == "/runs/run_wait/wait":
                assert params == {"timeout": None}
                return {"run": {"id": "run_wait", "status": "succeeded", "exit_code": 0, "command": "echo linked"}}
            if path == "/projects/prj_cli/runs":
                return {"runs": [{"id": "run_cli", "started": "2026-05-19T00:00:00+00:00", "exit_code": 0, "command": "echo ok"}]}
            if path == "/runs/run_cli/projects/prj_cli" and method == "POST":
                return {"ok": True, "link": {"project_id": "prj_cli", "entity_id": "run_cli", "entity_type": "run"}}
            if path == "/runs/run_cli/projects/prj_cli" and method == "DELETE":
                return {"ok": True}
            if path == "/projects/prj_cli/entities":
                assert params == {"limit": 50, "offset": 0, "entity_type": "domain"}
                return {"entities": [{"id": "ent_cli", "type": "domain", "value": "darklab.sh"}]}
            if path == "/atlas":
                assert params == {
                    "q": None,
                    "project_id": None,
                    "run_id": None,
                    "entity_type": None,
                    "orphan_filter": "hide",
                    "suppression_filter": "hide",
                }
                return {"total": 1, "findings": 1, "counts": {"domain": 1}}
            if path == "/atlas/runs":
                assert params == {"q": None, "run_id": None, "limit": 30}
                return {"runs": [{"id": "run_cli", "entity_count": 1, "finding_count": 1, "command": "echo ok"}]}
            if path == "/atlas/entities":
                assert params == {
                    "q": None,
                    "project_id": None,
                    "run_id": None,
                    "entity_type": "domain",
                    "orphan_filter": "hide",
                    "suppression_filter": "hide",
                    "limit": 50,
                    "offset": 0,
                }
                return {"entities": [{"id": "ent_cli", "type": "domain", "occurrence_count": 2, "canonical_value": "darklab.sh"}]}
            if path == "/atlas/entities/ent_cli":
                return {"entity": {"id": "ent_cli", "type": "domain", "occurrence_count": 2, "canonical_value": "darklab.sh"}}
            if path == "/atlas/findings":
                assert params == {
                    "q": None,
                    "project_id": None,
                    "run_id": None,
                    "entity_type": None,
                    "orphan_filter": "hide",
                    "suppression_filter": "hide",
                    "limit": 50,
                    "offset": 0,
                    "review_state": [],
                }
                return {"findings": [{"id": "fnd_cli", "status": "new", "severity": "medium", "title": "Open port"}]}
            if path == "/atlas/findings/fnd_cli":
                return {"finding": {"id": "fnd_cli", "status": "new", "severity": "medium", "title": "Open port"}}
            raise cli_main.DarklabCliError("not_found: missing")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)
    return SimpleNamespace(
        cli_main=cli_main,
        finding_requests=finding_requests,
        http_profile_requests=http_profile_requests,
        osv_requests=osv_requests,
    )
