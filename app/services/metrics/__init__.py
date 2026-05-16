"""Prometheus metric definitions and instrumentation helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import os
from pathlib import Path
import platform
import re
import tempfile
from typing import Any

from config import APP_VERSION, CFG
from core.helpers import GRACEFUL_TERMINATION_EXIT_CODE
from services.commands.registry_validation import command_root
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL, normalize_run_kind

RUN_DURATION_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0, 900.0, 1800.0, 3600.0)
HTTP_DURATION_BUCKETS = (0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
OUTPUT_BYTES_BUCKETS = (1024.0, 10240.0, 102400.0, 1048576.0, 10485760.0, 104857600.0)
INTEL_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
DB_QUERY_DURATION_BUCKETS = (0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
PTY_SNAPSHOT_AGE_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 15.0, 60.0, 300.0)
EVIDENCE_PACKAGE_DURATION_BUCKETS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0)

EXIT_CODE_CLASSES = frozenset({"success", "error", "signal", "timeout"})
RUN_KINDS = frozenset({RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL})
RATE_LIMIT_SCOPES = frozenset({"global", "secrets", "pty_input", "intel"})
INTEL_OUTCOMES = frozenset({"success", "cache_hit", "error", "missing_secret", "rate_limited", "disabled"})
PTY_DROP_REASONS = frozenset({"rate_limit", "oversize", "not_owner", "closed"})
WORKSPACE_EVICTION_REASONS = frozenset({"quota", "inactive", "manual"})
SNAPSHOT_TRIGGERS = frozenset({"manual", "permalink", "auto"})
BOOL_LABELS = frozenset({"true", "false"})
HISTORY_SEARCH_FALLBACK_REASONS = frozenset({"missing_fts", "fts_error"})
EVIDENCE_PACKAGE_OUTCOMES = frozenset({"success", "too_large", "not_found", "error"})

_LABEL_VALUE_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")
_DEFAULT_PROMETHEUS_MULTIPROC_DIR = Path(tempfile.gettempdir()) / "darklab_shell-prom"


def _configured_buckets(key: str, defaults: tuple[float, ...]) -> tuple[float, ...]:
    raw = CFG.get(key)
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


def setup_prometheus_multiproc_dir(cfg: Mapping[str, Any] | None = None) -> str:
    active_cfg = CFG if cfg is None else cfg
    configured = str(active_cfg.get("prometheus_multiproc_dir") or "").strip()
    path = Path(configured).expanduser() if configured else _DEFAULT_PROMETHEUS_MULTIPROC_DIR
    path.mkdir(parents=True, exist_ok=True)
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(path)
    return str(path)


setup_prometheus_multiproc_dir()

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
    HISTORY_SEARCH_FALLBACKS,
    WORKSPACE_EVICTIONS,
    WORKSPACE_QUOTA_REJECTIONS,
    INTEL_REQUESTS,
    INTEL_REQUEST_DURATION,
    FINDINGS_MATERIALIZED,
    SNAPSHOT_CREATES,
    SNAPSHOT_VIEWS,
    EVIDENCE_PACKAGE_BUILD_DURATION,
    EVIDENCE_PACKAGE_ARCHIVE_BYTES,
    EVIDENCE_PACKAGE_SKIPPED_ITEMS,
    CLIENT_ERRORS,
    UNHANDLED_EXCEPTIONS,
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
    EVIDENCE_PACKAGE_BUILD_DURATION,
    EVIDENCE_PACKAGE_ARCHIVE_BYTES,
)


def _bounded_label(value: object, fallback: str = "unknown", max_len: int = 80) -> str:
    label = _LABEL_VALUE_RE.sub("_", str(value or "").strip().lower())
    label = label.strip("._:-")
    return (label or fallback)[:max_len]


def normalize_tool_label(command: object) -> str:
    root = command_root(str(command or "")) or "unknown"
    return _bounded_label(root)


def normalize_endpoint_label(value: object) -> str:
    return _bounded_label(value, fallback="unknown", max_len=120)


def normalize_provider_label(value: object) -> str:
    return _bounded_label(value)


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
    endpoint_label = normalize_endpoint_label(endpoint)
    HTTP_REQUESTS.labels(str(method or "GET").upper(), endpoint_label, status_class(status_code)).inc()
    HTTP_REQUEST_DURATION.labels(endpoint_label).observe(max(0.0, float(duration_seconds or 0.0)))


def record_rate_limit_rejection(route: object, scope: str = "global") -> None:
    normalized_scope = scope if scope in RATE_LIMIT_SCOPES else "global"
    RATE_LIMIT_REJECTIONS.labels(normalize_endpoint_label(route), normalized_scope).inc()


def record_run_started(command: object, run_kind: object, *, active: bool = True) -> None:
    RUNS_STARTED.labels(normalize_tool_label(command), normalize_run_kind_label(run_kind, command=str(command or ""))).inc()
    if active:
        ACTIVE_RUNS.inc()


def record_run_removed(run_type: str = "command") -> None:
    if str(run_type or "") == "pty":
        PTY_ACTIVE.dec()
    else:
        ACTIVE_RUNS.dec()


def record_pty_started(command: object) -> None:
    PTY_STARTED.labels(normalize_tool_label(command)).inc()
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
    elapsed = max(0.0, float(elapsed_seconds or 0.0))
    RUNS_FINISHED.labels(tool, kind, exit_code_class(exit_code)).inc()
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
    del exit_code
    PTY_DURATION.labels(normalize_tool_label(command)).observe(max(0.0, float(elapsed_seconds or 0.0)))


def record_run_finalize_error(stage: str) -> None:
    stage_label = stage if stage in {"capture", "db_write", "artifact_write", "entity_materialize"} else "db_write"
    RUN_FINALIZE_ERRORS.labels(stage_label).inc()


def record_broker_event(event_type: object) -> None:
    BROKER_EVENTS_PUBLISHED.labels(_bounded_label(event_type, max_len=40)).inc()


def record_broker_publish_error(cause: str) -> None:
    cause_label = cause if cause in {"redis_unavailable", "serialize", "unknown"} else "unknown"
    BROKER_PUBLISH_ERRORS.labels(cause_label).inc()


def record_broker_subscriber_delta(delta: int) -> None:
    if delta > 0:
        BROKER_SUBSCRIBERS.inc(delta)
    elif delta < 0:
        BROKER_SUBSCRIBERS.dec(abs(delta))


def record_db_query(operation: object, duration_seconds: float) -> None:
    DB_QUERY_DURATION.labels(_bounded_label(operation, fallback="unknown", max_len=80)).observe(
        max(0.0, float(duration_seconds or 0.0))
    )


def record_history_search_fallback(reason: str) -> None:
    reason_label = reason if reason in HISTORY_SEARCH_FALLBACK_REASONS else "fts_error"
    HISTORY_SEARCH_FALLBACKS.labels(reason_label).inc()


def record_intel_lookup(provider: object, outcome: str, duration_seconds: float = 0.0, retry_after_seconds: int = 0) -> None:
    outcome_label = outcome if outcome in INTEL_OUTCOMES else "error"
    provider_label = normalize_provider_label(provider)
    INTEL_REQUESTS.labels(provider_label, outcome_label).inc()
    if duration_seconds:
        INTEL_REQUEST_DURATION.labels(provider_label).observe(max(0.0, float(duration_seconds)))
    if outcome_label == "rate_limited" and retry_after_seconds:
        INTEL_PROVIDER_RATE_LIMIT_WAITS.labels(provider_label).observe(max(0.0, float(retry_after_seconds)))


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
    skipped_items: int = 0,
) -> None:
    outcome_label = outcome if outcome in EVIDENCE_PACKAGE_OUTCOMES else "error"
    EVIDENCE_PACKAGE_BUILD_DURATION.labels(outcome_label).observe(max(0.0, float(duration_seconds or 0.0)))
    if outcome_label == "success":
        EVIDENCE_PACKAGE_ARCHIVE_BYTES.observe(max(0, int(archive_bytes or 0)))
        if skipped_artifacts > 0:
            EVIDENCE_PACKAGE_SKIPPED_ITEMS.labels("artifact").inc(skipped_artifacts)
        other_skipped = max(0, int(skipped_items or 0) - int(skipped_artifacts or 0))
        if other_skipped > 0:
            EVIDENCE_PACKAGE_SKIPPED_ITEMS.labels("item").inc(other_skipped)


def record_client_error(context: object) -> None:
    CLIENT_ERRORS.labels(_bounded_label(context, fallback="unknown", max_len=60)).inc()


def record_unhandled_exception(endpoint: object) -> None:
    UNHANDLED_EXCEPTIONS.labels(normalize_endpoint_label(endpoint)).inc()


def validate_metric_definitions(metrics: Iterable[Any] = METRIC_DEFINITIONS) -> None:
    for metric in metrics:
        name = str(getattr(metric, "_name", "") or "")
        if not name.startswith("darklab_"):
            raise RuntimeError(f"metric name must start with darklab_: {name}")
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
