# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Application configuration and scanner-user setup.
Imported by database, process, permalinks, and app modules.
"""

import os
import pwd
import logging
import ipaddress
import re
from copy import deepcopy
from collections.abc import Iterator, Mapping, MutableMapping
from typing import Any, cast
import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, ValidationError, create_model
import config_paths
from core.redaction import BUILTIN_SHARE_REDACTION_RULES, normalize_redaction_rules
from core.startup_logging import configure_config_log_fallback, install_config_log_buffer

CONFIG_LOAD_WARNINGS: list[dict[str, str]] = []
CONFIG_LOAD_SUMMARY: dict[str, Any] = {}

APP_VERSION = "2.6.0-rc.3"
PROJECT_NAME = "darklab_shell"
APP_NAME_MAX_CHARS = 20

log = install_config_log_buffer(logging.getLogger("shell"), app_version=APP_VERSION)

PROJECT_SOURCE = f"https://gitlab.com/darklab.sh/darklab_shell/-/tree/v{APP_VERSION}#darklab_shell"
APP_CONF_DIR = os.environ.get("APP_CONF_DIR", "")
APP_LOCAL_CONF_DIR = os.environ.get("APP_LOCAL_CONF_DIR", "")
DEFAULT_PROMPT_IDENTITY = "anon@darklab.sh"

_DERIVED_CONFIG_DEFAULTS = {
    "full_output_max_bytes": 5 * 1024 * 1024,
    "output_preview_max_bytes": 1024 * 1024,
}
_SECRET_CONFIG_KEYS = {
    "ai_api_key",
    "ai_api_key_secret_name",
    "notifications.smtp.password_secret_id",
}
_SENSITIVE_URL_CONFIG_KEYS = {
    "database_url",
}
_MAX_CONFIG_ERROR_VALUE_CHARS = 120
_MAX_CONFIG_LOG_PATH_CHARS = 240


class ConfigLoadError(RuntimeError):
    """Raised when app config cannot be loaded into a valid model."""


def _config_log_value(value: object, limit: int) -> str:
    normalized = "".join(
        character if character.isprintable() and character not in "\r\n" else "?"
        for character in str(value)
    )
    return normalized[:limit]


def _config_log_path(value: object) -> str:
    """Return a bounded, single-line path for structured config logs."""
    return _config_log_value(value, _MAX_CONFIG_LOG_PATH_CHARS)


def _record_config_load_failure(
    *,
    phase: str,
    source: str,
    key: str = "",
    error: object | None = None,
) -> None:
    extra = {"phase": phase, "source": _config_log_path(source), "key": key}
    if error is not None:
        safe_error = type(error).__name__ if isinstance(error, BaseException) else error
        extra["error"] = _config_log_value(safe_error, _MAX_CONFIG_ERROR_VALUE_CHARS)
    log.error("CONFIG_LOAD_FAILED", extra=extra)


def get_config_load_summary() -> dict[str, Any]:
    return dict(CONFIG_LOAD_SUMMARY)


def _overlay_path_counts(overlay: Mapping[str, Any], allowed_paths: set[str]) -> tuple[int, int]:
    overlay_paths = _flatten_config_paths(dict(overlay))
    known_paths = {path for path in overlay_paths if path in allowed_paths}
    return len(known_paths), len(overlay_paths - known_paths)


def split_prompt_identity(identity):
    raw = str(identity or DEFAULT_PROMPT_IDENTITY).strip() or DEFAULT_PROMPT_IDENTITY
    if raw.endswith("$"):
        raw = raw[:-1].rstrip()
    if ":" in raw:
        head, tail = raw.rsplit(":", 1)
        if head and tail and not any(ch.isspace() for ch in tail):
            raw = head.strip()
    username, sep, domain = raw.partition("@")
    username = username.strip() or "anon"
    domain = domain.strip() if sep else "darklab.sh"
    return username, domain or "darklab.sh"


def _load_yaml_config(path):
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            loaded = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        _record_config_load_failure(phase="yaml_parse", source=str(path), error=exc)
        raise ConfigLoadError(
            f"Invalid YAML in {_config_log_path(path)}: {type(exc).__name__}"
        ) from None
    if not isinstance(loaded, dict):
        _record_config_load_failure(phase="root_shape", source=str(path), error="expected a mapping")
        raise ConfigLoadError(
            f"Invalid config root in {_config_log_path(path)}: expected a mapping"
        )
    return loaded


def _load_yaml_config_optional(path):
    if not path.exists():
        return {}
    return _load_yaml_config(path)


def _coerce_mb_value(value):
    # Accept both numeric YAML scalars and human-edited strings like "25" or
    # "25mb" so the config layer stays forgiving without leaking bad values.
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        token = value.strip().lower().replace(" ", "")
        if token.endswith("mb"):
            token = token[:-2]
        elif token.endswith("m"):
            token = token[:-1]
        if not token:
            return None
        try:
            return max(0, int(token))
        except ValueError:
            try:
                return max(0, int(float(token)))
            except ValueError:
                return None
    return None


def _coerce_int_value(value, default=0, *, minimum=0):
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        try:
            parsed = int(float(str(value).strip()))
        except (TypeError, ValueError):
            return default
    return max(minimum, parsed)


def _parse_int_value(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None


def _coerce_forgiving_mb_config_value(defaults: Mapping[str, Any], key: str, fallback: int | None) -> int | None:
    if key not in _FORGIVING_MB_KEYS:
        raise KeyError(f"Unknown forgiving MB config key: {key}")
    parsed = _coerce_mb_value(defaults.get(key))
    if parsed is None:
        return fallback
    return parsed


def _coerce_bool_value(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _normalize_app_name(value, provenance: Mapping[str, str]):
    raw = str(value or PROJECT_NAME).strip() or PROJECT_NAME
    normalized = " ".join(raw.split())
    if len(normalized) <= APP_NAME_MAX_CHARS:
        return normalized
    source = _config_log_path(_config_source(provenance, "app_name"))
    CONFIG_LOAD_WARNINGS.append({
        "event": "APP_NAME_TRUNCATED",
        "key": "app_name",
        "source": source,
        "reason": "above_maximum_chars",
    })
    log.warning("APP_NAME_TRUNCATED", extra={
        "key": "app_name",
        "source": source,
        "reason": "above_maximum_chars",
        "configured_chars": len(normalized),
        "max_chars": APP_NAME_MAX_CHARS,
    })
    return normalized[:APP_NAME_MAX_CHARS].rstrip() or PROJECT_NAME


def _config_source(provenance: Mapping[str, str], key: str) -> str:
    return provenance.get(key, "effective config")


def _config_source_is_override(source: str) -> bool:
    return source != "built-in defaults"


def _warn_config_value_dropped(
    key: str,
    provenance: Mapping[str, str],
    *,
    reason: str,
    value_field: str,
    value: str,
    warning_event: str,
) -> None:
    bounded_value = value[:120]
    source = _config_log_path(_config_source(provenance, key))
    CONFIG_LOAD_WARNINGS.append({
        "event": "CONFIG_VALUE_DROPPED",
        "key": key,
        "source": source,
        "reason": reason,
    })
    log.warning(warning_event, extra={value_field: bounded_value})
    log.warning(
        "CONFIG_VALUE_DROPPED",
        extra={
            "key": key,
            "source": source,
            "reason": reason,
            value_field: bounded_value,
        },
    )


def _warn_config_value_defaulted(
    key: str,
    provenance: Mapping[str, str],
    *,
    reason: str,
    fallback: Any,
) -> None:
    source = _config_log_path(_config_source(provenance, key))
    CONFIG_LOAD_WARNINGS.append({
        "event": "CONFIG_VALUE_DEFAULTED",
        "key": key,
        "source": source,
        "reason": reason,
    })
    log.warning(
        "CONFIG_VALUE_DEFAULTED",
        extra={
            "key": key,
            "source": source,
            "reason": reason,
            "fallback": fallback,
        },
    )


def _warn_config_value_clamped(
    key: str,
    provenance: Mapping[str, str],
    *,
    reason: str,
    minimum: Any | None = None,
    maximum: Any | None = None,
) -> None:
    source = _config_log_path(_config_source(provenance, key))
    CONFIG_LOAD_WARNINGS.append({
        "event": "CONFIG_VALUE_CLAMPED",
        "key": key,
        "source": source,
        "reason": reason,
    })
    extra = {
        "key": key,
        "source": source,
        "reason": reason,
    }
    if minimum is not None:
        extra["minimum"] = minimum
    if maximum is not None:
        extra["maximum"] = maximum
    log.warning("CONFIG_VALUE_CLAMPED", extra=extra)


def _normalize_cidr_list(value, warning_event, key: str, provenance: Mapping[str, str]):
    if isinstance(value, str):
        raw_values = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple, set)):
        raw_values = [str(item).strip() for item in value if str(item or "").strip()]
    else:
        raw_values = []
    normalized = []
    for cidr in raw_values:
        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            _warn_config_value_dropped(
                key,
                provenance,
                reason="invalid_cidr",
                value_field="cidr",
                value=cidr,
                warning_event=warning_event,
            )
            continue
        normalized.append(cidr)
    return normalized


def _normalize_ai_base_url_allowed_cidrs(value, provenance):
    return _normalize_cidr_list(value, "AI_BASE_URL_ALLOWED_CIDR_INVALID", "ai_base_url_allowed_cidrs", provenance)


def _normalize_restricted_command_input_cidrs(value, provenance):
    return _normalize_cidr_list(
        value,
        "RESTRICTED_COMMAND_INPUT_CIDR_INVALID",
        "restricted_command_input_cidrs",
        provenance,
    )


def _normalize_output_entity_extra_domain_suffixes(value, provenance):
    if isinstance(value, str):
        raw_values = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple, set)):
        raw_values = [str(item).strip() for item in value if str(item or "").strip()]
    else:
        raw_values = []
    normalized = []
    seen = set()
    for suffix in raw_values:
        token = suffix.strip().lower().strip(".")
        if not token:
            continue
        try:
            ascii_labels = [label.encode("idna").decode("ascii") for label in token.split(".") if label]
        except UnicodeError:
            _warn_config_value_dropped(
                "output_entity_extra_domain_suffixes",
                provenance,
                reason="invalid_domain_suffix",
                value_field="suffix",
                value=suffix,
                warning_event="OUTPUT_ENTITY_EXTRA_DOMAIN_SUFFIX_INVALID",
            )
            continue
        ascii_suffix = ".".join(ascii_labels).lower()
        if (
            not ascii_suffix
            or any(not label for label in ascii_suffix.split("."))
            or any(not re.match(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", label) for label in ascii_suffix.split("."))
        ):
            _warn_config_value_dropped(
                "output_entity_extra_domain_suffixes",
                provenance,
                reason="invalid_domain_suffix",
                value_field="suffix",
                value=suffix,
                warning_event="OUTPUT_ENTITY_EXTRA_DOMAIN_SUFFIX_INVALID",
            )
            continue
        if ascii_suffix in seen:
            continue
        seen.add(ascii_suffix)
        normalized.append(ascii_suffix)
    return normalized


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SmtpNotificationConfig(_ConfigModel):
    host: StrictStr = ""
    port: StrictInt = 587
    user: StrictStr = ""
    password_secret_id: StrictStr = ""
    from_address: StrictStr = ""
    tls: StrictStr = "starttls"


class NotificationRetryConfig(_ConfigModel):
    max_attempts: StrictInt = 6
    max_age_hours: StrictInt = 24
    base_delay_seconds: StrictInt = 30


class NotificationEventsConfig(_ConfigModel):
    retention_days: StrictInt = 30


class NotificationsConfig(_ConfigModel):
    do_not_disturb: StrictBool = False
    delivery_rate_per_minute: StrictInt = 10
    http_timeout_seconds: StrictInt = 8
    test_timeout_seconds: StrictInt = 4
    http_private_host_allowlist: list[StrictStr] = Field(default_factory=list)
    smtp: SmtpNotificationConfig = Field(default_factory=SmtpNotificationConfig)
    retry: NotificationRetryConfig = Field(default_factory=NotificationRetryConfig)
    events: NotificationEventsConfig = Field(default_factory=NotificationEventsConfig)


class SchedulerConfig(_ConfigModel):
    lock_path: StrictStr = ""
    tick_seconds: StrictInt = 5
    max_per_session: StrictInt = 32
    missed_fire_policy: StrictStr = "coalesce"
    max_catchup_window_seconds: StrictInt = 3600
    default_timezone: StrictStr = "UTC"


class WatchersConfig(_ConfigModel):
    max_per_session: StrictInt = 32


class ProjectDigestsConfig(_ConfigModel):
    default_cadence_preset: StrictStr = "daily"
    first_send_lookback_hours: StrictInt = 24


_FORGIVING_BOOL_KEYS = {
    "raw_packet_scanning_enabled",
    "database_postgres_jit",
    "audit_log_enabled",
    "ai_enabled",
    "ai_allow_full_output",
    "ai_require_private_base_url",
    "ai_feature_summary",
    "ai_feature_next_commands",
    "ai_feature_run_suggestions",
}
_FORGIVING_BOOL_DEFAULTS = {
    "raw_packet_scanning_enabled": False,
    "database_postgres_jit": False,
    "audit_log_enabled": True,
    "ai_enabled": False,
    "ai_allow_full_output": False,
    "ai_require_private_base_url": True,
    "ai_feature_summary": False,
    "ai_feature_next_commands": False,
    "ai_feature_run_suggestions": False,
}
_FORGIVING_INT_KEYS = {
    "database_pool_min",
    "database_pool_max",
    "audit_retention_days",
    "audit_export_max_rows",
    "ai_connect_timeout_seconds",
    "ai_timeout_seconds",
    "ai_max_input_chars",
    "ai_max_output_tokens",
    "ai_next_commands_max_output_tokens",
    "ai_max_concurrent",
    "ai_max_queue_depth",
    "ai_rate_limit_per_session_hour",
    "ai_rate_limit_global_per_minute",
    "workflow_active_execution_limit",
    "workflow_execution_max_runtime_seconds",
}
_FORGIVING_INT_DEFAULTS: dict[str, tuple[int, int]] = {
    "database_pool_min": (1, 0),
    "database_pool_max": (5, 1),
    "audit_retention_days": (90, 0),
    "audit_export_max_rows": (10000, 1),
    "ai_connect_timeout_seconds": (5, 1),
    "ai_timeout_seconds": (120, 1),
    "ai_max_input_chars": (24000, 1000),
    "ai_max_output_tokens": (120, 1),
    "ai_next_commands_max_output_tokens": (180, 1),
    "ai_max_concurrent": (1, 1),
    "ai_max_queue_depth": (20, 0),
    "ai_rate_limit_per_session_hour": (5, 1),
    "ai_rate_limit_global_per_minute": (2, 1),
    "workflow_active_execution_limit": (3, 1),
    "workflow_execution_max_runtime_seconds": (14400, 1),
}
_FORGIVING_MB_KEYS = {"output_preview_max_mb", "full_output_max_mb"}
_NORMALIZED_LIST_KEYS = {
    "ai_base_url_allowed_cidrs",
    "restricted_command_input_cidrs",
    "share_redaction_rules",
    "output_entity_extra_domain_suffixes",
}
_STRING_LIST_KEYS = {"trusted_proxy_cidrs", "diagnostics_allowed_cidrs", "welcome_status_labels"}
_FLOAT_LIST_KEYS = {
    "metrics_histogram_buckets_run_duration",
    "metrics_histogram_buckets_http_duration",
    "metrics_histogram_buckets_ai_provider_duration",
}
_FLOAT_KEYS = {"interactive_pty_control_poll_seconds", "interactive_pty_snapshot_min_publish_seconds"}
_NESTED_CONFIG_MODELS = {
    "notifications": NotificationsConfig,
    "scheduler": SchedulerConfig,
    "watchers": WatchersConfig,
    "project_digests": ProjectDigestsConfig,
}


class AppConfig(MutableMapping[str, Any]):
    """Validated config with dict-style compatibility for existing callers."""

    def __init__(
        self,
        data: BaseModel | dict[str, Any],
        schema_model: type[BaseModel],
        provenance: dict[str, str] | None = None,
        schema_defaults: dict[str, Any] | None = None,
    ):
        model = data if isinstance(data, BaseModel) else schema_model.model_validate(data)
        object.__setattr__(self, "_model", model)
        object.__setattr__(self, "_schema_model", schema_model)
        object.__setattr__(self, "_provenance", dict(provenance or {}))
        object.__setattr__(self, "_schema_defaults", deepcopy(schema_defaults or {}))

    def _validate_candidate(self, data: dict[str, Any], provenance: dict[str, str] | None = None) -> BaseModel:
        active_provenance = dict(provenance or self._provenance)
        candidate = deepcopy(self._schema_defaults)
        _merge_dict_data(candidate, data)
        _normalize_config_data(candidate, active_provenance)
        try:
            parsed = self._schema_model.model_validate(candidate)
        except ValidationError as exc:
            raise ConfigLoadError(
                f"Invalid app config mutation: {_format_validation_error(exc, active_provenance, candidate)}"
            ) from exc
        return parsed

    def _commit_candidate(self, data: dict[str, Any], provenance: dict[str, str] | None = None) -> None:
        parsed = self._validate_candidate(data, provenance)
        object.__setattr__(self, "_model", parsed)
        if provenance is not None:
            self._provenance.clear()
            self._provenance.update(provenance)

    def __getitem__(self, key: str) -> Any:
        return self.model_dump()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        data = self.model_dump()
        data[key] = value
        provenance = dict(self._provenance)
        _record_value_provenance({key: value}, provenance, "runtime mutation")
        self._commit_candidate(data, provenance)

    def __delitem__(self, key: str) -> None:
        data = self.model_dump()
        del data[key]
        self._commit_candidate(data)

    def clear(self) -> None:
        self._commit_candidate({})

    def __iter__(self) -> Iterator[str]:
        return iter(self.model_dump())

    def __len__(self) -> int:
        return len(self.model_dump())

    def __getattr__(self, key: str) -> Any:
        if key in self._schema_model.model_fields:
            return getattr(self._model, key)
        raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key.startswith("_"):
            object.__setattr__(self, key, value)
            return
        self[key] = value

    def __repr__(self) -> str:
        return f"AppConfig({self.redacted_model_dump()!r})"

    def copy(self) -> dict[str, Any]:
        return self.model_dump()

    def with_overrides(self, overrides: dict[str, Any] | None = None) -> "AppConfig":
        data = self.model_dump()
        provenance = dict(self._provenance)
        if overrides:
            _merge_dict_data(data, overrides)
            _record_value_provenance(overrides, provenance, "test overrides")
        parsed = self._validate_candidate(data, provenance)
        return AppConfig(parsed, self._schema_model, provenance, self._schema_defaults)

    def model_dump(self) -> dict[str, Any]:
        return self._model.model_dump(mode="python")

    def model_json_schema(self) -> dict[str, Any]:
        return self._schema_model.model_json_schema()

    def redacted_model_dump(self) -> dict[str, Any]:
        return _redact_config_mapping(self.model_dump())


def _path_join(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def _merge_dict_data(target: dict[str, Any], overlay: dict[str, Any]) -> None:
    for key, value in overlay.items():
        existing = target.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            _merge_dict_data(existing, value)
            continue
        target[key] = value


def _flatten_config_paths(data: dict[str, Any], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for key, value in data.items():
        path = _path_join(prefix, str(key))
        paths.add(path)
        if isinstance(value, dict):
            paths.update(_flatten_config_paths(value, path))
    return paths


def _record_default_provenance(data: dict[str, Any], provenance: dict[str, str], prefix: str = "") -> None:
    for key, value in data.items():
        path = _path_join(prefix, str(key))
        provenance[path] = "built-in defaults"
        if isinstance(value, dict):
            _record_default_provenance(value, provenance, path)


def _record_value_provenance(data: Mapping[str, Any], provenance: dict[str, str], source: str, prefix: str = "") -> None:
    for key, value in data.items():
        path = _path_join(prefix, str(key))
        provenance[path] = source
        if isinstance(value, Mapping):
            _record_value_provenance(value, provenance, source, path)


def _redacted_config_value(path: str, value: Any) -> str:
    if path in _SECRET_CONFIG_KEYS or path.endswith("_secret_id") or path.endswith("_secret_name"):
        return "<redacted>"
    if path in _SENSITIVE_URL_CONFIG_KEYS:
        return "<redacted>"
    if "api_key" in path or "password" in path or "webhook" in path:
        return "<redacted>"
    text = repr(value)
    if len(text) > _MAX_CONFIG_ERROR_VALUE_CHARS:
        return text[: _MAX_CONFIG_ERROR_VALUE_CHARS - 3] + "..."
    return text


def _redact_config_mapping(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        path = _path_join(prefix, str(key))
        if isinstance(value, Mapping):
            redacted[str(key)] = _redact_config_mapping(value, path)
        elif _redacted_config_value(path, value) == "<redacted>":
            redacted[str(key)] = "<redacted>"
        else:
            redacted[str(key)] = value
    return redacted


def _warn_unknown_config_key(path: str, source: str) -> None:
    payload = {"key": path, "source": source}
    CONFIG_LOAD_WARNINGS.append(payload)
    log.warning(
        "CONFIG_UNKNOWN_KEY_IGNORED",
        extra={"key": path, "source": _config_log_path(source)},
    )


def _merge_config_overlay(
    target: dict[str, Any],
    overlay: dict[str, Any],
    *,
    source: str,
    provenance: dict[str, str],
    allowed_paths: set[str],
    prefix: str = "",
) -> None:
    for raw_key, value in overlay.items():
        key = str(raw_key)
        path = _path_join(prefix, key)
        if path not in allowed_paths:
            _warn_unknown_config_key(path, source)
            continue
        existing = target.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            _merge_config_overlay(
                existing,
                value,
                source=source,
                provenance=provenance,
                allowed_paths=allowed_paths,
                prefix=path,
            )
            continue
        target[key] = value
        provenance[path] = source


def _set_config_value(data: dict[str, Any], provenance: dict[str, str], key: str, value: Any, source: str) -> None:
    data[key] = value
    provenance[key] = source


def _field_type_for(key: str, value: Any) -> Any:
    if key in _NESTED_CONFIG_MODELS:
        return _NESTED_CONFIG_MODELS[key]
    if key in _STRING_LIST_KEYS:
        return list[StrictStr]
    if key in _FLOAT_LIST_KEYS:
        return list[StrictFloat]
    if key in _NORMALIZED_LIST_KEYS:
        return list[Any]
    if key in _FLOAT_KEYS:
        return StrictFloat
    if isinstance(value, bool):
        return StrictBool
    if isinstance(value, int):
        return StrictInt
    if isinstance(value, float):
        return StrictFloat
    if isinstance(value, str):
        return StrictStr
    if isinstance(value, list):
        return list[Any]
    if isinstance(value, dict):
        return dict[str, Any]
    return Any


def _schema_fields_from_defaults(defaults: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    field_source = {**defaults, **_DERIVED_CONFIG_DEFAULTS}
    fields: dict[str, tuple[Any, Any]] = {}
    for key, value in field_source.items():
        field_type = _field_type_for(key, value)
        if key in _NESTED_CONFIG_MODELS and isinstance(value, dict):
            fields[key] = (field_type, field_type.model_validate(value))
            continue
        fields[key] = (field_type, value)
    return fields


def _format_validation_error(exc: ValidationError, provenance: dict[str, str], raw_values: dict[str, Any]) -> str:
    parts = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ())) or "<config>"
        source = provenance.get(loc, "effective config")
        raw_value: Any = raw_values
        for part in loc.split("."):
            if isinstance(raw_value, dict) and part in raw_value:
                raw_value = raw_value[part]
            else:
                raw_value = None
                break
        parts.append(
            f"{loc} from {source}: {error.get('msg', 'invalid value')} "
            f"(value={_redacted_config_value(loc, raw_value)})"
        )
    return "; ".join(parts)


def _normalize_config_data(defaults: dict[str, Any], provenance: dict[str, str]) -> None:
    defaults["ai_base_url_allowed_cidrs"] = _normalize_ai_base_url_allowed_cidrs(
        defaults.get("ai_base_url_allowed_cidrs"),
        provenance,
    )
    defaults["restricted_command_input_cidrs"] = _normalize_restricted_command_input_cidrs(
        defaults.get("restricted_command_input_cidrs"),
        provenance,
    )
    defaults["output_entity_extra_domain_suffixes"] = _normalize_output_entity_extra_domain_suffixes(
        defaults.get("output_entity_extra_domain_suffixes"),
        provenance,
    )
    for key in _FORGIVING_INT_KEYS:
        fallback, minimum = _FORGIVING_INT_DEFAULTS[key]
        raw_value = defaults.get(key)
        raw_source = _config_source(provenance, key)
        parsed_value = _parse_int_value(raw_value)
        defaults[key] = _coerce_int_value(raw_value, fallback, minimum=minimum)
        if _config_source_is_override(raw_source):
            if parsed_value is None:
                _warn_config_value_defaulted(key, provenance, reason="invalid_int", fallback=fallback)
            elif parsed_value < minimum:
                _warn_config_value_clamped(key, provenance, reason="below_minimum", minimum=minimum)
    for key in _FORGIVING_BOOL_KEYS:
        raw_value = defaults.get(key)
        raw_source = _config_source(provenance, key)
        parsed_value = _parse_bool_value(raw_value)
        fallback = _FORGIVING_BOOL_DEFAULTS[key]
        defaults[key] = _coerce_bool_value(raw_value, fallback)
        if _config_source_is_override(raw_source) and parsed_value is None:
            _warn_config_value_defaulted(key, provenance, reason="invalid_bool", fallback=fallback)
    if defaults["database_pool_max"] < defaults["database_pool_min"]:
        _warn_config_value_clamped(
            "database_pool_max",
            provenance,
            reason="below_database_pool_min",
            minimum=defaults["database_pool_min"] or 1,
        )
        defaults["database_pool_max"] = defaults["database_pool_min"] or 1
    defaults["app_name"] = _normalize_app_name(defaults.get("app_name"), provenance)
    legacy_full_output_max_bytes = defaults.pop("full_output_max_bytes", None)
    full_output_max_mb = _coerce_forgiving_mb_config_value(defaults, "full_output_max_mb", None)
    full_output_max_mb_source = provenance.get("full_output_max_mb", "built-in defaults")
    if legacy_full_output_max_bytes is not None and (
        full_output_max_mb is None or full_output_max_mb_source == "built-in defaults"
    ):
        log.debug(
            "CONFIG_LEGACY_KEY_MIGRATED",
            extra={
                "legacy_key": "full_output_max_bytes",
                "target_key": "full_output_max_mb",
                "source": _config_log_path(
                    provenance.get("full_output_max_bytes", "legacy full_output_max_bytes")
                ),
            },
        )
        CONFIG_LOAD_SUMMARY["legacy_key_migrated"] = True
        try:
            legacy_bytes = max(0, int(legacy_full_output_max_bytes))
        except (TypeError, ValueError):
            _warn_config_value_defaulted(
                "full_output_max_bytes",
                provenance,
                reason="invalid_int",
                fallback=0,
            )
            legacy_bytes = 0
        defaults["full_output_max_mb"] = max(0, (legacy_bytes + (1024 * 1024) - 1) // (1024 * 1024))
        defaults["full_output_max_bytes"] = legacy_bytes
        provenance["full_output_max_mb"] = provenance.get("full_output_max_bytes", "legacy full_output_max_bytes")
        provenance["full_output_max_bytes"] = provenance.get("full_output_max_bytes", "legacy full_output_max_bytes")
    else:
        if full_output_max_mb is None:
            _warn_config_value_defaulted(
                "full_output_max_mb",
                provenance,
                reason="invalid_mb",
                fallback=5,
            )
            full_output_max_mb = _coerce_forgiving_mb_config_value(defaults, "full_output_max_mb", 5)
        assert full_output_max_mb is not None
        defaults["full_output_max_mb"] = full_output_max_mb
        defaults["full_output_max_bytes"] = full_output_max_mb * 1024 * 1024
        provenance["full_output_max_bytes"] = provenance.get("full_output_max_mb", "derived from full_output_max_mb")
    output_preview_max_mb = _coerce_forgiving_mb_config_value(defaults, "output_preview_max_mb", 1)
    if output_preview_max_mb == 1 and _coerce_mb_value(defaults.get("output_preview_max_mb")) is None:
        _warn_config_value_defaulted(
            "output_preview_max_mb",
            provenance,
            reason="invalid_mb",
            fallback=1,
        )
    assert output_preview_max_mb is not None
    defaults["output_preview_max_mb"] = output_preview_max_mb
    defaults["output_preview_max_bytes"] = output_preview_max_mb * 1024 * 1024
    provenance["output_preview_max_bytes"] = provenance.get("output_preview_max_mb", "derived from output_preview_max_mb")
    if defaults["audit_export_max_rows"] > 200000:
        _warn_config_value_clamped(
            "audit_export_max_rows",
            provenance,
            reason="above_maximum",
            maximum=200000,
        )
        defaults["audit_export_max_rows"] = 200000
    # Share/export redaction rules are normalized up front so the browser and
    # the snapshot endpoint both receive the same validated rule set.
    defaults["share_redaction_rules"] = normalize_redaction_rules(
        defaults.get("share_redaction_rules", [])
    )


def _validate_config_model(defaults: dict[str, Any], provenance: dict[str, str], schema_defaults: dict[str, Any]) -> AppConfig:
    schema_fields = cast(dict[str, Any], _schema_fields_from_defaults(schema_defaults))
    schema_model = create_model("AppConfigModel", __base__=_ConfigModel, **schema_fields)
    try:
        parsed = schema_model.model_validate(defaults)
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {}
        key = ".".join(str(part) for part in first_error.get("loc", ()))
        _record_config_load_failure(
            phase="schema_validation",
            source=provenance.get(key, "effective config"),
            key=key,
            error=first_error.get("msg", "invalid value"),
        )
        raise ConfigLoadError(
            f"Invalid app config: {_format_validation_error(exc, provenance, defaults)}"
        ) from None
    CONFIG_LOAD_SUMMARY.update({
        "schema_field_count": len(schema_fields),
        "derived_keys": len(_DERIVED_CONFIG_DEFAULTS),
        "warning_count": len(CONFIG_LOAD_WARNINGS),
    })
    log.info(
        "CONFIG_VALIDATED",
        extra={
            "schema_field_count": len(schema_fields),
            "derived_keys": len(_DERIVED_CONFIG_DEFAULTS),
            "warning_count": len(CONFIG_LOAD_WARNINGS),
        },
    )
    return AppConfig(parsed, schema_model, provenance, schema_defaults)


def load_config(conf_dir=None, local_conf_dir=None):
    """Load config.yaml plus optional config.local.yaml overlays.

    config.local.yaml is read after config.yaml, so it can override selected
    keys while leaving the checked-in defaults in place.
    """
    CONFIG_LOAD_WARNINGS.clear()
    CONFIG_LOAD_SUMMARY.clear()
    defaults = {
        "app_name":                   "darklab_shell",
        "app_public_base_url":        "",
        "prompt_username":            split_prompt_identity(DEFAULT_PROMPT_IDENTITY)[0],
        "prompt_domain":              split_prompt_identity(DEFAULT_PROMPT_IDENTITY)[1],
        "motd":                       "",
        "default_theme":              "darklab_obsidian.yaml",
        "asset_bundle_mode":          "bundle",
        "history_panel_limit":        50,
        "recent_commands_limit":      50,
        "data_dir":                   "",
        "database_backend":           "sqlite",
        "database_url":               "",
        "database_pool_min":          1,
        "database_pool_max":          5,
        "database_postgres_jit":       False,
        "permalink_retention_days":   365,
        "audit_log_enabled":          True,
        "audit_retention_days":       90,
        "audit_export_max_rows":      10000,
        "log_level":                  "INFO",
        "log_format":                 "text",
        "trusted_proxy_cidrs":        ["127.0.0.1/32", "::1/128"],
        "diagnostics_allowed_cidrs":  [],
        "metrics_enabled":            True,
        "prometheus_multiproc_dir":   "/tmp/darklab_shell-prom",
        "metrics_histogram_buckets_run_duration": [0.1, 0.5, 1, 2, 5, 10, 30, 60, 300, 900, 1800, 3600],
        "metrics_histogram_buckets_http_duration": [0.005, 0.01, 0.05, 0.1, 0.5, 1, 5],
        "metrics_histogram_buckets_ai_provider_duration": [0.1, 0.5, 1, 2, 5, 10, 30, 60],
        "ai_enabled":                 False,
        "ai_provider":                "openai_compatible",
        "ai_base_url":                "",
        "ai_model":                   "",
        "ai_api_key_secret_name":     "",
        "ai_api_key":                 "",
        "ai_connect_timeout_seconds": 5,
        "ai_timeout_seconds":         120,
        "ai_max_input_chars":         24000,
        "ai_max_output_tokens":       120,
        "ai_next_commands_max_output_tokens": 180,
        "ai_max_concurrent":          1,
        "ai_max_queue_depth":         20,
        "ai_rate_limit_per_session_hour": 5,
        "ai_rate_limit_global_per_minute": 2,
        "ai_allow_full_output":       False,
        "ai_require_private_base_url": True,
        "ai_base_url_allowed_cidrs":  [],
        "ai_prompt_version_override": "",
        "ai_feature_summary":         False,
        "ai_feature_next_commands":   False,
        "ai_feature_run_suggestions": False,
        "restricted_command_input_cidrs": [],
        "raw_packet_scanning_enabled": False,
        "workflow_active_execution_limit": 3,
        "workflow_execution_max_runtime_seconds": 14400,
        "share_redaction_enabled":    True,
        "share_redaction_rules":      [],
        "rate_limit_enabled":         True,
        "http_rate_limit_per_minute": 240,
        "http_rate_limit_per_second": 60,
        "rate_limit_per_minute":      30,
        "rate_limit_per_second":      5,
        "team_read_rate_limit_per_minute": 180,
        "team_read_rate_limit_per_second": 20,
        "team_write_rate_limit_per_minute": 30,
        "intel_cache_ttl_shodan_ip_seconds": 86400,
        "intel_cache_ttl_shodan_search_seconds": 21600,
        "intel_cache_ttl_shodan_internetdb_ip_seconds": 86400,
        "intel_cache_ttl_censys_host_seconds": 21600,
        "intel_cache_ttl_virustotal_domain_seconds": 21600,
        "intel_cache_ttl_virustotal_file_seconds": 86400,
        "intel_cache_ttl_greynoise_ip_seconds": 3600,
        "intel_cache_ttl_otx_indicator_seconds": 21600,
        "intel_cache_ttl_abuseipdb_ip_seconds": 21600,
        "intel_cache_ttl_ipinfo_ip_seconds": 21600,
        "intel_cache_ttl_teamcymru_ip_seconds": 86400,
        "intel_cache_ttl_tls_certificate_domain_seconds": 21600,
        "intel_cache_ttl_crtsh_domain_seconds": 86400,
        "intel_cache_ttl_hibp_password_seconds": 604800,
        "intel_cache_ttl_nvd_cve_seconds": 86400,
        "intel_cache_ttl_vulners_cve_seconds": 86400,
        "intel_cache_ttl_urlscan_search_seconds": 21600,
        "intel_cache_ttl_urlscan_result_seconds": 86400,
        "intel_cache_ttl_urlhaus_host_seconds": 21600,
        "intel_cache_ttl_urlhaus_payload_seconds": 86400,
        "intel_cache_ttl_urlhaus_url_seconds": 21600,
        "intel_cache_ttl_threatfox_ioc_seconds": 21600,
        "intel_cache_ttl_threatfox_hash_seconds": 86400,
        "intel_cache_ttl_securitytrails_domain_seconds": 86400,
        "intel_cache_ttl_routeviews_prefix_seconds": 21600,
        "intel_cache_ttl_fofa_search_seconds": 21600,
        "intel_cache_ttl_zoomeye_search_seconds": 21600,
        "intel_rate_limit_shodan_bucket": 5,
        "intel_rate_limit_shodan_refill_seconds": 1,
        "intel_rate_limit_shodan_internetdb_bucket": 30,
        "intel_rate_limit_shodan_internetdb_refill_seconds": 2,
        "intel_rate_limit_censys_bucket": 10,
        "intel_rate_limit_censys_refill_seconds": 6,
        "intel_rate_limit_virustotal_public_bucket": 4,
        "intel_rate_limit_virustotal_public_refill_seconds": 15,
        "intel_rate_limit_greynoise_community_bucket": 50,
        "intel_rate_limit_greynoise_community_refill_seconds": 12096,
        "intel_rate_limit_greynoise_unauthenticated_bucket": 10,
        "intel_rate_limit_greynoise_unauthenticated_refill_seconds": 8640,
        "intel_rate_limit_otx_bucket": 30,
        "intel_rate_limit_otx_refill_seconds": 2,
        "intel_rate_limit_abuseipdb_bucket": 20,
        "intel_rate_limit_abuseipdb_refill_seconds": 4,
        "intel_rate_limit_ipinfo_bucket": 30,
        "intel_rate_limit_ipinfo_refill_seconds": 2,
        "intel_rate_limit_teamcymru_bucket": 30,
        "intel_rate_limit_teamcymru_refill_seconds": 2,
        "intel_rate_limit_tls_certificate_bucket": 20,
        "intel_rate_limit_tls_certificate_refill_seconds": 3,
        "intel_rate_limit_crtsh_bucket": 10,
        "intel_rate_limit_crtsh_refill_seconds": 6,
        "intel_rate_limit_hibp_bucket": 10,
        "intel_rate_limit_hibp_refill_seconds": 2,
        "intel_rate_limit_nvd_anonymous_bucket": 5,
        "intel_rate_limit_nvd_anonymous_refill_seconds": 6,
        "intel_rate_limit_vulners_bucket": 10,
        "intel_rate_limit_vulners_refill_seconds": 6,
        "intel_rate_limit_urlscan_bucket": 10,
        "intel_rate_limit_urlscan_refill_seconds": 6,
        "intel_rate_limit_urlhaus_bucket": 20,
        "intel_rate_limit_urlhaus_refill_seconds": 3,
        "intel_rate_limit_threatfox_bucket": 20,
        "intel_rate_limit_threatfox_refill_seconds": 3,
        "intel_rate_limit_securitytrails_bucket": 10,
        "intel_rate_limit_securitytrails_refill_seconds": 6,
        "intel_rate_limit_routeviews_bucket": 20,
        "intel_rate_limit_routeviews_refill_seconds": 3,
        "intel_rate_limit_fofa_bucket": 10,
        "intel_rate_limit_fofa_refill_seconds": 6,
        "intel_rate_limit_zoomeye_bucket": 10,
        "intel_rate_limit_zoomeye_refill_seconds": 6,
        "intel_negative_cache_virustotal_quota_seconds": 21600,
        "intel_negative_cache_censys_quota_seconds": 21600,
        "intel_negative_cache_otx_quota_seconds": 21600,
        "intel_negative_cache_abuseipdb_quota_seconds": 21600,
        "intel_negative_cache_ipinfo_quota_seconds": 21600,
        "intel_negative_cache_urlhaus_quota_seconds": 21600,
        "intel_negative_cache_vulners_quota_seconds": 21600,
        "intel_negative_cache_urlscan_quota_seconds": 21600,
        "intel_negative_cache_threatfox_quota_seconds": 21600,
        "intel_negative_cache_securitytrails_quota_seconds": 21600,
        "intel_negative_cache_fofa_quota_seconds": 21600,
        "intel_negative_cache_zoomeye_quota_seconds": 21600,
        "max_output_lines":           5000,
        "high_volume_output_line_threshold": 50000,
        "high_volume_output_status_interval_lines": 50000,
        "output_preview_max_mb":      1,
        "persist_full_run_output":    True,
        "full_output_max_mb":         5,
        "runs_search_text_inline_max_bytes": 0,
        "snapshots_inline_max_bytes": 0,
        "intel_payload_inline_max_bytes": 0,
        "output_entity_extra_domain_suffixes": [],
        "workspace_enabled":          False,
        "workspace_backend":          "tmpfs",
        # Intentional server-side workspace root default. Workspaces are
        # disabled unless explicitly enabled and all file names are validated
        # relative to hashed per-session directories before use.
        "workspace_root":             "/tmp/darklab_shell-workspaces",  # nosec
        "workspace_quota_mb":         50,
        "workspace_max_file_mb":      5,
        "workspace_max_files":        100,
        "workspace_inactivity_ttl_hours": 1,
        "max_projects_per_session":   100,
        "max_project_links_per_project": 5000,
        "max_project_entities_per_project": 5000,
        "max_project_auto_promote_preview_matches": 200,
        "max_project_auto_promote_scan_candidates": 5000,
        "max_project_auto_promote_apply_matches": 1000,
        "max_project_auto_promote_run_matches": 100,
        "max_project_auto_promote_rules_per_run": 50,
        "max_project_auto_promote_rules_per_project": 100,
        "project_auto_promote_preview_rate_limit_per_minute": 30,
        "project_auto_promote_preview_rate_limit_per_second": 2,
        "atlas_import_max_upload_mb": 10,
        "atlas_import_max_rows": 5000,
        "atlas_import_max_findings": 5000,
        "atlas_import_max_warnings": 100,
        "atlas_import_max_xml_elements": 100000,
        "atlas_import_preview_sample_limit": 20,
        "atlas_import_warning_sample_limit": 50,
        "atlas_import_draft_ttl_minutes": 30,
        "max_project_targets_per_project": 200,
        "max_evidence_packages_per_project": 25,
        "max_entity_labels_per_session": 5000,
        "max_entity_labels_per_entity": 20,
        "max_entity_notes_per_session": 2000,
        "max_finding_triage_details_per_owner": 5000,
        "evidence_package_max_mb":    25,
        "evidence_package_max_uncompressed_mb": 500,
        "evidence_package_max_artifacts": 100,
        "package_presets_file":       "package_presets.yaml",
        "report_templates_file":      "report_templates.yaml",
        "evidence_package_download_rate_limit_per_minute": 10,
        "evidence_package_download_rate_limit_per_second": 2,
        "notifications": {
            "do_not_disturb": False,
            "delivery_rate_per_minute": 10,
            "http_timeout_seconds": 8,
            "test_timeout_seconds": 4,
            "http_private_host_allowlist": [],
            "smtp": {
                "host": "",
                "port": 587,
                "user": "",
                "password_secret_id": "",
                "from_address": "",
                "tls": "starttls",
            },
            "retry": {
                "max_attempts": 6,
                "max_age_hours": 24,
                "base_delay_seconds": 30,
            },
            "events": {
                "retention_days": 30,
            },
        },
        "scheduler": {
            "lock_path": "",
            "tick_seconds": 5,
            "max_per_session": 32,
            "missed_fire_policy": "coalesce",
            "max_catchup_window_seconds": 3600,
            "default_timezone": "UTC",
        },
        "watchers": {
            "max_per_session": 32,
        },
        "project_digests": {
            "default_cadence_preset": "daily",
            "first_send_lookback_hours": 24,
        },
        "max_tabs":                   8,
        "command_timeout_seconds":    3600,
        "heartbeat_interval_seconds": 20,
        "run_broker_enabled":         True,
        "run_broker_require_redis":   True,
        "run_broker_active_stream_ttl_seconds": 14400,
        "run_broker_completed_stream_ttl_seconds": 3600,
        "run_broker_max_replay_bytes": 10485760,
        "run_broker_subscriber_block_seconds": 15,
        "run_broker_heartbeat_seconds": 20,
        "run_broker_owner_stale_seconds": 75,
        "interactive_pty_enabled":     False,
        "interactive_pty_max_runtime_seconds": 900,
        "interactive_pty_max_concurrent_per_session": 4,
        "interactive_pty_input_rate_limit_per_minute": 500,
        "interactive_pty_input_rate_limit_per_second": 10,
        "interactive_pty_resize_rate_limit_per_minute": 600,
        "interactive_pty_resize_rate_limit_per_second": 30,
        "interactive_pty_buffer_limit": 512,
        "interactive_pty_input_max_bytes": 4096,
        "interactive_pty_heartbeat_seconds": 15,
        "interactive_pty_control_poll_seconds": 0.2,
        "interactive_pty_stream_fetch_count": 100,
        "interactive_pty_stream_maxlen": 5000,
        "interactive_pty_snapshot_publish_bytes": 8192,
        "interactive_pty_snapshot_publish_seconds": 1,
        "interactive_pty_snapshot_min_publish_seconds": 0.2,
        "interactive_pty_snapshot_fallback_entry_limit": 200,
        "welcome_char_ms":            18,
        "welcome_jitter_ms":          12,
        "welcome_post_cmd_ms":        650,
        "welcome_inter_block_ms":     850,
        "welcome_first_prompt_idle_ms": 1500,
        "welcome_post_status_pause_ms": 500,
        "welcome_sample_count":       5,
        "welcome_status_labels":      ["CONFIG", "RUNNER", "HISTORY", "LIMITS", "AUTOCOMPLETE"],
        "welcome_hint_interval_ms":   4200,
        "welcome_hint_rotations":     0,
        "tour_enabled":               True,
    }
    schema_defaults = deepcopy(defaults)
    allowed_paths = _flatten_config_paths(schema_defaults)
    allowed_paths.add("full_output_max_bytes")
    provenance: dict[str, str] = {}
    _record_default_provenance(defaults, provenance)
    roots = config_paths.config_roots(
        conf_dir if conf_dir is not None else APP_CONF_DIR or None,
        local_conf_dir if local_conf_dir is not None else APP_LOCAL_CONF_DIR or None,
    )
    conf_path = roots.shipped
    local_conf_path = roots.local
    local_overlay_path = config_paths.config_asset_paths(
        "config.yaml",
        shipped_conf_dir=conf_path,
        local_conf_dir=local_conf_path,
    ).local
    conf_log_path = _config_log_path(conf_path)
    local_conf_log_path = _config_log_path(local_conf_path)
    base_overlay_path = conf_path / "config.yaml"
    base_overlay_log_path = _config_log_path(base_overlay_path)
    local_overlay_log_path = _config_log_path(local_overlay_path)
    local_overlay_present = local_overlay_path.exists()
    log.debug(
        "CONFIG_SOURCE_SELECTED",
        extra={
            "conf_dir": conf_log_path,
            "local_conf_dir": local_conf_log_path,
            "local_overlay": local_overlay_present,
        },
    )
    CONFIG_LOAD_SUMMARY.update({
        "conf_dir": conf_log_path,
        "local_conf_dir": local_conf_log_path,
        "local_overlay": local_overlay_present,
        "supported_local_overlays": len(
            config_paths.supported_overlay_assets(shipped_conf_dir=conf_path)
        ),
        "present_local_overlays": list(config_paths.present_local_overlays(
            shipped_conf_dir=conf_path,
            local_conf_dir=local_conf_path,
        )),
        "overlays": [],
        "env_keys": [],
    })
    base_overlay = _load_yaml_config(base_overlay_path)
    base_known_count, base_unknown_count = _overlay_path_counts(base_overlay, allowed_paths)
    _merge_config_overlay(
        defaults,
        base_overlay,
        source=str(base_overlay_path),
        provenance=provenance,
        allowed_paths=allowed_paths,
    )
    configure_config_log_fallback(
        log,
        log_format=defaults.get("log_format", "text"),
        app_name=defaults.get("app_name", PROJECT_NAME),
        app_version=APP_VERSION,
    )
    if base_known_count:
        cast(list[dict[str, Any]], CONFIG_LOAD_SUMMARY["overlays"]).append({
            "source": base_overlay_log_path,
            "known_keys": base_known_count,
            "unknown_keys": base_unknown_count,
        })
        log.debug(
            "CONFIG_OVERLAY_APPLIED",
            extra={
                "source": base_overlay_log_path,
                "known_keys": base_known_count,
                "unknown_keys": base_unknown_count,
            },
        )
    else:
        log.debug(
            "CONFIG_OVERLAY_CHECKED",
            extra={
                "source": base_overlay_log_path,
                "present": base_overlay_path.exists(),
                "known_keys": base_known_count,
                "unknown_keys": base_unknown_count,
            },
        )
    local_overlay = _load_yaml_config_optional(local_overlay_path)
    local_known_count, local_unknown_count = _overlay_path_counts(local_overlay, allowed_paths)
    _merge_config_overlay(
        defaults,
        local_overlay,
        source=str(local_overlay_path),
        provenance=provenance,
        allowed_paths=allowed_paths,
    )
    configure_config_log_fallback(
        log,
        log_format=defaults.get("log_format", "text"),
        app_name=defaults.get("app_name", PROJECT_NAME),
        app_version=APP_VERSION,
    )
    if local_known_count:
        cast(list[dict[str, Any]], CONFIG_LOAD_SUMMARY["overlays"]).append({
            "source": local_overlay_log_path,
            "known_keys": local_known_count,
            "unknown_keys": local_unknown_count,
        })
        log.debug(
            "CONFIG_OVERLAY_APPLIED",
            extra={
                "source": local_overlay_log_path,
                "known_keys": local_known_count,
                "unknown_keys": local_unknown_count,
            },
        )
    else:
        log.debug(
            "CONFIG_OVERLAY_CHECKED",
            extra={
                "source": local_overlay_log_path,
                "present": local_overlay_present,
                "known_keys": local_known_count,
                "unknown_keys": local_unknown_count,
            },
        )
    applied_env_names: list[str] = []
    env_workspace_root = str(os.environ.get("WORKSPACE_ROOT") or "").strip()
    if env_workspace_root:
        _set_config_value(defaults, provenance, "workspace_root", env_workspace_root, "WORKSPACE_ROOT")
        applied_env_names.append("WORKSPACE_ROOT")
    env_prometheus_multiproc_dir = str(os.environ.get("PROMETHEUS_MULTIPROC_DIR") or "").strip()
    if env_prometheus_multiproc_dir:
        _set_config_value(
            defaults,
            provenance,
            "prometheus_multiproc_dir",
            env_prometheus_multiproc_dir,
            "PROMETHEUS_MULTIPROC_DIR",
        )
        applied_env_names.append("PROMETHEUS_MULTIPROC_DIR")
    env_asset_bundle_mode = str(os.environ.get("ASSET_BUNDLE_MODE") or "").strip()
    if env_asset_bundle_mode:
        _set_config_value(defaults, provenance, "asset_bundle_mode", env_asset_bundle_mode, "ASSET_BUNDLE_MODE")
        applied_env_names.append("ASSET_BUNDLE_MODE")
    env_restricted_command_input_cidrs = str(os.environ.get("RESTRICTED_COMMAND_INPUT_CIDRS") or "").strip()
    if env_restricted_command_input_cidrs:
        _set_config_value(
            defaults,
            provenance,
            "restricted_command_input_cidrs",
            [item.strip() for item in env_restricted_command_input_cidrs.split(",") if item.strip()],
            "RESTRICTED_COMMAND_INPUT_CIDRS",
        )
        applied_env_names.append("RESTRICTED_COMMAND_INPUT_CIDRS")
    env_raw_packet_scanning_enabled = str(os.environ.get("RAW_PACKET_SCANNING_ENABLED") or "").strip()
    if env_raw_packet_scanning_enabled:
        _set_config_value(
            defaults,
            provenance,
            "raw_packet_scanning_enabled",
            env_raw_packet_scanning_enabled,
            "RAW_PACKET_SCANNING_ENABLED",
        )
        applied_env_names.append("RAW_PACKET_SCANNING_ENABLED")
    env_database_backend = str(os.environ.get("DATABASE_BACKEND") or "").strip()
    if env_database_backend:
        _set_config_value(defaults, provenance, "database_backend", env_database_backend, "DATABASE_BACKEND")
        applied_env_names.append("DATABASE_BACKEND")
    env_database_url = str(os.environ.get("DATABASE_URL") or "").strip()
    if env_database_url:
        _set_config_value(defaults, provenance, "database_url", env_database_url, "DATABASE_URL")
        applied_env_names.append("DATABASE_URL")
    env_database_pool_min = str(os.environ.get("DATABASE_POOL_MIN") or "").strip()
    if env_database_pool_min:
        _set_config_value(defaults, provenance, "database_pool_min", env_database_pool_min, "DATABASE_POOL_MIN")
        applied_env_names.append("DATABASE_POOL_MIN")
    env_database_pool_max = str(os.environ.get("DATABASE_POOL_MAX") or "").strip()
    if env_database_pool_max:
        _set_config_value(defaults, provenance, "database_pool_max", env_database_pool_max, "DATABASE_POOL_MAX")
        applied_env_names.append("DATABASE_POOL_MAX")
    env_database_postgres_jit = str(os.environ.get("DATABASE_POSTGRES_JIT") or "").strip()
    if env_database_postgres_jit:
        _set_config_value(
            defaults,
            provenance,
            "database_postgres_jit",
            env_database_postgres_jit,
            "DATABASE_POSTGRES_JIT",
        )
        applied_env_names.append("DATABASE_POSTGRES_JIT")
    ai_env_keys = {
        "AI_ENABLED": "ai_enabled",
        "AI_PROVIDER": "ai_provider",
        "AI_BASE_URL": "ai_base_url",
        "AI_MODEL": "ai_model",
        "AI_API_KEY_SECRET_NAME": "ai_api_key_secret_name",
        "AI_API_KEY": "ai_api_key",
        "AI_CONNECT_TIMEOUT_SECONDS": "ai_connect_timeout_seconds",
        "AI_TIMEOUT_SECONDS": "ai_timeout_seconds",
        "AI_MAX_INPUT_CHARS": "ai_max_input_chars",
        "AI_MAX_OUTPUT_TOKENS": "ai_max_output_tokens",
        "AI_NEXT_COMMANDS_MAX_OUTPUT_TOKENS": "ai_next_commands_max_output_tokens",
        "AI_MAX_CONCURRENT": "ai_max_concurrent",
        "AI_MAX_QUEUE_DEPTH": "ai_max_queue_depth",
        "AI_RATE_LIMIT_PER_SESSION_HOUR": "ai_rate_limit_per_session_hour",
        "AI_RATE_LIMIT_GLOBAL_PER_MINUTE": "ai_rate_limit_global_per_minute",
        "AI_ALLOW_FULL_OUTPUT": "ai_allow_full_output",
        "AI_REQUIRE_PRIVATE_BASE_URL": "ai_require_private_base_url",
        "AI_BASE_URL_ALLOWED_CIDRS": "ai_base_url_allowed_cidrs",
        "AI_PROMPT_VERSION_OVERRIDE": "ai_prompt_version_override",
        "AI_FEATURE_SUMMARY": "ai_feature_summary",
        "AI_FEATURE_NEXT_COMMANDS": "ai_feature_next_commands",
        "AI_FEATURE_RUN_SUGGESTIONS": "ai_feature_run_suggestions",
    }
    for env_name, cfg_key in ai_env_keys.items():
        raw = str(os.environ.get(env_name) or "").strip()
        if not raw:
            continue
        if cfg_key == "ai_base_url_allowed_cidrs":
            value = [item.strip() for item in raw.split(",") if item.strip()]
        else:
            value = raw
        _set_config_value(defaults, provenance, cfg_key, value, env_name)
        applied_env_names.append(env_name)
    CONFIG_LOAD_SUMMARY["env_keys"] = sorted(applied_env_names)
    log.debug("CONFIG_ENV_OVERRIDES_APPLIED", extra={"env_keys": sorted(applied_env_names)})
    _normalize_config_data(defaults, provenance)
    return _validate_config_model(defaults, provenance, schema_defaults)


CFG = load_config()


def resolve_effective_cfg(cfg: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    return CFG if cfg is None else cfg


def _is_writable_directory(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe_path = os.path.join(path, f".darklab_write_probe_{os.getpid()}")
        with open(probe_path, "w", encoding="utf-8") as f:
            f.write("")
        os.unlink(probe_path)
        return True
    except OSError:
        return False


def _configured_data_dir(value):
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def _require_writable_data_dir(path, source):
    resolved = os.path.expanduser(path)
    if not _is_writable_directory(resolved):
        raise RuntimeError(f"{source} is not writable: {resolved}")
    return resolved


def resolve_data_dir(cfg=None):
    """Return the writable directory used for SQLite and run-output artifacts."""
    env_data_dir = _configured_data_dir(os.environ.get("APP_DATA_DIR"))
    if env_data_dir:
        return _require_writable_data_dir(env_data_dir, "APP_DATA_DIR")

    active_cfg = CFG if cfg is None else cfg
    configured = _configured_data_dir(active_cfg.get("data_dir"))
    if configured:
        return _require_writable_data_dir(configured, "data_dir")

    if _is_writable_directory("/data"):
        return "/data"
    return _require_writable_data_dir("/tmp", "fallback data_dir")  # nosec


def get_share_redaction_rules(cfg=None):
    """Return the effective share/export redaction rules for the current config."""
    active_cfg = cfg or CFG
    if not active_cfg.get("share_redaction_enabled", True):
        return []
    # Built-in rules provide a conservative baseline. Operator-defined rules are
    # appended so deployments can add environment-specific masking on top.
    return BUILTIN_SHARE_REDACTION_RULES + list(active_cfg.get("share_redaction_rules") or [])


_THEME_DEFAULTS = {
    # These builtin families are the source of truth for generated example
    # themes and for missing-key fallback when custom themes are partial.
    "dark": {
        "bg":                  "#000000",
        "surface":             "#141414",
        "border":              "#2a2a2a",
        "border_bright":       "#3c3c3c",
        "border_soft":         "rgba(255, 255, 255, 0.08)",
        "text":                "#e0e0e0",
        "muted":               "#9a9a9a",
        "green":               "#39ff14",
        "green_dim":           "#1a7a08",
        "green_glow":          "rgba(57,255,20,0.12)",
        "amber":               "#ffb800",
        "red":                 "#ff3c3c",
        "blue":                "#6ab0f5",
        "terminal_font_size":  "14px",
        "terminal_line_height": "1.65",
        "prompt_line_text":    "#e8e8e8",
        "panel_bg":            "#141414",
        "panel_border":        "#3c3c3c",
        "panel_shadow":        "rgba(170,170,170,0.12)",
        "terminal_bar_bg":     "#000000",
        "chrome_bg":           "#0c0c0c",
        "chrome_header_bg":    "#0c0c0c",
        "chrome_row_bg":       "#0c0c0c",
        "chrome_row_hover_bg": "rgba(57,255,20,0.12)",
        "chrome_control_bg":   "color-mix(in srgb, var(--surface) 92%, transparent)",
        "chrome_control_border": "var(--border-bright)",
        "chrome_divider_color": "#2a2a2a",
        "chrome_shadow":       "rgba(0,0,0,0.6)",
        "scrollbar_track":     "color-mix(in srgb, var(--surface) 72%, transparent)",
        "scrollbar_thumb":     "color-mix(in srgb, var(--muted) 44%, var(--border-bright))",
        "scrollbar_thumb_hover": "color-mix(in srgb, var(--text) 38%, var(--border-bright))",
        "toolbar_button_bg":   "transparent",
        "toolbar_button_border": "#3c3c3c",
        "toolbar_button_text": "#9a9a9a",
        "toolbar_button_hover_bg": "transparent",
        "toolbar_button_hover_border": "#1a7a08",
        "toolbar_button_hover_text": "#39ff14",
        "toolbar_button_active_bg": "rgba(57,255,20,0.06)",
        "toolbar_button_active_border": "#1a7a08",
        "toolbar_button_active_text": "#39ff14",
        "button_secondary_bg": "color-mix(in srgb, var(--surface) 66%, transparent)",
        "button_secondary_border": "color-mix(in srgb, var(--border-bright) 88%, transparent)",
        "button_secondary_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_secondary_hover_bg": "color-mix(in srgb, var(--_tone) 7%, transparent)",
        "button_secondary_hover_border": "color-mix(in srgb, var(--_tone-dim) 72%, var(--border-bright))",
        "button_ghost_border": "color-mix(in srgb, var(--border-bright) 58%, transparent)",
        "button_ghost_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_ghost_hover_bg": "color-mix(in srgb, var(--_tone) 10%, transparent)",
        "button_ghost_hover_border": "color-mix(in srgb, var(--_tone-dim) 62%, var(--border-bright))",
        "button_destructive_bg": "color-mix(in srgb, var(--_tone) 8%, transparent)",
        "button_destructive_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_destructive_hover_bg": "color-mix(in srgb, var(--_tone) 16%, transparent)",
        "tab_text":             "#9a9a9a",
        "tab_hover_text":       "#e0e0e0",
        "tab_active_bg":        "rgba(57,255,20,0.04)",
        "tab_close_bg":         "rgba(255,255,255,0.02)",
        "tab_close_border":     "rgba(255,255,255,0.06)",
        "tab_close_hover_bg":   "color-mix(in srgb, var(--green-dim) 18%, transparent)",
        "tab_close_hover_border": "color-mix(in srgb, var(--green-dim) 30%, transparent)",
        "tab_close_hover_text": "inherit",
        "tab_touch_drag_text_shadow": "0 0 10px color-mix(in srgb, var(--green) 14%, transparent)",
        "tab_drop_shadow":      "0 0 10px color-mix(in srgb, var(--green) 45%, transparent)",
        "history_load_overlay_bg": "rgba(0,0,0,0.76)",
        "modal_bg":             "#141414",
        "dropdown_bg":          "color-mix(in srgb, var(--surface) 96%, transparent)",
        "dropdown_border":      "color-mix(in srgb, var(--green) 18%, transparent)",
        "dropdown_border_soft": "color-mix(in srgb, var(--green) 14%, transparent)",
        "dropdown_shadow":      "rgba(0,0,0,0.35)",
        "dropdown_shadow_ring": "color-mix(in srgb, var(--theme-dropdown-shadow) 24%, transparent)",
        "dropdown_shadow_ring_strong": "color-mix(in srgb, var(--theme-dropdown-shadow) 36%, transparent)",
        "dropdown_item_text":   "#9a9a9a",
        "overlay_backdrop_bg":  "rgba(0,0,0,0.76)",
        "search_highlight_bg": "color-mix(in srgb, var(--amber) 35%, transparent)",
        "search_highlight_current_bg": "color-mix(in srgb, var(--amber) 70%, transparent)",
        "search_signal_bg":    "color-mix(in srgb, var(--amber) 8%, transparent)",
        "search_signal_accent": "color-mix(in srgb, var(--amber) 55%, transparent)",
        "search_signal_current_bg": "color-mix(in srgb, var(--amber) 16%, transparent)",
        "search_signal_current_accent": "color-mix(in srgb, var(--amber) 88%, transparent)",
        "inline_surface_bg":    "#141414",
        "toast_bg":             "#141414",
        "toast_text":           "#39ff14",
        "toast_border":         "#1a7a08",
        "toast_error_bg":       "color-mix(in srgb, var(--red) 8%, var(--bg))",
        "toast_error_text":     "#ff3c3c",
        "toast_error_border":   "color-mix(in srgb, var(--red) 45%, transparent)",
        "toast_shadow":         "0 12px 28px color-mix(in srgb, var(--theme-panel-shadow) 74%, transparent)",
        "welcome_command_hover_bg": "color-mix(in srgb, var(--green) 6%, transparent)",
        "welcome_command_hover_shadow": "0 0 0 1px var(--green-glow)",
        "welcome_ascii_text_shadow": (
            "0 0 10px color-mix(in srgb, var(--green) 14%, transparent), "
            "0 0 4px color-mix(in srgb, var(--green) 18%, transparent), "
            "0 1px 0 rgba(8,16,12,0.4)"
        ),
        "welcome_ascii_color": "var(--green)",
        "welcome_ascii_filter": "saturate(1.12) contrast(1.08) brightness(1.08)",
        "on_accent_text":      "#000",
        "selection_text":      "#f7fff2",
        "selection_line_text": "#eef7ee",
        "modal_danger_btn_text": "#fff",
        "modal_warning_btn_text": "#000",
    },
    "light": {
        "bg":                  "#b8c4d0",
        "surface":             "#eef2f6",
        "border":              "rgba(0,0,0,0.15)",
        "border_bright":       "rgba(0,0,0,0.28)",
        "border_soft":         "rgba(0,0,0,0.12)",
        "text":                "#101820",
        "muted":               "#5a6878",
        "green":               "#2a5d18",
        "green_dim":           "#355f24",
        "green_glow":          "rgba(42,93,24,0.08)",
        "amber":               "#9a4200",
        "red":                 "#cc2200",
        "blue":                "#1a5aaa",
        "terminal_font_size":  "14px",
        "terminal_line_height": "1.65",
        "prompt_line_text":    "#1c201a",
        "panel_bg":            "#d4e0ec",
        "panel_border":        "rgba(0,0,0,0.28)",
        "panel_shadow":        "rgba(0,0,0,0.22)",
        "terminal_bar_bg":     "#b8c4d0",
        "chrome_bg":           "#b8c4d0",
        "chrome_header_bg":    "#b8c4d0",
        "chrome_row_bg":       "#b8c4d0",
        "chrome_row_hover_bg": "rgba(26,90,170,0.06)",
        "chrome_control_bg":   "color-mix(in srgb, var(--surface) 92%, transparent)",
        "chrome_control_border": "var(--border-bright)",
        "chrome_divider_color": "rgba(0,0,0,0.15)",
        "chrome_shadow":       "rgba(0,0,0,0.6)",
        "scrollbar_track":     "color-mix(in srgb, var(--surface) 72%, transparent)",
        "scrollbar_thumb":     "color-mix(in srgb, var(--muted) 44%, var(--border-bright))",
        "scrollbar_thumb_hover": "color-mix(in srgb, var(--text) 38%, var(--border-bright))",
        "toolbar_button_bg":   "#c8d4e0",
        "toolbar_button_border": "#8898b0",
        "toolbar_button_text": "#202838",
        "toolbar_button_hover_bg": "#b8c8d8",
        "toolbar_button_hover_border": "#6880a0",
        "toolbar_button_hover_text": "#101820",
        "toolbar_button_active_bg": "#a0b4c8",
        "toolbar_button_active_border": "#6880a0",
        "toolbar_button_active_text": "#101820",
        "button_secondary_bg": "color-mix(in srgb, var(--surface) 66%, transparent)",
        "button_secondary_border": "color-mix(in srgb, var(--border-bright) 88%, transparent)",
        "button_secondary_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_secondary_hover_bg": "color-mix(in srgb, var(--_tone) 7%, transparent)",
        "button_secondary_hover_border": "color-mix(in srgb, var(--_tone-dim) 72%, var(--border-bright))",
        "button_ghost_border": "color-mix(in srgb, var(--border-bright) 58%, transparent)",
        "button_ghost_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_ghost_hover_bg": "color-mix(in srgb, var(--_tone) 10%, transparent)",
        "button_ghost_hover_border": "color-mix(in srgb, var(--_tone-dim) 62%, var(--border-bright))",
        "button_destructive_bg": "color-mix(in srgb, var(--_tone) 8%, transparent)",
        "button_destructive_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_destructive_hover_bg": "color-mix(in srgb, var(--_tone) 16%, transparent)",
        "tab_text":             "#5a6878",
        "tab_hover_text":       "#101820",
        "tab_active_bg":        "#c0cedd",
        "tab_close_bg":         "rgba(255,255,255,0.02)",
        "tab_close_border":     "rgba(255,255,255,0.06)",
        "tab_close_hover_bg":   "color-mix(in srgb, var(--red) 18%, transparent)",
        "tab_close_hover_border": "color-mix(in srgb, var(--red) 30%, transparent)",
        "tab_close_hover_text": "inherit",
        "tab_touch_drag_text_shadow": "0 0 10px rgba(42,93,24,0.08)",
        "tab_drop_shadow":      "0 0 10px rgba(42,93,24,0.18)",
        "history_load_overlay_bg": "rgba(0,0,0,0.76)",
        "modal_bg":             "#e8eef6",
        "dropdown_bg":          "#d4e0ec",
        "dropdown_border":      "rgba(26,90,170,0.25)",
        "dropdown_border_soft": "rgba(26,90,170,0.18)",
        "dropdown_shadow":      "rgba(0,0,0,0.14)",
        "dropdown_shadow_ring": "color-mix(in srgb, var(--theme-dropdown-shadow) 24%, transparent)",
        "dropdown_shadow_ring_strong": "color-mix(in srgb, var(--theme-dropdown-shadow) 36%, transparent)",
        "dropdown_item_text":   "#4a5868",
        "overlay_backdrop_bg":  "rgba(34,58,88,0.22)",
        "search_highlight_bg": "rgba(154,66,0,0.18)",
        "search_highlight_current_bg": "rgba(154,66,0,0.34)",
        "search_signal_bg":    "rgba(154,66,0,0.08)",
        "search_signal_accent": "rgba(154,66,0,0.28)",
        "search_signal_current_bg": "rgba(154,66,0,0.14)",
        "search_signal_current_accent": "rgba(154,66,0,0.42)",
        "inline_surface_bg":    "#dce6f0",
        "toast_bg":             "#e4eef8",
        "toast_text":           "#2a5d18",
        "toast_border":         "rgba(0,0,0,0.28)",
        "toast_error_bg":       "#e4eef8",
        "toast_error_text":     "#cc2200",
        "toast_error_border":   "rgba(204,34,0,0.38)",
        "toast_shadow":         "0 12px 28px color-mix(in srgb, var(--theme-panel-shadow) 74%, transparent)",
        "welcome_command_hover_bg": "rgba(42,93,24,0.06)",
        "welcome_command_hover_shadow": "0 0 0 1px rgba(42,93,24,0.1)",
        "welcome_ascii_color": "var(--green)",
        "welcome_ascii_text_shadow": "0 0 0 transparent, 0 0 0 transparent, 0 1px 0 rgba(255,255,255,0.5)",
        "welcome_ascii_filter": "saturate(0.9) contrast(0.95) brightness(0.9)",
        "on_accent_text":      "#000",
        "selection_text":      "#f7fff2",
        "selection_line_text": "#eef7ee",
        "modal_danger_btn_text": "#fff",
        "modal_warning_btn_text": "#000",
    },
}

_THEME_CONF_DIR = config_paths.config_roots(APP_CONF_DIR or None, APP_LOCAL_CONF_DIR or None).shipped
_THEME_VARIANT_DIR = _THEME_CONF_DIR / "themes"
_THEME_BASE_CSS_KEYS = (
    "bg",
    "surface",
    "border",
    "border_bright",
    "border_soft",
    "text",
    "muted",
    "green",
    "green_dim",
    "green_glow",
    "amber",
    "red",
    "blue",
    "terminal_font_size",
    "terminal_line_height",
)


_THEME_CSS_ORDER = (
    "bg",
    "surface",
    "border",
    "border_bright",
    "border_soft",
    "text",
    "muted",
    "green",
    "green_dim",
    "green_glow",
    "amber",
    "red",
    "blue",
    "terminal_font_size",
    "terminal_line_height",
    "prompt_line_text",
    "panel_bg",
    "panel_border",
    "panel_shadow",
    "terminal_bar_bg",
    "chrome_bg",
    "chrome_header_bg",
    "chrome_row_bg",
    "chrome_row_hover_bg",
    "chrome_control_bg",
    "chrome_control_border",
    "chrome_divider_color",
    "chrome_shadow",
    "scrollbar_track",
    "scrollbar_thumb",
    "scrollbar_thumb_hover",
    "toolbar_button_bg",
    "toolbar_button_border",
    "toolbar_button_text",
    "toolbar_button_hover_bg",
    "toolbar_button_hover_border",
    "toolbar_button_hover_text",
    "toolbar_button_active_bg",
    "toolbar_button_active_border",
    "toolbar_button_active_text",
    "button_secondary_bg",
    "button_secondary_border",
    "button_secondary_text",
    "button_secondary_hover_bg",
    "button_secondary_hover_border",
    "button_ghost_border",
    "button_ghost_text",
    "button_ghost_hover_bg",
    "button_ghost_hover_border",
    "button_destructive_bg",
    "button_destructive_text",
    "button_destructive_hover_bg",
    "tab_text",
    "tab_hover_text",
    "tab_active_bg",
    "tab_close_bg",
    "tab_close_border",
    "tab_close_hover_bg",
    "tab_close_hover_border",
    "tab_close_hover_text",
    "tab_touch_drag_text_shadow",
    "tab_drop_shadow",
    "history_load_overlay_bg",
    "modal_bg",
    "dropdown_bg",
    "dropdown_border",
    "dropdown_border_soft",
    "dropdown_shadow",
    "dropdown_shadow_ring",
    "dropdown_shadow_ring_strong",
    "dropdown_item_text",
    "overlay_backdrop_bg",
    "search_highlight_bg",
    "search_highlight_current_bg",
    "search_signal_bg",
    "search_signal_accent",
    "search_signal_current_bg",
    "search_signal_current_accent",
    "inline_surface_bg",
    "toast_bg",
    "toast_text",
    "toast_border",
    "toast_error_bg",
    "toast_error_text",
    "toast_error_border",
    "toast_shadow",
    "welcome_ascii_color",
    "welcome_command_hover_bg",
    "welcome_command_hover_shadow",
    "welcome_ascii_text_shadow",
    "welcome_ascii_filter",
    "on_accent_text",
    "selection_text",
    "selection_line_text",
    "modal_danger_btn_text",
    "modal_warning_btn_text",
)


def theme_css_vars(theme: dict) -> dict:
    """Return CSS custom property names for a theme dict."""
    # Export only the ordered theme keys that CSS/templates are expected to read.
    css_vars = {}
    for key in _THEME_CSS_ORDER:
        if key in theme:
            css_vars[f"--theme-{key.replace('_', '-')}"] = theme[key]
    return css_vars


def theme_runtime_css_vars(theme: dict) -> dict:
    """Return the full runtime CSS custom property map for a theme dict."""
    css_vars = {}
    for key in _THEME_BASE_CSS_KEYS:
        if key in theme:
            css_vars[f"--{key.replace('_', '-')}"] = theme[key]
    css_vars.update(theme_css_vars(theme))
    return css_vars


def _parse_theme_rgb(value: str):
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith("#"):
        hex_value = raw[1:]
        if len(hex_value) == 3:
            try:
                return tuple(int(ch * 2, 16) for ch in hex_value)
            except ValueError:
                return None
        if len(hex_value) == 6:
            try:
                return tuple(int(hex_value[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                return None
        return None
    if raw.lower().startswith("rgb(") or raw.lower().startswith("rgba("):
        parts = raw[raw.find("(") + 1: raw.rfind(")")].split(",")
        if len(parts) < 3:
            return None
        try:
            return tuple(max(0, min(255, int(float(parts[i].strip())))) for i in range(3))
        except ValueError:
            return None
    return None


def theme_color_scheme(theme: dict) -> str:
    """Return a best-effort document color-scheme hint for the resolved theme."""
    for key in ("bg", "surface", "panel_bg"):
        rgb = _parse_theme_rgb(theme.get(key, ""))
        if rgb is None:
            continue
        red, green, blue = rgb
        luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
        return "only light" if luminance >= 160 else "only dark"
    return "light dark"


def _theme_name_stem(name: str) -> str:
    stem = str(name).strip()
    if stem.lower().endswith(".yaml"):
        stem = stem[:-5]
    return stem


def _theme_label_from_name(name: str) -> str:
    stem = _theme_name_stem(name)
    for prefix in ("cg_", "c_", "g_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    if stem.startswith("theme_light_"):
        stem = stem[len("theme_light_"):]
    elif stem.startswith("theme_dark_"):
        stem = stem[len("theme_dark_"):]
    elif stem.startswith("light_"):
        stem = stem[len("light_"):]
    elif stem.startswith("dark_"):
        stem = stem[len("dark_"):]
    stem = stem.replace("_", " ").strip()
    return stem.title() if stem else name.replace("_", " ").title()


def _theme_sort_value(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _theme_default_family(theme_data: dict) -> str:
    # color_scheme selects which builtin family fills any keys the theme omits.
    raw = str(theme_data.get("color_scheme", "")).strip().lower()
    if raw in ("light", "only light"):
        return "light"
    if raw in ("dark", "only dark"):
        return "dark"
    return "dark"


def _theme_file_candidates(name):
    stem = _theme_name_stem(name)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", stem):
        return ()
    return (_THEME_VARIANT_DIR / f"{stem}.yaml",)


def _load_theme_mapping(path, *, source):
    try:
        with open(path) as f:
            loaded = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        log.warning(
            "THEME_OVERLAY_LOAD_FAILED",
            extra={
                "path": _config_log_path(path),
                "source": source,
                "error_type": type(exc).__name__,
            },
        )
        return {}
    if not isinstance(loaded, dict):
        log.warning(
            "THEME_OVERLAY_LOAD_FAILED",
            extra={
                "path": _config_log_path(path),
                "source": source,
                "error_type": "InvalidRootType",
            },
        )
        return {}
    return loaded


def _load_theme_yaml(name):
    # Support both exact filenames and stem-like names so operator config can be
    # human friendly while the on-disk registry stays filename based.
    theme_data = {}
    for theme_path in _theme_file_candidates(name):
        if not os.path.exists(theme_path):
            continue
        theme_data.update(_load_theme_mapping(theme_path, source="shipped"))
        local_overlay = config_paths.local_overlay_path_for(
            theme_path,
            shipped_conf_dir=_THEME_CONF_DIR,
            local_conf_dir=APP_LOCAL_CONF_DIR or None,
        )
        if local_overlay.exists():
            theme_data.update(_load_theme_mapping(local_overlay, source="local"))
        return theme_data
    return {}


def load_theme(name):
    """Load a theme YAML file, falling back to the matching built-in defaults for missing keys."""
    # Partial or malformed themes should still resolve to a complete palette so
    # the UI never renders with missing CSS variables.
    name = _theme_name_stem(name)
    user_theme = _load_theme_yaml(name)
    defaults = dict(_THEME_DEFAULTS[_theme_default_family(user_theme)])
    defaults.update({k: str(v) for k, v in user_theme.items() if k in defaults})
    return defaults


def _builtin_theme_entry(name):
    theme = dict(_THEME_DEFAULTS["dark"])
    return {
        "name": name,
        "label": _theme_label_from_name(name),
        "group": "Other",
        "sort": 0,
        "source": "built-in",
        "color_scheme": theme_color_scheme(theme),
        "vars": theme_runtime_css_vars(theme),
        "theme_vars": theme_css_vars(theme),
    }


DARK_THEME = dict(_THEME_DEFAULTS["dark"])


def _theme_entry(name, *, source="variant"):
    theme_name = _theme_name_stem(name)
    user_theme = _load_theme_yaml(theme_name)
    label = str(user_theme.get("label", "")).strip() or _theme_label_from_name(theme_name)
    group = str(user_theme.get("group", "")).strip() or "Other"
    theme = load_theme(theme_name)
    return {
        "name": theme_name,
        "filename": f"{theme_name}.yaml",
        "label": label,
        "group": group,
        "sort": _theme_sort_value(user_theme.get("sort")),
        "source": source,
        "color_scheme": theme_color_scheme(theme),
        "vars": theme_runtime_css_vars(theme),
        "theme_vars": theme_css_vars(theme),
    }


def load_theme_registry():
    """Return the full list of selectable themes."""
    # Preserve selector metadata like label/group/sort/source; the frontend uses
    # it to render the theme chooser declaratively.
    entries = []
    seen = set()
    if _THEME_VARIANT_DIR.exists():
        for theme_path in sorted(_THEME_VARIANT_DIR.glob("*.yaml")):
            if theme_path.name.endswith(".local.yaml"):
                continue
            name = theme_path.stem
            if name in seen:
                continue
            entries.append(_theme_entry(name, source="variant"))
            seen.add(name)
    entries.sort(key=lambda entry: (
        entry.get("sort") is None,
        entry.get("sort") if entry.get("sort") is not None else 0,
        str(entry.get("group", "")),
        str(entry.get("label", "")),
        str(entry.get("name", "")),
    ))
    return entries


THEME_REGISTRY = load_theme_registry()
THEME_REGISTRY_MAP = {}
for entry in THEME_REGISTRY:
    THEME_REGISTRY_MAP[entry["name"]] = entry
    filename = entry.get("filename")
    if filename:
        THEME_REGISTRY_MAP[filename] = entry


def get_theme_entry(name, fallback="dark"):
    """Return a resolved theme registry entry."""
    if name in THEME_REGISTRY_MAP:
        return THEME_REGISTRY_MAP[name]
    if _theme_name_stem(name) in THEME_REGISTRY_MAP:
        return THEME_REGISTRY_MAP[_theme_name_stem(name)]
    if fallback in THEME_REGISTRY_MAP:
        return THEME_REGISTRY_MAP[fallback]
    if _theme_name_stem(fallback) in THEME_REGISTRY_MAP:
        return THEME_REGISTRY_MAP[_theme_name_stem(fallback)]
    return _builtin_theme_entry("dark")

# Scanner user wrapping — prepend sudo to run commands as the unprivileged
# scanner user with the shared appuser group. The explicit run group keeps
# validated workspace files readable/writable without making them world-accessible.
# appuser (Gunicorn) is granted NOPASSWD sudo rights with SETENV to that runas
# pair in /etc/sudoers. SETENV is needed so the app can preserve only declared
# encrypted-secret env vars through sudo without putting values in argv. Falls
# back to running directly if sudo/scanner aren't available (local dev).
SCANNER_PREFIX = []
try:
    pwd.getpwnam("scanner")
    # Pass HOME=/tmp explicitly so nuclei (and other tools) use the tmpfs mount
    # for config/cache instead of /home/scanner which doesn't exist on the
    # read-only filesystem.
    SCANNER_PREFIX = ["sudo", "-u", "scanner", "-g", "appuser", "env", "HOME=/tmp"]
except KeyError:
    pass  # scanner user doesn't exist — local dev, run directly
