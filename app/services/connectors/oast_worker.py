# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Recoverable worker for operator-managed private OAST correlations."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import logging
import os
import signal
import time
from typing import Any

from config import resolve_effective_cfg
from runtime_bootstrap import bootstrap_runtime
from services.connectors.oast_config import (
    OastConnectorSettings,
    oast_connector_settings,
    resolve_oast_token,
)
from services.connectors.oast_correlation_lifecycle import (
    close_oast_correlation,
    expire_oast_correlations,
    purge_oast_correlations,
)
from services.connectors.oast_correlations import OastCorrelationError
from services.connectors.oast_interactions import ingest_oast_interaction
from services.connectors.oast_observability import (
    log_oast_cleanup_scope_mismatch,
    log_oast_provider_deregistration_failed,
    log_oast_provider_session_failed,
    log_oast_retry,
    oast_provider_scope_matches,
    safe_oast_error_code,
)
from services.connectors.oast_provider_contracts import OastProviderSession
from services.connectors.oast_provider_spool import (
    OastProviderSessionSpoolError,
    discard_oast_provider_session,
    load_oast_provider_session,
    oast_provider_session_is_staged,
    stale_oast_provider_session_ids,
    store_oast_provider_session,
)
from services.connectors.oast_provider_transport import (
    deregister_oast_provider_session,
    poll_oast_provider_session,
    register_oast_provider_session,
)
from services.connectors.oast_worker_lock import acquire_oast_worker_lock
from services.connectors.oast_worker_state import (
    oast_correlations_by_ids,
    oast_correlations_for_worker,
    record_oast_provider_rejections,
)


log = logging.getLogger("shell")
_STOP = False
_TICK_SECONDS = 5.0
_TERMINAL_STATUSES = frozenset({"closed", "failed", "expired"})


def _handle_stop(_signum, _frame) -> None:
    global _STOP
    _STOP = True


def _fail_unrecoverable_session(
    correlation: Mapping[str, object],
    exc: BaseException,
) -> None:
    correlation_id = str(correlation.get("id") or "")
    try:
        close_oast_correlation(
            str(correlation.get("session_id") or ""),
            correlation_id,
            team_id=str(correlation.get("team_id") or ""),
            failed=True,
            error_code=safe_oast_error_code(exc, "oast_provider_session_unrecoverable"),
            error_detail="The private OAST provider session could not be recovered",
        )
    except OastCorrelationError as close_error:
        if close_error.code != "oast_correlation_close_conflict":
            raise
    log_oast_provider_session_failed(correlation, exc)


def _register_session(
    correlation: Mapping[str, object],
    settings: OastConnectorSettings,
    token: str,
    cfg: Mapping[str, Any],
) -> OastProviderSession | None:
    session = register_oast_provider_session(
        settings,
        token,
        str(correlation.get("callback_label") or ""),
    )
    try:
        store_oast_provider_session(correlation, session, cfg)
    except OastProviderSessionSpoolError as exc:
        try:
            deregister_oast_provider_session(settings, token, session)
        except Exception as cleanup_exc:  # noqa: BLE001
            log_oast_provider_deregistration_failed(correlation, cleanup_exc)
        discard_oast_provider_session(str(correlation.get("id") or ""), cfg)
        _fail_unrecoverable_session(correlation, exc)
        return None
    return session


def _load_or_register_session(
    correlation: Mapping[str, object],
    settings: OastConnectorSettings,
    token: str,
    cfg: Mapping[str, Any],
) -> OastProviderSession | None:
    if not oast_provider_session_is_staged(str(correlation.get("id") or ""), cfg):
        return _register_session(correlation, settings, token, cfg)
    try:
        return load_oast_provider_session(correlation, cfg)
    except OastProviderSessionSpoolError as exc:
        _fail_unrecoverable_session(correlation, exc)
        return None


