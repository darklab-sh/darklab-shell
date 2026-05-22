# Storage Scaling

darklab_shell keeps SQLite as the default backend because it works well for local and single-user deployments. Postgres is also supported for heavier deployments. The numbers below explain when storage pressure starts to matter and what to watch when deciding whether SQLite is enough or Postgres is the better fit.

## Baseline

The current baseline comes from one heavy single-user pre-release database after about six weeks of use. It is not a perfect production sample, but it is useful because it includes real scanner runs, saved output previews, FTS search data, snapshots, project records, Atlas entities, and output artifacts.

| Measure | Value |
| ------- | ----- |
| Runs | 12,272 |
| Snapshots | 98 |
| Output artifact rows | 7,819 |
| Findings | 94 |
| Entities | 31 |
| Intel snapshots | 38 |
| SQLite allocated size from `dbstat` | 432.27 MB |
| SQLite file size from page count | 437.77 MB |
| SQLite freelist | 5.50 MB |
| File-backed output artifacts | 190.28 MB |
| Combined SQLite plus output artifacts | 622.55 MB |

That works out to roughly 292 runs per day for this user. The workload is heavier than casual local use, but it is still only one person's data, so multi-user sizing should keep comfortable headroom.

## What Grows

The database is dominated by saved run preview/search data and the FTS index that makes history search fast.

| Object | Allocated size |
| ------ | -------------- |
| `runs` | 214.09 MB |
| `runs_fts_*` total | 197.03 MB |
| `snapshots` | 14.27 MB |
| run indexes | about 5.28 MB |
| Atlas, findings, projects, secrets, recents, and session data | less than 1 MB combined |

The logical payloads tell the same story:

| Payload | Size |
| ------- | ---- |
| `runs.output_search_text` | 106.78 MB |
| `runs.output_preview` | 100.59 MB |
| `snapshots.content` | 14.19 MB |
| `runs.output` | 0.64 MB |
| `entity_intel_snapshots.data_json` | 0.03 MB |

Full output is already mostly outside SQLite because completed runs persist larger transcripts as compressed artifacts. The database still keeps the preview and search text so History, search, restore, and permalink flows stay fast.

darklab_shell also has an optional body store for large text bodies under `data_dir/body-store`. The thresholds default to `0`, which keeps the existing all-inline shape. When enabled, oversized `runs.output_search_text`, `snapshots.content`, and `entity_intel_snapshots.data_json` values are written as compressed files and the database column keeps pointer metadata, byte size, checksum, and a short preview.

## Largest Runs

The largest rows came from scanner output that created multi-megabyte previews/search text:

| Command shape | Largest observed payload |
| ------------- | ------------------------ |
| `nuclei -l ... -j -o ...` | 4.40 MB |
| `cat darklab_findings.txt` | 3.62 MB |
| `ffuf -u ... -w ...` | 3.28 MB |
| `katana -list ... -d 3 ...` | 2.86 MB |

This confirms that scanner JSON, replaying scanner output with `cat`, and high-volume enumerators are the main SQLite pressure points. Normal short commands are not meaningful contributors.

## Per-Run Averages

| Measure | Average |
| ------- | ------- |
| `runs.output` | 0.05 KB |
| `runs.output_search_text` | 8.91 KB |
| File-backed output artifacts | 15.88 KB |
| Findings per run | 0.01 |
| Entities per run | less than 0.01 |

The current workload stores about 36 KB of SQLite data per run and about 16 KB of file-backed output artifacts per run. FTS adds almost as much storage as the searchable text itself.

## Snapshots And Intel

Snapshots matter, but they are not the primary storage driver in the measured database:

| Measure | Value |
| ------- | ----- |
| Snapshot count | 98 |
| Average snapshot content | 148.26 KB |
| Largest snapshot content | 0.85 MB |

Intel payloads are tiny right now. The measured `entity_intel_snapshots.data_json` total is about 36 KB. That could change if future Atlas workflows cache larger raw provider responses, but current normalized provider data is not a storage risk.

## One-Year Projection

These projections assume the same heavy-user behavior continues for a full year and no old runs are pruned. The default `permalink_retention_days` is 365, so this is a reasonable worst-case default for active run and snapshot history.

| Heavy users | SQLite per year | Output artifacts per year | Combined per year |
| ----------- | --------------- | ------------------------- | ----------------- |
| 1 | 3.76 GB | 1.65 GB | 5.41 GB |
| 10 | 37.6 GB | 16.5 GB | 54.1 GB |
| 30 | 112.8 GB | 49.5 GB | 162.3 GB |
| 100 | 376 GB | 165 GB | 541 GB |

For shorter retention windows, scale these numbers roughly by retention days divided by 365. For example, 90 days of this workload is about 25% of the one-year total.

## Recommendations

SQLite is still the right default for local and single-user installs. A heavy single-user deployment can run comfortably on SQLite as long as the operator gives `/data` enough disk and keeps retention intentional.

For small teams, SQLite can still be viable if the deployment is mostly one active operator at a time and the storage path is backed by reliable disk. Watch `/diag` and `/metrics` for growth, especially `runs`, `runs_fts_*`, snapshot size, and artifact bytes.

Postgres becomes the better default for heavy multi-user deployments. The storage numbers alone do not force Postgres at 10 users, but combined write concurrency, backup expectations, query visibility, and operational tooling do. A 30-user heavy deployment should start on Postgres. A 100-user deployment should not rely on SQLite.

## Body Store Offload

