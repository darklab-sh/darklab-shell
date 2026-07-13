# Workflow Playbooks

Workflows turn repeat command sequences into reusable playbooks. Legacy workflows are simple browser-run lists. Explicit `version: 2` playbooks add typed parameters, branching, bounded output captures, durable progress, cancellation, and links back to every normal run they start.

## Using Workflows

Open **Browse all workflows** from the desktop rail, press `Alt+G`, or choose **Workflows** from the mobile menu. Every entry point opens the same workspace. The **Workflows** tab combines built-in, deployment-defined, personal, and active-team definitions in a searchable catalog; use the source menu to narrow it, then choose a row to see its parameters and steps. A workflow row in the desktop rail opens the same catalog with that definition selected. On mobile, choosing a row opens its detail and **Workflows** returns to the catalog.

- Choose parameter values before starting a playbook. Target fields can use active Project targets and recent values. Files and wordlist fields can use active Files entries, while wordlist fields can also use packaged wordlists.
- **Run all** starts a durable execution for a v2 playbook and switches to the **Executions** tab so its live status is immediately visible. You can close the panel or browser without stopping it.
- The **Executions** tab shows the latest runs for the active personal/team scope, including the current step, elapsed time, branch outcomes, capture names, and linked runs. Attach opens an active run in the terminal; Open shows a finished run in Run Details.
- Cancel stops pending work and signals the active run after confirmation.
- Run Details and History show the playbook and step that produced a run, with shortcuts to sibling step runs and the execution in the Workflows panel.

The in-app editor saves personal workflows in personal scope and shared workflows in active team scope. Team owners and admins can create, edit, and delete shared definitions. Team members with command-run permission can run them.

## Terminal Commands

The `workflow` command exposes the same catalog and durable execution state:

```text
workflow list
workflow show resolve_and_scan
workflow run resolve_and_scan --target example.com --ports 80,443
workflow runs
workflow status wfx_...
workflow cancel wfx_...
```

Starting a playbook with **Run all** keeps its progress in the Workflows panel and doesn't add a one-step snapshot to the active terminal. Starting it with `workflow run` prints the durable execution id and a matching `workflow status` command so the terminal response stays useful without pretending the initial step is still current.

Missing required inputs are prompted in the transcript. Autocomplete suggests workflow names, input flags, recent execution ids, compatible targets, Files paths, and wordlists. Sensitive input values aren't included in the start summary.

## Definition Files

Add deployment workflows to `app/conf/workflows.local.yaml`. The app merges them after `app/conf/workflows.yaml` and reloads the files on each catalog request, so edits don't need a restart. A malformed v2 entry is skipped as a whole and logged with a bounded warning; other valid entries remain available.

New deployment playbooks use `version: 2` and a stable `id`:

```yaml
- version: 2
  id: resolve_and_scan
  title: Resolve and scan
  description: Resolve a domain, then scan the selected ports.
  inputs:
    - id: target
      label: Target
      type: domain
      required: true
      placeholder: example.com
    - id: ports
      label: Ports
      type: port_set
      default: "80,443"
  steps:
    - id: resolve
      cmd: "dig +short A {{target}}"
      note: Save the first returned address for the scan.
      captures:
        - name: resolved_ip
          source: first_nonempty_line
          required: true
      next:
        success: scan
        failure: stop
    - id: scan
      cmd: "nmap -sV -p {{ports}} {{resolved_ip}}"
      next:
        codes:
          "1": complete
        success: complete
        failure: stop
```

Top-level fields:

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `version` | Yes for v2 | Use `2` for durable playbook behavior. An omitted version keeps legacy behavior; other explicit versions are rejected. |
| `id` | Yes for deployment v2 entries | Stable identity that starts with a lowercase letter and then uses only lowercase letters, numbers, and underscores. Saved personal/team workflows receive an id from the app. |
| `title` | Yes | Catalog and execution display name. |
| `description` | No | Short catalog description. |
| `inputs` | No | Typed values available as `{{input_id}}` in commands and notes. |
| `steps` | Yes | Ordered command steps. V2 steps also have ids, captures, and transitions. |
| `feature_required` | No | One feature name or a list, such as `workspace`; the catalog hides the workflow when the feature is unavailable. |

## Parameters

Each parameter supports `id`, `label`, `type`, `required`, `default`, `placeholder`, `help`, and `sensitive`. Parameter IDs start with a lowercase letter and then use only lowercase letters, numbers, and underscores. They can't collide with capture names.