def process_oast_correlation(
    correlation: dict[str, Any],
    settings: OastConnectorSettings,
    token: str,
    cfg: Mapping[str, Any],
) -> None:
    """Register or poll one live correlation without exposing provider material."""
    if not oast_provider_scope_matches(correlation, settings):
        log_oast_retry(
            "OAST_PROVIDER_SCOPE_RETRY",
            correlation,
            RuntimeError("configured provider scope changed"),
        )
        return
    try:
        session = _load_or_register_session(correlation, settings, token, cfg)
        if session is None or str(correlation.get("status") or "") != "active":
            return
        batch = poll_oast_provider_session(settings, token, session)
        provider_rejected = batch.rejected_count + batch.ignored_shared_count
        if provider_rejected:
            record_oast_provider_rejections(
                str(correlation.get("id") or ""),
                provider_rejected,
            )
        for interaction in batch.interactions:
            try:
                ingest_oast_interaction(
                    str(correlation.get("session_id") or ""),
                    str(correlation.get("id") or ""),
                    interaction,
                    team_id=str(correlation.get("team_id") or ""),
                )
            except OastCorrelationError as exc:
                log_oast_retry("OAST_INTERACTION_REJECTED", correlation, exc)
    except Exception as exc:  # noqa: BLE001
        log_oast_retry("OAST_PROVIDER_RETRY", correlation, exc)


def cleanup_oast_provider_session(
    correlation: dict[str, Any],
    settings: OastConnectorSettings,
    token: str,
    cfg: Mapping[str, Any],
) -> bool:
    """Deregister and remove one staged terminal provider session."""
    if not oast_provider_scope_matches(correlation, settings):
        log_oast_cleanup_scope_mismatch(correlation, settings)
        return False
    try:
        session = load_oast_provider_session(correlation, cfg)
        deregister_oast_provider_session(settings, token, session)
    except Exception as exc:  # noqa: BLE001
        log_oast_retry("OAST_PROVIDER_CLEANUP_RETRY", correlation, exc)
        return False
    discard_oast_provider_session(str(correlation.get("id") or ""), cfg)
    return True


def run_once(
    *,
    limit: int = 50,
    cfg: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    active_cfg = resolve_effective_cfg(cfg)
    instant = datetime.now(timezone.utc)
    expire_oast_correlations(now=instant)
    stale_ids = stale_oast_provider_session_ids(active_cfg, grace_seconds=60)
    staged_rows = oast_correlations_by_ids(stale_ids)
    terminal_rows = [
        staged_rows[correlation_id]
        for correlation_id in stale_ids
        if correlation_id in staged_rows
        and str(staged_rows[correlation_id].get("status") or "") in _TERMINAL_STATUSES
    ]
    for correlation_id in stale_ids:
        if correlation_id not in staged_rows:
            discard_oast_provider_session(correlation_id, active_cfg)
    correlations = oast_correlations_for_worker(limit=limit)
    if not correlations and not terminal_rows:
        purge_oast_correlations(now=instant)
        return 0
    settings = oast_connector_settings(active_cfg)
    try:
        token = resolve_oast_token(settings, environ=environ)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "OAST_PROVIDER_CREDENTIAL_RETRY",
            extra={
                "correlation_count": len(correlations) + len(terminal_rows),
                "error_class": type(exc).__name__,
                "error_code": safe_oast_error_code(
                    exc, "oast_provider_credentials_unavailable"
                ),
            },
        )
        purge_oast_correlations(now=instant)
        return 0
    processed = 0
    for correlation in terminal_rows:
        cleanup_oast_provider_session(correlation, settings, token, active_cfg)
        processed += 1
    for correlation in correlations:
        process_oast_correlation(correlation, settings, token, active_cfg)
        processed += 1
    purge_oast_correlations(now=instant)
    return processed


def run_forever(*, tick_seconds: float = _TICK_SECONDS, limit: int = 50) -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    with acquire_oast_worker_lock(resolve_effective_cfg()) as acquired:
        if not acquired:
            log.info("OAST_WORKER_LOCK_HELD")
            return
        log.info("OAST_WORKER_STARTED", extra={"pid": os.getpid()})
        while not _STOP:
            try:
                run_once(limit=limit)
            except Exception:  # noqa: BLE001
                log.error("OAST_WORKER_TICK_FAILED", exc_info=True)
            time.sleep(max(0.5, float(tick_seconds)))
        log.info("OAST_WORKER_STOPPED", extra={"pid": os.getpid()})


def main() -> None:
    bootstrap_runtime(
        resolve_effective_cfg(),
        init_metrics=False,
        init_process=True,
        init_db=True,
        runtime_name="oast_worker",
    )
    run_forever()


if __name__ == "__main__":
    main()
