# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Prometheus metric definitions and instrumentation helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import os
import platform
import re
from typing import Any

from config import APP_VERSION, resolve_effective_cfg
from core.helpers import GRACEFUL_TERMINATION_EXIT_CODE
from services.metrics_environment import setup_prometheus_multiproc_dir as setup_prometheus_multiproc_dir
from services.commands.registry_validation import command_root
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL, normalize_run_kind
RUN_DURATION_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0, 900.0, 1800.0, 3600.0)
HTTP_DURATION_BUCKETS = (0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
OUTPUT_BYTES_BUCKETS = (1024.0, 10240.0, 102400.0, 1048576.0, 10485760.0, 104857600.0)
INTEL_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
AI_PROVIDER_DURATION_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
DB_QUERY_DURATION_BUCKETS = (0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
PTY_SNAPSHOT_AGE_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 15.0, 60.0, 300.0)
EVIDENCE_PACKAGE_DURATION_BUCKETS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0)

EXIT_CODE_CLASSES = frozenset({"success", "error", "signal", "timeout"})
RUN_KINDS = frozenset({RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL})
RATE_LIMIT_SCOPES = frozenset({"global", "secrets", "pty_input", "intel"})
INTEL_OUTCOMES = frozenset({"success", "cache_hit", "error", "missing_secret", "rate_limited", "disabled"})
AI_ASSIST_VARIANTS = frozenset({"summary", "next_commands", "diag_test"})
AI_REQUEST_STATUSES = frozenset({"success", "error", "cache_hit", "rate_limited", "rejected"})
AI_PROVIDER_TIMING_PHASES = frozenset({"prompt", "generation"})
AI_ERROR_CODES = frozenset({
    "",
    "ai_busy",
    "ai_context_too_large",
    "ai_context_changed",
    "ai_disabled",
    "ai_feature_disabled",
    "ai_malformed",
    "ai_no_context",
    "ai_rate_limited",
    "ai_run_active",
    "ai_suggestion_rejected",
    "ai_unsupported_variant",
    "ai_unavailable",
    "ai_base_url_not_allowed",
    "not_found",
})
AI_SUGGESTION_REJECTION_REASONS = frozenset({
    "command_target_absent",
    "target_absent",
    "port_absent",
    "shell_chain",
    "denied_flag",
    "missing_secret",
    "private_network",
    "redaction_sentinel",
    "unknown_root",
    "extraction_failed",
    "invalid_flag",
    "policy_rejected",
    "unicode_obfuscation",
})
PTY_DROP_REASONS = frozenset({"rate_limit", "oversize", "not_owner", "closed"})
WORKSPACE_EVICTION_REASONS = frozenset({"quota", "inactive", "manual"})
SNAPSHOT_TRIGGERS = frozenset({"manual", "permalink", "auto"})
BOOL_LABELS = frozenset({"true", "false"})
HISTORY_SEARCH_FALLBACK_REASONS = frozenset({"missing_fts", "fts_error"})
EVIDENCE_PACKAGE_OUTCOMES = frozenset({"success", "too_large", "not_found", "error"})
HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"})
STATUS_CLASSES = frozenset({"1xx", "2xx", "3xx", "4xx", "5xx", "unknown"})
RUN_FINALIZE_STAGES = frozenset({
    "capture", "db_write", "artifact_write", "entity_materialize", "nmap_evidence", "version_inference"})
BROKER_EVENT_TYPES = frozenset({
    "clear",
    "error",
    "exit",
    "heartbeat",
    "killed",
    "notice",
    "output",
    "started",
})
BROKER_PUBLISH_ERROR_CAUSES = frozenset({"redis_unavailable", "serialize", "unknown"})
EVIDENCE_PACKAGE_SKIPPED_KINDS = frozenset({"artifact", "item"})

