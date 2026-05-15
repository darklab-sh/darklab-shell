# Session Entity Atlas Exports

Atlas can export the current session's entity rows as CSV or JSONL. Exports are meant for handoff, offline review, and quick spreadsheet work. They include entity summary fields and lightweight metadata, but they do not include raw provider response bodies.

## Endpoint

```text
GET /atlas/entities/export
```

The route is session-scoped. It only returns entities owned by the current browser session or named session token.

## Query Parameters

| Parameter | Values | Default | Notes |
| --- | --- | --- | --- |
| `format` | `csv`, `jsonl` | `csv` | Controls the file format. |
| `type` | `ip`, `domain`, `url`, `hash`, `cve` | all types | Matches the Atlas entity tabs. |
| `q` | text | empty | Filters by canonical entity value. |
| `project_id` | project id | empty | Limits results to entities linked to that project. |
| `limit` | `1` to `10000` | `10000` | Caps the number of exported rows. |

The Atlas UI sends the same `type`, search text, and project filter that are active in the entity tab when the user clicks **CSV** or **JSONL**.

## Schema

| Field | CSV | JSONL | Description |
| --- | --- | --- | --- |
| `id` | string | string | Atlas entity id. |
| `type` | string | string | Entity type: `ip`, `domain`, `url`, `hash`, or `cve`. |
| `canonical_value` | string | string | Normalized entity value. |
| `first_seen_at` | string | string | First time Atlas saw the entity in this session. |
| `last_seen_at` | string | string | Most recent time Atlas saw the entity in this session. |
| `occurrence_count` | number | number | Total materialized occurrences across saved source runs. |
| `labels` | `; ` separated string | array | Labels attached to the Atlas entity. |
| `notes` | string | string | The entity note body, if one exists. |
| `project_names` | `; ` separated string | array | Projects linked to the entity. |
| `intel_providers_with_data` | `; ` separated string | array | Provider names whose cached Atlas intel snapshot contains usable data. |

CSV uses a header row and semicolon-separated strings for list fields so the file opens cleanly in spreadsheet tools. JSONL emits one JSON object per line and keeps list fields as arrays.

## Redaction

Atlas exports follow the same share/export redaction baseline used elsewhere in the app. They include provider names that have usable cached intel, but they do not include raw intel response bodies.
