"""
Tests for session token routes: /session/token/generate and /session/migrate.
"""
import json
import sqlite3

import app as shell_app
from database import DB_PATH


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
        uuid = __import__("uuid").uuid4().hex[:8] + "-" + "x" * 4 + "-" + "x" * 4 + "-" + "x" * 4 + "-" + "x" * 12
        resp = client.post("/session/token/verify", json={"token": uuid})
        assert resp.status_code == 200
        assert json.loads(resp.data)["exists"] is True

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
