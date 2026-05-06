"""
Tests for session token routes: /session/token/generate and /session/migrate.
"""
import json
import sqlite3

import app as shell_app
from database import DB_PATH
import workspace


def get_client():
    shell_app.app.config["TESTING"] = True
    shell_app.app.config["RATELIMIT_ENABLED"] = False
    return shell_app.app.test_client()


# ── /session/token/generate ───────────────────────────────────────────────────

class TestSessionTokenGenerate:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/session/token/generate")
        assert resp.status_code == 200

    def test_response_has_session_token_key(self):
        client = get_client()
        data = json.loads(client.get("/session/token/generate").data)
        assert "session_token" in data

    def test_token_has_tok_prefix(self):
        client = get_client()
        data = json.loads(client.get("/session/token/generate").data)
        assert data["session_token"].startswith("tok_")

    def test_token_length(self):
        # tok_ + 32 hex characters = 36 total
        client = get_client()
        data = json.loads(client.get("/session/token/generate").data)
        assert len(data["session_token"]) == 36

    def test_token_persisted_in_db(self):
        client = get_client()
        data = json.loads(client.get("/session/token/generate").data)
        token = data["session_token"]
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT token FROM session_tokens WHERE token = ?", (token,)
            ).fetchone()
        assert row is not None
        assert row[0] == token

    def test_multiple_calls_return_different_tokens(self):
        client = get_client()
        t1 = json.loads(client.get("/session/token/generate").data)["session_token"]
        t2 = json.loads(client.get("/session/token/generate").data)["session_token"]
        assert t1 != t2


# ── /session/token/verify ─────────────────────────────────────────────────────

class TestSessionTokenVerify:
    def test_verify_returns_true_for_issued_token(self):
        client = get_client()
        token = json.loads(client.get("/session/token/generate").data)["session_token"]
        resp = client.post("/session/token/verify", json={"token": token})
        assert resp.status_code == 200
        assert json.loads(resp.data)["exists"] is True

    def test_verify_returns_false_for_unknown_tok_token(self):
        client = get_client()
        fake = "tok_" + "a" * 32
        resp = client.post("/session/token/verify", json={"token": fake})
        assert resp.status_code == 200
        assert json.loads(resp.data)["exists"] is False

    def test_verify_returns_true_for_uuid(self):
        """UUID anonymous sessions are never in session_tokens but are always valid."""
        client = get_client()
        session_id = "a1b2c3d4-0000-4000-8000-000000000001"
        resp = client.post("/session/token/verify", json={"token": session_id})
        assert resp.status_code == 200
        assert json.loads(resp.data)["exists"] is True

    def test_verify_rejects_invalid_anonymous_session_id(self):
        client = get_client()
        resp = client.post("/session/token/verify", json={"token": "abc123"})
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "invalid anonymous session id"

    def test_verify_requires_token_field(self):
        client = get_client()
        resp = client.post("/session/token/verify", json={})
        assert resp.status_code == 400


# ── /session/migrate ──────────────────────────────────────────────────────────