_LABEL_VALUE_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")
LABEL_CARDINALITY_POLICIES: dict[str, dict[str, dict[str, Any]]] = {
    "darklab_http_requests": {
        "method": {"kind": "enum", "values": HTTP_METHODS, "fallback": "GET"},
        "endpoint": {"kind": "bounded", "max_values": 160, "max_len": 120, "fallback": "unknown"},
        "status_class": {"kind": "enum", "values": STATUS_CLASSES, "fallback": "unknown"},
    },
    "darklab_http_request_duration_seconds": {
        "endpoint": {"kind": "bounded", "max_values": 160, "max_len": 120, "fallback": "unknown"},
    },
    "darklab_runs_started": {
        "tool": {"kind": "bounded", "max_values": 96, "max_len": 80, "fallback": "other"},
        "run_kind": {"kind": "enum", "values": RUN_KINDS, "fallback": RUN_KIND_EXTERNAL},
    },
    "darklab_runs_finished": {
        "tool": {"kind": "bounded", "max_values": 96, "max_len": 80, "fallback": "other"},
        "run_kind": {"kind": "enum", "values": RUN_KINDS, "fallback": RUN_KIND_EXTERNAL},
        "exit_code_class": {"kind": "enum", "values": EXIT_CODE_CLASSES, "fallback": "error"},
    },
    "darklab_run_duration_seconds": {
        "tool": {"kind": "bounded", "max_values": 96, "max_len": 80, "fallback": "other"},
        "run_kind": {"kind": "enum", "values": RUN_KINDS, "fallback": RUN_KIND_EXTERNAL},
    },
    "darklab_run_output_bytes": {
        "tool": {"kind": "bounded", "max_values": 96, "max_len": 80, "fallback": "other"},
    },
    "darklab_run_output_truncated": {
        "tool": {"kind": "bounded", "max_values": 96, "max_len": 80, "fallback": "other"},
    },
    "darklab_run_finalize_errors": {
        "stage": {"kind": "enum", "values": RUN_FINALIZE_STAGES, "fallback": "db_write"},
    },
    "darklab_pty_started": {
        "tool": {"kind": "bounded", "max_values": 96, "max_len": 80, "fallback": "other"},
    },
    "darklab_pty_finished": {
        "tool": {"kind": "bounded", "max_values": 96, "max_len": 80, "fallback": "other"},
        "exit_code_class": {"kind": "enum", "values": EXIT_CODE_CLASSES, "fallback": "error"},
    },
    "darklab_pty_duration_seconds": {
        "tool": {"kind": "bounded", "max_values": 96, "max_len": 80, "fallback": "other"},
    },
    "darklab_pty_input_dropped_bytes": {
        "reason": {"kind": "enum", "values": PTY_DROP_REASONS, "fallback": "closed"},
    },
    "darklab_rate_limit_rejections": {
        "route": {"kind": "bounded", "max_values": 160, "max_len": 120, "fallback": "unknown"},
        "scope": {"kind": "enum", "values": RATE_LIMIT_SCOPES, "fallback": "global"},
    },
    "darklab_intel_provider_rate_limit_waits_seconds": {
        "provider": {"kind": "known_provider", "fallback": "unknown"},
    },
    "darklab_broker_events_published": {
        "event_type": {"kind": "enum", "values": BROKER_EVENT_TYPES, "fallback": "error"},
    },
    "darklab_broker_publish_errors": {
        "cause": {"kind": "enum", "values": BROKER_PUBLISH_ERROR_CAUSES, "fallback": "unknown"},
    },
    "darklab_db_query_duration_seconds": {
        "operation": {"kind": "bounded", "max_values": 48, "max_len": 80, "fallback": "other"},
    },
    "darklab_history_search_fallbacks": {
        "reason": {"kind": "enum", "values": HISTORY_SEARCH_FALLBACK_REASONS, "fallback": "fts_error"},
    },
    "darklab_workspace_evictions": {
        "reason": {"kind": "enum", "values": WORKSPACE_EVICTION_REASONS, "fallback": "manual"},
    },
    "darklab_intel_requests": {
        "provider": {"kind": "known_provider", "fallback": "unknown"},
        "outcome": {"kind": "enum", "values": INTEL_OUTCOMES, "fallback": "error"},
    },
    "darklab_intel_request_duration_seconds": {
        "provider": {"kind": "known_provider", "fallback": "unknown"},
    },
    "darklab_ai_requests": {
        "variant": {"kind": "enum", "values": AI_ASSIST_VARIANTS, "fallback": "summary"},
        "status": {"kind": "enum", "values": AI_REQUEST_STATUSES, "fallback": "error"},
        "error_code": {"kind": "enum", "values": AI_ERROR_CODES, "fallback": "ai_unavailable"},
    },
    "darklab_ai_provider_duration_seconds": {
        "provider": {"kind": "bounded", "max_values": 16, "max_len": 80, "fallback": "unknown"},
        "status": {"kind": "enum", "values": AI_REQUEST_STATUSES, "fallback": "error"},
    },
    "darklab_ai_provider_phase_duration_seconds": {
        "provider": {"kind": "bounded", "max_values": 16, "max_len": 80, "fallback": "unknown"},
        "status": {"kind": "enum", "values": AI_REQUEST_STATUSES, "fallback": "error"},
        "phase": {"kind": "enum", "values": AI_PROVIDER_TIMING_PHASES, "fallback": "prompt"},
    },
    "darklab_ai_cache_hits": {
        "variant": {"kind": "enum", "values": AI_ASSIST_VARIANTS, "fallback": "summary"},
    },
    "darklab_ai_suggestion_rejections": {
        "reason": {"kind": "enum", "values": AI_SUGGESTION_REJECTION_REASONS, "fallback": "unknown_root"},
    },
    "darklab_findings_materialized": {
        "run_kind": {"kind": "enum", "values": RUN_KINDS, "fallback": RUN_KIND_EXTERNAL},
    },
    "darklab_snapshot_creates": {
        "trigger": {"kind": "enum", "values": SNAPSHOT_TRIGGERS, "fallback": "manual"},
    },
    "darklab_snapshot_views": {
        "redacted": {"kind": "enum", "values": BOOL_LABELS, "fallback": "false"},
    },
    "darklab_evidence_package_build_duration_seconds": {
        "outcome": {"kind": "enum", "values": EVIDENCE_PACKAGE_OUTCOMES, "fallback": "error"},
    },
    "darklab_evidence_package_skipped_items": {
        "kind": {"kind": "enum", "values": EVIDENCE_PACKAGE_SKIPPED_KINDS, "fallback": "item"},
    },
    "darklab_client_errors": {
        "context": {"kind": "bounded", "max_values": 96, "max_len": 60, "fallback": "other"},
    },
    "darklab_unhandled_exceptions": {
        "endpoint": {"kind": "bounded", "max_values": 160, "max_len": 120, "fallback": "unknown"},
    },
}

