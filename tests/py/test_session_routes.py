# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for browser-session storage routes and removed identity endpoints."""

import json
import sqlite3
from conftest import reusable_test_app
from identity_helpers import anonymous_session_id, browser_identity_headers
from core.database import DB_PATH


def get_client():
    return reusable_test_app(__name__).test_client()


def test_legacy_identity_routes_are_gone():
    client = get_client()

    for method, path in (
        ("get", "/session/token/generate"),
        ("get", "/session/token/info"),
        ("post", "/session/token/verify"),
        ("post", "/session/token/revoke"),
        ("post", "/session/migrate"),
    ):
        response = getattr(client, method)(path, json={} if method == "post" else None)
        assert response.status_code == 404, path


def _audit_event_rows(event_type):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT event_type, target_type, target_id, details FROM audit_events WHERE event_type = ? ORDER BY created, id",
            (event_type,),
        ).fetchall()
    return [
        {
            "event_type": row["event_type"],
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "details": json.loads(row["details"] or "{}"),
        }
        for row in rows
    ]


class TestSessionWorkflows:
    def _payload(self, title="Saved DNS"):
        return {
            "title": title,
            "description": "custom workflow",
            "inputs": [
                {
                    "id": "domain",
                    "label": "Domain",
                    "type": "domain",
                    "required": True,
                    "placeholder": "example.com",
                    "default": "",
                    "help": "",
                    "sensitive": True,
                },
            ],
            "steps": [{"cmd": "dig {{domain}} A", "note": "resolve apex"}],
        }

    def test_create_lists_and_returns_normalized_workflow(self, monkeypatch):
        client = get_client()
        session_id = anonymous_session_id("workflow-create-" + __import__("uuid").uuid4().hex[:8])
        launched: list[str] = []
        monkeypatch.setattr(
            "blueprints.workflows.launch_execution_step",
            lambda execution_id: launched.append(execution_id) or {"execution_id": execution_id},
        )

        create_resp = client.post(
            "/session/workflows",
            json=self._payload(),
            headers={**browser_identity_headers(session_id)},
        )
        list_resp = client.get("/session/workflows", headers={**browser_identity_headers(session_id)})
        created = json.loads(create_resp.data)["workflow"]
        listed = json.loads(list_resp.data)["items"]

        assert create_resp.status_code == 201
        assert created["source"] == "user"
        assert created["inputs"][0]["id"] == "domain"
        assert created["inputs"][0]["sensitive"] is True
        assert listed[0]["id"] == created["id"]

        collection_resp = client.post(
            "/session/workflows",
            json={
                "version": 3,
                "title": "Saved bounded fan-out",
                "description": "collect and probe",
                "inputs": [],
                "steps": [
                    {
                        "id": "collect",
                        "cmd": "echo hosts",
                        "captures": [
                            {
                                "name": "hosts",
                                "kind": "collection",
                                "source": "json_pointer",
                                "pointer": "/hosts",
                                "item_limit": 4,
                            }
                        ],
                    },
                    {
                        "id": "probe",
                        "cmd": "httpx -u {{hosts}} -silent",
                        "for_each": {"collection": "hosts", "max_parallel": 2},
                    },
                ],
            },
            headers={**browser_identity_headers(session_id)},
        )
        collection = collection_resp.get_json()["workflow"]
        assert collection_resp.status_code == 201
        assert collection["version"] == 3
        assert collection["steps"][1]["for_each"] == {
            "collection": "hosts",
            "failure_mode": "fail_fast",
            "retries": 0,
            "max_parallel": 2,
            "max_failures": 1,
        }
        launch_resp = client.post(
            "/workflow-executions",
            json={"workflow_id": collection["id"], "inputs": {}},
            headers={**browser_identity_headers(session_id)},
        )
        assert launch_resp.status_code == 202
        launched_execution = launch_resp.get_json()["execution"]
        assert launched == [launched_execution["id"]]
        assert launched_execution["workflow_id"] == collection["id"]

    def test_rejects_undeclared_workflow_variables(self):
        client = get_client()
        session_id = anonymous_session_id("workflow-invalid-" + __import__("uuid").uuid4().hex[:8])
        payload = self._payload()
        payload["inputs"] = []

        resp = client.post(
            "/session/workflows",
            json=payload,
            headers={**browser_identity_headers(session_id)},
        )

        assert resp.status_code == 400
        assert "variables" in json.loads(resp.data)["error"]

    def test_create_and_update_return_field_level_definition_errors(self):
        client = get_client()
        session_id = anonymous_session_id("workflow-fields-" + __import__("uuid").uuid4().hex[:8])
        invalid_create = {
            **self._payload(),
            "version": 2,
            "inputs": [{"id": "Bad ID", "type": "target"}],
            "steps": [{"id": "resolve", "cmd": "dig darklab.sh", "note": ""}],
        }

        create_error = client.post(
            "/session/workflows",
            json=invalid_create,
            headers={**browser_identity_headers(session_id)},
        )
        assert create_error.status_code == 400
        assert create_error.get_json()["errors"] == [
            {
                "field": "inputs.0.id",
                "message": ("parameter ID must start with a letter and use lowercase letters, numbers, and underscores"),
            }
        ]

        created = client.post(
            "/session/workflows",
            json=self._payload(),
            headers={**browser_identity_headers(session_id)},
        ).get_json()["workflow"]
        invalid_update = {
            **self._payload("Invalid graph"),
            "version": 2,
            "steps": [
                {"id": "scan", "cmd": "dig {{domain}} A", "note": ""},
                {"id": "scan", "cmd": "nmap {{domain}}", "note": ""},
            ],
        }
        update_error = client.put(
            f"/session/workflows/{created['id']}",
            json=invalid_update,
            headers={**browser_identity_headers(session_id)},
        )
        assert update_error.status_code == 400
        assert update_error.get_json()["errors"] == [
            {
                "field": "steps.1.id",
                "message": "step ID must be unique",
            }
        ]

        invalid_capture = {
            **self._payload("Invalid capture"),
            "version": 2,
            "steps": [
                {
                    "id": "resolve",
                    "cmd": "dig {{domain}} A",
                    "note": "",
                    "captures": [
                        {
                            "name": "resolved_ip",
                            "source": "json_pointer",
                            "pointer": "result.ip",
                        }
                    ],
                }
            ],
        }
        capture_error = client.put(
            f"/session/workflows/{created['id']}",
            json=invalid_capture,
            headers={**browser_identity_headers(session_id)},
        )
        assert capture_error.status_code == 400
        assert capture_error.get_json()["errors"] == [
            {
                "field": "steps.0.captures.0.pointer",
                "message": "workflow capture JSON Pointer must start with /",
            }
        ]

        invalid_sensitive = self._payload("Invalid sensitive flag")
        invalid_sensitive["inputs"][0]["sensitive"] = "yes"
        sensitive_error = client.put(
            f"/session/workflows/{created['id']}",
            json=invalid_sensitive,
            headers={**browser_identity_headers(session_id)},
        )
        assert sensitive_error.status_code == 400
        assert sensitive_error.get_json()["errors"] == [
            {
                "field": "inputs.0.sensitive",
                "message": "parameter sensitive state must be true or false",
            }
        ]

        unsupported_version = self._payload("Unsupported version")
        unsupported_version["version"] = 4
        version_error = client.put(
            f"/session/workflows/{created['id']}",
            json=unsupported_version,
            headers={**browser_identity_headers(session_id)},
        )
        assert version_error.status_code == 400
        assert version_error.get_json()["errors"] == [
            {
                "field": "version",
                "message": "unsupported workflow version",
            }
        ]

    def test_update_and_delete_are_session_scoped(self):
        client = get_client()
        session_id = anonymous_session_id("workflow-update-" + __import__("uuid").uuid4().hex[:8])
        other_session_id = anonymous_session_id("workflow-other-" + __import__("uuid").uuid4().hex[:8])
        created = json.loads(
            client.post(
                "/session/workflows",
                json=self._payload(),
                headers={**browser_identity_headers(session_id)},
            ).data
        )["workflow"]

        denied = client.put(
            f"/session/workflows/{created['id']}",
            json=self._payload("Other Edit"),
            headers={**browser_identity_headers(other_session_id)},
        )
        updated = client.put(
            f"/session/workflows/{created['id']}",
            json=self._payload("Updated DNS"),
            headers={**browser_identity_headers(session_id)},
        )
        deleted = client.delete(
            f"/session/workflows/{created['id']}",
            headers={**browser_identity_headers(session_id)},
        )

        assert denied.status_code == 404
        assert json.loads(updated.data)["workflow"]["title"] == "Updated DNS"
        assert deleted.status_code == 200
        assert (
            json.loads(
                client.get(
                    "/session/workflows",
                    headers={**browser_identity_headers(session_id)},
                ).data
            )["items"]
            == []
        )


