# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

from admin_helpers import operator_db as _operator_db

from core.database_access import get_db_connect
from services.auth import operator_grants, storage
from services.auth.contracts import PrincipalDisabled

operator_db = _operator_db


def principal():
    with get_db_connect()() as conn:
        bundle = storage.create_principal_with_credential(conn=conn)
        conn.commit()
    return bundle.principal.id


def test_grants_are_explicit_idempotent_and_audited(operator_db, caplog):
    target, peer = principal(), principal()
    assert not operator_grants.has_grant(target)
    assert not operator_grants.set_grant(target, granted=False)["changed"]
    assert operator_grants.set_grant(target, granted=True)["changed"]
    assert not operator_grants.set_grant(target, granted=True)["changed"]
    assert operator_grants.has_grant(target)
    assert not operator_grants.has_grant(peer)
    assert operator_grants.set_grant(target, granted=False)["changed"]
    assert not operator_grants.has_grant(target)
    assert not operator_grants.set_grant(target, granted=False)["changed"]
    with get_db_connect()() as conn:
        events = conn.execute("SELECT event_type, actor_role, target_id, details FROM audit_events "
                              "WHERE event_type LIKE ? ORDER BY created", ("instance_operator.%",)).fetchall()
        assert [row["event_type"] for row in events] == ["instance_operator.grant", "instance_operator.revoke"]
        for row in events:
            assert row["actor_role"] == "local_operator" and row["target_id"] == target
            details = row["details"] if isinstance(row["details"], dict) else json.loads(row["details"])
            assert details["source"] == "local_operator"


def test_disabled_principal_can_be_inspected_and_revoked_but_not_granted(operator_db):
    target = principal()
    operator_grants.set_grant(target, granted=True)
    with get_db_connect()() as conn:
        conn.execute("UPDATE principals SET status = 'disabled', disabled_at = ? WHERE id = ?",
                     ("2026-09-18T00:00:00+00:00", target))
        conn.commit()
    assert operator_grants.grant_status(target)["granted"]
    assert not operator_grants.has_grant(target)
    with pytest.raises(PrincipalDisabled):
        operator_grants.set_grant(target, granted=True)
    assert operator_grants.set_grant(target, granted=False)["changed"]
    assert not operator_grants.grant_status(target)["granted"]


def test_audit_failure_rolls_back_grant_and_does_not_publish_success(operator_db, monkeypatch, caplog):
    target = principal()
    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr(operator_grants, "record_event", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        operator_grants.set_grant(target, granted=True)
    assert not operator_grants.has_grant(target)
    assert not any(record.message == "INSTANCE_OPERATOR_GRANT_CHANGED" for record in caplog.records)


def test_local_list_pages_current_grants_and_reports_disabled_principals(operator_db, monkeypatch, capsys):
    active, disabled, revoked, never_granted = [principal() for _ in range(4)]
    for target in (active, disabled, revoked):
        operator_grants.set_grant(target, granted=True)
    operator_grants.set_grant(revoked, granted=False)
    with get_db_connect()() as conn:
        conn.execute("UPDATE principals SET status = 'disabled', disabled_at = ? WHERE id = ?",
                     ("2026-09-20T00:00:00+00:00", disabled))
        conn.commit()

    path = Path(__file__).resolve().parents[2] / "scripts/operations/manage_principal_access.py"
    spec = importlib.util.spec_from_file_location("operator_list_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_require_container", lambda: None)
    monkeypatch.setattr(module, "configure_logging", lambda *args, **kwargs: None)

    assert module.main(["operator-list", "--limit", "1"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["next_after"] == min(active, disabled)
    assert module.main(["operator-list", "--limit", "1", "--after", first["next_after"]]) == 0
    last = json.loads(capsys.readouterr().out)
    assert last["next_after"] is None
    rows = first["operators"] + last["operators"]
    assert [row["principal_id"] for row in rows] == sorted([active, disabled])
    assert {row["principal_id"]: row["eligible"] for row in rows} == {active: True, disabled: False}
    assert all(row["granted"] and row["granted_at"] and row["revoked_at"] is None for row in rows)
    assert revoked not in json.dumps(rows) and never_granted not in json.dumps(rows)
    assert all(set(row) == {"principal_id", "principal_status", "eligible", "granted", "granted_at", "revoked_at"}
               for row in rows)
    assert module.main(["operator-list", "--limit", "0"]) == 1
    assert capsys.readouterr().out == ""
    for target in (active, disabled):
        operator_grants.set_grant(target, granted=False)
    assert operator_grants.list_grants() == {"operators": [], "next_after": None}


@pytest.mark.parametrize("audit_enabled", [True, False])
def test_fresh_grant_command_logs_only_committed_changes_to_stderr(operator_db, tmp_path, audit_enabled):
    target = principal()
    config = tmp_path / "cli-conf"
    config.mkdir()
    (config / "config.yaml").write_text(
        f"log_level: INFO\nlog_format: gelf\naudit_log_enabled: {str(audit_enabled).lower()}\n"
    )
    env = {**os.environ, "APP_CONF_DIR": str(config), "APP_LOCAL_CONF_DIR": str(config),
           "DATABASE_BACKEND": operator_db.backend,
           "DATABASE_URL": str(operator_db.cfg.get("database_url") or "")}
    if operator_db.backend == "postgres":
        from psycopg.conninfo import conninfo_to_dict
        # The pool adds its JIT setting through PGOPTIONS, which takes precedence
        # over DSN options. Keep the subprocess in the fixture's isolated schema.
        env["PGOPTIONS"] = conninfo_to_dict(env["DATABASE_URL"])["options"]
    program = """
import sys
sys.path.insert(0, "scripts/operations")
import manage_principal_access as command
from core import database
if sys.argv[3] != "-":
    database.DB_PATH = sys.argv[3]
command._require_container = lambda: None
raise SystemExit(command.main([sys.argv[1], sys.argv[2]]))
"""
    for action, changed, granted in [("operator-grant", True, True), ("operator-grant", False, True),
                                     ("operator-revoke", True, False), ("operator-revoke", False, False)]:
        result = subprocess.run(
            [sys.executable, "-c", program, action, target, str(operator_db.path or "-")],
            cwd=Path(__file__).resolve().parents[2],
            env=env, capture_output=True, text=True, check=False, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["changed"] is changed and payload["granted"] is granted
        assert operator_grants.grant_status(target)["granted"] is granted
        events = [json.loads(line) for line in result.stderr.splitlines()]
        milestones = [event for event in events if event["short_message"] == "INSTANCE_OPERATOR_GRANT_CHANGED"]
        assert len(milestones) == int(changed)
        if changed:
            assert milestones[0]["level"] == 6
            assert milestones[0]["_principal_id"] == target
            assert milestones[0]["_event_source"] == "local_operator" and milestones[0]["_granted"] is granted
            assert "full_message" not in milestones[0]