_LABEL_CARDINALITY_SEEN: dict[tuple[str, str], set[str]] = {}


def _configured_buckets(key: str, defaults: tuple[float, ...]) -> tuple[float, ...]:
    raw = resolve_effective_cfg().get(key)
    if not isinstance(raw, (list, tuple)):
        return defaults
    values = []
    for item in raw:
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    values = sorted(set(values))
    return tuple(values) or defaults


from prometheus_client import Counter, Gauge, Histogram, multiprocess  # noqa: E402
from prometheus_client.core import CollectorRegistry  # noqa: E402
from prometheus_client.exposition import generate_latest  # noqa: E402

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


HTTP_REQUESTS = Counter(
    "darklab_http_requests",
    "HTTP requests by method, Flask endpoint, and status class.",
    ("method", "endpoint", "status_class"),
)
HTTP_REQUEST_DURATION = Histogram(
    "darklab_http_request_duration_seconds",
    "HTTP request duration by Flask endpoint.",
    ("endpoint",),
    buckets=_configured_buckets("metrics_histogram_buckets_http_duration", HTTP_DURATION_BUCKETS),
)
ACTIVE_RUNS = Gauge(
    "darklab_active_runs",
    "Currently tracked active runs.",
    multiprocess_mode="livesum",
)
RUNS_STARTED = Counter(
    "darklab_runs_started",
    "Runs started by normalized tool root and run kind.",
    ("tool", "run_kind"),
)
RUNS_FINISHED = Counter(
    "darklab_runs_finished",
    "Runs finished by normalized tool root, run kind, and exit-code class.",
    ("tool", "run_kind", "exit_code_class"),
)
RUN_DURATION = Histogram(
    "darklab_run_duration_seconds",
    "Completed run duration by normalized tool root and run kind.",
    ("tool", "run_kind"),
    buckets=_configured_buckets("metrics_histogram_buckets_run_duration", RUN_DURATION_BUCKETS),
)
RUN_OUTPUT_BYTES = Histogram(
    "darklab_run_output_bytes",
    "Captured run output bytes before compression by normalized tool root.",
    ("tool",),
    buckets=OUTPUT_BYTES_BUCKETS,
)
RUN_OUTPUT_TRUNCATED = Counter(
    "darklab_run_output_truncated",
    "Runs whose preview or full-output artifact was truncated.",
    ("tool",),
)
RUN_FINALIZE_ERRORS = Counter(
    "darklab_run_finalize_errors",
    "Run-finalize errors by bounded persistence stage.",
    ("stage",),
)
PTY_ACTIVE = Gauge(
    "darklab_pty_active",
    "Currently tracked active PTY sessions.",
    multiprocess_mode="livesum",
)
PTY_STARTED = Counter(
    "darklab_pty_started",
    "PTY runs started by normalized tool root.",
    ("tool",),
)
PTY_FINISHED = Counter(
    "darklab_pty_finished",
    "PTY runs finished by normalized tool root and exit-code class.",
    ("tool", "exit_code_class"),
)
PTY_DURATION = Histogram(
    "darklab_pty_duration_seconds",
    "Completed PTY duration by normalized tool root.",
    ("tool",),
    buckets=_configured_buckets("metrics_histogram_buckets_run_duration", RUN_DURATION_BUCKETS),
)
PTY_INPUT_BYTES = Counter(
    "darklab_pty_input_bytes",
    "Total bytes sent from browsers into PTYs.",
)
PTY_INPUT_DROPPED_BYTES = Counter(
    "darklab_pty_input_dropped_bytes",
    "Input bytes rejected before reaching a PTY.",
    ("reason",),
)
PTY_CONTROL_QUEUE_DEPTH = Gauge(
    "darklab_pty_control_queue_depth",
    "Latest observed PTY control queue depth.",
    multiprocess_mode="livemax",
)
PTY_SNAPSHOT_AGE = Histogram(
    "darklab_pty_snapshot_age_seconds",
    "Age of PTY reattach snapshots when served.",
    buckets=PTY_SNAPSHOT_AGE_BUCKETS,
)
RATE_LIMIT_REJECTIONS = Counter(
    "darklab_rate_limit_rejections",
    "Rate-limit rejections by Flask endpoint and bounded scope.",
    ("route", "scope"),
)
INTEL_PROVIDER_RATE_LIMIT_WAITS = Histogram(
    "darklab_intel_provider_rate_limit_waits_seconds",
    "Provider token-bucket wait time exposed to users.",
    ("provider",),
    buckets=(1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0, 900.0),
)
BROKER_EVENTS_PUBLISHED = Counter(
    "darklab_broker_events_published",
    "Run broker events published by bounded event type.",
    ("event_type",),
)
BROKER_SUBSCRIBERS = Gauge(
    "darklab_broker_subscribers",
    "Currently attached broker SSE subscribers.",
    multiprocess_mode="livesum",
)
BROKER_PUBLISH_ERRORS = Counter(
    "darklab_broker_publish_errors",
    "Run broker publish errors by bounded cause.",
    ("cause",),
)
DB_QUERY_DURATION = Histogram(
    "darklab_db_query_duration_seconds",
    "Duration of selected hot database operations.",
    ("operation",),
    buckets=DB_QUERY_DURATION_BUCKETS,
)
POSTGRES_POOL_OPEN_FAILURES = Counter(
    "darklab_postgres_pool_open_failures",
    "Postgres pool open failures.",
)
HISTORY_SEARCH_FALLBACKS = Counter(
    "darklab_history_search_fallbacks",
    "History searches that fell back from FTS to LIKE by bounded reason.",
    ("reason",),
)
WORKSPACE_EVICTIONS = Counter(
    "darklab_workspace_evictions",
    "Workspace removals by bounded reason.",
    ("reason",),
)
WORKSPACE_QUOTA_REJECTIONS = Counter(
    "darklab_workspace_quota_rejections",
    "Workspace writes rejected by quota checks.",
)
INTEL_REQUESTS = Counter(
    "darklab_intel_requests",
    "App-native intel provider lookups by provider and bounded outcome.",
    ("provider", "outcome"),
)
INTEL_REQUEST_DURATION = Histogram(
    "darklab_intel_request_duration_seconds",
    "App-native intel provider lookup duration.",
    ("provider",),
    buckets=INTEL_DURATION_BUCKETS,
)
AI_REQUESTS = Counter(
    "darklab_ai_requests",
    "AI assist requests by variant, bounded status, and bounded error code.",
    ("variant", "status", "error_code"),
)
AI_PROVIDER_DURATION = Histogram(
    "darklab_ai_provider_duration_seconds",
    "AI provider call duration by provider and bounded status.",
    ("provider", "status"),
    buckets=_configured_buckets("metrics_histogram_buckets_ai_provider_duration", AI_PROVIDER_DURATION_BUCKETS),
)
AI_PROVIDER_PHASE_DURATION = Histogram(
    "darklab_ai_provider_phase_duration_seconds",
    "AI provider prompt and generation phase duration by provider and bounded status.",
    ("provider", "status", "phase"),
    buckets=_configured_buckets("metrics_histogram_buckets_ai_provider_duration", AI_PROVIDER_DURATION_BUCKETS),
)
AI_IN_FLIGHT = Gauge(
    "darklab_ai_in_flight",
    "Currently in-flight AI provider calls.",
    multiprocess_mode="livesum",
)
AI_CACHE_HITS = Counter(
    "darklab_ai_cache_hits",
    "AI assist cache hits by variant.",
    ("variant",),
)
AI_SUGGESTION_REJECTIONS = Counter(
    "darklab_ai_suggestion_rejections",
    "AI suggested commands rejected by bounded reason.",
    ("reason",),
)
FINDINGS_MATERIALIZED = Counter(
    "darklab_findings_materialized",
    "Findings materialized from run output by run kind.",
    ("run_kind",),
)
SNAPSHOT_CREATES = Counter(
    "darklab_snapshot_creates",
    "Snapshots created by bounded trigger.",
    ("trigger",),
)
SNAPSHOT_VIEWS = Counter(
    "darklab_snapshot_views",
    "Snapshot views by redaction state.",
    ("redacted",),
)
EVIDENCE_PACKAGE_BUILD_DURATION = Histogram(
    "darklab_evidence_package_build_duration_seconds",
    "Evidence package archive build duration by bounded outcome.",
    ("outcome",),
    buckets=EVIDENCE_PACKAGE_DURATION_BUCKETS,
)
EVIDENCE_PACKAGE_ARCHIVE_BYTES = Histogram(
    "darklab_evidence_package_archive_bytes",
    "Evidence package archive byte size for successful builds.",
    buckets=OUTPUT_BYTES_BUCKETS,
)
EVIDENCE_PACKAGE_SKIPPED_ITEMS = Counter(
    "darklab_evidence_package_skipped_items",
    "Evidence package skipped item count by bounded kind.",
    ("kind",),
)
CLIENT_ERRORS = Counter(
    "darklab_client_errors",
    "Browser-reported client errors by bounded context.",
    ("context",),
)
UNHANDLED_EXCEPTIONS = Counter(
    "darklab_unhandled_exceptions",
    "Unhandled server exceptions by Flask endpoint.",
    ("endpoint",),
)
from services.metrics import workflows as workflow_metrics  # noqa: E402
LABEL_CARDINALITY_POLICIES.update(workflow_metrics.LABEL_CARDINALITY_POLICIES)
METRIC_DEFINITIONS = (
    HTTP_REQUESTS,
    HTTP_REQUEST_DURATION,
    ACTIVE_RUNS,
    RUNS_STARTED,
    RUNS_FINISHED,
    RUN_DURATION,
    RUN_OUTPUT_BYTES,
    RUN_OUTPUT_TRUNCATED,
    RUN_FINALIZE_ERRORS,
    PTY_ACTIVE,
    PTY_STARTED,
    PTY_FINISHED,
    PTY_DURATION,
    PTY_INPUT_BYTES,
    PTY_INPUT_DROPPED_BYTES,
    PTY_CONTROL_QUEUE_DEPTH,
    PTY_SNAPSHOT_AGE,
    RATE_LIMIT_REJECTIONS,
    INTEL_PROVIDER_RATE_LIMIT_WAITS,
    BROKER_EVENTS_PUBLISHED,
    BROKER_SUBSCRIBERS,
    BROKER_PUBLISH_ERRORS,
    DB_QUERY_DURATION,
    POSTGRES_POOL_OPEN_FAILURES,
    HISTORY_SEARCH_FALLBACKS,
    WORKSPACE_EVICTIONS,
    WORKSPACE_QUOTA_REJECTIONS,
    INTEL_REQUESTS,
    INTEL_REQUEST_DURATION,
    AI_REQUESTS,
    AI_PROVIDER_DURATION,
    AI_PROVIDER_PHASE_DURATION,
    AI_IN_FLIGHT,
    AI_CACHE_HITS,
    AI_SUGGESTION_REJECTIONS,
    FINDINGS_MATERIALIZED,
    SNAPSHOT_CREATES,
    SNAPSHOT_VIEWS,
    EVIDENCE_PACKAGE_BUILD_DURATION,
    EVIDENCE_PACKAGE_ARCHIVE_BYTES,
    EVIDENCE_PACKAGE_SKIPPED_ITEMS,
    CLIENT_ERRORS,
    UNHANDLED_EXCEPTIONS,
    *workflow_metrics.METRIC_DEFINITIONS,
)
HISTOGRAM_DEFINITIONS = (
    HTTP_REQUEST_DURATION,
    RUN_DURATION,
    RUN_OUTPUT_BYTES,
    PTY_DURATION,
    PTY_SNAPSHOT_AGE,
    INTEL_PROVIDER_RATE_LIMIT_WAITS,
    DB_QUERY_DURATION,
    INTEL_REQUEST_DURATION,
    AI_PROVIDER_DURATION,
    AI_PROVIDER_PHASE_DURATION,
    EVIDENCE_PACKAGE_BUILD_DURATION,
    EVIDENCE_PACKAGE_ARCHIVE_BYTES,
    *workflow_metrics.HISTOGRAM_DEFINITIONS,
)


