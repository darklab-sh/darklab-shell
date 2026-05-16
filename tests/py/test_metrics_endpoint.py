"""Prometheus `/metrics` route and instrumentation tests."""

import re
import uuid
from unittest import mock

import pytest

import app as shell_app
import config
from services import metrics as app_metrics


def get_client(*, use_forwarded_for=True):
    shell_app.app.config["TESTING"] = True
    client = shell_app.app.test_client()
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

    def test_scrape_includes_runtime_gauge_families(self):
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
        ]
        for name in expected_names:
            assert name in body

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
        app_metrics.record_history_search_fallback("missing_fts")
        app_metrics.record_evidence_package_build(
            "success",
            0.2,
            archive_bytes=2048,
            skipped_artifacts=1,
            skipped_other_items=1,
        )
        app_metrics.record_completed_pty("mtr darklab.sh", 130, 0.5)
        app_metrics.record_workspace_evictions(2, "manual")

        body = _allowed_metrics(get_client(use_forwarded_for=False)).get_data(as_text=True)

        assert 'darklab_rate_limit_rejections_total{route="run.start_brokered_run",scope="global"}' in body
        assert 'darklab_intel_requests_total{outcome="cache_hit",provider="shodan"}' in body
        assert 'darklab_intel_requests_total{outcome="error",provider="unknown"}' in body
        assert 'provider="user_supplied_provider"' not in body
        assert 'darklab_db_query_duration_seconds_bucket{le="0.05",operation="history_list"}' in body
        assert 'darklab_history_search_fallbacks_total{reason="missing_fts"}' in body
        assert 'darklab_evidence_package_build_duration_seconds_bucket{le="0.5",outcome="success"}' in body
        assert "darklab_evidence_package_archive_bytes_bucket" in body
        assert 'darklab_evidence_package_skipped_items_total{kind="artifact"}' in body
        assert 'darklab_evidence_package_skipped_items_total{kind="item"}' in body
        assert 'darklab_pty_finished_total{exit_code_class="signal",tool="mtr"}' in body
        assert 'darklab_workspace_evictions_total{reason="manual"}' in body


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
