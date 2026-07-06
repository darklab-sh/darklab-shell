"""Operator diagnostics for the optional AI provider."""

from __future__ import annotations

from collections.abc import Mapping

import logging
import time
from typing import Any

from services.ai import ai_cfg
from services.ai.client import AIClientError, OpenAICompatibleClient
from services.ai.prompts import SYSTEM_PROMPT, developer_prompt
from services.ai.schemas import validate_diag_test_payload

log = logging.getLogger("shell")


def _model_ids(payload: dict[str, Any]) -> set[str]:
    values = payload.get("data")
    if not isinstance(values, list):
        return set()
    ids = set()
    for item in values:
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
    return ids


def provider_probe(cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    settings = ai_cfg(cfg)
    result = {
        "enabled": settings["enabled"],
        "provider": settings["provider"],
        "base_url_configured": bool(settings["base_url"]),
        "model": settings["model"],
        "model_configured": bool(settings["model"]),
        "feature_summary": settings["feature_summary"],
        "feature_next_commands": settings["feature_next_commands"],
        "feature_run_suggestions": settings["feature_run_suggestions"],
        "ok": False,
        "reachable": False,
        "model_installed": False,
    }
    if not settings["enabled"]:
        result["status"] = "disabled"
        return result
    if not settings["base_url"] or not settings["model"]:
        result["status"] = "not_configured"
        return result

    client = OpenAICompatibleClient(cfg)
    started = time.perf_counter()
    try:
        models = client.list_models()
    except AIClientError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log.warning(
            "AI_PROVIDER_PROBE_FAILED",
            extra={
                "provider": settings["provider"],
                "model": settings["model"],
                "base_url_configured": bool(settings["base_url"]),
                "error_code": exc.code,
                "status": exc.status,
                "latency_ms": latency_ms,
            },
        )
        result.update({
            "status": exc.code,
            "error": str(exc),
            "latency_ms": latency_ms,
        })
        return result
    model_ids = _model_ids(models)
    result.update({
        "ok": True,
        "reachable": True,
        "model_installed": settings["model"] in model_ids,
        "models_seen": sorted(model_ids)[:20],
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "status": "ok",
    })
    return result


def run_test_prompt(cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    settings = ai_cfg(cfg)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": developer_prompt("diag_test")},
        {
            "role": "user",
            "content": 'Return exactly this JSON shape with status ok and a short message: {"status":"ok","message":"pong"}',
        },
    ]
    client = OpenAICompatibleClient(cfg)
    result = client.chat_completion(
        messages,
        validate=validate_diag_test_payload,
        max_tokens=min(80, settings["max_output_tokens"]),
    )
    return {
        "ok": True,
        "payload": result.payload,
        "latency_ms": result.duration_ms,
        "provider_timings": result.provider_timings,
        "raw_response": result.raw_content[:4096],
        "output_chars": result.output_chars,
        "finish_reason": result.finish_reason,
    }
