"""Optional AI assist foundation."""

from __future__ import annotations

from urllib.parse import urlparse

from config import resolve_effective_cfg


def _is_bundled_llama_cpp(active: dict) -> bool:
    try:
        host = urlparse(str(active.get("ai_base_url") or "")).hostname
    except ValueError:
        host = ""
    return str(host or "").strip().lower() == "llama"


def ai_cfg(cfg: dict | None = None) -> dict:
    """Return the effective AI config subset with stable key names."""
    active = resolve_effective_cfg(cfg)
    raw_cidrs = active.get("ai_base_url_allowed_cidrs") or []
    if isinstance(raw_cidrs, str):
        allowed_cidrs = [item.strip() for item in raw_cidrs.split(",") if item.strip()]
    elif isinstance(raw_cidrs, (list, tuple, set)):
        allowed_cidrs = [str(item).strip() for item in raw_cidrs if str(item or "").strip()]
    else:
        allowed_cidrs = []
    return {
        "enabled": bool(active.get("ai_enabled", False)),
        "provider": str(active.get("ai_provider") or "openai_compatible").strip(),
        "base_url": str(active.get("ai_base_url") or "").strip().rstrip("/"),
        "model": str(active.get("ai_model") or "").strip(),
        "api_key_secret_name": str(active.get("ai_api_key_secret_name") or "").strip(),
        "api_key": str(active.get("ai_api_key") or "").strip(),
        "connect_timeout_seconds": int(active.get("ai_connect_timeout_seconds") or 5),
        "timeout_seconds": int(active.get("ai_timeout_seconds") or 120),
        "max_input_chars": int(active.get("ai_max_input_chars") or 24000),
        "max_output_tokens": int(active.get("ai_max_output_tokens") or 120),
        "next_commands_max_output_tokens": int(active.get("ai_next_commands_max_output_tokens") or 180),
        "max_concurrent": int(active.get("ai_max_concurrent") or 1),
        "max_queue_depth": int(active.get("ai_max_queue_depth") or 20),
        "rate_limit_per_session_hour": int(active.get("ai_rate_limit_per_session_hour") or 5),
        "rate_limit_global_per_minute": int(active.get("ai_rate_limit_global_per_minute") or 2),
        "allow_full_output": bool(active.get("ai_allow_full_output", False)),
        "require_private_base_url": bool(active.get("ai_require_private_base_url", True)),
        "base_url_allowed_cidrs": allowed_cidrs,
        "prompt_version_override": str(active.get("ai_prompt_version_override") or "").strip(),
        "feature_summary": bool(active.get("ai_feature_summary", False)),
        "feature_next_commands": bool(active.get("ai_feature_next_commands", False)),
        "feature_run_suggestions": bool(active.get("ai_feature_run_suggestions", False)),
        "cache_prompt": _is_bundled_llama_cpp(active),
    }
