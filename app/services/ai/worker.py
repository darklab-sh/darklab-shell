# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Dedicated AI assist worker entry point."""

from __future__ import annotations

from collections.abc import Mapping

from contextlib import contextmanager
import logging
import signal
import threading
import time
from typing import TYPE_CHECKING, Any

from config import resolve_effective_cfg
from core.database_backend import is_transient_postgres_error
from core.helpers import get_log_session_id
from runtime_bootstrap import bootstrap_runtime, setup_metrics_environment

if TYPE_CHECKING:
    from services.ai.client import AIProviderResult

log = logging.getLogger("shell")

DEFAULT_POLL_SECONDS = 2.0
DEFAULT_LIMIT = 1
DEFAULT_ASSIST_HEARTBEAT_SECONDS = 30.0
_STOP = False
app_metrics: Any = None
AIClientError: Any = None
OpenAICompatibleClient: Any = None
AICoordinationUnavailable: Any = None
acquire_worker_slot: Any = None
release_worker_slot: Any = None
worker_slot_heartbeat: Any = None
build_run_context: Any = None
claim_next_assist: Any = None
complete_assist: Any = None
fail_assist: Any = None
heartbeat_assist: Any = None
reclaim_stale_assists: Any = None
replace_suggestion_validations: Any = None
update_assist_progress: Any = None
_VARIANT_RUNNERS: dict[str, Any] = {}
_RUNTIME_DEPENDENCY_NAMES = (
    "app_metrics",
    "AIClientError",
    "OpenAICompatibleClient",
    "AICoordinationUnavailable",
    "acquire_worker_slot",
    "release_worker_slot",
    "worker_slot_heartbeat",
    "build_run_context",
    "claim_next_assist",
    "complete_assist",
    "fail_assist",
    "heartbeat_assist",
    "reclaim_stale_assists",
    "replace_suggestion_validations",
    "update_assist_progress",
)


def _runtime_dependencies_loaded() -> bool:
    return bool(_VARIANT_RUNNERS) and all(globals().get(name) is not None for name in _RUNTIME_DEPENDENCY_NAMES)