The body store is useful when a deployment is healthy but wide text rows are making database storage grow faster than expected. It reduces SQLite row width immediately and keeps Postgres rows narrower too.

| Setting | Stored body | Good starting point |
| ------- | ----------- | ------------------- |
| `runs_search_text_inline_max_bytes` | History search text copied from full output or preview | `262144` (256 KB) for high-volume scanner users |
| `snapshots_inline_max_bytes` | Saved tab snapshot permalink bodies | `524288` (512 KB) when users share very large tabs |
| `intel_payload_inline_max_bytes` | Atlas intel provider JSON payloads | `262144` (256 KB) if provider payloads grow beyond normalized summaries |

Offload alone is usually enough for a local or single-user deployment where `/diag` shows `runs`, snapshots, or intel payload columns growing, but the app has one active writer and simple backup needs. It is also a good first step for small teams that mostly use the app serially.

Postgres is still the better answer when the pain is concurrent writes, shared production backups, query visibility, multiple active users, or multi-worker operational expectations. Body-store offload reduces storage pressure; it does not turn SQLite into a high-concurrency production database.

`runs.output_preview` stays inline because History and run-detail views read it constantly and it is already bounded by `max_output_lines` and `output_preview_max_mb`. Full run output is already handled separately by compressed run-output artifacts.

FTS deserves separate treatment on SQLite. The measured FTS shadow tables consume about 197 MB for about 107 MB of `output_search_text`, so search doubles a large part of the run-output footprint. Postgres does not reproduce SQLite FTS5 directly; it uses trigram indexes that preserve the current command/output lookup behavior.

## Run Output Artifact Format

Full run output artifacts live under `data_dir/run-output` as gzip-compressed JSONL files. New artifacts start with a small header line:

```json
{"v":1,"created":"2026-05-21T00:00:00Z","run_id":"<run-id>"}
```

Every following line is one versioned output event. The event keeps the legacy `text`, `cls`, `tsC`, and `tsE` fields for compatibility, and also includes typed `kind` and `role` fields so newer code can tell semantic output (`warn`, `error`, `notice`) apart from display roles such as prompt echoes, PTY markers, and built-in key/value rows. Rows can also carry optional `signals`, `line_index`, `command_root`, `target`, and `entities` metadata; [ARCHITECTURE.md](../ARCHITECTURE.md#run-output-model) describes the model in more detail.

Older artifacts did not have the header and may contain either legacy JSON rows or plain text rows. darklab_shell does not rewrite those files in place. Readers detect the shape when they open the artifact: headered files skip the first line, headerless JSON rows are upgraded through the compatibility parser, and plain text rows are treated as normal body output.

The inline `runs.output_preview` column stays in the older JSON-array shape so History and run-detail reads remain cheap and stable. The searchable `runs.output_search_text` value is derived from the structured events and includes validated entity canonical values when the run captured them, while the SQLite FTS table itself keeps the same schema.

## Operating Guidance

Use `/diag` Storage breakdown for point-in-time analysis and `/metrics` for trend graphs. On SQLite, the most useful signals are total database size, `runs` allocation, `runs_fts_*` allocation, snapshot bytes, output artifact bytes, largest run payloads, and freelist bytes. On Postgres, watch relation sizes in `/diag`, table row/size gauges in `/metrics`, largest run payloads, and artifact bytes.

If SQLite grows quickly, first check whether retention is set correctly. Then check whether a few scanner runs are creating very large previews or search text. If growth is normal but the deployment has many active users, move the deployment to Postgres instead of trying to tune SQLite indefinitely.

---

## Related Docs

- [Default.md](../.gitlab/merge_request_templates/Default.md) - default GitLab merge request template
- [ARCHITECTURE.md](../ARCHITECTURE.md) - runtime layers, request flow, persistence, security, and app internals
- [CHANGELOG.md](../CHANGELOG.md) - release-by-release changes
- [CONFIGURATION.md](../CONFIGURATION.md) - operator config reference for `app/conf/`, `.env`, Compose, storage, and production tuning
- [CONTRIBUTING.md](../CONTRIBUTING.md) - local setup, test workflow, linting, branch workflow, and merge request guidance
- [CONTRIBUTORS.md](../CONTRIBUTORS.md) - contributor and acknowledgement notes
- [DECISIONS.md](../DECISIONS.md) - architectural rationale, tradeoffs, and implementation-history notes
- [DOC_STANDARDS.md](../DOC_STANDARDS.md) - documentation structure, templates, and review rules
- [FEATURES.md](../FEATURES.md) - full per-feature reference
- [README.md](../README.md) - project overview, quick start, documentation map, and installed tools
- [THEME.md](../THEME.md) - theme registry, token reference, and custom theme authoring
- [TODO.md](../TODO.md) - open follow-ups, research notes, known issues, and future ideas
- [docs/api.md](api.md) - headless API and bundled CLI usage guide
- [docs/external-command-integrations.md](external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/notifications.md](notifications.md) - outbound notification channels, payloads, retries, and setup guide
- [docs/postgres-migration.md](postgres-migration.md) - offline SQLite-to-Postgres cutover helper and validation workflow
- [docs/schedules.md](schedules.md) - scheduled-command cadence, timezone, worker, and audit behavior
- [docs/watchers.md](watchers.md) - change-detection watcher baseline, diff, scheduler, and notification behavior
- [tests/README.md](../tests/README.md) - detailed suite appendix, smoke-test coverage, and focused test commands
- [tests/ui-capture-scenes.md](../tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
