# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json

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