def _bounded_label(value: object, fallback: str = "unknown", max_len: int = 80) -> str:
    label = _LABEL_VALUE_RE.sub("_", str(value or "").strip().lower())
    label = label.strip("._:-")
    return (label or fallback)[:max_len]


def _metric_name(metric: Any) -> str:
    return str(getattr(metric, "_name", "") or "")


def _known_intel_provider_labels() -> frozenset[str]:
    try:
        from services.intel.registry import INTEL_PROVIDERS  # noqa: PLC0415
    except Exception:
        return frozenset()
    return frozenset(_bounded_label(provider_id) for provider_id in INTEL_PROVIDERS)


def _enum_metric_label(value: object, allowed: frozenset[str], fallback: str) -> str:
    label = str(value or "").strip()
    return label if label in allowed else fallback


def _cardinality_guarded_label(metric_name: str, label_name: str, value: object) -> str:
    policy = LABEL_CARDINALITY_POLICIES.get(metric_name, {}).get(label_name, {})
    fallback = str(policy.get("fallback") or "other")
    kind = str(policy.get("kind") or "")
    if kind == "enum":
        values = frozenset(str(item) for item in policy.get("values", frozenset()))
        return _enum_metric_label(value, values, fallback)
    if kind == "known_provider":
        label = _bounded_label(value, fallback=fallback, max_len=int(policy.get("max_len") or 80))
        return label if label in _known_intel_provider_labels() else fallback

    max_len = int(policy.get("max_len") or 80)
    label = _bounded_label(value, fallback=fallback, max_len=max_len)
    max_values = int(policy.get("max_values") or 0)
    if max_values <= 0:
        return label
    key = (metric_name, label_name)
    seen = _LABEL_CARDINALITY_SEEN.setdefault(key, set())
    if label in seen:
        return label
    if len(seen) < max_values:
        seen.add(label)
        return label
    return fallback