def _load_runtime_dependencies() -> None:
    global app_metrics, AIClientError, OpenAICompatibleClient, AICoordinationUnavailable
    global acquire_worker_slot, release_worker_slot, worker_slot_heartbeat, build_run_context
    global claim_next_assist, complete_assist, fail_assist, heartbeat_assist
    global reclaim_stale_assists, replace_suggestion_validations, update_assist_progress

    if _runtime_dependencies_loaded():
        log.debug("AI_WORKER_DEPENDENCIES_SKIPPED", extra={"reason": "already_loaded"})
        return
    log.debug("AI_WORKER_DEPENDENCIES_LOADING")
    setup_metrics_environment(resolve_effective_cfg())
    from services import metrics as loaded_metrics  # noqa: PLC0415
    from services.ai import next_commands, summarize  # noqa: PLC0415
    from services.ai.client import (  # noqa: PLC0415
        AIClientError as LoadedAIClientError,
        OpenAICompatibleClient as LoadedOpenAICompatibleClient,
    )
    from services.ai.coordination import (  # noqa: PLC0415
        AICoordinationUnavailable as LoadedAICoordinationUnavailable,
        acquire_worker_slot as loaded_acquire_worker_slot,
        release_worker_slot as loaded_release_worker_slot,
        worker_slot_heartbeat as loaded_worker_slot_heartbeat,
    )
    from services.ai.context import build_run_context as loaded_build_run_context  # noqa: PLC0415
    from services.ai.storage import (  # noqa: PLC0415
        claim_next_assist as loaded_claim_next_assist,
        complete_assist as loaded_complete_assist,
        fail_assist as loaded_fail_assist,
        heartbeat_assist as loaded_heartbeat_assist,
        reclaim_stale_assists as loaded_reclaim_stale_assists,
        replace_suggestion_validations as loaded_replace_suggestion_validations,
        update_assist_progress as loaded_update_assist_progress,
    )

    app_metrics = loaded_metrics if app_metrics is None else app_metrics
    AIClientError = LoadedAIClientError if AIClientError is None else AIClientError
    OpenAICompatibleClient = (
        LoadedOpenAICompatibleClient if OpenAICompatibleClient is None else OpenAICompatibleClient
    )
    AICoordinationUnavailable = (
        LoadedAICoordinationUnavailable if AICoordinationUnavailable is None else AICoordinationUnavailable
    )
    acquire_worker_slot = loaded_acquire_worker_slot if acquire_worker_slot is None else acquire_worker_slot
    release_worker_slot = loaded_release_worker_slot if release_worker_slot is None else release_worker_slot
    worker_slot_heartbeat = loaded_worker_slot_heartbeat if worker_slot_heartbeat is None else worker_slot_heartbeat
    build_run_context = loaded_build_run_context if build_run_context is None else build_run_context
    claim_next_assist = loaded_claim_next_assist if claim_next_assist is None else claim_next_assist
    complete_assist = loaded_complete_assist if complete_assist is None else complete_assist
    fail_assist = loaded_fail_assist if fail_assist is None else fail_assist
    heartbeat_assist = loaded_heartbeat_assist if heartbeat_assist is None else heartbeat_assist
    reclaim_stale_assists = loaded_reclaim_stale_assists if reclaim_stale_assists is None else reclaim_stale_assists
    replace_suggestion_validations = (
        loaded_replace_suggestion_validations
        if replace_suggestion_validations is None
        else replace_suggestion_validations
    )
    update_assist_progress = loaded_update_assist_progress if update_assist_progress is None else update_assist_progress
    if not _VARIANT_RUNNERS:
        _VARIANT_RUNNERS.update({
            "summary": summarize.run,
            "next_commands": next_commands.run,
        })
    log.info(
        "AI_WORKER_DEPENDENCIES_LOADED",
        extra={"variants": ",".join(sorted(_VARIANT_RUNNERS)), "metrics_initialized": app_metrics is not None},
    )


def _handle_stop(signum, frame):  # noqa: ANN001
    global _STOP
    _STOP = True


def run_once(*, limit: int = DEFAULT_LIMIT, cfg: Mapping[str, Any] | None = None) -> int:
    """Reap stale assists and process a small batch of queued assists."""
    _load_runtime_dependencies()
    processed = reclaim_stale_assists()
    if processed:
        log.warning(
            "AI_ASSIST_STALE_RECLAIMED",
            extra={"count": processed, "stale_after_seconds": 300},
        )
    active_cfg = resolve_effective_cfg(cfg)
    for _ in range(max(1, int(limit))):
        try:
            slot = acquire_worker_slot(cfg=active_cfg)
        except AICoordinationUnavailable as exc:
            log.warning("AI_WORKER_COORDINATION_UNAVAILABLE", extra={"error": str(exc)})
            break
        if not slot.acquired:
            log.debug("AI_WORKER_BUSY", extra={"max_concurrent": active_cfg.get("ai_max_concurrent") or 1})
            break
        try:
            assist = claim_next_assist()
            if not assist:
                break
            with worker_slot_heartbeat(slot):
                _process_assist(assist, cfg=active_cfg)
            processed += 1
        finally:
            release_worker_slot(slot)
    return processed


