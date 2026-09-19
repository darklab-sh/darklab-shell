# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Pure configuration models and normalization. Importing this module performs no runtime startup.
"""

from __future__ import annotations

import ipaddress
import re
from copy import deepcopy
from collections.abc import Iterator, Mapping, MutableMapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, NoReturn, cast
from urllib.parse import urlsplit
from pydantic import (
    BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr,
    ValidationError, ValidationInfo, create_model, field_validator, model_validator,
)
from config_redaction import normalize_redaction_rules

PROJECT_NAME = "darklab_shell"
APP_NAME_MAX_CHARS = 20
DEFAULT_PROMPT_IDENTITY = "anon@darklab.sh"


@dataclass
class BuildEvents:
    """Collect diagnostics without touching logging or application globals."""

    events: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def debug(self, event, *, extra):
        self.events.append(("debug", event, extra))

    def info(self, event, *, extra):
        self.events.append(("info", event, extra))

    def warning(self, event, *, extra):
        self.events.append(("warning", event, extra))

    def error(self, event, *, extra):
        self.events.append(("error", event, extra))


@dataclass
class _BuildState:
    warnings: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    log: BuildEvents = field(default_factory=BuildEvents)


_BUILD_STATE: ContextVar[_BuildState | None] = ContextVar("config_build_state", default=None)


def _state() -> _BuildState:
    # Mapping-compatible runtime mutation deliberately has no startup side effects.
    return _BUILD_STATE.get() or _BuildState()


@dataclass(frozen=True)
class ConfigBuildResult:
    config: AppConfig
    provenance: dict[str, str]
    warnings: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    events: tuple[tuple[str, str, dict[str, Any]], ...]


_DERIVED_CONFIG_DEFAULTS = {
    "full_output_max_bytes": 5 * 1024 * 1024,
    "output_preview_max_bytes": 1024 * 1024,
}
_SECRET_CONFIG_KEYS = {
    "oidc_client_secret",
    "ai_api_key",
    "ai_api_key_secret_name",
    "notifications.smtp.password_secret_id",
    "oast_connector.token_secret_id",
    "zap_connector.api_key_secret_id",
    "zap_connector.scope_policy_token_secret_id",
}
_SENSITIVE_URL_CONFIG_KEYS = {
    "database_url",
    "oast_connector.base_url",
    "zap_connector.base_url",
    "zap_connector.scope_policy_url",
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
    _state().log.error("CONFIG_LOAD_FAILED", extra=extra)


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
    _state().warnings.append({
        "event": "APP_NAME_TRUNCATED",
        "key": "app_name",
        "source": source,
        "reason": "above_maximum_chars",
    })
    _state().log.warning("APP_NAME_TRUNCATED", extra={
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
    _state().warnings.append({
        "event": "CONFIG_VALUE_DROPPED",
        "key": key,
        "source": source,
        "reason": reason,
    })
    _state().log.warning(warning_event, extra={value_field: bounded_value})
    _state().log.warning(
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
    _state().warnings.append({
        "event": "CONFIG_VALUE_DEFAULTED",
        "key": key,
        "source": source,
        "reason": reason,
    })
    _state().log.warning(
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
    _state().warnings.append({
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
    _state().log.warning("CONFIG_VALUE_CLAMPED", extra=extra)


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


class AssessmentBatchesConfig(_ConfigModel):
    item_limit: StrictInt = Field(default=128, ge=1, le=512)
    max_active_per_owner: StrictInt = Field(default=3, ge=1, le=8)
    max_parallel: StrictInt = Field(default=8, ge=1, le=8)
    max_owner_parallel: StrictInt = Field(default=16, ge=1, le=32)
    max_instance_parallel: StrictInt = Field(default=32, ge=1, le=64)
    retention_days: StrictInt = Field(default=30, ge=0, le=3650)
    max_runtime_seconds: StrictInt = Field(default=14400, ge=60, le=604800)


class CveRiskConfig(_ConfigModel):
    bootstrap_enabled: StrictBool = True
    refresh_enabled: StrictBool = False
    refresh_interval_seconds: StrictInt = Field(default=86400, ge=300, le=604800)
    stale_after_hours: StrictInt = Field(default=48, ge=1, le=8760)
    http_timeout_seconds: StrictInt = Field(default=30, ge=3, le=120)
    max_download_bytes: StrictInt = Field(default=67108864, ge=1024, le=268435456)
    max_attempts: StrictInt = Field(default=3, ge=1, le=5)
    lease_seconds: StrictInt = Field(default=300, ge=30, le=3600)
    work_batch_size: StrictInt = Field(default=100, ge=1, le=1000)
    owner_batch_size: StrictInt = Field(default=100, ge=1, le=1000)
    work_max_attempts: StrictInt = Field(default=5, ge=1, le=20)
    epss_activation_probability: StrictFloat = Field(default=0.10, ge=0, le=1)
    epss_reset_probability: StrictFloat = Field(default=0.08, ge=0, le=1)
    advisory_mode: StrictStr = "disabled"
    nvd_local_path: StrictStr = ""
    osv_advisory_mode: StrictStr = "disabled"
    osv_local_path: StrictStr = ""
    advisory_positive_ttl_seconds: StrictInt = Field(default=604800, ge=3600, le=2592000)
    advisory_negative_ttl_seconds: StrictInt = Field(default=86400, ge=300, le=604800)
    advisory_cvss_downgrade_delta: StrictFloat = Field(default=1.0, gt=0, le=10)
    advisory_max_local_bytes: StrictInt = Field(default=268435456, ge=1024, le=1073741824)
    advisory_max_records: StrictInt = Field(default=500000, ge=1, le=1000000)
    allowed_hosts: list[StrictStr] = Field(default_factory=lambda: [
        "epss.cyentia.com",
        "www.cisa.gov",
        "api.osv.dev",
    ])

    @model_validator(mode="after")
    def validate_contract(self):
        if not 0 <= self.epss_reset_probability < self.epss_activation_probability <= 1:
            raise ValueError(
                "epss_reset_probability must be lower than epss_activation_probability"
            )
        self.advisory_mode = self.advisory_mode.strip().lower()
        if self.advisory_mode not in {"disabled", "local", "external"}:
            raise ValueError("cve_risk.advisory_mode must be disabled, local, or external")
        self.nvd_local_path = self.nvd_local_path.strip()
        if self.advisory_mode == "local" and not self.nvd_local_path:
            raise ValueError("cve_risk.nvd_local_path is required when advisory_mode is local")
        self.osv_advisory_mode = self.osv_advisory_mode.strip().lower()
        if self.osv_advisory_mode not in {"disabled", "local", "external"}:
            raise ValueError(
                "cve_risk.osv_advisory_mode must be disabled, local, or external"
            )
        self.osv_local_path = self.osv_local_path.strip()
        if self.osv_advisory_mode == "local" and not self.osv_local_path:
            raise ValueError(
                "cve_risk.osv_local_path is required when osv_advisory_mode is local"
            )
        normalized_hosts: list[str] = []
        for value in self.allowed_hosts:
            host = value.strip().lower()
            if (
                not host
                or "://" in host
                or "/" in host
                or "@" in host
                or host.startswith(".")
                or host.endswith(".")
            ):
                raise ValueError("cve_risk.allowed_hosts entries must be hostnames")
            normalized_hosts.append(host)
        if not normalized_hosts:
            raise ValueError("cve_risk.allowed_hosts must include at least one hostname")
        self.allowed_hosts = list(dict.fromkeys(normalized_hosts))
        return self


class ZapConnectorConfig(_ConfigModel):
    enabled: StrictBool = False
    base_url: StrictStr = ""
    api_key_secret_id: StrictStr = ""
    tls_verify: StrictBool = True
    allowed_target_cidrs: list[StrictStr] = Field(default_factory=list)
    scope_policy_url: StrictStr = ""
    scope_policy_token_secret_id: StrictStr = ""
    scope_policy_id: StrictStr = ""
    egress_proxy_host: StrictStr = ""
    egress_proxy_port: StrictInt = Field(default=0, ge=0, le=65535)
    max_concurrent_jobs: StrictInt = Field(default=1, ge=1, le=8)
    job_timeout_seconds: StrictInt = Field(default=1800, ge=30, le=86400)
    max_report_bytes: StrictInt = Field(default=10485760, ge=1024, le=52428800)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            if info.data.get("enabled"):
                raise ValueError("is required when the connector is enabled")
            return ""
        try:
            parsed = urlsplit(normalized)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("must be a valid HTTP(S) origin") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or (port is None and parsed.netloc.endswith(":"))
        ):
            raise ValueError("must be an HTTP(S) origin without credentials or a path")
        return normalized

    @field_validator("api_key_secret_id")
    @classmethod
    def validate_api_key_secret_id(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized and info.data.get("enabled"):
            raise ValueError("is required when the connector is enabled")
        if normalized and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", normalized):
            raise ValueError("must name an environment variable")
        return normalized

    @field_validator("allowed_target_cidrs")
    @classmethod
    def validate_allowed_target_cidrs(
        cls,
        values: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        normalized: list[str] = []
        for value in values:
            try:
                network = ipaddress.ip_network(value.strip(), strict=False)
            except ValueError as exc:
                raise ValueError("entries must be IP networks") from exc
            normalized.append(str(network))
        deduplicated = list(dict.fromkeys(normalized))
        if not deduplicated and info.data.get("enabled"):
            raise ValueError("must include at least one network when the connector is enabled")
        return deduplicated

    @field_validator("scope_policy_url")
    @classmethod
    def validate_scope_policy_url(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            if info.data.get("enabled"):
                raise ValueError("is required when the connector is enabled")
            return ""
        try:
            parsed = urlsplit(normalized)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("must be the fixed HTTPS scope-policy endpoint") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/v1/zap-scope/review"
            or parsed.query
            or parsed.fragment
            or (port is None and parsed.netloc.endswith(":"))
        ):
            raise ValueError("must be an HTTPS URL ending in /v1/zap-scope/review")
        return normalized

    @field_validator("scope_policy_token_secret_id")
    @classmethod
    def validate_scope_policy_token_secret_id(
        cls,
        value: str,
        info: ValidationInfo,
    ) -> str:
        normalized = value.strip()
        if not normalized and info.data.get("enabled"):
            raise ValueError("is required when the connector is enabled")
        if normalized and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", normalized):
            raise ValueError("must name an environment variable")
        return normalized

    @field_validator("scope_policy_id")
    @classmethod
    def validate_scope_policy_id(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized and info.data.get("enabled"):
            raise ValueError("is required when the connector is enabled")
        if normalized and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", normalized):
            raise ValueError("must contain only letters, numbers, dot, underscore, and dash")
        return normalized

    @field_validator("egress_proxy_host")
    @classmethod
    def validate_egress_proxy_host(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip().rstrip(".").lower()
        if not normalized:
            if info.data.get("enabled"):
                raise ValueError("is required when the connector is enabled")
            return ""
        try:
            ipaddress.ip_address(normalized)
        except ValueError:
            if (
                len(normalized) > 253
                or not all(
                    re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in normalized.split(".")
                )
            ):
                raise ValueError("must be a hostname or IP address") from None
        return normalized

    @field_validator("egress_proxy_port")
    @classmethod
    def validate_egress_proxy_port(cls, value: int, info: ValidationInfo) -> int:
        if info.data.get("enabled") and value == 0:
            raise ValueError("must be between 1 and 65535 when the connector is enabled")
        return value


class OastConnectorConfig(_ConfigModel):
    enabled: StrictBool = False
    base_url: StrictStr = ""
    token_secret_id: StrictStr = ""
    allowed_domain: StrictStr = ""
    tls_verify: StrictBool = True
    callback_retention_seconds: StrictInt = Field(default=604800, ge=300, le=2592000)
    privacy_acknowledged: StrictBool = False

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            if info.data.get("enabled"):
                raise ValueError("is required when the connector is enabled")
            return ""
        try:
            parsed = urlsplit(normalized)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("must be a valid HTTPS origin") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or (port is None and parsed.netloc.endswith(":"))
        ):
            raise ValueError("must be an HTTPS origin without credentials or a path")
        return normalized

    @field_validator("token_secret_id")
    @classmethod
    def validate_token_secret_id(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized and info.data.get("enabled"):
            raise ValueError("is required when the connector is enabled")
        if normalized and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", normalized):
            raise ValueError("must name an environment variable")
        return normalized

    @field_validator("allowed_domain")
    @classmethod
    def validate_allowed_domain(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip().lower().rstrip(".")
        if not normalized:
            if info.data.get("enabled"):
                raise ValueError("is required when the connector is enabled")
            return ""
        labels = normalized.split(".")
        valid_label = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
        try:
            ipaddress.ip_address(normalized)
        except ValueError:
            pass
        else:
            raise ValueError("must be a DNS suffix rather than an IP address")
        if (
            len(normalized) > 253
            or len(labels) < 2
            or any(not valid_label.fullmatch(label) for label in labels)
        ):
            raise ValueError("must be an exact DNS suffix without a wildcard")
        return normalized

    @field_validator("privacy_acknowledged")
    @classmethod
    def validate_privacy_acknowledged(cls, value: bool, info: ValidationInfo) -> bool:
        if info.data.get("enabled") and not value:
            raise ValueError("must be true when the connector is enabled")
        return value


_FORGIVING_BOOL_KEYS = {
    "restricted_public_shares_enabled",
    "workspace_enabled",
    "interactive_pty_enabled",
    "assessment_intrusive_actions_enabled",
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
    "restricted_public_shares_enabled": False,
    "workspace_enabled": False,
    "interactive_pty_enabled": False,
    "assessment_intrusive_actions_enabled": False,
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
    "assessment_batches": AssessmentBatchesConfig,
    "cve_risk": CveRiskConfig,
    "oast_connector": OastConnectorConfig,
    "zap_connector": ZapConnectorConfig,
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
    if isinstance(value, Mapping):
        text = repr(_redact_config_mapping(value, path))
    else:
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
    _state().warnings.append(payload)
    _state().log.warning(
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
        if source == "built-in defaults" and "." in loc:
            parent = loc.rsplit(".", 1)[0] + "."
            sibling_sources = {
                candidate_source
                for candidate_path, candidate_source in provenance.items()
                if candidate_path.startswith(parent)
                and candidate_source != "built-in defaults"
            }
            if len(sibling_sources) == 1:
                source = sibling_sources.pop()
            elif sibling_sources:
                source = "effective config"
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


def _reject_access_config(
    provenance: dict[str, str], key: str, reason: str, message: str,
    *, phase: str = "oidc_validation",
) -> NoReturn:
    _record_config_load_failure(
        phase=phase, source=_config_source(provenance, key), key=key, error=reason,
    )
    raise ConfigLoadError(message) from None


def _normalize_config_data(defaults: dict[str, Any], provenance: dict[str, str]) -> None:
    access_profile = str(defaults.get("access_profile") or "open").strip().lower()
    if access_profile not in {"open", "token_required", "oidc_required", "mixed"}:
        _record_config_load_failure(
            phase="access_profile_validation",
            source=_config_source(provenance, "access_profile"),
            key="access_profile",
            error="unsupported profile",
        )
        raise ConfigLoadError("access_profile must be open, token_required, oidc_required, or mixed")
    defaults["access_profile"] = access_profile
    for key in ("oidc_issuer", "oidc_client_id", "oidc_client_secret", "oidc_redirect_uri", "oidc_ca_bundle"):
        defaults[key] = str(defaults.get(key) or "").strip()
    policy = str(defaults.get("oidc_provisioning") or "disabled").strip().lower()
    if policy not in {"disabled", "allowlist", "automatic"}:
        _reject_access_config(provenance, "oidc_provisioning", "unsupported_provisioning",
                              "oidc_provisioning must be disabled, allowlist, or automatic")
    defaults["oidc_provisioning"] = policy
    for key, separator in (("oidc_scopes", " "), ("oidc_allowed_subjects", ",")):
        value = defaults.get(key) or []
        if isinstance(value, str):
            value = value.split(separator)
        if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
            _reject_access_config(provenance, key, "invalid_list", f"{key} must be a list of strings")
        defaults[key] = [item.strip() for item in value if item.strip()]
    if "openid" not in defaults["oidc_scopes"]:
        _reject_access_config(provenance, "oidc_scopes", "openid_scope_missing", "oidc_scopes must include openid")
    if len(defaults["oidc_scopes"]) != len(set(defaults["oidc_scopes"])):
        _reject_access_config(provenance, "oidc_scopes", "duplicate_values", "oidc_scopes must not repeat values")
    if len(defaults["oidc_allowed_subjects"]) != len(set(defaults["oidc_allowed_subjects"])):
        _reject_access_config(provenance, "oidc_allowed_subjects", "duplicate_values",
                              "oidc_allowed_subjects must not repeat values")
    configured = any(defaults[key] for key in (
        "oidc_issuer", "oidc_client_id", "oidc_client_secret", "oidc_redirect_uri", "oidc_ca_bundle"
    ))
    if access_profile in {"oidc_required", "mixed"} and not configured:
        _reject_access_config(provenance, "access_profile", "oidc_configuration_required",
                              "OIDC provider configuration is required for this access profile")
    if configured:
        for key in ("oidc_issuer", "oidc_client_id", "oidc_client_secret", "oidc_redirect_uri"):
            if not defaults[key]:
                _reject_access_config(provenance, key, "required_setting_missing", f"{key} is required when OIDC is configured")
        try:
            issuer = urlsplit(defaults["oidc_issuer"])
        except ValueError:
            _reject_access_config(provenance, "oidc_issuer", "invalid_issuer_url", "oidc_issuer must be a valid HTTPS issuer URL")
        try:
            redirect = urlsplit(defaults["oidc_redirect_uri"])
        except ValueError:
            _reject_access_config(provenance, "oidc_redirect_uri", "invalid_redirect_uri",
                                  "oidc_redirect_uri must be a valid HTTPS callback URL")
        if (issuer.scheme != "https" or not issuer.netloc or issuer.username or issuer.password
                or issuer.query or issuer.fragment or defaults["oidc_issuer"].endswith("/")):
            _reject_access_config(provenance, "oidc_issuer", "invalid_issuer_url",
                                  "oidc_issuer must be an HTTPS issuer URL without a trailing slash or query")
        if (redirect.scheme != "https" or not redirect.netloc or redirect.username or redirect.password
                or redirect.query or redirect.fragment or redirect.path != "/auth/oidc/callback"):
            _reject_access_config(provenance, "oidc_redirect_uri", "invalid_redirect_uri",
                                  "oidc_redirect_uri must be an HTTPS /auth/oidc/callback URL")
    if policy == "allowlist" and not defaults["oidc_allowed_subjects"]:
        _reject_access_config(provenance, "oidc_allowed_subjects", "allowlist_required",
                              "oidc_allowed_subjects is required for allowlist provisioning")
    if policy != "allowlist" and defaults["oidc_allowed_subjects"]:
        _reject_access_config(provenance, "oidc_allowed_subjects", "allowlist_not_enabled",
                              "oidc_allowed_subjects is only used with allowlist provisioning")
    if access_profile not in {"oidc_required", "mixed"} and policy != "disabled":
        _reject_access_config(provenance, "oidc_provisioning", "access_profile_disallows_provisioning",
                              "OIDC provisioning requires oidc_required or mixed access")
    for key, minimum, maximum in (
        ("browser_session_idle_minutes", 1, 1440),
        ("browser_session_absolute_hours", 1, 8760),
    ):
        parsed = _parse_int_value(defaults.get(key))
        if parsed is None or not minimum <= parsed <= maximum:
            _record_config_load_failure(
                phase="access_profile_validation",
                source=_config_source(provenance, key),
                key=key,
                error="invalid duration",
            )
            raise ConfigLoadError(f"{key} must be an integer from {minimum} through {maximum}")
        defaults[key] = parsed
    if defaults["browser_session_idle_minutes"] * 60 > defaults["browser_session_absolute_hours"] * 3600:
        _reject_access_config(
            provenance, "browser_session_idle_minutes", "idle_exceeds_absolute",
            "browser_session_idle_minutes cannot be longer than browser_session_absolute_hours",
            phase="access_profile_validation",
        )
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
        _state().log.debug(
            "CONFIG_LEGACY_KEY_MIGRATED",
            extra={
                "legacy_key": "full_output_max_bytes",
                "target_key": "full_output_max_mb",
                "source": _config_log_path(
                    provenance.get("full_output_max_bytes", "legacy full_output_max_bytes")
                ),
            },
        )
        _state().summary["legacy_key_migrated"] = True
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
        defaults.get("share_redaction_rules", []), logger=_state().log
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
    _state().summary.update({
        "schema_field_count": len(schema_fields),
        "derived_keys": len(_DERIVED_CONFIG_DEFAULTS),
        "warning_count": len(_state().warnings),
    })
    _state().log.info(
        "CONFIG_VALIDATED",
        extra={
            "schema_field_count": len(schema_fields),
            "derived_keys": len(_DERIVED_CONFIG_DEFAULTS),
            "warning_count": len(_state().warnings),
        },
    )
    return AppConfig(parsed, schema_model, provenance, schema_defaults)


def config_defaults() -> dict[str, Any]:
    """Return fresh built-in inputs; no files or environment are consulted."""
    return {
        "app_name":                   "darklab_shell",
        "app_public_base_url":        "",
        "access_profile":             "open",
        "restricted_public_shares_enabled": False,
        "browser_session_idle_minutes": 30,
        "browser_session_absolute_hours": 12,
        "oidc_issuer": "",
        "oidc_client_id": "",
        "oidc_client_secret": "",
        "oidc_redirect_uri": "",
        "oidc_scopes": ["openid"],
        "oidc_provisioning": "disabled",
        "oidc_allowed_subjects": [],
        "oidc_ca_bundle": "",
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
        "assessment_intrusive_actions_enabled": False,
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
        "atlas_import_max_expanded_mb": 50,
        "atlas_import_max_rows": 5000,
        "atlas_import_max_findings": 5000,
        "atlas_import_max_warnings": 100,
        "atlas_import_max_xml_elements": 100000,
        "atlas_import_preview_sample_limit": 20,
        "atlas_import_warning_sample_limit": 50,
        "atlas_import_draft_ttl_minutes": 30,
        "max_project_targets_per_project": 200,
        "max_project_assessments_per_owner": 100,
        "max_project_assessments_per_project": 25,
        "max_project_http_profiles_per_project": 50,
        "max_project_assessment_checks_per_owner": 250000,
        "max_project_assessment_checks_per_project": 50000,
        "max_project_assessment_evidence_per_owner": 1000000,
        "max_project_assessment_evidence_per_project": 250000,
        "max_project_assessment_finding_deltas_per_assessment": 100000,
        "max_evidence_packages_per_project": 25,
        "max_entity_labels_per_session": 5000,
        "max_entity_labels_per_entity": 20,
        "max_entity_notes_per_session": 2000,
        "max_finding_triage_details_per_owner": 5000,
        "max_manual_findings_per_owner": 5000,
        "max_finding_evidence_links_per_owner": 10000,
        "max_finding_evidence_links_per_finding": 200,
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
        "assessment_batches": {
            "item_limit": 128,
            "max_active_per_owner": 3,
            "max_parallel": 8,
            "max_owner_parallel": 16,
            "max_instance_parallel": 32,
            "retention_days": 30,
            "max_runtime_seconds": 14400,
        },
        "cve_risk": {
            "bootstrap_enabled": True,
            "refresh_enabled": False,
            "refresh_interval_seconds": 86400,
            "stale_after_hours": 48,
            "http_timeout_seconds": 30,
            "max_download_bytes": 67108864,
            "max_attempts": 3,
            "lease_seconds": 300,
            "work_batch_size": 100,
            "owner_batch_size": 100,
            "work_max_attempts": 5,
            "epss_activation_probability": 0.10,
            "epss_reset_probability": 0.08,
            "advisory_cvss_downgrade_delta": 1.0,
            "allowed_hosts": ["epss.cyentia.com", "www.cisa.gov", "api.osv.dev"],
        },
        "zap_connector": {
            "enabled": False,
            "base_url": "",
            "api_key_secret_id": "",
            "tls_verify": True,
            "allowed_target_cidrs": [],
            "scope_policy_url": "",
            "scope_policy_token_secret_id": "",
            "scope_policy_id": "",
            "egress_proxy_host": "",
            "egress_proxy_port": 0,
            "max_concurrent_jobs": 1,
            "job_timeout_seconds": 1800,
            "max_report_bytes": 10485760,
        },
        "oast_connector": {
            "enabled": False,
            "base_url": "",
            "token_secret_id": "",
            "allowed_domain": "",
            "tls_verify": True,
            "callback_retention_seconds": 604800,
            "privacy_acknowledged": False,
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


def _build_config(layers, environment):
    defaults = config_defaults()
    schema_defaults = deepcopy(defaults)
    allowed_paths = _flatten_config_paths(schema_defaults) | {"full_output_max_bytes"}
    provenance: dict[str, str] = {}
    _record_default_provenance(defaults, provenance)
    for source, overlay in layers:
        _merge_config_overlay(defaults, deepcopy(overlay), source=source,
                              provenance=provenance, allowed_paths=allowed_paths)
    applied_env_names: list[str] = []
    access_env_keys = {
        "ACCESS_PROFILE": "access_profile",
        "RESTRICTED_PUBLIC_SHARES_ENABLED": "restricted_public_shares_enabled",
        "BROWSER_SESSION_IDLE_MINUTES": "browser_session_idle_minutes",
        "BROWSER_SESSION_ABSOLUTE_HOURS": "browser_session_absolute_hours",
        "OIDC_ISSUER": "oidc_issuer",
        "OIDC_CLIENT_ID": "oidc_client_id",
        "OIDC_CLIENT_SECRET": "oidc_client_secret",
        "OIDC_REDIRECT_URI": "oidc_redirect_uri",
        "OIDC_SCOPES": "oidc_scopes",
        "OIDC_PROVISIONING": "oidc_provisioning",
        "OIDC_ALLOWED_SUBJECTS": "oidc_allowed_subjects",
        "OIDC_CA_BUNDLE": "oidc_ca_bundle",
    }
    for env_name, cfg_key in access_env_keys.items():
        raw = str(environment.get(env_name) or "").strip()
        if raw:
            _set_config_value(defaults, provenance, cfg_key, raw, env_name)
            applied_env_names.append(env_name)
    env_workspace_enabled = str(environment.get("WORKSPACE_ENABLED") or "").strip()
    if env_workspace_enabled:
        _set_config_value(
            defaults,
            provenance,
            "workspace_enabled",
            env_workspace_enabled,
            "WORKSPACE_ENABLED",
        )
        applied_env_names.append("WORKSPACE_ENABLED")
    env_workspace_backend = str(environment.get("WORKSPACE_BACKEND") or "").strip()
    if env_workspace_backend:
        _set_config_value(
            defaults,
            provenance,
            "workspace_backend",
            env_workspace_backend,
            "WORKSPACE_BACKEND",
        )
        applied_env_names.append("WORKSPACE_BACKEND")
    env_workspace_root = str(environment.get("WORKSPACE_ROOT") or "").strip()
    if env_workspace_root:
        _set_config_value(defaults, provenance, "workspace_root", env_workspace_root, "WORKSPACE_ROOT")
        applied_env_names.append("WORKSPACE_ROOT")
    env_interactive_pty_enabled = str(environment.get("INTERACTIVE_PTY_ENABLED") or "").strip()
    if env_interactive_pty_enabled:
        _set_config_value(
            defaults,
            provenance,
            "interactive_pty_enabled",
            env_interactive_pty_enabled,
            "INTERACTIVE_PTY_ENABLED",
        )
        applied_env_names.append("INTERACTIVE_PTY_ENABLED")
    env_prometheus_multiproc_dir = str(environment.get("PROMETHEUS_MULTIPROC_DIR") or "").strip()
    if env_prometheus_multiproc_dir:
        _set_config_value(
            defaults,
            provenance,
            "prometheus_multiproc_dir",
            env_prometheus_multiproc_dir,
            "PROMETHEUS_MULTIPROC_DIR",
        )
        applied_env_names.append("PROMETHEUS_MULTIPROC_DIR")
    env_asset_bundle_mode = str(environment.get("ASSET_BUNDLE_MODE") or "").strip()
    if env_asset_bundle_mode:
        _set_config_value(defaults, provenance, "asset_bundle_mode", env_asset_bundle_mode, "ASSET_BUNDLE_MODE")
        applied_env_names.append("ASSET_BUNDLE_MODE")
    env_restricted_command_input_cidrs = str(environment.get("RESTRICTED_COMMAND_INPUT_CIDRS") or "").strip()
    if env_restricted_command_input_cidrs:
        _set_config_value(
            defaults,
            provenance,
            "restricted_command_input_cidrs",
            [item.strip() for item in env_restricted_command_input_cidrs.split(",") if item.strip()],
            "RESTRICTED_COMMAND_INPUT_CIDRS",
        )
        applied_env_names.append("RESTRICTED_COMMAND_INPUT_CIDRS")
    env_raw_packet_scanning_enabled = str(environment.get("RAW_PACKET_SCANNING_ENABLED") or "").strip()
    if env_raw_packet_scanning_enabled:
        _set_config_value(
            defaults,
            provenance,
            "raw_packet_scanning_enabled",
            env_raw_packet_scanning_enabled,
            "RAW_PACKET_SCANNING_ENABLED",
        )
        applied_env_names.append("RAW_PACKET_SCANNING_ENABLED")
    env_assessment_intrusive_actions_enabled = str(
        environment.get("ASSESSMENT_INTRUSIVE_ACTIONS_ENABLED") or ""
    ).strip()
    if env_assessment_intrusive_actions_enabled:
        _set_config_value(
            defaults,
            provenance,
            "assessment_intrusive_actions_enabled",
            env_assessment_intrusive_actions_enabled,
            "ASSESSMENT_INTRUSIVE_ACTIONS_ENABLED",
        )
        applied_env_names.append("ASSESSMENT_INTRUSIVE_ACTIONS_ENABLED")
    env_database_backend = str(environment.get("DATABASE_BACKEND") or "").strip()
    if env_database_backend:
        _set_config_value(defaults, provenance, "database_backend", env_database_backend, "DATABASE_BACKEND")
        applied_env_names.append("DATABASE_BACKEND")
    env_database_url = str(environment.get("DATABASE_URL") or "").strip()
    if env_database_url:
        _set_config_value(defaults, provenance, "database_url", env_database_url, "DATABASE_URL")
        applied_env_names.append("DATABASE_URL")
    env_database_pool_min = str(environment.get("DATABASE_POOL_MIN") or "").strip()
    if env_database_pool_min:
        _set_config_value(defaults, provenance, "database_pool_min", env_database_pool_min, "DATABASE_POOL_MIN")
        applied_env_names.append("DATABASE_POOL_MIN")
    env_database_pool_max = str(environment.get("DATABASE_POOL_MAX") or "").strip()
    if env_database_pool_max:
        _set_config_value(defaults, provenance, "database_pool_max", env_database_pool_max, "DATABASE_POOL_MAX")
        applied_env_names.append("DATABASE_POOL_MAX")
    env_database_postgres_jit = str(environment.get("DATABASE_POSTGRES_JIT") or "").strip()
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
        raw = str(environment.get(env_name) or "").strip()
        if not raw:
            continue
        if cfg_key == "ai_base_url_allowed_cidrs":
            value = [item.strip() for item in raw.split(",") if item.strip()]
        else:
            value = raw
        _set_config_value(defaults, provenance, cfg_key, value, env_name)
        applied_env_names.append(env_name)
    _state().summary["env_keys"] = sorted(applied_env_names)
    _state().log.debug("CONFIG_ENV_OVERRIDES_APPLIED", extra={"env_keys": sorted(applied_env_names)})
    _normalize_config_data(defaults, provenance)
    return _validate_config_model(defaults, provenance, schema_defaults)


def build_config(layers=(), environment: Mapping[str, str] | None = None) -> ConfigBuildResult:
    """Evaluate ordered mapping layers and explicit environment without I/O."""
    state = _BuildState()
    token = _BUILD_STATE.set(state)
    try:
        cfg = _build_config(layers, {} if environment is None else environment)
        return ConfigBuildResult(cfg, dict(cfg._provenance), tuple(deepcopy(state.warnings)),
                                 deepcopy(state.summary), tuple(deepcopy(state.log.events)))
    except ConfigLoadError as exc:
        exc.events = tuple(state.log.events)
        exc.warnings = tuple(state.warnings)
        raise
    finally:
        _BUILD_STATE.reset(token)