def normalize_tool_label(command: object) -> str:
    root = command_root(str(command or "")) or "unknown"
    return _bounded_label(root)


def normalize_endpoint_label(value: object) -> str:
    return _bounded_label(value, fallback="unknown", max_len=120)


def normalize_provider_label(value: object) -> str:
    return _cardinality_guarded_label(_metric_name(INTEL_REQUESTS), "provider", value)


def normalize_run_kind_label(value: object, *, command: str = "") -> str:
    return normalize_run_kind(value, command=command)


def exit_code_class(exit_code: Any) -> str:
    try:
        code = int(exit_code)
    except (TypeError, ValueError):
        return "error"
    if code == 0:
        return "success"
    if code == GRACEFUL_TERMINATION_EXIT_CODE:
        return "timeout"
    if code < 0 or code >= 128:
        return "signal"
    return "error"


def status_class(status_code: Any) -> str:
    try:
        code = int(status_code)
    except (TypeError, ValueError):
        return "unknown"
    if 100 <= code <= 599:
        return f"{code // 100}xx"
    return "unknown"


def record_http_request(method: object, endpoint: object, status_code: object, duration_seconds: float) -> None:
    endpoint_label = _cardinality_guarded_label(
        _metric_name(HTTP_REQUESTS), "endpoint", normalize_endpoint_label(endpoint)
    )
    method_label = _cardinality_guarded_label(_metric_name(HTTP_REQUESTS), "method", str(method or "GET").upper())
    status_label = _cardinality_guarded_label(_metric_name(HTTP_REQUESTS), "status_class", status_class(status_code))
    HTTP_REQUESTS.labels(method_label, endpoint_label, status_label).inc()
    HTTP_REQUEST_DURATION.labels(endpoint_label).observe(max(0.0, float(duration_seconds or 0.0)))


