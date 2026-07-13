"""Prometheus `/metrics` route and instrumentation tests."""

from datetime import datetime, timedelta, timezone
import fnmatch
import re
import uuid
from unittest import mock

import pytest

from conftest import make_test_app as _test_app
import config
from core import database
from core.database_backend import DatabaseBackend
from services import metrics as app_metrics


def get_client(*, use_forwarded_for=True):
    client = _test_app(init_db=False).test_client()
    if use_forwarded_for:
        client.environ_base["HTTP_X_FORWARDED_FOR"] = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
    return client


def _allowed_metrics(client):
    with mock.patch.dict(config.CFG, {"diagnostics_allowed_cidrs": ["127.0.0.1/32"], "metrics_enabled": True}):
        return client.get("/metrics")


class _Capture:
    preview_truncated = False
    full_output_truncated = False
    full_output_bytes = 42
    preview_bytes = 42


class _RedisMetricsClient:
    def __init__(self, keys: list[str] | None = None) -> None:
        self.keys = sorted(keys or [])

    def ping(self):
        return True

    def scan(self, cursor=0, match=None, count=100):  # noqa: ARG002
        start = int(cursor or 0)
        matched = [key for key in self.keys if fnmatch.fnmatch(key, match or "*")]
        end = min(start + max(1, int(count or 100)), len(matched))
        next_cursor = 0 if end >= len(matched) else end
        return next_cursor, matched[start:end]

    def xlen(self, key):
        return 3 if key == "runstream:run-1" else 0

    def info(self):
        return {"connected_clients": 2}