class TestSessionMigrate:
    def _seed_runs(self, session_id, count=2):
        """Insert synthetic run rows for the given session_id."""
        import uuid
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(DB_PATH) as conn:
            for _ in range(count):
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, 'echo hi', ?)",
                    (str(uuid.uuid4()), session_id, now),
                )
            conn.commit()

    def _seed_snapshots(self, session_id, count=1):
        import uuid
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(DB_PATH) as conn:
            for i in range(count):
                conn.execute(
                    "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), session_id, f"label-{i}", now, "{}"),
                )
            conn.commit()

    def _count_rows(self, table, session_id):
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE session_id = ?",  # nosec B608
                (session_id,),
            ).fetchone()[0]

    def _seed_preferences(self, session_id, preferences):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO session_preferences (session_id, preferences, updated) VALUES (?, ?, datetime('now'))",
                (session_id, json.dumps(preferences, sort_keys=True)),
            )
            conn.commit()

    def _seed_variable(self, session_id, name, value):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO session_variables (session_id, name, value, updated) "
                "VALUES (?, ?, ?, datetime('now'))",
                (session_id, name, value),
            )
            conn.commit()

    def _seed_workflow(self, session_id, workflow_id="usr_test_workflow"):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_workflows "
                "(id, session_id, title, description, inputs, steps, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (
                    workflow_id,
                    session_id,
                    "Saved DNS",
                    "custom workflow",
                    json.dumps([
                        {
                            "id": "domain",
                            "label": "Domain",
                            "type": "domain",
                            "required": True,
                            "placeholder": "example.com",
                            "default": "",
                            "help": "",
                        },
                    ]),
                    json.dumps([{"cmd": "dig {{domain}} A", "note": "resolve apex"}]),
                ),
            )
            conn.commit()

    def _seed_recent_domains(self, session_id, rows):
        with sqlite3.connect(DB_PATH) as conn:
            for domain, last_used, use_count in rows:
                conn.execute(
                    "INSERT OR REPLACE INTO recent_domains (session_id, domain, last_used, use_count) "
                    "VALUES (?, ?, ?, ?)",
                    (session_id, domain, last_used, use_count),
                )
            conn.commit()

    def _enable_workspace(self, monkeypatch, tmp_path, **overrides):
        cfg = {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(tmp_path / "workspaces"),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
            "workspace_inactivity_ttl_hours": 1,
        }
        cfg.update(overrides)
        for key, value in cfg.items():
            monkeypatch.setitem(workspace.CFG, key, value)
        return cfg

    def test_returns_200_with_valid_request(self):
        client = get_client()
        from_id = "migrate-from-valid-test"
        to_id = str(__import__("uuid").uuid4())
        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"] is True

    def test_rejects_mismatched_from_session_id(self):
        client = get_client()
        resp = client.post(
            "/session/migrate",
            json={"from_session_id": "some-other-session", "to_session_id": "tok_abc"},
            headers={"X-Session-ID": "actual-current-session"},
        )
        assert resp.status_code == 403

    def test_rejects_missing_from_field(self):
        client = get_client()
        resp = client.post(
            "/session/migrate",
            json={"to_session_id": "tok_abc"},
            headers={"X-Session-ID": "s"},
        )
        assert resp.status_code == 400

    def test_rejects_missing_to_field(self):
        client = get_client()
        resp = client.post(
            "/session/migrate",
            json={"from_session_id": "s"},
            headers={"X-Session-ID": "s"},
        )
        assert resp.status_code == 400

    def test_rejects_equal_session_ids(self):
        client = get_client()
        resp = client.post(
            "/session/migrate",
            json={"from_session_id": "same-id", "to_session_id": "same-id"},
            headers={"X-Session-ID": "same-id"},
        )
        assert resp.status_code == 400

    def test_rejects_unissued_tok_destination(self):
        """Migrating to a tok_ token that is not in session_tokens must be rejected."""
        client = get_client()
        from_id = "migrate-tok-check-" + __import__("uuid").uuid4().hex[:8]
        fake_tok = "tok_" + "f" * 32
        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": fake_tok},
            headers={"X-Session-ID": from_id},
        )
        assert resp.status_code == 400
        assert "not a known issued token" in json.loads(resp.data).get("error", "")

    def test_allows_uuid_destination(self):
        """Migrating to a UUID (anonymous session) must still be accepted."""
        client = get_client()
        from_id = "migrate-uuid-dst-" + __import__("uuid").uuid4().hex[:8]
        uuid_dst = str(__import__("uuid").uuid4())
        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": uuid_dst},
            headers={"X-Session-ID": from_id},
        )
        assert resp.status_code == 200

    def test_migrates_runs(self):
        client = get_client()
        from_id = "migrate-runs-from-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        self._seed_runs(from_id, count=3)

        assert self._count_rows("runs", from_id) == 3
        client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        assert self._count_rows("runs", from_id) == 0
        assert self._count_rows("runs", to_id) == 3

    def test_migrates_snapshots(self):
        client = get_client()
        from_id = "migrate-snaps-from-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        self._seed_snapshots(from_id, count=2)

        assert self._count_rows("snapshots", from_id) == 2
        client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        assert self._count_rows("snapshots", from_id) == 0
        assert self._count_rows("snapshots", to_id) == 2

    def test_returns_correct_counts(self):
        client = get_client()
        from_id = "migrate-counts-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        self._seed_runs(from_id, count=2)
        self._seed_snapshots(from_id, count=1)

        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        data = json.loads(resp.data)
        assert data["migrated_runs"] == 2
        assert data["migrated_snapshots"] == 1

    def test_does_not_migrate_other_sessions(self):
        client = get_client()
        from_id = "migrate-own-" + __import__("uuid").uuid4().hex[:8]
        bystander_id = "bystander-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        self._seed_runs(from_id, count=2)
        self._seed_runs(bystander_id, count=3)

        client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        assert self._count_rows("runs", bystander_id) == 3

    def _seed_stars(self, session_id, commands):
        with sqlite3.connect(DB_PATH) as conn:
            for cmd in commands:
                conn.execute(
                    "INSERT OR IGNORE INTO starred_commands (session_id, command) VALUES (?, ?)",
                    (session_id, cmd),
                )
            conn.commit()

    def test_migrates_starred_commands(self):
        client = get_client()
        from_id = "migrate-stars-from-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        self._seed_stars(from_id, ["nmap target", "dig example.com"])

        assert self._count_rows("starred_commands", from_id) == 2
        client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        assert self._count_rows("starred_commands", from_id) == 0
        assert self._count_rows("starred_commands", to_id) == 2

    def test_migrate_returns_migrated_stars_count(self):
        client = get_client()
        from_id = "migrate-stars-count-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        self._seed_stars(from_id, ["cmd1", "cmd2", "cmd3"])

        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        data = json.loads(resp.data)
        assert data["migrated_stars"] == 3

    def test_migrate_stars_no_duplicates_in_destination(self):
        client = get_client()
        from_id = "migrate-stars-dedup-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        self._seed_stars(from_id, ["shared-cmd", "from-only"])
        self._seed_stars(to_id, ["shared-cmd", "dest-only"])

        client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        # dest should have exactly 3 unique commands, not 4
        assert self._count_rows("starred_commands", to_id) == 3

    def test_migrate_returns_only_newly_inserted_star_count(self):
        """migrated_stars must reflect INSERT rowcount, not DELETE rowcount.

        When the destination already has some of the same starred commands, the
        INSERT OR IGNORE skips them.  The returned count should be the number
        actually written into the destination, not the (larger) number deleted
        from the source.
        """
        client = get_client()
        from_id = "migrate-stars-insert-ct-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        # source has 3, destination already has 1 overlap
        self._seed_stars(from_id, ["shared", "from-only-1", "from-only-2"])
        self._seed_stars(to_id, ["shared"])

        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        data = json.loads(resp.data)
        # Only 2 commands were actually inserted (the 1 already present was skipped)
        assert data["migrated_stars"] == 2

    def test_migrates_session_preferences_when_destination_has_none(self):
        client = get_client()
        from_id = "migrate-prefs-from-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        prefs = {"pref_theme_name": "theme_light_blue", "pref_timestamps": "clock"}
        self._seed_preferences(from_id, prefs)

        client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )

        with sqlite3.connect(DB_PATH) as conn:
            src = conn.execute(
                "SELECT preferences FROM session_preferences WHERE session_id = ?",
                (from_id,),
            ).fetchone()
            dst = conn.execute(
                "SELECT preferences FROM session_preferences WHERE session_id = ?",
                (to_id,),
            ).fetchone()
        assert src is None
        assert json.loads(dst[0]) == prefs

    def test_migrates_session_variables(self):
        client = get_client()
        from_id = "migrate-vars-from-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        self._seed_variable(from_id, "HOST", "ip.darklab.sh")

        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["migrated_variables"] == 1
        assert self._count_rows("session_variables", from_id) == 0
        vars_resp = client.get("/session/variables", headers={"X-Session-ID": to_id})
        vars_data = json.loads(vars_resp.data)
        assert vars_data["variables"] == [{"name": "HOST", "value": "ip.darklab.sh"}]

    def test_migrates_user_workflows(self):
        client = get_client()
        from_id = "migrate-workflows-from-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        self._seed_workflow(from_id, "usr_migrate_test")

        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["migrated_workflows"] == 1
        assert self._count_rows("user_workflows", from_id) == 0
        assert self._count_rows("user_workflows", to_id) == 1

    def test_migrates_recent_domains_and_merges_destination(self):
        client = get_client()
        from_id = "migrate-recents-from-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        self._seed_recent_domains(from_id, [
            ("alpha.example.com", "2026-05-01 10:00:00.000001", 2),
            ("shared.example.com", "2026-05-01 11:00:00.000001", 3),
        ])
        self._seed_recent_domains(to_id, [
            ("shared.example.com", "2026-05-01 09:00:00.000001", 4),
        ])

        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        data = json.loads(resp.data)

        with sqlite3.connect(DB_PATH) as conn:
            source_count = conn.execute(
                "SELECT COUNT(*) FROM recent_domains WHERE session_id = ?",
                (from_id,),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT domain, last_used, use_count FROM recent_domains WHERE session_id = ?",
                (to_id,),
            ).fetchall()
        by_domain = {row[0]: {"last_used": row[1], "use_count": row[2]} for row in rows}
        assert resp.status_code == 200
        assert data["migrated_recent_domains"] == 2
        assert source_count == 0
        assert by_domain["alpha.example.com"]["use_count"] == 2
        assert by_domain["shared.example.com"]["use_count"] == 7
        assert by_domain["shared.example.com"]["last_used"] == "2026-05-01 11:00:00.000001"

    def test_migrate_keeps_existing_destination_session_preferences(self):
        client = get_client()
        from_id = "migrate-prefs-src-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        src_prefs = {"pref_theme_name": "theme_light_blue", "pref_timestamps": "clock"}
        dst_prefs = {"pref_theme_name": "darklab_obsidian.yaml", "pref_timestamps": "off"}
        self._seed_preferences(from_id, src_prefs)
        self._seed_preferences(to_id, dst_prefs)

        client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )

        with sqlite3.connect(DB_PATH) as conn:
            dst = conn.execute(
                "SELECT preferences FROM session_preferences WHERE session_id = ?",
                (to_id,),
            ).fetchone()
        assert json.loads(dst[0]) == dst_prefs

    def test_migrate_workspace_returns_zero_without_source_workspace(self, tmp_path, monkeypatch):
        client = get_client()
        self._enable_workspace(monkeypatch, tmp_path)
        from_id = "migrate-ws-none-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())

        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["migrated_workspace_files"] == 0
        assert data["skipped_workspace_files"] == 0

    def test_migrates_source_workspace_files_to_destination(self, tmp_path, monkeypatch):
        client = get_client()
        cfg = self._enable_workspace(monkeypatch, tmp_path)
        from_id = "migrate-ws-src-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        workspace.write_workspace_text_file(from_id, "targets.txt", "darklab.sh\n", cfg)
        workspace.create_workspace_directory(from_id, "reports/empty", cfg)

        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["migrated_workspace_files"] == 1
        assert data["skipped_workspace_files"] == 0
        assert data["migrated_workspace_directories"] >= 2
        assert workspace.read_workspace_text_file(to_id, "targets.txt", cfg) == "darklab.sh\n"
        assert workspace.list_workspace_files(from_id, cfg) == []
        assert any(item["path"] == "reports/empty" for item in workspace.list_workspace_directories(to_id, cfg))

    def test_migrate_workspace_keeps_destination_only_files(self, tmp_path, monkeypatch):
        client = get_client()
        cfg = self._enable_workspace(monkeypatch, tmp_path)
        from_id = "migrate-ws-dst-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        workspace.write_workspace_text_file(to_id, "existing.txt", "keep\n", cfg)

        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["migrated_workspace_files"] == 0
        assert data["skipped_workspace_files"] == 0
        assert workspace.read_workspace_text_file(to_id, "existing.txt", cfg) == "keep\n"

    def test_migrate_workspace_skips_conflicting_files_without_overwrite(self, tmp_path, monkeypatch):
        client = get_client()
        cfg = self._enable_workspace(monkeypatch, tmp_path)
        from_id = "migrate-ws-conflict-" + __import__("uuid").uuid4().hex[:8]
        to_id = str(__import__("uuid").uuid4())
        workspace.write_workspace_text_file(from_id, "shared.txt", "source\n", cfg)
        workspace.write_workspace_text_file(from_id, "from-only.txt", "move\n", cfg)
        workspace.write_workspace_text_file(to_id, "shared.txt", "dest\n", cfg)

        resp = client.post(
            "/session/migrate",
            json={"from_session_id": from_id, "to_session_id": to_id},
            headers={"X-Session-ID": from_id},
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["migrated_workspace_files"] == 1
        assert data["skipped_workspace_files"] == 1
        assert workspace.read_workspace_text_file(to_id, "shared.txt", cfg) == "dest\n"
        assert workspace.read_workspace_text_file(to_id, "from-only.txt", cfg) == "move\n"
        assert workspace.read_workspace_text_file(from_id, "shared.txt", cfg) == "source\n"


# ── /session/workflows ────────────────────────────────────────────────────────

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
                },
            ],
            "steps": [{"cmd": "dig {{domain}} A", "note": "resolve apex"}],
        }

    def test_create_lists_and_returns_normalized_workflow(self):
        client = get_client()
        session_id = "workflow-create-" + __import__("uuid").uuid4().hex[:8]

        create_resp = client.post(
            "/session/workflows",
            json=self._payload(),
            headers={"X-Session-ID": session_id},
        )
        list_resp = client.get("/session/workflows", headers={"X-Session-ID": session_id})
        created = json.loads(create_resp.data)["workflow"]
        listed = json.loads(list_resp.data)["items"]

        assert create_resp.status_code == 201
        assert created["source"] == "user"
        assert created["inputs"][0]["id"] == "domain"
        assert listed[0]["id"] == created["id"]

    def test_rejects_undeclared_workflow_variables(self):
        client = get_client()
        session_id = "workflow-invalid-" + __import__("uuid").uuid4().hex[:8]
        payload = self._payload()
        payload["inputs"] = []

        resp = client.post(
            "/session/workflows",
            json=payload,
            headers={"X-Session-ID": session_id},
        )

        assert resp.status_code == 400
        assert "variables" in json.loads(resp.data)["error"]

    def test_update_and_delete_are_session_scoped(self):
        client = get_client()
        session_id = "workflow-update-" + __import__("uuid").uuid4().hex[:8]
        other_session_id = "workflow-other-" + __import__("uuid").uuid4().hex[:8]
        created = json.loads(client.post(
            "/session/workflows",
            json=self._payload(),
            headers={"X-Session-ID": session_id},
        ).data)["workflow"]

        denied = client.put(
            f"/session/workflows/{created['id']}",
            json=self._payload("Other Edit"),
            headers={"X-Session-ID": other_session_id},
        )
        updated = client.put(
            f"/session/workflows/{created['id']}",
            json=self._payload("Updated DNS"),
            headers={"X-Session-ID": session_id},
        )
        deleted = client.delete(
            f"/session/workflows/{created['id']}",
            headers={"X-Session-ID": session_id},
        )

        assert denied.status_code == 404
        assert json.loads(updated.data)["workflow"]["title"] == "Updated DNS"
        assert deleted.status_code == 200
        assert json.loads(client.get(
            "/session/workflows",
            headers={"X-Session-ID": session_id},
        ).data)["items"] == []