def record_rate_limit_rejection(route: object, scope: str = "global") -> None:
    normalized_scope = _cardinality_guarded_label(_metric_name(RATE_LIMIT_REJECTIONS), "scope", scope)
    route_label = _cardinality_guarded_label(
        _metric_name(RATE_LIMIT_REJECTIONS), "route", normalize_endpoint_label(route)
    )
    RATE_LIMIT_REJECTIONS.labels(route_label, normalized_scope).inc()


def record_run_started(command: object, run_kind: object, *, active: bool = True) -> None:
    tool = _cardinality_guarded_label(_metric_name(RUNS_STARTED), "tool", normalize_tool_label(command))
    kind = _cardinality_guarded_label(
        _metric_name(RUNS_STARTED), "run_kind", normalize_run_kind_label(run_kind, command=str(command or ""))
    )
    RUNS_STARTED.labels(tool, kind).inc()
    if active:
        ACTIVE_RUNS.inc()


def record_run_removed(run_type: str = "command") -> None:
    if str(run_type or "") == "pty":
        PTY_ACTIVE.dec()
    else:
        ACTIVE_RUNS.dec()


def record_pty_started(command: object) -> None:
    PTY_STARTED.labels(_cardinality_guarded_label(_metric_name(PTY_STARTED), "tool", normalize_tool_label(command))).inc()
    PTY_ACTIVE.inc()


def record_completed_run_values(
    command: object,
    run_kind: object,
    exit_code: object,
    elapsed_seconds: float,
    output_bytes: int = 0,
    truncated: bool = False,
) -> None:
    tool = normalize_tool_label(command)
    kind = normalize_run_kind_label(run_kind, command=str(command or ""))
    tool = _cardinality_guarded_label(_metric_name(RUNS_FINISHED), "tool", tool)
    kind = _cardinality_guarded_label(_metric_name(RUNS_FINISHED), "run_kind", kind)
    elapsed = max(0.0, float(elapsed_seconds or 0.0))
    RUNS_FINISHED.labels(
        tool,
        kind,
        _cardinality_guarded_label(_metric_name(RUNS_FINISHED), "exit_code_class", exit_code_class(exit_code)),
    ).inc()
    RUN_DURATION.labels(tool, kind).observe(elapsed)
    RUN_OUTPUT_BYTES.labels(tool).observe(max(0, output_bytes))
    if truncated:
        RUN_OUTPUT_TRUNCATED.labels(tool).inc()


def record_completed_run(command: object, run_kind: object, exit_code: object, elapsed_seconds: float, capture: object) -> None:
    output_bytes = int(getattr(capture, "full_output_bytes", 0) or 0)
    if not output_bytes:
        output_bytes = int(getattr(capture, "preview_bytes", 0) or 0)
    record_completed_run_values(
        command,
        run_kind,
        exit_code,
        elapsed_seconds,
        output_bytes=output_bytes,
        truncated=bool(getattr(capture, "preview_truncated", False))
        or bool(getattr(capture, "full_output_truncated", False)),
    )


def record_completed_pty(command: object, exit_code: object, elapsed_seconds: float) -> None:
    tool = _cardinality_guarded_label(_metric_name(PTY_FINISHED), "tool", normalize_tool_label(command))
    PTY_FINISHED.labels(
        tool,
        _cardinality_guarded_label(_metric_name(PTY_FINISHED), "exit_code_class", exit_code_class(exit_code)),
    ).inc()
    PTY_DURATION.labels(tool).observe(max(0.0, float(elapsed_seconds or 0.0)))


def _metric_sample_value(sample: object) -> float:
    raw_value = getattr(sample, "value", 0.0)
    if raw_value is None:
        return 0.0
    return float(raw_value)


def _metric_sample_total(metric: Any, sample_name: str) -> float:
    total = 0.0
    try:
        families = metric.collect()
    except Exception:
        return 0.0
    for family in families:
        for sample in getattr(family, "samples", []) or []:
            if getattr(sample, "name", "") == sample_name:
                try:
                    total += _metric_sample_value(sample)
                except (TypeError, ValueError):
                    continue
    return total


def _pty_duration_summary() -> dict[str, float]:
    count = _metric_sample_total(PTY_DURATION, "darklab_pty_duration_seconds_count")
    total = _metric_sample_total(PTY_DURATION, "darklab_pty_duration_seconds_sum")
    buckets: dict[float, float] = {}
    try:
        families = PTY_DURATION.collect()
    except Exception:
        families = []
    for family in families:
        for sample in getattr(family, "samples", []) or []:
            if getattr(sample, "name", "") != "darklab_pty_duration_seconds_bucket":
                continue
            labels = getattr(sample, "labels", {}) or {}
            raw_le = labels.get("le")
            if raw_le is None:
                continue
            try:
                le = float(raw_le)
                value = _metric_sample_value(sample)
            except (TypeError, ValueError):
                continue
            buckets[le] = buckets.get(le, 0.0) + value
    p95 = 0.0
    if count > 0 and buckets:
        threshold = count * 0.95
        for le in sorted(buckets):
            if buckets[le] >= threshold:
                p95 = le
                break
    return {
        "average_seconds": round(total / count, 3) if count > 0 else 0.0,
        "p95_seconds": round(p95, 3),
        "completed_count": int(count),
    }