class TestMetricsEndpoint:
    def test_ip_gate_denies_non_allowlisted_callers(self):
        client = get_client(use_forwarded_for=False)
        with mock.patch.dict(config.CFG, {"diagnostics_allowed_cidrs": ["10.0.0.0/8"], "metrics_enabled": True}):
            resp = client.get("/metrics")
        assert resp.status_code == 404

    def test_disabled_route_returns_404_even_when_allowlisted(self):
        client = get_client(use_forwarded_for=False)
        with mock.patch.dict(config.CFG, {"diagnostics_allowed_cidrs": ["127.0.0.1/32"], "metrics_enabled": False}):
            resp = client.get("/metrics")
        assert resp.status_code == 404

    def test_allowlisted_callers_get_prometheus_text(self):
        resp = _allowed_metrics(get_client(use_forwarded_for=False))

        assert resp.status_code == 200
        assert resp.content_type == "text/plain; version=0.0.4; charset=utf-8"
        body = resp.get_data(as_text=True)
        assert "# HELP darklab_build_info" in body
        assert "# TYPE darklab_http_requests_total counter" in body

    def test_scrape_includes_runtime_gauge_families(self, monkeypatch):
        from services.metrics import collectors

        monkeypatch.setattr(
            collectors.process,
            "redis_client",
            _RedisMetricsClient([
                "ai:assist:inflight:dedupe",
                "ai:provider:inflight",
                "ai:provider:slot:0",
                "ai:rate:global:123",
                "ai:rate:session:abcd:456",
                "intel:cache:shodan:abc",
                "proc:123",
                "procmeta:123",
                "runstream:run-1",
                "sessionprocs:tok",
            ]),
        )
        body = _allowed_metrics(get_client(use_forwarded_for=False)).get_data(as_text=True)

        expected_names = [
            "darklab_app_start_time_seconds",
            "darklab_db_size_bytes",
            "darklab_db_table_rows",
            "darklab_db_fts_orphans",
            "darklab_redis_up",
            "darklab_broker_mode_info",
            "darklab_workspace_bytes_used",
            "darklab_atlas_entities",
            "darklab_findings_total",
            "darklab_snapshots_total",
            "darklab_health_status",
            "darklab_intel_cache_entries",
            "darklab_intel_quota_cache_entries",
            "darklab_ai_assist_rows",
            "darklab_ai_assist_oldest_queued_age_seconds",
            "darklab_ai_assist_oldest_in_progress_age_seconds",
            "darklab_ai_assist_oldest_heartbeat_age_seconds",
        ]
        for name in expected_names:
            assert name in body
        assert 'darklab_redis_keys{prefix="ai_rate"} 2.0' in body
        assert 'darklab_redis_keys{prefix="ai_assist_inflight"} 1.0' in body
        assert 'darklab_redis_keys{prefix="ai_provider_slot"} 1.0' in body
        assert 'darklab_redis_keys{prefix="ai_provider_legacy"} 1.0' in body
        assert 'darklab_redis_stream_length{prefix="runstream"} 3.0' in body

    def test_scrape_includes_durable_ai_assist_queue_health(self, monkeypatch, tmp_path):
        db_path = tmp_path / "metrics-ai.db"
        monkeypatch.setattr(database, "DB_PATH", str(db_path))
        monkeypatch.setattr(database, "DB_INIT_LOCK_PATH", str(tmp_path / "metrics-ai.db.init.lock"))
        monkeypatch.setattr(database, "DB_BACKEND", DatabaseBackend.SQLITE)
        database.db_init()
        now = datetime.now(timezone.utc)
        with database.db_connect() as conn:
            conn.executemany(
                "INSERT INTO ai_run_assists "
                "(id, run_id, session_id, variant, prompt_version, prompt_version_source, "
                "payload_schema_version, model, context_hash, status, created_at, updated_at, "
                "claimed_at, heartbeat_at) "
                "VALUES (?, ?, ?, ?, 'ai-assist-v1', 'canonical', 'v1', 'llama', ?, ?, ?, ?, ?, ?)",
                [
                    (
                        "ai_metrics_queued",
                        "run-metrics",
                        "tok_metrics",
                        "summary",
                        "hash-q",
                        "queued",
                        (now - timedelta(minutes=7)).isoformat(),
                        now.isoformat(),
                        None,
                        None,
                    ),
                    (
                        "ai_metrics_progress",
                        "run-metrics",
                        "tok_metrics",
                        "next_commands",
                        "hash-p",
                        "in_progress",
                        (now - timedelta(minutes=12)).isoformat(),
                        now.isoformat(),
                        (now - timedelta(minutes=11)).isoformat(),
                        (now - timedelta(minutes=3)).isoformat(),
                    ),
                    (
                        "ai_metrics_completed",
                        "run-metrics",
                        "tok_metrics",
                        "next_commands",
                        "hash-c",
                        "completed",
                        (now - timedelta(minutes=1)).isoformat(),
                        now.isoformat(),
                        None,
                        None,
                    ),
                ],
            )
            conn.commit()

        body = _allowed_metrics(get_client(use_forwarded_for=False)).get_data(as_text=True)

        assert re.search(r'darklab_ai_assist_rows\{status="queued",variant="summary"\} 1\.0', body)
        assert re.search(r'darklab_ai_assist_rows\{status="in_progress",variant="next_commands"\} 1\.0', body)
        assert re.search(r'darklab_ai_assist_rows\{status="completed",variant="next_commands"\} 1\.0', body)
        assert re.search(r'darklab_ai_assist_oldest_queued_age_seconds\{variant="summary"\} [1-9]\d*(?:\.\d+)?', body)
        assert re.search(
            r'darklab_ai_assist_oldest_in_progress_age_seconds\{variant="next_commands"\} [1-9]\d*(?:\.\d+)?',
            body,
        )
        assert re.search(
            r'darklab_ai_assist_oldest_heartbeat_age_seconds\{variant="next_commands"\} [1-9]\d*(?:\.\d+)?',
            body,
        )

    def test_scrape_includes_postgres_pool_config_and_state(self, monkeypatch):
        from services.metrics import collectors

        monkeypatch.setattr(collectors.database, "DB_BACKEND", DatabaseBackend.POSTGRES)
        monkeypatch.setattr(
            collectors,
            "postgres_pool_metrics_snapshot",
            lambda _cfg: {
                "configured_min": 2,
                "configured_max": 7,
                "jit_enabled": 0,
                "open": 1,
                "size": 4,
                "available": 3,
                "used": 1,
                "waiting": 2,
            },
        )

        body = _allowed_metrics(get_client(use_forwarded_for=False)).get_data(as_text=True)

        assert 'darklab_postgres_pool_config{setting="min"} 2.0' in body
        assert 'darklab_postgres_pool_config{setting="max"} 7.0' in body
        assert 'darklab_postgres_pool_config{setting="jit_enabled"} 0.0' in body
        assert 'darklab_postgres_pool_connections{state="open"} 1.0' in body
        assert 'darklab_postgres_pool_connections{state="size"} 4.0' in body
        assert 'darklab_postgres_pool_connections{state="available"} 3.0' in body
        assert 'darklab_postgres_pool_connections{state="used"} 1.0' in body
        assert 'darklab_postgres_pool_connections{state="waiting"} 2.0' in body

    def test_run_finalize_metric_uses_bounded_labels(self):
        app_metrics.record_completed_run("nmap -sV darklab.sh", "external", 0, 1.25, _Capture())

        body = _allowed_metrics(get_client(use_forwarded_for=False)).get_data(as_text=True)

        assert (
            'darklab_runs_finished_total{exit_code_class="success",run_kind="external",tool="nmap"}'
            in body
        )
        assert 'darklab_run_output_bytes_bucket{le="1024.0",tool="nmap"}' in body

    def test_rate_limit_and_intel_helpers_render_expected_labels(self):
        app_metrics.record_rate_limit_rejection("run.start_brokered_run", scope="global")
        app_metrics.record_intel_lookup("shodan", "cache_hit", 0.05)
        app_metrics.record_intel_lookup("user supplied provider", "surprise")
        app_metrics.record_db_query("history_list", 0.01)
        app_metrics.record_postgres_pool_open_failure()
        app_metrics.record_history_search_fallback("missing_fts")
        for error_code in (
            "ai_context_changed",
            "ai_feature_disabled",
            "ai_no_context",
            "ai_run_active",
            "ai_unsupported_variant",
            "not_found",
        ):
            app_metrics.record_ai_request("summary", "rejected", error_code=error_code)
        app_metrics.record_ai_request("summary", "error", error_code="unexpected_ai_error")
        app_metrics.record_evidence_package_build(
            "success",
            0.2,
            archive_bytes=2048,
            skipped_artifacts=1,
            skipped_other_items=1,
        )
        app_metrics.record_completed_pty("mtr darklab.sh", 130, 0.5)
        app_metrics.record_workspace_evictions(2, "manual")
        from services.metrics import workflows as workflow_metrics

        workflow_metrics.record_workflow_execution_outcome("completed", 2.5)
        workflow_metrics.record_workflow_step_outcome("succeeded", 1.25)
        workflow_metrics.record_workflow_capture_failure("required_missing")
        workflow_metrics.record_workflow_cancellation()
        workflow_metrics.record_workflow_recovery_action("recovered")

        body = _allowed_metrics(get_client(use_forwarded_for=False)).get_data(as_text=True)

        assert 'darklab_rate_limit_rejections_total{route="run.start_brokered_run",scope="global"}' in body
        assert 'darklab_intel_requests_total{outcome="cache_hit",provider="shodan"}' in body
        assert 'darklab_intel_requests_total{outcome="error",provider="unknown"}' in body
        assert 'provider="user_supplied_provider"' not in body
        assert 'darklab_db_query_duration_seconds_bucket{le="0.05",operation="history_list"}' in body
        assert re.search(r"darklab_postgres_pool_open_failures_total [1-9]\d*(?:\.0)?", body)
        for error_code in (
            "ai_context_changed",
            "ai_feature_disabled",
            "ai_no_context",
            "ai_run_active",
            "ai_unsupported_variant",
            "not_found",
        ):
            assert f'darklab_ai_requests_total{{error_code="{error_code}",status="rejected",variant="summary"}}' in body
        assert 'darklab_ai_requests_total{error_code="unexpected_ai_error"' not in body
        assert 'darklab_ai_requests_total{error_code="ai_unavailable",status="error",variant="summary"}' in body
        assert 'darklab_history_search_fallbacks_total{reason="missing_fts"}' in body
        assert 'darklab_evidence_package_build_duration_seconds_bucket{le="0.5",outcome="success"}' in body
        assert "darklab_evidence_package_archive_bytes_bucket" in body
        assert 'darklab_evidence_package_skipped_items_total{kind="artifact"}' in body
        assert 'darklab_evidence_package_skipped_items_total{kind="item"}' in body
        assert 'darklab_pty_finished_total{exit_code_class="signal",tool="mtr"}' in body
        assert 'darklab_workspace_evictions_total{reason="manual"}' in body
        assert 'darklab_workflow_executions_finished_total{outcome="completed"}' in body
        assert 'darklab_workflow_step_duration_seconds_bucket{le="2.0",outcome="succeeded"}' in body
        assert 'darklab_workflow_capture_failures_total{reason="required_missing"}' in body
        assert re.search(r"darklab_workflow_cancellations_total [1-9]", body)
        assert 'darklab_workflow_recovery_actions_total{action="recovered"}' in body


class TestMetricsDefinitionDrift:
    def test_metric_names_use_darklab_prefix(self):
        for metric in app_metrics.METRIC_DEFINITIONS:
            assert str(getattr(metric, "_name", "")).startswith("darklab_")

    def test_histograms_have_explicit_buckets(self):
        for histogram in app_metrics.HISTOGRAM_DEFINITIONS:
            buckets = [
                item for item in getattr(histogram, "_upper_bounds", ())
                if item != float("inf")
            ]
            assert buckets, f"{getattr(histogram, '_name', '<unknown>')} should declare buckets"

    def test_labeled_metrics_have_cardinality_policies(self):
        app_metrics.validate_metric_definitions()

        class FakeMetric:
            _name = "darklab_unreviewed_labels"
            _labelnames = ("raw_user_input",)

        with pytest.raises(RuntimeError, match="missing cardinality policy"):
            app_metrics.validate_metric_definitions([FakeMetric()])

    def test_route_label_normalizer_does_not_use_raw_paths(self):
        normalized = app_metrics.normalize_endpoint_label("/history/abc-123/details?q=raw")

        assert "/" not in normalized
        assert "?" not in normalized
        assert re.fullmatch(r"[a-z0-9_.:-]+", normalized)