# ── /session/recent-domains ───────────────────────────────────────────────────

class TestSessionRecentDomains:
    def _domains(self, session_id):
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT domain FROM recent_domains WHERE session_id = ? ORDER BY last_used DESC, domain ASC",
                (session_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def test_get_returns_empty_list_for_new_session(self):
        client = get_client()
        session_id = "recent-empty-" + __import__("uuid").uuid4().hex[:8]
        resp = client.get("/session/recent-domains", headers={"X-Session-ID": session_id})

        assert resp.status_code == 200
        assert json.loads(resp.data)["domains"] == []

    def test_post_normalizes_filters_and_caps_domains(self):
        client = get_client()
        session_id = "recent-save-" + __import__("uuid").uuid4().hex[:8]
        valid = [f"d{i}.example.com" for i in range(12)]
        resp = client.post(
            "/session/recent-domains",
            json={
                "domains": [
                    "Alpha.Example.com.",
                    "https://ignored.example",
                    "127.0.0.1",
                    "192.168.1",
                    "999.0.0.1",
                    "user@example.com",
                    "with/path.example",
                    "Alpha.Example.com",
                    *valid,
                ],
            },
            headers={"X-Session-ID": session_id},
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["saved"] == 10
        assert data["domains"] == [
            "alpha.example.com",
            "127.0.0.1",
            "d0.example.com",
            "d1.example.com",
            "d2.example.com",
            "d3.example.com",
            "d4.example.com",
            "d5.example.com",
            "d6.example.com",
            "d7.example.com",
        ]
        assert self._domains(session_id) == data["domains"]

    def test_post_is_session_scoped(self):
        client = get_client()
        session_a = "recent-scope-a-" + __import__("uuid").uuid4().hex[:8]
        session_b = "recent-scope-b-" + __import__("uuid").uuid4().hex[:8]

        client.post(
            "/session/recent-domains",
            json={"domains": ["alpha.example.com"]},
            headers={"X-Session-ID": session_a},
        )
        resp = client.get("/session/recent-domains", headers={"X-Session-ID": session_b})

        assert json.loads(resp.data)["domains"] == []

    def test_post_updates_existing_domain_count_and_recency(self):
        client = get_client()
        session_id = "recent-upsert-" + __import__("uuid").uuid4().hex[:8]

        client.post(
            "/session/recent-domains",
            json={"domains": ["alpha.example.com"]},
            headers={"X-Session-ID": session_id},
        )
        client.post(
            "/session/recent-domains",
            json={"domains": ["beta.example.org"]},
            headers={"X-Session-ID": session_id},
        )
        client.post(
            "/session/recent-domains",
            json={"domains": ["alpha.example.com"]},
            headers={"X-Session-ID": session_id},
        )

        with sqlite3.connect(DB_PATH) as conn:
            count = conn.execute(
                "SELECT use_count FROM recent_domains WHERE session_id = ? AND domain = ?",
                (session_id, "alpha.example.com"),
            ).fetchone()[0]
        resp = client.get("/session/recent-domains", headers={"X-Session-ID": session_id})
        assert json.loads(resp.data)["domains"][0] == "alpha.example.com"
        assert count == 2

    def test_post_rejects_non_list_payload(self):
        client = get_client()
        session_id = "recent-invalid-" + __import__("uuid").uuid4().hex[:8]
        resp = client.post(
            "/session/recent-domains",
            json={"domains": "alpha.example.com"},
            headers={"X-Session-ID": session_id},
        )

        assert resp.status_code == 400


# ── /session/run-count ────────────────────────────────────────────────────────

class TestSessionRunCount:
    def _seed_runs(self, session_id, count):
        import uuid
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(DB_PATH) as conn:
            for _ in range(count):
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, 'echo hi', ?)",
                    (str(uuid.uuid4()), session_id, now),
                )
            conn.commit()

    def test_returns_zero_for_empty_session(self):
        client = get_client()
        session_id = "run-count-empty-" + __import__("uuid").uuid4().hex[:8]
        resp = client.get("/session/run-count", headers={"X-Session-ID": session_id})
        assert resp.status_code == 200
        assert json.loads(resp.data)["count"] == 0
        assert json.loads(resp.data)["workflow_count"] == 0

    def test_returns_true_count(self):
        client = get_client()
        session_id = "run-count-seeded-" + __import__("uuid").uuid4().hex[:8]
        self._seed_runs(session_id, count=7)
        resp = client.get("/session/run-count", headers={"X-Session-ID": session_id})
        assert json.loads(resp.data)["count"] == 7

    def test_is_uncapped_beyond_history_panel_limit(self):
        """The count must not be capped by history_panel_limit (default 50)."""
        client = get_client()
        session_id = "run-count-uncapped-" + __import__("uuid").uuid4().hex[:8]
        self._seed_runs(session_id, count=75)
        resp = client.get("/session/run-count", headers={"X-Session-ID": session_id})
        assert json.loads(resp.data)["count"] == 75

    def test_is_scoped_to_session(self):
        client = get_client()
        session_a = "run-count-scope-a-" + __import__("uuid").uuid4().hex[:8]
        session_b = "run-count-scope-b-" + __import__("uuid").uuid4().hex[:8]
        self._seed_runs(session_a, count=3)
        self._seed_runs(session_b, count=5)
        resp = client.get("/session/run-count", headers={"X-Session-ID": session_a})
        assert json.loads(resp.data)["count"] == 3

    def test_returns_user_workflow_count(self):
        client = get_client()
        session_id = "run-count-workflows-" + __import__("uuid").uuid4().hex[:8]
        client.post(
            "/session/workflows",
            headers={"X-Session-ID": session_id},
            json=TestSessionWorkflows()._payload(),
        )

        resp = client.get("/session/run-count", headers={"X-Session-ID": session_id})

        assert json.loads(resp.data)["workflow_count"] == 1

    def test_returns_recent_domain_count(self):
        client = get_client()
        session_id = "run-count-recents-" + __import__("uuid").uuid4().hex[:8]
        client.post(
            "/session/recent-domains",
            headers={"X-Session-ID": session_id},
            json={"domains": ["alpha.example.com", "beta.example.org"]},
        )

        resp = client.get("/session/run-count", headers={"X-Session-ID": session_id})

        assert json.loads(resp.data)["recent_domain_count"] == 2