def pty_metrics_snapshot() -> dict[str, object]:
    duration = _pty_duration_summary()
    return {
        "active": int(_metric_sample_total(PTY_ACTIVE, "darklab_pty_active")),
        "input_bytes": int(_metric_sample_total(PTY_INPUT_BYTES, "darklab_pty_input_bytes_total")),
        "dropped_input_bytes": int(_metric_sample_total(
            PTY_INPUT_DROPPED_BYTES,
            "darklab_pty_input_dropped_bytes_total",
        )),
        "control_queue_depth": int(_metric_sample_total(
            PTY_CONTROL_QUEUE_DEPTH,
            "darklab_pty_control_queue_depth",
        )),
        **duration,
    }


def record_run_finalize_error(stage: str) -> None:
    stage_label = stage if stage in RUN_FINALIZE_STAGES else "db_write"
    RUN_FINALIZE_ERRORS.labels(stage_label).inc()


def record_broker_event(event_type: object) -> None:
    BROKER_EVENTS_PUBLISHED.labels(
        _cardinality_guarded_label(_metric_name(BROKER_EVENTS_PUBLISHED), "event_type", _bounded_label(event_type, max_len=40))
    ).inc()


def record_broker_publish_error(cause: str) -> None:
    cause_label = cause if cause in {"redis_unavailable", "serialize", "unknown"} else "unknown"
    BROKER_PUBLISH_ERRORS.labels(cause_label).inc()


def record_broker_subscriber_delta(delta: int) -> None:
    if delta > 0:
        BROKER_SUBSCRIBERS.inc(delta)
    elif delta < 0:
        BROKER_SUBSCRIBERS.dec(abs(delta))


def record_db_query(operation: object, duration_seconds: float) -> None:
    DB_QUERY_DURATION.labels(
        _cardinality_guarded_label(
            _metric_name(DB_QUERY_DURATION), "operation", _bounded_label(operation, fallback="unknown", max_len=80)
        )
    ).observe(
        max(0.0, float(duration_seconds or 0.0))
    )


def record_postgres_pool_open_failure() -> None:
    POSTGRES_POOL_OPEN_FAILURES.inc()


def record_history_search_fallback(reason: str) -> None:
    reason_label = reason if reason in HISTORY_SEARCH_FALLBACK_REASONS else "fts_error"
    HISTORY_SEARCH_FALLBACKS.labels(reason_label).inc()


def record_intel_lookup(provider: object, outcome: str, duration_seconds: float = 0.0, retry_after_seconds: int = 0) -> None:
    outcome_label = _cardinality_guarded_label(_metric_name(INTEL_REQUESTS), "outcome", outcome)
    provider_label = normalize_provider_label(provider)
    INTEL_REQUESTS.labels(provider_label, outcome_label).inc()
    if duration_seconds:
        INTEL_REQUEST_DURATION.labels(provider_label).observe(max(0.0, float(duration_seconds)))
    if outcome_label == "rate_limited" and retry_after_seconds:
        INTEL_PROVIDER_RATE_LIMIT_WAITS.labels(provider_label).observe(max(0.0, float(retry_after_seconds)))


def record_ai_request(
    variant: str,
    status: str,
    duration_seconds: float = 0.0,
    *,
    error_code: str = "",
    provider: object = "openai_compatible",
    provider_timings: Mapping[str, Any] | None = None,
) -> None:
    variant_label = _cardinality_guarded_label(_metric_name(AI_REQUESTS), "variant", variant)
    status_label = _cardinality_guarded_label(_metric_name(AI_REQUESTS), "status", status)
    error_label = _cardinality_guarded_label(_metric_name(AI_REQUESTS), "error_code", error_code)
    AI_REQUESTS.labels(variant_label, status_label, error_label).inc()
    if duration_seconds:
        provider_label = _cardinality_guarded_label(
            _metric_name(AI_PROVIDER_DURATION),
            "provider",
            _bounded_label(provider, fallback="unknown", max_len=80),
        )
        AI_PROVIDER_DURATION.labels(provider_label, status_label).observe(max(0.0, float(duration_seconds)))
        timings = provider_timings if isinstance(provider_timings, Mapping) else {}
        for phase, key in (("prompt", "prompt_ms"), ("generation", "predicted_ms")):
            value = timings.get(key)
            if not isinstance(value, (int, float)):
                continue
            phase_label = _cardinality_guarded_label(
                _metric_name(AI_PROVIDER_PHASE_DURATION),
                "phase",
                phase,
            )
            AI_PROVIDER_PHASE_DURATION.labels(provider_label, status_label, phase_label).observe(
                max(0.0, float(value) / 1000.0)
            )


def record_ai_cache_hit(variant: str) -> None:
    variant_label = _cardinality_guarded_label(_metric_name(AI_CACHE_HITS), "variant", variant)
    AI_CACHE_HITS.labels(variant_label).inc()


def record_ai_suggestion_rejection(reason: str) -> None:
    reason_label = _cardinality_guarded_label(_metric_name(AI_SUGGESTION_REJECTIONS), "reason", reason)
    AI_SUGGESTION_REJECTIONS.labels(reason_label).inc()