def _process_assist(assist: dict, *, cfg: Mapping[str, Any] | None = None) -> None:
    _load_runtime_dependencies()
    active_cfg = resolve_effective_cfg(cfg)
    assist_id = str(assist.get("id") or "")
    run_id = str(assist.get("run_id") or "")
    session_id = str(assist.get("session_id") or "")
    team_id = str(assist.get("team_id") or "")
    variant = str(assist.get("variant") or "")
    provider_request_started = False
    try:
        runner = _VARIANT_RUNNERS.get(variant)
        if runner is None:
            raise AIClientError("ai_unsupported_variant", f"AI worker does not support variant {variant}")
        context = build_run_context(run_id, session_id=session_id, team_id=team_id, cfg=active_cfg, variant=variant)
        if str(assist.get("context_hash") or "") != context.context_hash:
            raise AIClientError("ai_context_changed", "Run context changed after assist was queued")
        heartbeat_assist(assist_id)
        client = OpenAICompatibleClient(
            active_cfg,
            session_token=session_id,
            secret_scope_token=team_id or session_id,
            progress_callback=_progress_updater(assist_id, run_id, variant),
        )
        log.info("AI_ASSIST_PROVIDER_REQUEST", extra={
            **_assist_scope_log_fields(assist),
            "assist_id": assist_id,
            "run_id": run_id,
            "variant": variant,
            "model": client.model,
            "connect_timeout_seconds": client.connect_timeout,
            "read_timeout_seconds": client.read_timeout,
        })
        provider_request_started = True
        with _assist_db_heartbeat(assist_id, run_id=run_id, variant=variant):
            payload, result, validation_rows, suggestion_count, rejected_count = runner(
                client,
                context=context.context,
                active_cfg=active_cfg,
                assist=assist,
                session_id=session_id,
                assist_id=assist_id,
                run_id=run_id,
            )
        if validation_rows:
            replace_suggestion_validations(assist_id, validation_rows)
        complete_assist(
            assist_id,
            payload=payload,
            raw_model_payload=result.raw_content,
            output_chars=result.output_chars,
            duration_ms=result.duration_ms,
        )
        log.info("AI_ASSIST_COMPLETED", extra={
            **_assist_scope_log_fields(assist),
            "assist_id": assist_id,
            "run_id": run_id,
            "variant": variant,
            "context_hash": context.context_hash,
            "prompt_version": assist.get("prompt_version") or "",
            "prompt_version_source": assist.get("prompt_version_source") or "",
            "model": assist.get("model") or "",
            "duration_ms": result.duration_ms,
            "input_chars": context.input_chars,
            "output_chars": result.output_chars,
            "estimated_input_tokens": context.estimated_input_tokens,
            "redacted_bytes": context.redacted_bytes,
            "suggestion_count": suggestion_count,
            "rejected_count": rejected_count,
            **_provider_timing_log_fields(result),
        })
    except AIClientError as exc:
        if not provider_request_started:
            _record_worker_error_metric(variant, exc.code, active_cfg)
        fail_assist(assist_id, error_code=exc.code, error_message=str(exc))
        log.warning("AI_ASSIST_FAILED", extra={
            **_assist_failure_log_fields(assist),
            "assist_id": assist_id,
            "run_id": run_id,
            "variant": variant,
            "error_code": exc.code,
            "error_message": str(exc)[:240],
            "http_status": exc.status,
        })
    except Exception as exc:  # noqa: BLE001
        _record_worker_error_metric(variant, "ai_unavailable", active_cfg)
        fail_assist(assist_id, error_code="ai_unavailable", error_message=str(exc))
        log.warning("AI_ASSIST_FAILED", exc_info=True, extra={
            **_assist_failure_log_fields(assist),
            "assist_id": assist_id,
            "run_id": run_id,
            "variant": variant,
            "error_code": "ai_unavailable",
            "error_message": str(exc)[:240],
        })


def _assist_failure_log_fields(assist: dict) -> dict[str, str]:
    return {
        **_assist_scope_log_fields(assist),
        "model": str(assist.get("model") or ""),
        "prompt_version": str(assist.get("prompt_version") or ""),
        "prompt_version_source": str(assist.get("prompt_version_source") or ""),
        "context_hash": str(assist.get("context_hash") or ""),
    }


def _assist_scope_log_fields(assist: dict) -> dict[str, str]:
    team_id = str(assist.get("team_id") or "")
    fields = {
        "team_id": team_id,
        "session": get_log_session_id(assist.get("session_id")),
        "secret_scope": "team" if team_id else "personal",
    }
    actor_member_id = str(assist.get("actor_member_id") or "")
    if actor_member_id:
        fields["actor_member_id"] = actor_member_id
    return fields