# ── /session/starred ──────────────────────────────────────────────────────────

class TestSessionStarred:
    def _count_stars(self, session_id):
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM starred_commands WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]

    def _get_stars(self, session_id):
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT command FROM starred_commands WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        return {row[0] for row in rows}

    # GET /session/starred

    def test_get_returns_empty_list_for_new_session(self):
        client = get_client()
        session_id = "get-stars-new-" + __import__("uuid").uuid4().hex[:8]
        resp = client.get("/session/starred", headers={"X-Session-ID": session_id})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["commands"] == []

    def test_get_returns_starred_commands(self):
        client = get_client()
        session_id = "get-stars-existing-" + __import__("uuid").uuid4().hex[:8]
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                (session_id, "nmap target"),
            )
            conn.commit()
        resp = client.get("/session/starred", headers={"X-Session-ID": session_id})
        data = json.loads(resp.data)
        assert "nmap target" in data["commands"]

    def test_get_is_scoped_to_session(self):
        client = get_client()
        session_a = "get-stars-scope-a-" + __import__("uuid").uuid4().hex[:8]
        session_b = "get-stars-scope-b-" + __import__("uuid").uuid4().hex[:8]
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                (session_a, "cmd-a"),
            )
            conn.commit()
        resp = client.get("/session/starred", headers={"X-Session-ID": session_b})
        data = json.loads(resp.data)
        assert data["commands"] == []

    # POST /session/starred

    def test_post_adds_starred_command(self):
        client = get_client()
        session_id = "post-stars-add-" + __import__("uuid").uuid4().hex[:8]
        resp = client.post(
            "/session/starred",
            json={"command": "dig example.com"},
            headers={"X-Session-ID": session_id},
        )
        assert resp.status_code == 200
        assert json.loads(resp.data)["ok"] is True
        assert "dig example.com" in self._get_stars(session_id)

    def test_post_is_idempotent(self):
        client = get_client()
        session_id = "post-stars-idem-" + __import__("uuid").uuid4().hex[:8]
        client.post(
            "/session/starred",
            json={"command": "ping target"},
            headers={"X-Session-ID": session_id},
        )
        client.post(
            "/session/starred",
            json={"command": "ping target"},
            headers={"X-Session-ID": session_id},
        )
        assert self._count_stars(session_id) == 1

    def test_post_rejects_missing_command(self):
        client = get_client()
        resp = client.post(
            "/session/starred",
            json={},
            headers={"X-Session-ID": "post-stars-no-cmd"},
        )
        assert resp.status_code == 400

    def test_post_rejects_empty_command(self):
        client = get_client()
        resp = client.post(
            "/session/starred",
            json={"command": ""},
            headers={"X-Session-ID": "post-stars-empty-cmd"},
        )
        assert resp.status_code == 400

    # DELETE /session/starred (single)

    def test_delete_removes_one_command(self):
        client = get_client()
        session_id = "del-stars-one-" + __import__("uuid").uuid4().hex[:8]
        with sqlite3.connect(DB_PATH) as conn:
            for cmd in ["keep", "remove"]:
                conn.execute(
                    "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                    (session_id, cmd),
                )
            conn.commit()
        client.delete(
            "/session/starred",
            json={"command": "remove"},
            headers={"X-Session-ID": session_id},
        )
        stars = self._get_stars(session_id)
        assert "keep" in stars
        assert "remove" not in stars

    def test_delete_one_is_idempotent(self):
        client = get_client()
        session_id = "del-stars-idem-" + __import__("uuid").uuid4().hex[:8]
        resp = client.delete(
            "/session/starred",
            json={"command": "nonexistent"},
            headers={"X-Session-ID": session_id},
        )
        assert resp.status_code == 200
        assert json.loads(resp.data)["ok"] is True

    def test_delete_one_only_affects_own_session(self):
        client = get_client()
        session_a = "del-stars-scope-a-" + __import__("uuid").uuid4().hex[:8]
        session_b = "del-stars-scope-b-" + __import__("uuid").uuid4().hex[:8]
        with sqlite3.connect(DB_PATH) as conn:
            for sid in [session_a, session_b]:
                conn.execute(
                    "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                    (sid, "shared-cmd"),
                )
            conn.commit()
        client.delete(
            "/session/starred",
            json={"command": "shared-cmd"},
            headers={"X-Session-ID": session_a},
        )
        assert self._count_stars(session_a) == 0
        assert self._count_stars(session_b) == 1

    # DELETE /session/starred (clear all)

    def test_delete_all_clears_session_stars(self):
        client = get_client()
        session_id = "del-stars-all-" + __import__("uuid").uuid4().hex[:8]
        with sqlite3.connect(DB_PATH) as conn:
            for cmd in ["cmd1", "cmd2", "cmd3"]:
                conn.execute(
                    "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                    (session_id, cmd),
                )
            conn.commit()
        resp = client.delete(
            "/session/starred",
            json={},
            headers={"X-Session-ID": session_id},
        )
        assert resp.status_code == 200
        assert self._count_stars(session_id) == 0

    def test_delete_all_does_not_affect_other_sessions(self):
        client = get_client()
        session_a = "del-all-scope-a-" + __import__("uuid").uuid4().hex[:8]
        session_b = "del-all-scope-b-" + __import__("uuid").uuid4().hex[:8]
        with sqlite3.connect(DB_PATH) as conn:
            for sid in [session_a, session_b]:
                conn.execute(
                    "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                    (sid, "cmd"),
                )
            conn.commit()
        client.delete(
            "/session/starred",
            json={},
            headers={"X-Session-ID": session_a},
        )
        assert self._count_stars(session_b) == 1


