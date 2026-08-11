# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Recoverable private OAST worker tests with local fakes only."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
from unittest import mock

from core.database_backend import DatabaseBackend
from services.connectors import oast_worker
from services.connectors import oast_worker_lock
from services.connectors import oast_observability
from services.connectors import oast_readiness
from services.connectors.oast_config import (
    OastConnectorSettings,
    OastConnectorUnavailable,
)
from services.connectors.oast_correlations import OastCorrelationError
from services.connectors.oast_provider_contracts import (
    OastProviderPollBatch,
    OastProviderSession,
)
from services.connectors.oast_provider_spool import OastProviderSessionSpoolError
from services.connectors.oast_worker_state import (
    oast_correlations_by_ids,
    oast_correlations_for_worker,
    record_oast_provider_rejections,
)


_CORRELATION_ID = "ocr_0123456789abcdef0123456789abcdef"
_CALLBACK_LABEL = "abcdefghijklmnopqrstuvwxy01234567"


def _settings() -> OastConnectorSettings:
    return OastConnectorSettings(
        enabled=True,
        base_url="https://interactsh.example.test",
        token_secret_id="DARKLAB_OAST_TOKEN",
        allowed_domain="callbacks.example.test",
        tls_verify=True,
        callback_retention_seconds=3600,
        privacy_acknowledged=True,
    )


def _correlation(status: str = "reserved", **changes: object) -> dict[str, object]:
    settings = _settings()
    value: dict[str, object] = {
        "id": _CORRELATION_ID,
        "session_id": "owner-a",
        "team_id": "",
        "status": status,
        "callback_label": _CALLBACK_LABEL,
        "allowed_domain": settings.allowed_domain,
        "service_origin_sha256": sha256(settings.base_url.encode()).hexdigest(),
    }
    value.update(changes)
    return value


def _session() -> OastProviderSession:
    return OastProviderSession(
        callback_label=_CALLBACK_LABEL,
        correlation_id=_CALLBACK_LABEL[:20],
        secret_key="00000000-0000-4000-8000-000000000000",
        private_key_pem=b"private",
    )


def test_oast_worker_registers_reserved_session_without_polling():
    correlation = _correlation()
    session = _session()
    with (
        mock.patch.object(oast_worker, "oast_provider_session_is_staged", return_value=False),
        mock.patch.object(
            oast_worker, "register_oast_provider_session", return_value=session
        ) as register,
        mock.patch.object(oast_worker, "store_oast_provider_session") as store,
        mock.patch.object(oast_worker, "poll_oast_provider_session") as poll,
    ):
        oast_worker.process_oast_correlation(
            correlation, _settings(), "provider-token", {"data_dir": "/tmp/data"}
        )

    register.assert_called_once_with(_settings(), "provider-token", _CALLBACK_LABEL)
    store.assert_called_once_with(correlation, session, {"data_dir": "/tmp/data"})
    poll.assert_not_called()


def test_oast_worker_polls_active_session_and_records_bounded_rejects():
    correlation = _correlation("active")
    interaction = {
        "protocol": "dns",
        "callback_label": _CALLBACK_LABEL,
        "observed_at": "2026-08-09T12:00:00+00:00",
        "details": {},
    }
    batch = OastProviderPollBatch((interaction,), 2, 1)
    with (
        mock.patch.object(oast_worker, "oast_provider_session_is_staged", return_value=True),
        mock.patch.object(oast_worker, "load_oast_provider_session", return_value=_session()),
        mock.patch.object(oast_worker, "poll_oast_provider_session", return_value=batch),
        mock.patch.object(oast_worker, "record_oast_provider_rejections") as rejected,
        mock.patch.object(oast_worker, "ingest_oast_interaction") as ingest,
    ):
        oast_worker.process_oast_correlation(
            correlation, _settings(), "provider-token", {"data_dir": "/tmp/data"}
        )

    rejected.assert_called_once_with(_CORRELATION_ID, 3)
    ingest.assert_called_once_with(
        "owner-a", _CORRELATION_ID, interaction, team_id=""
    )


