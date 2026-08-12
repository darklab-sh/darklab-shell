# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scrape-time Prometheus collectors for runtime state."""

from __future__ import annotations

import os
import logging
import time
from datetime import datetime, timezone
from typing import Any

from prometheus_client.core import GaugeMetricFamily

from config import APP_VERSION, resolve_effective_cfg
from core import database, process
from core.database_backend import (
    DatabaseBackend,
    SQLiteConnection,
    postgres_pool_metrics_snapshot,
)
from services.diagnostics.storage import storage_snapshot
from services.intel.registry import INTEL_PROVIDERS
from services.metrics import build_info_labels
from services.metrics.assessments import (
    ASSESSMENT_PROFILE_KEY_LIMIT,
    assessment_profile_key_label,
)
from services.workspace.files import workspace_root, workspace_settings


log = logging.getLogger("shell")

_REDIS_SCAN_KEY_CAP = 2000
_REDIS_KEY_PATTERNS = (
    ("runstream", "runstream:*"),
    ("proc", "proc:*"),
    ("procmeta", "procmeta:*"),
    ("sessionprocs", "sessionprocs:*"),
    ("teamprocs", "teamprocs:*"),
    ("intel", "intel:*"),
    ("ai_rate", "ai:rate:*"),
    ("ai_assist_inflight", "ai:assist:inflight:*"),
    ("ai_provider_slot", "ai:provider:slot:*"),
    ("ai_provider_legacy", "ai:provider:inflight"),
)
_AI_ASSIST_VARIANTS = frozenset({"summary", "next_commands", "diag_test"})
_AI_ASSIST_STATUSES = frozenset({"queued", "in_progress", "completed", "failed"})


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _db_file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_seconds(now: datetime, value: Any) -> float:
    parsed = _parse_utc(value)
    if parsed is None:
        return 0.0
    return max(0.0, (now - parsed).total_seconds())


def _ai_variant_label(value: Any) -> str:
    variant = str(value or "unknown")
    return variant if variant in _AI_ASSIST_VARIANTS else "unknown"


def _ai_status_label(value: Any) -> str:
    status = str(value or "unknown")
    return status if status in _AI_ASSIST_STATUSES else "unknown"


def _workspace_usage() -> tuple[int, int]:
    settings = workspace_settings(resolve_effective_cfg())
    if not settings.enabled:
        return 0, 0
    root = workspace_root(settings)
    if not root.exists():
        return 0, 0
    bytes_used = 0
    file_count = 0
    try:
        for path in root.rglob("*"):
            try:
                stat = path.lstat()
            except OSError:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            file_count += 1
            bytes_used += stat.st_size
    except OSError:
        return bytes_used, file_count
    return bytes_used, file_count


def _redis_scan_count(client: Any, pattern: str) -> int:
    cursor = 0
    count = 0
    while True:
        cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
        count += len(keys or [])
        if count >= _REDIS_SCAN_KEY_CAP:
            return _REDIS_SCAN_KEY_CAP
        if cursor in (0, "0"):
            return count


def _redis_stream_length_sample(client: Any, prefix: str) -> int:
    cursor = 0
    total = 0
    sampled = 0
    pattern = f"{prefix}:*"
    while True:
        cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
        for key in keys or []:
            try:
                total += _safe_int(client.xlen(key))
                sampled += 1
            except Exception:
                continue
            if sampled >= _REDIS_SCAN_KEY_CAP:
                return total
        if cursor in (0, "0"):
            return total


def _secret_envs_with_rows(conn: SQLiteConnection) -> set[str]:
    try:
        rows = conn.execute("SELECT name, consumer_envs FROM secrets").fetchall()
    except Exception:
        return set()
    envs = set()
    for row in rows:
        envs.add(str(row["name"]))
        raw_value = row["consumer_envs"] or ""
        if isinstance(raw_value, (list, tuple)):
            tokens = [str(item) for item in raw_value]
        else:
            raw = str(raw_value)
            tokens = raw.replace("[", "").replace("]", "").replace('"', "").split(",")
        for token in tokens:
            token = token.strip()
            if token:
                envs.add(token)
    return envs