# ── /session/recent-values ───────────────────────────────────────────────────


class TestSessionRecentValues:
    def _values(self, session_id, kind):
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT value FROM recent_values WHERE personal_workspace_id = ? AND kind = ? ORDER BY last_used DESC, value ASC",
                (session_id, kind),
            ).fetchall()
        return [row[0] for row in rows]

    def test_get_returns_empty_list_for_new_session(self):
        client = get_client()
        session_id = anonymous_session_id("recent-empty-" + __import__("uuid").uuid4().hex[:8])
        resp = client.get("/session/recent-values", headers={**browser_identity_headers(session_id)})

        assert resp.status_code == 200
        assert json.loads(resp.data)["values"] == {
            "domain": [],
            "ip": [],
            "port_set": [],
            "url": [],
        }

    def test_post_normalizes_filters_and_caps_values_per_kind(self):
        client = get_client()
        session_id = anonymous_session_id("recent-save-" + __import__("uuid").uuid4().hex[:8])
        valid = [f"d{i}.example.com" for i in range(12)]
        resp = client.post(
            "/session/recent-values",
            json={
                "values": [
                    {"kind": "domain", "value": "Alpha.Example.com."},
                    {"kind": "domain", "value": "https://ignored.example"},
                    {"kind": "domain", "value": "127.0.0.1"},
                    {"kind": "domain", "value": "user@example.com"},
                    {"kind": "domain", "value": "with/path.example"},
                    {"kind": "domain", "value": "Alpha.Example.com"},
                    {"kind": "ip", "value": "192.0.2.10"},
                    {"kind": "ip", "value": "2001:db8::1"},
                    {"kind": "ip", "value": "999.0.0.1"},
                    {"kind": "url", "value": "HTTPS://Example.com/login?token=secret#frag"},
                    {"kind": "url", "value": "ftp://ignored.example/file"},
                    {"kind": "url", "value": "https://user:pass@example.com"},
                    {"kind": "port_set", "value": "80, 443, 8000 - 8080"},
                    {"kind": "port_set", "value": "65536"},
                    *[{"kind": "domain", "value": value} for value in valid],
                ]
            },
            headers={**browser_identity_headers(session_id)},
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["saved"] == 14
        assert data["values"]["domain"] == [
            "alpha.example.com",
            "d0.example.com",
            "d1.example.com",
            "d2.example.com",
            "d3.example.com",
            "d4.example.com",
            "d5.example.com",
            "d6.example.com",
            "d7.example.com",
            "d8.example.com",
        ]
        assert data["values"]["ip"] == ["192.0.2.10", "2001:db8::1"]
        assert data["values"]["url"] == ["https://example.com/login"]
        assert data["values"]["port_set"] == ["80,443,8000-8080"]
        assert self._values(session_id, "domain") == data["values"]["domain"]

    def test_post_is_session_scoped(self):
        client = get_client()
        session_a = anonymous_session_id("recent-scope-a-" + __import__("uuid").uuid4().hex[:8])
        session_b = anonymous_session_id("recent-scope-b-" + __import__("uuid").uuid4().hex[:8])

        client.post(
            "/session/recent-values",
            json={"values": [{"kind": "domain", "value": "alpha.example.com"}]},
            headers={**browser_identity_headers(session_a)},
        )
        resp = client.get("/session/recent-values", headers={**browser_identity_headers(session_b)})

        assert json.loads(resp.data)["values"]["domain"] == []

    def test_post_updates_existing_value_count_and_recency(self):
        client = get_client()
        session_id = anonymous_session_id("recent-upsert-" + __import__("uuid").uuid4().hex[:8])

        client.post(
            "/session/recent-values",
            json={"values": [{"kind": "domain", "value": "alpha.example.com"}]},
            headers={**browser_identity_headers(session_id)},
        )
        client.post(
            "/session/recent-values",
            json={"values": [{"kind": "domain", "value": "beta.example.org"}]},
            headers={**browser_identity_headers(session_id)},
        )
        client.post(
            "/session/recent-values",
            json={"values": [{"kind": "domain", "value": "alpha.example.com"}]},
            headers={**browser_identity_headers(session_id)},
        )

        with sqlite3.connect(DB_PATH) as conn:
            count = conn.execute(
                "SELECT use_count FROM recent_values WHERE personal_workspace_id = ? AND kind = ? AND value = ?",
                (session_id, "domain", "alpha.example.com"),
            ).fetchone()[0]
        resp = client.get("/session/recent-values?kind=domain", headers={**browser_identity_headers(session_id)})
        assert json.loads(resp.data)["values"]["domain"][0] == "alpha.example.com"
        assert count == 2

    def test_post_rejects_non_list_payload(self):
        client = get_client()
        session_id = anonymous_session_id("recent-invalid-" + __import__("uuid").uuid4().hex[:8])
        resp = client.post(
            "/session/recent-values",
            json={"values": "alpha.example.com"},
            headers={**browser_identity_headers(session_id)},
        )

        assert resp.status_code == 400

    def test_get_rejects_unknown_kind(self):
        client = get_client()
        session_id = anonymous_session_id("recent-invalid-kind-" + __import__("uuid").uuid4().hex[:8])

        resp = client.get("/session/recent-values?kind=cve", headers={**browser_identity_headers(session_id)})

        assert resp.status_code == 400
class TestSessionStarred:
    def _count_stars(self, session_id):
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM starred_commands WHERE personal_workspace_id = ?",
                (session_id,),
            ).fetchone()[0]

    def _get_stars(self, session_id):
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT command FROM starred_commands WHERE personal_workspace_id = ?",
                (session_id,),
            ).fetchall()
        return {row[0] for row in rows}

    # GET /session/starred

    def test_get_returns_empty_list_for_new_session(self):
        client = get_client()
        session_id = anonymous_session_id("get-stars-new-" + __import__("uuid").uuid4().hex[:8])
        resp = client.get("/session/starred", headers={**browser_identity_headers(session_id)})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["commands"] == []

    def test_get_returns_starred_commands(self):
        client = get_client()
        session_id = anonymous_session_id("get-stars-existing-" + __import__("uuid").uuid4().hex[:8])
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO starred_commands (personal_workspace_id, command) VALUES (?, ?)",
                (session_id, "nmap target"),
            )
            conn.commit()
        resp = client.get("/session/starred", headers={**browser_identity_headers(session_id)})
        data = json.loads(resp.data)
        assert "nmap target" in data["commands"]

    def test_get_is_scoped_to_session(self):
        client = get_client()
        session_a = anonymous_session_id("get-stars-scope-a-" + __import__("uuid").uuid4().hex[:8])
        session_b = anonymous_session_id("get-stars-scope-b-" + __import__("uuid").uuid4().hex[:8])
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO starred_commands (personal_workspace_id, command) VALUES (?, ?)",
                (session_a, "cmd-a"),
            )
            conn.commit()
        resp = client.get("/session/starred", headers={**browser_identity_headers(session_b)})
        data = json.loads(resp.data)
        assert data["commands"] == []

    # POST /session/starred

    def test_post_adds_starred_command(self):
        client = get_client()
        session_id = anonymous_session_id("post-stars-add-" + __import__("uuid").uuid4().hex[:8])
        resp = client.post(
            "/session/starred",
            json={"command": "dig example.com"},
            headers={**browser_identity_headers(session_id)},
        )
        assert resp.status_code == 200
        assert json.loads(resp.data)["ok"] is True
        assert "dig example.com" in self._get_stars(session_id)

    def test_post_is_idempotent(self):
        client = get_client()
        session_id = anonymous_session_id("post-stars-idem-" + __import__("uuid").uuid4().hex[:8])
        client.post(
            "/session/starred",
            json={"command": "ping target"},
            headers={**browser_identity_headers(session_id)},
        )
        client.post(
            "/session/starred",
            json={"command": "ping target"},
            headers={**browser_identity_headers(session_id)},
        )
        assert self._count_stars(session_id) == 1

    def test_post_rejects_missing_command(self):
        client = get_client()
        resp = client.post(
            "/session/starred",
            json={},
            headers={**browser_identity_headers(anonymous_session_id("post-stars-no-cmd"))},
        )
        assert resp.status_code == 400

    def test_post_rejects_empty_command(self):
        client = get_client()
        resp = client.post(
            "/session/starred",
            json={"command": ""},
            headers={**browser_identity_headers(anonymous_session_id("post-stars-empty-cmd"))},
        )
        assert resp.status_code == 400

    # DELETE /session/starred (single)

    def test_delete_removes_one_command(self):
        client = get_client()
        session_id = anonymous_session_id("del-stars-one-" + __import__("uuid").uuid4().hex[:8])
        with sqlite3.connect(DB_PATH) as conn:
            for cmd in ["keep", "remove"]:
                conn.execute(
                    "INSERT INTO starred_commands (personal_workspace_id, command) VALUES (?, ?)",
                    (session_id, cmd),
                )
            conn.commit()
        client.delete(
            "/session/starred",
            json={"command": "remove"},
            headers={**browser_identity_headers(session_id)},
        )
        stars = self._get_stars(session_id)
        assert "keep" in stars
        assert "remove" not in stars

    def test_delete_one_is_idempotent(self):
        client = get_client()
        session_id = anonymous_session_id("del-stars-idem-" + __import__("uuid").uuid4().hex[:8])
        resp = client.delete(
            "/session/starred",
            json={"command": "nonexistent"},
            headers={**browser_identity_headers(session_id)},
        )
        assert resp.status_code == 200
        assert json.loads(resp.data)["ok"] is True

    def test_delete_one_only_affects_own_session(self):
        client = get_client()
        session_a = anonymous_session_id("del-stars-scope-a-" + __import__("uuid").uuid4().hex[:8])
        session_b = anonymous_session_id("del-stars-scope-b-" + __import__("uuid").uuid4().hex[:8])
        with sqlite3.connect(DB_PATH) as conn:
            for sid in [session_a, session_b]:
                conn.execute(
                    "INSERT INTO starred_commands (personal_workspace_id, command) VALUES (?, ?)",
                    (sid, "shared-cmd"),
                )
            conn.commit()
        client.delete(
            "/session/starred",
            json={"command": "shared-cmd"},
            headers={**browser_identity_headers(session_a)},
        )
        assert self._count_stars(session_a) == 0
        assert self._count_stars(session_b) == 1

    # DELETE /session/starred (clear all)

    def test_delete_all_clears_session_stars(self):
        client = get_client()
        session_id = anonymous_session_id("del-stars-all-" + __import__("uuid").uuid4().hex[:8])
        with sqlite3.connect(DB_PATH) as conn:
            for cmd in ["cmd1", "cmd2", "cmd3"]:
                conn.execute(
                    "INSERT INTO starred_commands (personal_workspace_id, command) VALUES (?, ?)",
                    (session_id, cmd),
                )
            conn.commit()
        resp = client.delete(
            "/session/starred",
            json={},
            headers={**browser_identity_headers(session_id)},
        )
        assert resp.status_code == 200
        assert self._count_stars(session_id) == 0

    def test_delete_all_does_not_affect_other_sessions(self):
        client = get_client()
        session_a = anonymous_session_id("del-all-scope-a-" + __import__("uuid").uuid4().hex[:8])
        session_b = anonymous_session_id("del-all-scope-b-" + __import__("uuid").uuid4().hex[:8])
        with sqlite3.connect(DB_PATH) as conn:
            for sid in [session_a, session_b]:
                conn.execute(
                    "INSERT INTO starred_commands (personal_workspace_id, command) VALUES (?, ?)",
                    (sid, "cmd"),
                )
            conn.commit()
        client.delete(
            "/session/starred",
            json={},
            headers={**browser_identity_headers(session_a)},
        )
        assert self._count_stars(session_b) == 1