def test_oast_worker_aggregates_interaction_rejections_by_error_code():
    correlation = _correlation("active")
    interaction = {
        "protocol": "dns",
        "callback_label": _CALLBACK_LABEL,
        "observed_at": "2026-08-09T12:00:00+00:00",
        "details": {},
    }
    rejected = OastCorrelationError("oast_interaction_scope_mismatch", "private")
    batch = OastProviderPollBatch((interaction, interaction), 0, 0)
    with (
        mock.patch.object(oast_worker, "oast_provider_session_is_staged", return_value=True),
        mock.patch.object(oast_worker, "load_oast_provider_session", return_value=_session()),
        mock.patch.object(oast_worker, "poll_oast_provider_session", return_value=batch),
        mock.patch.object(oast_worker, "ingest_oast_interaction", side_effect=rejected),
        mock.patch.object(oast_worker, "log_oast_retry") as retry_log,
    ):
        oast_worker.process_oast_correlation(
            correlation, _settings(), "provider-token", {"data_dir": "/tmp/data"}
        )
    retry_log.assert_called_once_with(
        "OAST_INTERACTION_REJECTED",
        correlation,
        rejected,
        retryable=False,
        next_retry_seconds=0,
        occurrence_count=2,
    )


def test_oast_worker_retries_scope_drift_without_contacting_provider():
    correlation = _correlation(service_origin_sha256="f" * 64)
    with mock.patch.object(oast_worker, "register_oast_provider_session") as register:
        oast_worker.process_oast_correlation(
            correlation, _settings(), "provider-token", {"data_dir": "/tmp/data"}
        )
    register.assert_not_called()


def test_oast_worker_fails_corrupt_or_unstorable_private_sessions():
    correlation = _correlation()
    unavailable = OastProviderSessionSpoolError(
        "oast_provider_session_invalid", "session unavailable"
    )
    with (
        mock.patch.object(oast_worker, "oast_provider_session_is_staged", return_value=True),
        mock.patch.object(
            oast_worker, "load_oast_provider_session", side_effect=unavailable
        ),
        mock.patch.object(oast_worker, "close_oast_correlation") as close,
        mock.patch.object(oast_worker, "register_oast_provider_session") as register,
        mock.patch.object(
            oast_worker, "log_oast_provider_session_failed"
        ) as failure_log,
    ):
        oast_worker.process_oast_correlation(
            correlation, _settings(), "provider-token", {"data_dir": "/tmp/data"}
        )
    register.assert_not_called()
    failure_log.assert_called_once_with(correlation, unavailable)
    assert close.call_args.kwargs == {
        "team_id": "",
        "failed": True,
        "error_code": "oast_provider_session_invalid",
        "error_detail": "The private OAST provider session could not be recovered",
    }

    session = _session()
    with (
        mock.patch.object(oast_worker, "oast_provider_session_is_staged", return_value=False),
        mock.patch.object(
            oast_worker, "register_oast_provider_session", return_value=session
        ),
        mock.patch.object(
            oast_worker, "store_oast_provider_session", side_effect=unavailable
        ),
        mock.patch.object(oast_worker, "deregister_oast_provider_session") as deregister,
        mock.patch.object(
            oast_worker, "log_oast_provider_deregistration_failed"
        ) as deregister_log,
        mock.patch.object(oast_worker, "discard_oast_provider_session") as discard,
        mock.patch.object(oast_worker, "close_oast_correlation") as close,
    ):
        oast_worker.process_oast_correlation(
            correlation, _settings(), "provider-token", {"data_dir": "/tmp/data"}
        )
    deregister.assert_called_once_with(_settings(), "provider-token", session)
    deregister_log.assert_not_called()
    discard.assert_called_once_with(_CORRELATION_ID, {"data_dir": "/tmp/data"})
    assert close.call_args.kwargs["failed"] is True


