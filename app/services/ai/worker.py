"""Dedicated AI assist worker entry point."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import signal
import threading
import time

from config import CFG
from core.database_backend import is_transient_postgres_error
from core.helpers import get_log_session_id
from core.logging_setup import configure_logging
from services import metrics as app_metrics
from services.ai.client import AIClientError, AIProviderResult, OpenAICompatibleClient
from services.ai.coordination import (
    AICoordinationUnavailable,
    acquire_worker_slot,
    release_worker_slot,
    worker_slot_heartbeat,
)
from services.ai.context import build_run_context
from services.ai import next_commands, summarize
from services.ai.storage import (
    claim_next_assist,
    complete_assist,
    fail_assist,
    heartbeat_assist,
    reclaim_stale_assists,
    replace_suggestion_validations,
    update_assist_progress,
)

log = logging.getLogger("shell")

DEFAULT_POLL_SECONDS = 2.0
DEFAULT_LIMIT = 1
DEFAULT_ASSIST_HEARTBEAT_SECONDS = 30.0
_STOP = False
_VARIANT_RUNNERS = {
    "summary": summarize.run,
    "next_commands": next_commands.run,
}


def _handle_stop(signum, frame):  # noqa: ANN001
    global _STOP
    _STOP = True


def run_once(*, limit: int = DEFAULT_LIMIT, cfg: dict | None = None) -> int:
    """Reap stale assists and process a small batch of queued assists."""
    processed = reclaim_stale_assists()
    if processed:
        log.warning(
            "AI_ASSIST_STALE_RECLAIMED",
            extra={"count": processed, "stale_after_seconds": 300},
        )
    active_cfg = CFG if cfg is None else cfg
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


def _process_assist(assist: dict, *, cfg: dict | None = None) -> None:
    active_cfg = CFG if cfg is None else cfg
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
            "status": exc.status,
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


def _record_worker_error_metric(variant: str, error_code: str, cfg: dict) -> None:
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
    configure_logging(CFG)
    run_forever()


if __name__ == "__main__":
    main()