def _assessment_cycle_samples(rows: list[Any]) -> list[tuple[str, str, int]]:
    normalized = [
        (
            "team" if str(row["owner_kind"] or "") == "team" else "personal",
            assessment_profile_key_label(row["profile_key"]),
            _safe_int(row["count"]),
        )
        for row in rows
    ]
    profile_keys = {profile for _owner, profile, _count in normalized}
    non_other = sorted(profile_keys - {"other"})
    needs_other = "other" in profile_keys or len(non_other) > ASSESSMENT_PROFILE_KEY_LIMIT
    reserved = int(needs_other)
    allowed = set(non_other[: max(0, ASSESSMENT_PROFILE_KEY_LIMIT - reserved)])
    if needs_other:
        allowed.add("other")
    samples: dict[tuple[str, str], int] = {}
    for owner, profile, count in normalized:
        label = profile if profile in allowed else "other"
        samples[(owner, label)] = samples.get((owner, label), 0) + count
    return [
        (owner, profile, count)
        for (owner, profile), count in sorted(samples.items())
    ]


class RuntimeStateCollector:
    """Collects gauges that should be sampled only when Prometheus scrapes."""

    def collect(self):
        yield from self._collect_build()
        yield from self._collect_broker()
        health = GaugeMetricFamily("darklab_health_status", "Component health status, 1 is healthy.", labels=("component",))
        yield from self._collect_database(health)
        yield from self._collect_postgres_pool()
        yield from self._collect_redis(health)
        yield health
        yield from self._collect_intel_cache()
        yield from self._collect_workspace()

    def _collect_build(self):
        build = GaugeMetricFamily(
            "darklab_build_info",
            "Application build and runtime information.",
            labels=("version", "git_sha", "python_version"),
        )
        labels = build_info_labels()
        build.add_metric([labels["version"], labels["git_sha"], labels["python_version"]], 1)
        yield build

        start = GaugeMetricFamily(
            "darklab_app_start_time_seconds",
            "Unix timestamp when the app process started.",
        )
        start.add_metric([], _safe_int(os.environ.get("DARKLAB_APP_START_TIME_SECONDS"), int(time.time())))
        yield start

        version = GaugeMetricFamily(
            "darklab_version_info",
            "Application version marker.",
            labels=("version",),
        )
        version.add_metric([str(APP_VERSION)], 1)
        yield version

    def _collect_broker(self):
        broker = GaugeMetricFamily(
            "darklab_broker_mode_info",
            "Run broker backend mode marker.",
            labels=("mode",),
        )
        try:
            from services.runs.broker import broker_mode  # noqa: PLC0415
            mode = broker_mode()
        except Exception:
            mode = "unknown"
        broker.add_metric([mode], 1)
        yield broker

    def _collect_postgres_pool(self):
        if database.DB_BACKEND != DatabaseBackend.POSTGRES:
            return
        config_metric = GaugeMetricFamily(
            "darklab_postgres_pool_config",
            "Postgres pool configured values by setting.",
            labels=("setting",),
        )
        connections = GaugeMetricFamily(
            "darklab_postgres_pool_connections",
            "Postgres pool connection state gauges.",
            labels=("state",),
        )
        try:
            snapshot = postgres_pool_metrics_snapshot(resolve_effective_cfg())
        except Exception:
            log.debug("METRICS_POSTGRES_POOL_COLLECT_FAILED", exc_info=True)
            snapshot = {}

        for setting, key in (
            ("min", "configured_min"),
            ("max", "configured_max"),
            ("jit_enabled", "jit_enabled"),
        ):
            if key in snapshot:
                config_metric.add_metric([setting], _safe_int(snapshot.get(key)))
        for state in ("open", "size", "available", "used", "waiting"):
            if state in snapshot:
                connections.add_metric([state], _safe_int(snapshot.get(state)))
        yield config_metric
        yield connections

    def _collect_database(self, health: GaugeMetricFamily):
        backend_info = GaugeMetricFamily(
            "darklab_db_backend_info",
            "Database backend marker.",
            labels=("backend",),
        )
        backend_info.add_metric([database.DB_BACKEND.value], 1)
        yield backend_info

        db_size = GaugeMetricFamily("darklab_db_size_bytes", "Database storage size in bytes.")

        wal_size = GaugeMetricFamily("darklab_db_wal_size_bytes", "SQLite WAL file size in bytes; 0 for Postgres.")
        wal_size.add_metric(
            [],
            0 if database.DB_BACKEND == DatabaseBackend.POSTGRES else _db_file_size(f"{database.DB_PATH}-wal"),
        )
        yield wal_size

        reclaimable = GaugeMetricFamily("darklab_db_reclaimable_bytes", "Database reclaimable bytes when available.")
        table_rows = GaugeMetricFamily("darklab_db_table_rows", "Database table row counts.", labels=("table",))
        table_bytes = GaugeMetricFamily(
            "darklab_db_table_allocated_bytes",
            "Database allocated bytes by object.",
            labels=("table",),
        )
        fts_orphans = GaugeMetricFamily(
            "darklab_db_fts_orphans",
            "SQLite FTS rows without matching runs rows; 0 for Postgres.",
        )
        atlas_entities = GaugeMetricFamily("darklab_atlas_entities", "Atlas entity counts by type.", labels=("type",))
        findings = GaugeMetricFamily(
            "darklab_findings_total",
            "Finding counts by severity and status.",
            labels=("severity", "status"),
        )
        snapshots = GaugeMetricFamily("darklab_snapshots_total", "Total saved snapshots.")
        intel_missing = GaugeMetricFamily(
            "darklab_intel_provider_secret_missing",
            "1 when a registered keyed provider has no saved secret in any session.",
            labels=("provider",),
        )
        ai_assists = GaugeMetricFamily(
            "darklab_ai_assist_rows",
            "Durable AI assist rows by bounded variant and status.",
            labels=("variant", "status"),
        )
        ai_queued_age = GaugeMetricFamily(
            "darklab_ai_assist_oldest_queued_age_seconds",
            "Age in seconds of the oldest queued AI assist by bounded variant.",
            labels=("variant",),
        )
        ai_in_progress_age = GaugeMetricFamily(
            "darklab_ai_assist_oldest_in_progress_age_seconds",
            "Age in seconds of the oldest in-progress AI assist by bounded variant.",
            labels=("variant",),
        )
        ai_heartbeat_age = GaugeMetricFamily(
            "darklab_ai_assist_oldest_heartbeat_age_seconds",
            "Age in seconds of the oldest AI assist heartbeat by bounded variant.",
            labels=("variant",),
        )
        assessment_cycles = GaugeMetricFamily(
            "darklab_assessment_active_cycles",
            "Active Project assessment cycles by bounded owner kind and profile key.",
            labels=("owner_kind", "profile_key"),
        )

        try:
            with database.db_connect() as conn:
                conn.execute("SELECT 1")
                health.add_metric(["db"], 1)
                snapshot = storage_snapshot(conn, database.DB_BACKEND, db_path=database.DB_PATH)
                db_size.add_metric([], _safe_int(snapshot.get("size")))
                reclaimable.add_metric([], _safe_int(snapshot.get("reclaimable_size")))
                allocated = snapshot.get("allocated_by_object") or {}
                for item in snapshot.get("tables") or []:
                    name = str(item.get("name") or "")
                    if not name:
                        continue
                    table_rows.add_metric([name], _safe_int(item.get("rows")))
                    if name in allocated:
                        table_bytes.add_metric([name], _safe_int(allocated[name]))
                fts_orphans.add_metric([], _safe_int(snapshot.get("fts_orphans")))
                self._add_atlas(conn, atlas_entities)
                self._add_findings(conn, findings)
                self._add_snapshots(conn, snapshots)
                self._add_intel_missing(conn, intel_missing)
                self._add_ai_assists(conn, ai_assists, ai_queued_age, ai_in_progress_age, ai_heartbeat_age)
                self._add_assessment_cycles(conn, assessment_cycles)
        except Exception:
            log.warning(
                "METRICS_DB_COLLECT_FAILED",
                exc_info=True,
                extra={"database_backend": database.DB_BACKEND.value},
            )
            health.add_metric(["db"], 0)
            db_size.add_metric([], 0)
            reclaimable.add_metric([], 0)
            fts_orphans.add_metric([], 0)
            snapshots.add_metric([], 0)
        yield db_size
        yield reclaimable
        yield table_rows
        yield table_bytes
        yield fts_orphans
        yield atlas_entities
        yield findings
        yield snapshots
        yield intel_missing
        yield ai_assists
        yield ai_queued_age
        yield ai_in_progress_age
        yield ai_heartbeat_age
        yield assessment_cycles

    def _add_atlas(self, conn: SQLiteConnection, metric: GaugeMetricFamily) -> None:
        try:
            rows = conn.execute("SELECT type, COUNT(*) AS count FROM entities GROUP BY type").fetchall()
        except Exception:
            rows = []
        for row in rows:
            metric.add_metric([str(row["type"] or "unknown")], _safe_int(row["count"]))

    def _add_findings(self, conn: SQLiteConnection, metric: GaugeMetricFamily) -> None:
        try:
            rows = conn.execute(
                "SELECT COALESCE(NULLIF(severity, ''), 'unknown') AS severity, "
                "COALESCE(NULLIF(status, ''), 'new') AS status, COUNT(*) AS count "
                "FROM findings GROUP BY severity, status"
            ).fetchall()
        except Exception:
            rows = []
        for row in rows:
            metric.add_metric([str(row["severity"]), str(row["status"])], _safe_int(row["count"]))

    def _add_snapshots(self, conn: SQLiteConnection, metric: GaugeMetricFamily) -> None:
        try:
            row = conn.execute("SELECT COUNT(*) AS count FROM snapshots").fetchone()
            metric.add_metric([], _safe_int(row["count"] if row else 0))
        except Exception:
            metric.add_metric([], 0)

    def _add_intel_missing(self, conn: SQLiteConnection, metric: GaugeMetricFamily) -> None:
        configured_envs = _secret_envs_with_rows(conn)
        for provider in INTEL_PROVIDERS.values():
            secret_env = str(provider.secret_env or "")
            if not secret_env:
                continue
            metric.add_metric([provider.id], 0 if secret_env in configured_envs else 1)

    def _add_assessment_cycles(
        self,
        conn: SQLiteConnection,
        metric: GaugeMetricFamily,
    ) -> None:
        try:
            rows = conn.execute(
                "SELECT CASE WHEN COALESCE(team_id, '') != '' THEN 'team' "
                "ELSE 'personal' END AS owner_kind, profile_key, COUNT(*) AS count "
                "FROM project_assessments WHERE status = 'active' "
                "GROUP BY owner_kind, profile_key"
            ).fetchall()
        except Exception:
            log.debug("METRICS_ASSESSMENT_CYCLES_COLLECT_FAILED", exc_info=True)
            return
        for owner, profile, count in _assessment_cycle_samples(list(rows)):
            metric.add_metric([owner, profile], count)

    def _add_ai_assists(
        self,
        conn: SQLiteConnection,
        assists: GaugeMetricFamily,
        queued_age: GaugeMetricFamily,
        in_progress_age: GaugeMetricFamily,
        heartbeat_age: GaugeMetricFamily,
    ) -> None:
        try:
            rows = conn.execute(
                "SELECT COALESCE(NULLIF(variant, ''), 'unknown') AS variant, "
                "COALESCE(NULLIF(status, ''), 'unknown') AS status, COUNT(*) AS count "
                "FROM ai_run_assists GROUP BY variant, status"
            ).fetchall()
            queued_rows = conn.execute(
                "SELECT COALESCE(NULLIF(variant, ''), 'unknown') AS variant, MIN(created_at) AS oldest_at "
                "FROM ai_run_assists WHERE status = 'queued' GROUP BY variant"
            ).fetchall()
            progress_rows = conn.execute(
                "SELECT COALESCE(NULLIF(variant, ''), 'unknown') AS variant, "
                "MIN(COALESCE(claimed_at, created_at)) AS oldest_at, "
                "MIN(COALESCE(heartbeat_at, claimed_at, created_at)) AS oldest_heartbeat_at "
                "FROM ai_run_assists WHERE status = 'in_progress' GROUP BY variant"
            ).fetchall()
        except Exception:
            log.debug("METRICS_AI_ASSIST_COLLECT_FAILED", exc_info=True)
            return

        now = datetime.now(timezone.utc)
        for row in rows:
            assists.add_metric(
                [_ai_variant_label(row["variant"]), _ai_status_label(row["status"])],
                _safe_int(row["count"]),
            )
        for row in queued_rows:
            queued_age.add_metric([_ai_variant_label(row["variant"])], _age_seconds(now, row["oldest_at"]))
        for row in progress_rows:
            variant = _ai_variant_label(row["variant"])
            in_progress_age.add_metric([variant], _age_seconds(now, row["oldest_at"]))
            heartbeat_age.add_metric([variant], _age_seconds(now, row["oldest_heartbeat_at"]))

    def _collect_redis(self, health: GaugeMetricFamily):
        redis_up = GaugeMetricFamily("darklab_redis_up", "Redis health, 1 is reachable.")
        redis_ping = GaugeMetricFamily("darklab_redis_ping_seconds", "Redis ping latency in seconds.")
        redis_keys = GaugeMetricFamily("darklab_redis_keys", "Redis key count by known prefix.", labels=("prefix",))
        redis_stream = GaugeMetricFamily(
            "darklab_redis_stream_length",
            "Redis stream lengths by known prefix.",
            labels=("prefix",),
        )
        redis_clients = GaugeMetricFamily("darklab_redis_connected_clients", "Redis connected client count.")
        client = process.redis_client
        if not client:
            redis_up.add_metric([], 0)
            redis_ping.add_metric([], 0)
            redis_clients.add_metric([], 0)
            health.add_metric(["redis"], 1)
            yield redis_up
            yield redis_ping
            yield redis_keys
            yield redis_stream
            yield redis_clients
            return

        try:
            start = time.perf_counter()
            client.ping()
            ping_seconds = time.perf_counter() - start
            redis_up.add_metric([], 1)
            redis_ping.add_metric([], ping_seconds)
            health.add_metric(["redis"], 1)
            for prefix, pattern in _REDIS_KEY_PATTERNS:
                redis_keys.add_metric([prefix], _redis_scan_count(client, pattern))
                if prefix == "runstream":
                    redis_stream.add_metric([prefix], _redis_stream_length_sample(client, prefix))
            try:
                info = client.info()
                redis_clients.add_metric([], _safe_int(info.get("connected_clients") if isinstance(info, dict) else 0))
            except Exception:
                redis_clients.add_metric([], 0)
        except Exception:
            log.warning("METRICS_REDIS_COLLECT_FAILED", exc_info=True)
            redis_up.add_metric([], 0)
            redis_ping.add_metric([], 0)
            redis_clients.add_metric([], 0)
            health.add_metric(["redis"], 0)
        yield redis_up
        yield redis_ping
        yield redis_keys
        yield redis_stream
        yield redis_clients

    def _collect_intel_cache(self):
        cache_entries = GaugeMetricFamily(
            "darklab_intel_cache_entries",
            "App-native intel response cache entries by provider.",
            labels=("provider",),
        )
        quota_entries = GaugeMetricFamily(
            "darklab_intel_quota_cache_entries",
            "App-native intel quota-exhaustion cache entries by provider.",
            labels=("provider",),
        )
        client = process.redis_client
        if client:
            for provider_id in INTEL_PROVIDERS:
                cache_entries.add_metric([provider_id], _redis_scan_count(client, f"intel:cache:{provider_id}:*"))
                quota_entries.add_metric([provider_id], _redis_scan_count(client, f"intel:quota:*:{provider_id}"))
            yield cache_entries
            yield quota_entries
            return

        try:
            from services.intel import cache as intel_cache  # noqa: PLC0415
            now = time.time()
            counts = {provider_id: {"cache": 0, "quota": 0} for provider_id in INTEL_PROVIDERS}
            with intel_cache._MEMORY_LOCK:  # noqa: SLF001
                for key, (expires_at, _) in list(intel_cache._MEMORY_CACHE.items()):  # noqa: SLF001
                    if expires_at <= now:
                        continue
                    parts = str(key).split(":")
                    if len(parts) >= 4 and parts[0:2] == ["intel", "cache"] and parts[2] in counts:
                        counts[parts[2]]["cache"] += 1
                    elif len(parts) >= 4 and parts[0:2] == ["intel", "quota"] and parts[-1] in counts:
                        counts[parts[-1]]["quota"] += 1
        except Exception:
            log.debug("METRICS_INTEL_CACHE_COLLECT_FAILED", exc_info=True)
            counts = {provider_id: {"cache": 0, "quota": 0} for provider_id in INTEL_PROVIDERS}
        for provider_id, provider_counts in counts.items():
            cache_entries.add_metric([provider_id], provider_counts["cache"])
            quota_entries.add_metric([provider_id], provider_counts["quota"])
        yield cache_entries
        yield quota_entries

    def _collect_workspace(self):
        bytes_used, file_count = _workspace_usage()
        quota = _safe_int(resolve_effective_cfg().get("workspace_quota_mb"), 50) * 1024 * 1024
        workspace_bytes = GaugeMetricFamily("darklab_workspace_bytes_used", "Workspace bytes used across sessions.")
        workspace_quota = GaugeMetricFamily("darklab_workspace_quota_bytes", "Configured per-session workspace quota in bytes.")
        workspace_files = GaugeMetricFamily("darklab_workspace_files", "Workspace file count across sessions.")
        workspace_bytes.add_metric([], bytes_used)
        workspace_quota.add_metric([], quota)
        workspace_files.add_metric([], file_count)
        yield workspace_bytes
        yield workspace_quota
        yield workspace_files