def test_oast_worker_cleans_up_only_after_confirmed_deregistration():
    correlation = _correlation("expired")
    cfg = {"data_dir": "/tmp/data"}
    with (
        mock.patch.object(oast_worker, "load_oast_provider_session", return_value=_session()),
        mock.patch.object(oast_worker, "deregister_oast_provider_session") as deregister,
        mock.patch.object(oast_worker, "discard_oast_provider_session") as discard,
    ):
        assert oast_worker.cleanup_oast_provider_session(
            correlation, _settings(), "provider-token", cfg
        ) is True
    deregister.assert_called_once()
    discard.assert_called_once_with(_CORRELATION_ID, cfg)

    with (
        mock.patch.object(oast_worker, "load_oast_provider_session", return_value=_session()),
        mock.patch.object(
            oast_worker,
            "deregister_oast_provider_session",
            side_effect=RuntimeError("temporary"),
        ),
        mock.patch.object(oast_worker, "discard_oast_provider_session") as discard,
    ):
        assert oast_worker.cleanup_oast_provider_session(
            correlation, _settings(), "provider-token", cfg
        ) is False
    discard.assert_not_called()

    changed_settings = OastConnectorSettings(
        **{**_settings().__dict__, "allowed_domain": "changed.example.test"}
    )
    with mock.patch.object(
        oast_worker, "log_oast_cleanup_scope_mismatch"
    ) as mismatch_log:
        assert oast_worker.cleanup_oast_provider_session(
            correlation, changed_settings, "provider-token", cfg
        ) is False
    mismatch_log.assert_called_once_with(correlation, changed_settings)


def test_oast_cleanup_observability_is_bounded_and_redacted():
    first = oast_observability.claim_oast_warning(
        "OAST_TEST_WARNING", _CORRELATION_ID, now=100.0
    )
    repeated = oast_observability.claim_oast_warning(
        "OAST_TEST_WARNING", _CORRELATION_ID, now=101.0
    )
    resumed = oast_observability.claim_oast_warning(
        "OAST_TEST_WARNING", _CORRELATION_ID, now=161.0
    )
    assert first == (True, 0)
    assert repeated == (False, 1)
    assert resumed == (True, 1)

    sensitive_error = OSError("/private/spool/path provider-secret")
    with mock.patch.object(oast_observability.log, "error") as error_log:
        oast_observability.log_oast_spool_cleanup_failed(
            _CORRELATION_ID, sensitive_error
        )
    _, kwargs = error_log.call_args
    assert kwargs["extra"] == {
        "correlation_id": _CORRELATION_ID,
        "cleanup_stage": "local_spool",
        "error_class": "OSError",
    }
    assert "provider-secret" not in repr(kwargs)
    assert "/private/spool/path" not in repr(kwargs)

    with mock.patch.object(oast_observability.log, "error") as error_log:
        oast_observability.log_oast_provider_deregistration_failed(
            _correlation(), sensitive_error
        )
    _, kwargs = error_log.call_args
    assert kwargs["extra"]["cleanup_stage"] == "registration_rollback"
    assert kwargs["extra"]["error_code"] == "oast_provider_deregistration_failed"
    assert "provider-secret" not in repr(kwargs)
    assert "/private/spool/path" not in repr(kwargs)

    changed_settings = OastConnectorSettings(
        **{**_settings().__dict__, "allowed_domain": "changed.example.test"}
    )
    with (
        mock.patch.object(
            oast_observability, "claim_oast_warning", return_value=(True, 2)
        ),
        mock.patch.object(oast_observability.log, "warning") as warning_log,
    ):
        oast_observability.log_oast_cleanup_scope_mismatch(
            _correlation(), changed_settings
        )
    _, kwargs = warning_log.call_args
    assert kwargs["extra"]["callback_scope_changed"] is True
    assert kwargs["extra"]["service_origin_changed"] is False
    assert kwargs["extra"]["suppressed_repeat_count"] == 2
    assert "changed.example.test" not in repr(kwargs)

    with mock.patch.object(oast_observability.log, "error") as error_log:
        oast_observability.log_oast_provider_session_failed(
            _correlation("active"), sensitive_error
        )
    event, = error_log.call_args.args
    _, kwargs = error_log.call_args
    assert event == "OAST_PROVIDER_SESSION_FAILED"
    assert kwargs["extra"] == {
        "correlation_id": _CORRELATION_ID,
        "from_status": "active",
        "to_status": "failed",
        "error_class": "OSError",
        "error_code": "oast_provider_session_unrecoverable",
    }
    assert "provider-secret" not in repr(kwargs)
    assert "/private/spool/path" not in repr(kwargs)


