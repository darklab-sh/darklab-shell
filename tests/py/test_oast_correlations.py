# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Private OAST reservation and lifecycle contracts."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import sqlite3

import pytest

from core.database_backend import DatabaseBackend
from core.migrations import MIGRATIONS
from core.migrations.runner import run_migrations
from services.connectors.oast_config import OastConnectorSettings
from services.connectors.oast_correlation_lifecycle import (
    activate_oast_correlation,
    close_oast_correlation,
    expire_oast_correlations,
    purge_oast_correlations,
)
from services.connectors.oast_correlations import (
    OastCorrelationError,
    oast_correlation_for_owner,
    oast_correlations_for_owner_check,
    reserve_oast_correlation,
)


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def correlation_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn, MIGRATIONS, backend=DatabaseBackend.SQLITE)
    timestamp = NOW.isoformat()
    conn.execute(
        "INSERT INTO projects (id, session_id, name, slug, created, updated) "
        "VALUES ('project-oast', 'owner-a', 'OAST', 'oast', ?, ?)",
        (timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO entities (id, session_id, type, canonical_value, signature_hash, "
        "first_seen_at, last_seen_at, occurrence_count, created) VALUES "
        "('entity-oast', 'owner-a', 'domain', 'app.example.test', 'target-hash', "
        "?, ?, 1, ?)",
        (timestamp, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_links (id, project_id, entity_type, entity_id, created) "
        "VALUES ('link-oast', 'project-oast', 'domain', 'entity-oast', ?)",
        (timestamp,),
    )
    conn.execute(
        "INSERT INTO project_assessments ("
        "id, session_id, project_id, title, profile_key, profile_version, "
        "started_at, created_at, updated_at) VALUES "
        "('assessment-oast', 'owner-a', 'project-oast', 'OAST cycle', "
        "'web', '1.0', ?, ?, ?)",
        (timestamp, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessment_checks ("
        "id, assessment_id, category, check_key, target_entity_id, target_type, "
        "target_value, target_value_hash, policy_level, recommended_action_key, "
        "created_at, updated_at) VALUES ("
        "'check-oast', 'assessment-oast', 'validation', 'private_oast', "
        "'entity-oast', 'domain', 'app.example.test', 'target-hash', "
        "'intrusive', 'oast_private_callback', ?, ?)",
        (timestamp, timestamp),
    )
    try:
        yield conn
    finally:
        conn.close()


def _settings(*, enabled: bool = True, retention_seconds: int = 3600):
    return OastConnectorSettings(
        enabled=enabled,
        base_url="https://interactsh.internal.example",
        token_secret_id="DARKLAB_OAST_TOKEN",
        allowed_domain="callbacks.example.test",
        tls_verify=True,
        callback_retention_seconds=retention_seconds,
        privacy_acknowledged=True,
    )


def _reserve(correlation_db, suffix: str, *, now: datetime = NOW):
    return reserve_oast_correlation(
        "owner-a",
        "project-oast",
        "assessment-oast",
        "check-oast",
        "oast_private_callback",
        _settings(retention_seconds=300),
        window_seconds=60,
        correlation_id=f"ocr_{suffix * 32}",
        callback_label=f"dl-{suffix * 32}",
        now=now,
        conn=correlation_db,
    )


def test_reservation_is_private_owner_scoped_and_provider_free(correlation_db):
    reservation = _reserve(correlation_db, "a")

    assert reservation["id"] == "ocr_" + "a" * 32
    assert reservation["status"] == "reserved"
    assert reservation["run_id"] == ""
    assert reservation["callback_domain"] == "dl-" + "a" * 32 + ".callbacks.example.test"
    assert reservation["service_origin_sha256"] == sha256(
        b"https://interactsh.internal.example"
    ).hexdigest()
    assert reservation["active_until"] == "2026-08-09T12:01:00+00:00"
    assert reservation["purge_at"] == "2026-08-09T12:05:00+00:00"
    assert "DARKLAB_OAST_TOKEN" not in str(reservation)
    assert "interactsh.internal.example" not in str(reservation)
    assert oast_correlation_for_owner(
        "owner-b", reservation["id"], conn=correlation_db
    ) is None
    assert [
        item["id"]
        for item in oast_correlations_for_owner_check(
            "owner-a",
            "project-oast",
            "assessment-oast",
            "check-oast",
            conn=correlation_db,
        )
    ] == [reservation["id"]]


def test_team_reservation_uses_team_scope_instead_of_actor_session(correlation_db):
    correlation_db.execute(
        "UPDATE projects SET team_id = 'team-a' WHERE id = 'project-oast'"
    )
    correlation_db.execute(
        "UPDATE entities SET team_id = 'team-a' WHERE id = 'entity-oast'"
    )
    correlation_db.execute(
        "UPDATE project_assessments SET team_id = 'team-a' "
        "WHERE id = 'assessment-oast'"
    )

    reservation = reserve_oast_correlation(
        "actor-session",
        "project-oast",
        "assessment-oast",
        "check-oast",
        "oast_private_callback",
        _settings(retention_seconds=300),
        team_id="team-a",
        window_seconds=60,
        correlation_id="ocr_" + "e" * 32,
        callback_label="dl-" + "e" * 32,
        now=NOW,
        conn=correlation_db,
    )

    assert reservation["team_id"] == "team-a"
    assert oast_correlation_for_owner(
        "different-actor", reservation["id"], team_id="team-a", conn=correlation_db
    ) is not None
    assert oast_correlation_for_owner(
        "actor-session", reservation["id"], team_id="team-b", conn=correlation_db
    ) is None


def test_reservation_requires_current_intrusive_action_and_bounded_window(correlation_db):
    with pytest.raises(OastCorrelationError) as exc_info:
        reserve_oast_correlation(
            "owner-a",
            "project-oast",
            "assessment-oast",
            "check-oast",
            "oast_private_callback",
            _settings(enabled=False),
            conn=correlation_db,
        )
    assert exc_info.value.code == "oast_correlation_disabled"

    with pytest.raises(OastCorrelationError) as exc_info:
        reserve_oast_correlation(
            "owner-a",
            "project-oast",
            "assessment-oast",
            "check-oast",
            "oast_other_callback",
            _settings(),
            conn=correlation_db,
        )
    assert exc_info.value.code == "oast_correlation_scope_changed"

    with pytest.raises(OastCorrelationError) as exc_info:
        reserve_oast_correlation(
            "owner-a",
            "project-oast",
            "assessment-oast",
            "check-oast",
            "oast_private_callback",
            _settings(retention_seconds=300),
            window_seconds=301,
            conn=correlation_db,
        )
    assert exc_info.value.code == "oast_correlation_window_invalid"

    correlation_db.execute(
        "UPDATE project_assessment_checks SET policy_level = 'standard' "
        "WHERE id = 'check-oast'"
    )
    with pytest.raises(OastCorrelationError) as exc_info:
        _reserve(correlation_db, "b")
    assert exc_info.value.code == "oast_correlation_scope_changed"


def test_lifecycle_binds_one_run_per_check_then_expires_and_purges(correlation_db):
    first = _reserve(correlation_db, "c")
    second = _reserve(correlation_db, "d")
    run_id = "12345678-1234-4123-8123-123456789abc"

    active = activate_oast_correlation(
        "owner-a", first["id"], run_id, now=NOW, conn=correlation_db
    )
    assert active["status"] == "active"
    assert active["run_id"] == run_id
    assert active["activated_at"] == NOW.isoformat()

    with pytest.raises(OastCorrelationError) as exc_info:
        activate_oast_correlation(
            "owner-a", second["id"], run_id, now=NOW, conn=correlation_db
        )
    assert exc_info.value.code == "oast_correlation_run_conflict"

    closed = close_oast_correlation(
        "owner-a", first["id"], now=NOW + timedelta(seconds=30), conn=correlation_db
    )
    assert closed["status"] == "closed"
    assert closed["closed_at"] == "2026-08-09T12:00:30+00:00"
    with pytest.raises(OastCorrelationError) as exc_info:
        close_oast_correlation("owner-a", first["id"], conn=correlation_db)
    assert exc_info.value.code == "oast_correlation_close_conflict"

    assert expire_oast_correlations(
        now=NOW + timedelta(seconds=61), conn=correlation_db
    ) == 1
    expired = oast_correlation_for_owner(
        "owner-a", second["id"], conn=correlation_db
    )
    assert expired is not None
    assert expired["status"] == "expired"
    assert expired["error_code"] == "oast_correlation_expired"
    assert purge_oast_correlations(
        now=NOW + timedelta(seconds=301), conn=correlation_db
    ) == 2
    assert correlation_db.execute(
        "SELECT COUNT(*) FROM oast_correlations"
    ).fetchone()[0] == 0


def test_reservation_rejects_instead_of_evicting_at_check_limit(correlation_db):
    for suffix in ("1", "2", "3", "4"):
        _reserve(correlation_db, suffix)

    with pytest.raises(OastCorrelationError) as exc_info:
        _reserve(correlation_db, "5")
    assert exc_info.value.code == "oast_correlation_check_limit"
    assert correlation_db.execute(
        "SELECT COUNT(*) FROM oast_correlations"
    ).fetchone()[0] == 4