def record_workspace_evictions(count: int, reason: str) -> None:
    reason_label = reason if reason in WORKSPACE_EVICTION_REASONS else "manual"
    if count > 0:
        WORKSPACE_EVICTIONS.labels(reason_label).inc(count)


def record_workspace_quota_rejection() -> None:
    WORKSPACE_QUOTA_REJECTIONS.inc()


def record_findings_materialized(run_kind: object, count: int) -> None:
    if count > 0:
        FINDINGS_MATERIALIZED.labels(normalize_run_kind_label(run_kind)).inc(count)


def record_snapshot_created(trigger: str) -> None:
    trigger_label = trigger if trigger in SNAPSHOT_TRIGGERS else "manual"
    SNAPSHOT_CREATES.labels(trigger_label).inc()


def record_snapshot_view(redacted: bool) -> None:
    SNAPSHOT_VIEWS.labels("true" if redacted else "false").inc()


def record_evidence_package_build(
    outcome: str,
    duration_seconds: float,
    *,
    archive_bytes: int = 0,
    skipped_artifacts: int = 0,
    skipped_other_items: int = 0,
) -> None:
    outcome_label = outcome if outcome in EVIDENCE_PACKAGE_OUTCOMES else "error"
    EVIDENCE_PACKAGE_BUILD_DURATION.labels(outcome_label).observe(max(0.0, float(duration_seconds or 0.0)))
    if outcome_label == "success":
        EVIDENCE_PACKAGE_ARCHIVE_BYTES.observe(max(0, int(archive_bytes or 0)))
        if skipped_artifacts > 0:
            EVIDENCE_PACKAGE_SKIPPED_ITEMS.labels("artifact").inc(skipped_artifacts)
        if skipped_other_items > 0:
            EVIDENCE_PACKAGE_SKIPPED_ITEMS.labels("item").inc(skipped_other_items)


def record_client_error(context: object) -> None:
    CLIENT_ERRORS.labels(
        _cardinality_guarded_label(
            _metric_name(CLIENT_ERRORS), "context", _bounded_label(context, fallback="unknown", max_len=60)
        )
    ).inc()


def record_unhandled_exception(endpoint: object) -> None:
    UNHANDLED_EXCEPTIONS.labels(
        _cardinality_guarded_label(_metric_name(UNHANDLED_EXCEPTIONS), "endpoint", normalize_endpoint_label(endpoint))
    ).inc()


def validate_metric_definitions(metrics: Iterable[Any] = METRIC_DEFINITIONS) -> None:
    for metric in metrics:
        name = _metric_name(metric)
        if not name.startswith("darklab_"):
            raise RuntimeError(f"metric name must start with darklab_: {name}")
        label_names = tuple(str(item) for item in getattr(metric, "_labelnames", ()) or ())
        policy = LABEL_CARDINALITY_POLICIES.get(name, {})
        missing = sorted(label for label in label_names if label not in policy)
        extra = sorted(label for label in policy if label not in label_names)
        if missing:
            raise RuntimeError(f"metric label missing cardinality policy: {name} {', '.join(missing)}")
        if extra:
            raise RuntimeError(f"metric cardinality policy references unknown label: {name} {', '.join(extra)}")
        for label_name in label_names:
            label_policy = policy[label_name]
            kind = str(label_policy.get("kind") or "")
            if kind not in {"enum", "bounded", "known_provider"}:
                raise RuntimeError(f"metric label has invalid cardinality policy: {name}.{label_name}")
            if kind == "enum" and not label_policy.get("values"):
                raise RuntimeError(f"metric enum label has no allowed values: {name}.{label_name}")
            if kind == "bounded":
                max_values = int(label_policy.get("max_values") or 0)
                max_len = int(label_policy.get("max_len") or 0)
                if max_values <= 0 or max_values > 200 or max_len <= 0 or max_len > 120:
                    raise RuntimeError(f"metric bounded label needs tight limits: {name}.{label_name}")
            if kind == "known_provider" and not _known_intel_provider_labels():
                raise RuntimeError(f"metric provider label has no known provider set: {name}.{label_name}")
    for histogram in HISTOGRAM_DEFINITIONS:
        buckets = getattr(histogram, "_upper_bounds", ())
        finite = [item for item in buckets if item != float("inf")]
        if not finite:
            raise RuntimeError(f"histogram must declare explicit buckets: {getattr(histogram, '_name', '')}")


def build_info_labels() -> dict[str, str]:
    return {
        "version": str(APP_VERSION),
        "git_sha": str(os.environ.get("GIT_SHA") or os.environ.get("CI_COMMIT_SHA") or "unknown")[:40],
        "python_version": platform.python_version(),
    }


def metrics_registry() -> CollectorRegistry:
    registry = CollectorRegistry()
    try:
        multiprocess.MultiProcessCollector(registry)
    except ValueError:
        # If a local developer imports the module before the env var is set,
        # scrape-time collectors still make /metrics useful instead of failing.
        pass
    from services.metrics.collectors import RuntimeStateCollector  # noqa: PLC0415
    registry.register(RuntimeStateCollector())
    return registry


def render_latest_metrics() -> bytes:
    return generate_latest(metrics_registry())


validate_metric_definitions()