def test_oast_retry_observability_suppresses_repeats_with_attempt_context():
    event = "OAST_TEST_RETRY"
    correlation = _correlation("active")
    failure = RuntimeError("provider payload secret")
    oast_observability.clear_oast_retry(event, _CORRELATION_ID)
    with (
        mock.patch.object(
            oast_observability,
            "claim_oast_warning",
            side_effect=((True, 0), (False, 1)),
        ),
        mock.patch.object(oast_observability.log, "warning") as warning_log,
        mock.patch.object(oast_observability.log, "debug") as debug_log,
    ):
        oast_observability.log_oast_retry(event, correlation, failure)
        oast_observability.log_oast_retry(event, correlation, failure)

    warning_log.assert_called_once()
    assert warning_log.call_args.args == (event,)
    assert warning_log.call_args.kwargs["extra"]["attempt"] == 1
    assert warning_log.call_args.kwargs["extra"]["retryable"] is True
    assert warning_log.call_args.kwargs["extra"]["next_retry_seconds"] == 5.0
    debug_log.assert_called_once()
    assert debug_log.call_args.args == ("OAST_PROVIDER_RETRY_SUPPRESSED",)
    assert debug_log.call_args.kwargs["extra"]["attempt"] == 2
    assert debug_log.call_args.kwargs["extra"]["suppressed_repeat_count"] == 1
    assert "provider payload secret" not in repr(warning_log.call_args)
    assert "provider payload secret" not in repr(debug_log.call_args)


def test_oast_readiness_reports_spool_failure_once_without_private_values():
    unavailable = OastProviderSessionSpoolError(
        "oast_provider_spool_unavailable", "private path"
    )
    correlation = _correlation()
    with (
        mock.patch.object(
            oast_readiness,
            "oast_provider_session_is_staged",
            side_effect=unavailable,
        ),
        mock.patch.object(
            oast_readiness, "log_oast_spool_unavailable"
        ) as unavailable_log,
    ):
        assert oast_readiness.assessment_oast_provider_ready(correlation) is False
    unavailable_log.assert_called_once_with(_CORRELATION_ID, unavailable)


def test_oast_registration_rollback_reports_provider_cleanup_failure():
    correlation = _correlation()
    session = _session()
    spool_error = OastProviderSessionSpoolError(
        "oast_provider_session_store_failed", "unavailable"
    )
    cleanup_error = RuntimeError("provider response secret")
    with (
        mock.patch.object(oast_worker, "oast_provider_session_is_staged", return_value=False),
        mock.patch.object(
            oast_worker, "register_oast_provider_session", return_value=session
        ),
        mock.patch.object(
            oast_worker, "store_oast_provider_session", side_effect=spool_error
        ),
        mock.patch.object(
            oast_worker,
            "deregister_oast_provider_session",
            side_effect=cleanup_error,
        ),
        mock.patch.object(
            oast_worker, "log_oast_provider_deregistration_failed"
        ) as cleanup_log,
        mock.patch.object(oast_worker, "discard_oast_provider_session"),
        mock.patch.object(oast_worker, "close_oast_correlation"),
    ):
        oast_worker.process_oast_correlation(
            correlation, _settings(), "provider-token", {"data_dir": "/tmp/data"}
        )
    cleanup_log.assert_called_once_with(correlation, cleanup_error)


def test_oast_worker_tick_reconciles_orphans_terminal_sessions_and_live_work():
    orphan_id = "ocr_11111111111111111111111111111111"
    terminal_id = "ocr_22222222222222222222222222222222"
    terminal = _correlation("closed", id=terminal_id)
    live = _correlation("active")
    with (
        mock.patch.object(oast_worker, "expire_oast_correlations") as expire,
        mock.patch.object(
            oast_worker,
            "stale_oast_provider_session_ids",
            return_value=(orphan_id, terminal_id),
        ),
        mock.patch.object(
            oast_worker, "oast_correlations_by_ids", return_value={terminal_id: terminal}
        ),
        mock.patch.object(
            oast_worker, "oast_correlations_for_worker", return_value=[live]
        ),
        mock.patch.object(oast_worker, "oast_connector_settings", return_value=_settings()),
        mock.patch.object(oast_worker, "resolve_oast_token", return_value="provider-token"),
        mock.patch.object(oast_worker, "discard_oast_provider_session") as discard,
        mock.patch.object(oast_worker, "cleanup_oast_provider_session") as cleanup,
        mock.patch.object(oast_worker, "process_oast_correlation") as process,
        mock.patch.object(oast_worker, "purge_oast_correlations") as purge,
    ):
        assert oast_worker.run_once(cfg={"data_dir": "/tmp/data"}) == 2

    expire.assert_called_once()
    discard.assert_called_once_with(orphan_id, {"data_dir": "/tmp/data"})
    cleanup.assert_called_once_with(
        terminal, _settings(), "provider-token", {"data_dir": "/tmp/data"}
    )
    process.assert_called_once_with(
        live, _settings(), "provider-token", {"data_dir": "/tmp/data"}
    )
    purge.assert_called_once()