| Type | Accepted value |
| ---- | -------------- |
| `text` | Bounded plain text. |
| `target` | IP address, CIDR, or domain. |
| `domain` | Canonical lowercase domain. |
| `host` | IP address or domain. |
| `url` | An `http` or `https` URL. |
| `port` | One port from 1 through 65535. |
| `port_set` | Comma-separated ports and bounded ranges, such as `80,443,8000-8010`. |
| `workspace_path` | Relative path inside the active Files workspace. |
| `wordlist` | Relative Files path or packaged path under `/usr/share/wordlists/`. |

`path` remains a compatibility alias for `workspace_path`.

The browser remembers non-sensitive values by personal/team scope and workflow id. Values removed from a definition are cleared from the saved form state. Parameters marked `sensitive: true` use masked controls, stay redacted in command previews, run only through `Run all`, and aren't written to browser storage. In the terminal, omit sensitive flags from `workflow run`; the app prompts without echoing the answer and rejects inline values with a redacted command echo.

Starting an execution stores every supplied value, including values marked `sensitive`, in the owner-scoped workflow execution record. Those values enter the app database and its backups even though they aren't remembered by the browser or shown in workflow logs and summaries. Don't use workflow inputs for credentials or tokens that shouldn't become workflow history. Put supported command credentials in **Options → Secrets** instead, where the app can inject them without adding them to the workflow definition or execution inputs.

Browser previews substitute known inputs for readability. The server performs the authoritative rendering immediately before each step, quotes every value as one shell scalar, and sends the result through the normal command policy, secret, workspace, target, feature, and runtime-readiness checks. A policy or readiness change can therefore stop a later step even when the preview looked valid at execution start.

## Steps And Transitions

Every v2 step needs a stable `id` and a `cmd`. Step IDs, like parameter and capture IDs, start with a lowercase letter and then use only lowercase letters, numbers, and underscores. `note` is optional and can use the same declared variables as the command.

`next` can define:

- `success`: destination after exit code 0 and successful required captures.
- `failure`: destination after a nonzero exit or capture failure.
- `codes`: exact exit-code destinations. Quote YAML keys such as `"2"`; exact codes take precedence over `success` and `failure`.

A destination is another step id, `complete`, or `stop`. `complete` finishes the execution successfully. `stop` finishes it as failed. If a successful step has no transition, it advances to the next ordered step or completes when it is last. An unhandled failure stops. Unvisited steps are recorded as skipped.

Definitions are rejected when they contain duplicate ids, undeclared variables, capture use on any path that can skip its producer, unknown destinations, unreachable steps, or cycles. Operator files with malformed YAML or an unsupported explicit version are also rejected and logged without including their contents.

## Output Captures

Captures read normalized step output after the app's output filters run. They store one small scalar for later `{{capture_name}}` use and never overwrite session variables. Capture names follow the same identifier rule: start with a lowercase letter, followed only by lowercase letters, numbers, and underscores.

| Source | Extra field | Behavior |
| ------ | ----------- | -------- |
| `first_nonempty_line` | None | Saves the first eligible nonempty output line. |
| `first_line_containing` | `contains` | Saves the first eligible line containing the literal text. |
| `entity` | `entity_type` | Saves the first matching structured entity's canonical value. |
| `json_pointer` | `pointer` | Reads one scalar from the first valid JSON or JSONL object using JSON Pointer. |

Set `required: true` when a missing capture should fail the step and follow its failure transition. App notices, progress rows, status rows, exit rows, and known output noise don't satisfy line captures. Control characters and oversized values are rejected.

Each step accepts up to eight captures. One value is limited to 2 KiB, and capture values for one execution are limited to 8 KiB total. Capture names appear in execution summaries, but values stay inside the owner-scoped execution record and are omitted from workflow logs, audit details, metric labels, and notifications.

Regular-expression captures, arbitrary expressions, executable transforms, loops, retries, and parallel branches aren't supported. Existing safe command pipe helpers can shape output before a bounded capture sees it.

## Durable Execution

Starting a v2 playbook saves an immutable normalized definition snapshot plus the resolved inputs and current execution variables. Editing or deleting the source workflow doesn't change an execution already in progress or its historical detail.

Completed personal execution history moves with session-token migration and rotation. Migration is blocked while the current identity has an active workflow execution; wait for it to finish or cancel it before trying again. Team-owned execution history stays with the team.