class TestSessionPreferences:
    def test_returns_empty_preferences_when_none_saved(self):
        client = get_client()
        session_id = anonymous_session_id("prefs-empty-" + __import__("uuid").uuid4().hex[:8])
        resp = client.get("/session/preferences", headers={**browser_identity_headers(session_id)})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["preferences"] == {}
        assert data["updated"] is None

    def test_persists_and_returns_current_session_preferences(self):
        client = get_client()
        session_id = anonymous_session_id("prefs-save-" + __import__("uuid").uuid4().hex[:8])
        payload = {
            "preferences": {
                "pref_theme_name": "theme_light_blue",
                "pref_timestamps": "clock",
                "pref_project_auto_link_external_runs": "off",
                "pref_project_auto_link_run_entities": "off",
                "pref_run_notify": "on",
                "pref_command_outcome_summaries": "off",
                "pref_prompt_username": "operator_1",
                "pref_compare_view_mode": "unified",
                "pref_compare_context": "10",
                "pref_options_modal_last_tab": "secrets",
            }
        }
        save_resp = client.post("/session/preferences", json=payload, headers={**browser_identity_headers(session_id)})
        assert save_resp.status_code == 200

        get_resp = client.get("/session/preferences", headers={**browser_identity_headers(session_id)})
        data = json.loads(get_resp.data)
        assert data["preferences"] == payload["preferences"]
        assert data["updated"]

    def test_ignores_unknown_session_preference_keys(self):
        client = get_client()
        session_id = anonymous_session_id("prefs-filter-" + __import__("uuid").uuid4().hex[:8])
        resp = client.post(
            "/session/preferences",
            json={
                "preferences": {
                    "pref_theme_name": "theme_light_blue",
                    "pref_prompt_username": "../bad",
                    "pref_compare_view_mode": "split",
                    "pref_compare_context": "0",
                    "pref_options_modal_last_tab": "advanced",
                    "pref_unknown": "x",
                }
            },
            headers={**browser_identity_headers(session_id)},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["preferences"] == {"pref_theme_name": "theme_light_blue"}