def test_oast_worker_tick_keeps_live_work_when_credentials_are_unavailable():
    with (
        mock.patch.object(oast_worker, "expire_oast_correlations"),
        mock.patch.object(oast_worker, "stale_oast_provider_session_ids", return_value=()),
        mock.patch.object(oast_worker, "oast_correlations_by_ids", return_value={}),
        mock.patch.object(
            oast_worker, "oast_correlations_for_worker", return_value=[_correlation()]
        ),
        mock.patch.object(oast_worker, "oast_connector_settings", return_value=_settings()),
        mock.patch.object(
            oast_worker,
            "resolve_oast_token",
            side_effect=OastConnectorUnavailable("oast_token_unavailable", "missing"),
        ),
        mock.patch.object(oast_worker, "log_oast_retry") as retry_log,
        mock.patch.object(oast_worker, "process_oast_correlation") as process,
        mock.patch.object(oast_worker, "purge_oast_correlations"),
    ):
        assert oast_worker.run_once(cfg={"data_dir": "/tmp/data"}) == 0
    process.assert_not_called()
    retry_log.assert_called_once()
    assert retry_log.call_args.args[0:2] == (
        "OAST_PROVIDER_CREDENTIAL_RETRY",
        None,
    )
    assert retry_log.call_args.kwargs["correlation_count"] == 1


def test_oast_worker_state_queries_are_bounded_and_update_active_rejects():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE oast_correlations (id TEXT PRIMARY KEY, status TEXT, "
        "created_at TEXT, callback_label TEXT, allowed_domain TEXT, "
        "rejected_count INTEGER, updated_at TEXT)"
    )
    for correlation_id, status, created in (
        (_CORRELATION_ID, "reserved", "2026-08-09T10:00:00+00:00"),
        ("ocr_11111111111111111111111111111111", "active", "2026-08-09T11:00:00+00:00"),
        ("ocr_22222222222222222222222222222222", "closed", "2026-08-09T09:00:00+00:00"),
    ):
        conn.execute(
            "INSERT INTO oast_correlations VALUES (?, ?, ?, ?, ?, 0, ?)",
            (
                correlation_id,
                status,
                created,
                _CALLBACK_LABEL,
                "callbacks.example.test",
                created,
            ),
        )

    rows = oast_correlations_for_worker(limit=50, conn=conn)
    assert [row["status"] for row in rows] == ["active", "reserved"]
    selected = oast_correlations_by_ids(
        [_CORRELATION_ID, "../../invalid", "ocr_22222222222222222222222222222222"],
        conn=conn,
    )
    assert set(selected) == {
        _CORRELATION_ID,
        "ocr_22222222222222222222222222222222",
    }
    assert record_oast_provider_rejections(
        "ocr_11111111111111111111111111111111",
        3,
        now=datetime(2026, 8, 9, 12, tzinfo=timezone.utc),
        conn=conn,
    ) == 1
    assert conn.execute(
        "SELECT rejected_count FROM oast_correlations WHERE id = ?",
        ("ocr_11111111111111111111111111111111",),
    ).fetchone()[0] == 3


def test_oast_worker_lock_is_singleton_for_sqlite():
    with tempfile.TemporaryDirectory() as tmp:
        with (
            mock.patch.object(oast_worker_lock, "resolve_data_dir", return_value=tmp),
            mock.patch.object(
                oast_worker_lock.database, "DB_BACKEND", DatabaseBackend.SQLITE
            ),
        ):
            with oast_worker_lock.acquire_oast_worker_lock() as acquired:
                assert acquired is True
                assert (Path(tmp) / "oast-worker.lock").stat().st_mode & 0o777 == 0o600
                with oast_worker_lock.acquire_oast_worker_lock() as duplicate:
                    assert duplicate is False