The server claims one step at a time and starts it through the normal run broker. Each step remains a standard History run with its own output, findings, Atlas entities, artifacts, Project links, and exit code. Finalization saves the run before it advances the playbook, and transaction guards prevent a duplicate callback from launching the next step twice. Cancellation also stops a run that becomes active during the transition between steps.

At startup, recovery reconciles all active executions in bounded pages. It retries a step interrupted before run binding, advances a completed linked run from saved output, leaves a live run alone, and fails an execution whose active run disappeared. The initiating team's state, member permission, and personal or team session token are checked again before each new step.

Interactive PTY modes aren't workflow steps. A command containing a registry-declared PTY trigger, such as an interactive monitor flag, is rejected before broker launch with a clear execution failure. Run interactive commands directly from the terminal instead.

## Observability

Prometheus exposes bounded workflow counters and durations for execution outcomes, step outcomes, capture failures, cancellations, and recovery actions. These metrics use fixed outcome, reason, and action labels; they don't include workflow names, commands, input values, capture names or values, targets, paths, or output text. Workflow-specific logs, audit details, events, and notifications follow the same value-free rule.

## HTTP Surface

The browser uses owner-scoped routes under `/workflow-executions`:

| Method | Route | Purpose |
| ------ | ----- | ------- |
| `POST` | `/workflow-executions` | Validate inputs, snapshot context, and start a v2 execution. |
| `GET` | `/workflow-executions` | List recent executions for the active personal/team scope, optionally filtered by `workflow_id`. |
| `GET` | `/workflow-executions/<id>` | Read the definition snapshot and ordered step state. |
| `GET` | `/workflow-executions/<id>/events` | Replay bounded value-free lifecycle events after an integer cursor. |
| `POST` | `/workflow-executions/<id>/cancel` | Cancel pending steps and signal the active run. |

The event feed includes `started`, `step_started`, `step_completed`, `capture_saved`, `completed`, `failed`, and `canceled` events. Its payloads contain bounded ids, status, exit code, transition, timestamp, run links, and capture names, but not commands or input/capture values.

These browser routes follow the active personal/team session scope. They aren't part of the token-authenticated `/api/v1` surface.

## Limits And Troubleshooting

Two settings bound server-owned work:

| Setting | Default | Meaning |
| ------- | ------- | ------- |
| `workflow_active_execution_limit` | `3` | Active executions allowed for one personal session or team. |
| `workflow_execution_max_runtime_seconds` | `14400` | Total execution lifetime before another step is refused. |

Saved personal and team definitions also have fixed validation bounds:

| Item | Fixed limit |
| ---- | ----------- |
| Workflow title | 120 characters |
| Workflow description | 1,000 characters |
| Parameters | 24 per workflow |
| Steps | 40 per workflow |
| Step command | 1,200 characters |
| Step note | 1,000 characters |
| Supplied input value | 4,096 characters |

These are application validation limits, not operator settings. Deployment-file playbooks use the same strict identifier, graph, input, transition, and capture validation, while the title, description, step-count, command, and note limits above apply when saving personal or team definitions through the app.

When a playbook stops, open its row in the **Executions** tab for the failed step and linked run. Common causes are a normal command-policy denial, missing secret or tool, unavailable Files path, required capture miss, command exit failure, changed team permission, revoked initiating token, runtime limit, or an interactive PTY trigger. The saved run remains the source of truth for command output; the execution row explains the orchestration outcome and selected transition. If session-token migration or rotation reports an active workflow execution, let that execution finish or cancel it from this tab before retrying.

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
- [TODO.md](../TODO.md) - backlog items, research notes, and known issues
- [docs/ai-privacy.md](ai-privacy.md) - AI assist privacy posture, provider boundaries, redaction, storage, and logging
- [docs/api.md](api.md) - headless API and bundled CLI usage guide
- [docs/external-command-integrations.md](external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/notifications.md](notifications.md) - outbound notification channels, payloads, retries, and setup guide
- [docs/postgres-migration.md](postgres-migration.md) - offline SQLite-to-Postgres cutover and Postgres major-version export/import workflow
- [docs/schedules.md](schedules.md) - scheduled-command cadence, timezone, worker, and audit behavior
- [docs/storage-scaling.md](storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [docs/watchers.md](watchers.md) - change-detection watcher baseline, diff, scheduler, and notification behavior
- [tests/README.md](../tests/README.md) - detailed suite appendix, smoke-test coverage, and focused test commands
- [tests/ui-capture-scenes.md](../tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