# ── /session/token/info ───────────────────────────────────────────────────────

class TestSessionTokenInfo:
    def test_returns_null_for_uuid_session(self):
        client = get_client()
        resp = client.get(
            "/session/token/info",
            headers={"X-Session-ID": "a1b2c3d4-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["token"] is None
        assert data["created"] is None

    def test_returns_token_for_tok_session(self):
        client = get_client()
        token = json.loads(client.get("/session/token/generate").data)["session_token"]
        resp = client.get("/session/token/info", headers={"X-Session-ID": token})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["token"] == token

    def test_returns_created_date_for_tok_session(self):
        client = get_client()
        token = json.loads(client.get("/session/token/generate").data)["session_token"]
        data = json.loads(client.get("/session/token/info", headers={"X-Session-ID": token}).data)
        assert data["created"] is not None
        assert len(data["created"]) > 0

    def test_returns_null_for_tok_not_in_db(self):
        """tok_ token that was never issued is treated as anonymous — both fields null."""
        client = get_client()
        phantom = "tok_" + "f" * 32
        data = json.loads(client.get("/session/token/info", headers={"X-Session-ID": phantom}).data)
        assert data["token"] is None
        assert data["created"] is None

    def test_revoked_token_is_treated_as_anonymous(self):
        """After revocation, using the old token returns anonymous (null) info."""
        client = get_client()
        token = json.loads(client.get("/session/token/generate").data)["session_token"]
        client.post("/session/token/revoke", json={"token": token})
        data = json.loads(client.get("/session/token/info", headers={"X-Session-ID": token}).data)
        assert data["token"] is None
        assert data["created"] is None


# ── /session/preferences ──────────────────────────────────────────────────────

class TestSessionPreferences:
    def test_returns_empty_preferences_when_none_saved(self):
        client = get_client()
        session_id = "prefs-empty-" + __import__("uuid").uuid4().hex[:8]
        resp = client.get("/session/preferences", headers={"X-Session-ID": session_id})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["preferences"] == {}
        assert data["updated"] is None

    def test_persists_and_returns_current_session_preferences(self):
        client = get_client()
        session_id = "prefs-save-" + __import__("uuid").uuid4().hex[:8]
        payload = {
            "preferences": {
                "pref_theme_name": "theme_light_blue",
                "pref_timestamps": "clock",
                "pref_run_notify": "on",
                "pref_prompt_username": "operator_1",
            }
        }
        save_resp = client.post("/session/preferences", json=payload, headers={"X-Session-ID": session_id})
        assert save_resp.status_code == 200

        get_resp = client.get("/session/preferences", headers={"X-Session-ID": session_id})
        data = json.loads(get_resp.data)
        assert data["preferences"] == payload["preferences"]
        assert data["updated"]

    def test_ignores_unknown_session_preference_keys(self):
        client = get_client()
        session_id = "prefs-filter-" + __import__("uuid").uuid4().hex[:8]
        resp = client.post(
            "/session/preferences",
            json={
                "preferences": {
                    "pref_theme_name": "theme_light_blue",
                    "pref_prompt_username": "../bad",
                    "pref_unknown": "x",
                }
            },
            headers={"X-Session-ID": session_id},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["preferences"] == {"pref_theme_name": "theme_light_blue"}


# ── /session/token/revoke ─────────────────────────────────────────────────────

class TestSessionTokenRevoke:
    def test_returns_200_for_existing_token(self):
        client = get_client()
        token = json.loads(client.get("/session/token/generate").data)["session_token"]
        resp = client.post("/session/token/revoke", json={"token": token})
        assert resp.status_code == 200
        assert json.loads(resp.data)["ok"] is True

    def test_deletes_token_from_db(self):
        client = get_client()
        token = json.loads(client.get("/session/token/generate").data)["session_token"]
        client.post("/session/token/revoke", json={"token": token})
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT 1 FROM session_tokens WHERE token = ?", (token,)
            ).fetchone()
        assert row is None

    def test_returns_404_for_unknown_token(self):
        client = get_client()
        fake = "tok_" + "b" * 32
        resp = client.post("/session/token/revoke", json={"token": fake})
        assert resp.status_code == 404

    def test_rejects_uuid_format(self):
        client = get_client()
        resp = client.post(
            "/session/token/revoke",
            json={"token": "a1b2c3d4-0000-0000-0000-000000000002"},
        )
        assert resp.status_code == 400

    def test_rejects_missing_token_field(self):
        client = get_client()
        resp = client.post("/session/token/revoke", json={})
        assert resp.status_code == 400

    def test_can_revoke_own_current_token(self):
        """Revoking the caller's own active token is permitted."""
        client = get_client()
        token = json.loads(client.get("/session/token/generate").data)["session_token"]
        resp = client.post(
            "/session/token/revoke",
            json={"token": token},
            headers={"X-Session-ID": token},
        )
        assert resp.status_code == 200

    def test_second_revoke_returns_404(self):
        """Once revoked, the same token cannot be revoked again."""
        client = get_client()
        token = json.loads(client.get("/session/token/generate").data)["session_token"]
        client.post("/session/token/revoke", json={"token": token})
        resp = client.post("/session/token/revoke", json={"token": token})
        assert resp.status_code == 404