@contextmanager
def _assist_db_heartbeat(
    assist_id: str,
    *,
    run_id: str,
    variant: str,
    interval_seconds: float | None = None,
):
    stop = threading.Event()
    interval = DEFAULT_ASSIST_HEARTBEAT_SECONDS if interval_seconds is None else interval_seconds

    def refresh() -> None:
        while not stop.wait(max(0.05, float(interval))):
            try:
                heartbeat_assist(assist_id)
            except Exception:
                log.debug("AI_ASSIST_HEARTBEAT_FAILED", exc_info=True, extra={
                    "assist_id": assist_id,
                    "run_id": run_id,
                    "variant": variant,
                })

    thread = threading.Thread(target=refresh, name="ai-assist-db-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1.0)


def _record_worker_error_metric(variant: str, error_code: str, cfg: Mapping[str, Any]) -> None:
    _load_runtime_dependencies()
    app_metrics.record_ai_request(
        variant or "summary",
        "error",
        0.0,
        error_code=error_code or "ai_unavailable",
        provider=cfg.get("ai_provider", "openai_compatible"),
    )


def _provider_timing_log_fields(result: AIProviderResult) -> dict[str, int]:
    timings = getattr(result, "provider_timings", None)
    if not isinstance(timings, dict):
        return {}
    fields: dict[str, int] = {}
    mapping = {
        "prompt_n": "provider_prompt_tokens",
        "prompt_ms": "provider_prompt_ms",
        "predicted_n": "provider_predicted_tokens",
        "predicted_ms": "provider_predicted_ms",
        "total_n": "provider_total_tokens",
    }
    for source_key, log_key in mapping.items():
        value = timings.get(source_key)
        if isinstance(value, (int, float)):
            fields[log_key] = int(value)
    return fields


def _progress_updater(assist_id: str, run_id: str, variant: str):
    last_update = {"monotonic": 0.0, "tokens": -1, "chars": -1}

    def update(progress: dict) -> None:
        now = time.monotonic()
        tokens = int(progress.get("tokens_seen") or 0)
        chars = int(progress.get("output_chars_seen") or 0)
        if now - last_update["monotonic"] < 1.0 and tokens == last_update["tokens"] and chars == last_update["chars"]:
            return
        last_update.update({"monotonic": now, "tokens": tokens, "chars": chars})
        try:
            update_assist_progress(assist_id, progress)
        except Exception:
            log.debug("AI_ASSIST_PROGRESS_UPDATE_FAILED", exc_info=True, extra={
                "assist_id": assist_id,
                "run_id": run_id,
                "variant": variant,
            })

    return update


def run_forever(*, poll_seconds: float = DEFAULT_POLL_SECONDS) -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    log.info("AI_WORKER_STARTED")
    while not _STOP:
        try:
            processed = run_once()
        except Exception as exc:  # noqa: BLE001
            if is_transient_postgres_error(exc):
                log.warning("AI_WORKER_DATABASE_INTERRUPTED", extra={"error_type": type(exc).__name__})
                time.sleep(max(0.1, float(poll_seconds)))
                continue
            log.error("AI_WORKER_CRASHED", exc_info=True)
            raise
        log.debug("AI_WORKER_TICK", extra={"processed": processed})
        time.sleep(max(0.1, float(poll_seconds)))
    log.info("AI_WORKER_STOPPED")


def main() -> None:
    try:
        bootstrap_runtime(resolve_effective_cfg(), init_process=True, init_db=True, runtime_name="ai_worker")
    except Exception:
        log.error("AI_WORKER_BOOTSTRAP_FAILED", exc_info=True, extra={"phase": "bootstrap_runtime"})
        raise
    try:
        _load_runtime_dependencies()
    except Exception:
        log.error("AI_WORKER_BOOTSTRAP_FAILED", exc_info=True, extra={"phase": "load_runtime_dependencies"})
        raise
    run_forever()


if __name__ == "__main__":
    main()
