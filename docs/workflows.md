# Workflow Playbooks

Workflows turn repeat command sequences into reusable playbooks. Legacy workflows are simple browser-run lists. Explicit `version: 2` playbooks add typed parameters, branching, bounded scalar captures, durable progress, cancellation, and links back to every normal run they start. `version: 3` adds bounded collection capture and one controlled fan-out step that runs a normal scoped command for each item.

## Using Workflows

Open **Browse all workflows** from the desktop rail, press `Alt+G`, or choose **Workflows** from the mobile menu. Every entry point opens the same workspace. The **Workflows** tab combines built-in, deployment-defined, personal, and active-team definitions in a searchable catalog; use the source menu to narrow it, then choose a row to see its parameters and steps. A workflow row in the desktop rail opens the same catalog with that definition selected. On mobile, choosing a row opens its detail and **Workflows** returns to the catalog.

- Choose parameter values before starting a playbook. Target fields can use active Project targets and recent values. Files and wordlist fields can use active Files entries, while wordlist fields can also use packaged wordlists.
- **Run all** starts a durable execution for a v2 or v3 playbook and switches to the **Executions** tab so its live status is immediately visible. You can close the panel or browser without stopping it.
- The **Executions** tab shows the latest runs for the active personal/team scope, including the current step, elapsed time, branch outcomes, capture names, and linked runs. Collection steps show finished, pending, active, succeeded, failed, and skipped counts plus at most three failure codes; they never show collection items. Attach opens an active run in the terminal; Open shows a finished run in Run Details.
- Cancel stops pending work and signals the active run after confirmation.
- Run Details and History show the playbook and step that produced a run, with shortcuts to sibling step runs and the execution in the Workflows panel.

The in-app editor saves scalar and collection workflows in personal scope or the active team scope. Choose **Collection** on a capture to set its item limit, then enable **Collection fan-out** on a later step to select that capture and configure the failure policy, retries, parallel runs, and failure limit. The editor keeps ordinary definitions at version 2 and saves definitions that use collection behavior as version 3. Team owners and admins can create, edit, and delete shared definitions. Team members with command-run permission can run them.

### Bounded Subdomain Assessment

The built-in **Bounded Subdomain Assessment** playbook discovers no more than 16 unique subdomains from one approved root domain. It uses that private collection to start normal scoped DNSx, HTTPx, Katana, and safe-profile Nuclei runs for each candidate. DNS resolution and HTTP probing use at most four children at once; crawling and scanning use at most two. Each command also carries its own time, rate, retry, or output bounds where the tool supports them.

The playbook uses structured collection capture rather than a temporary Files list. Partial child failures remain visible in the execution counts and bounded failure sample while the remaining candidates continue. The safe Nuclei step excludes callbacks, redirects, automatic updates, intrusive and denial-of-service tags, headless checks, and local code or file protocols.

### Historical Web Surface Triage

The built-in Historical Web Surface Triage playbook starts with passive `gau` archive discovery and saves a bounded candidate list in Files. It then normalizes and restricts the candidates to the domain you supplied (including its subdomains), checks only that scoped set for live HTTP services, and rechecks scope before Katana crawls confirmed live URLs. A final scope pass protects the HTTPx summary too.

This playbook requires Files. Its intermediate candidate, scoped, live, crawl, and summary files are deliberately capped so archive volume can't turn into an unbounded scan. A scope or Files error stops the playbook instead of handing the previous step's unreviewed output to the next tool.

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

Add deployment workflows to `app/conf/workflows.local.yaml`. The app merges them after `app/conf/workflows.yaml` and reloads the files on each catalog request, so edits don't need a restart. A malformed durable entry is skipped as a whole and logged with a bounded warning; other valid entries remain available.

Scalar deployment playbooks use `version: 2` and a stable `id`:

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
| `version` | Yes for durable playbooks | Use `2` for scalar captures or `3` for collection capture and fan-out. An omitted version keeps legacy behavior; other explicit versions are rejected. |
| `id` | Yes for deployment v2/v3 entries | Stable identity that starts with a lowercase letter and then uses only lowercase letters, numbers, and underscores. Saved personal/team workflows receive an id from the app. |
| `title` | Yes | Catalog and execution display name. |
| `description` | No | Short catalog description. |
| `inputs` | No | Typed values available as `{{input_id}}` in commands and notes. |
| `steps` | Yes | Ordered command steps. V2 and v3 steps also have ids, captures, and transitions; v3 steps may add `for_each`. |
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

Starting an execution stores every supplied value, including values marked `sensitive`, in the owner-scoped workflow execution record. Those values enter the app database and its backups. They aren't remembered by the browser or returned by workflow execution status routes, and sensitive inputs appear as `[redacted]` in active-run summaries, History command text, Run Details, logs, metrics, and notifications. Values captured from earlier steps appear there as named placeholders such as `[captured:resolved_ip]`. The raw values are used only while the server validates and starts the command.

This protects app-managed command metadata; it doesn't scrub the command's own output. If a tool prints a sensitive input, that text can still enter its saved output. Don't use workflow inputs for credentials or tokens that shouldn't become workflow history. Put supported command credentials in **Options → Secrets** instead, where the app can inject them without adding them to the workflow definition or execution inputs.

Browser previews substitute known inputs for readability. The server performs the authoritative rendering immediately before each step, quotes every value as one shell scalar, and sends the result through the normal command policy, secret, workspace, target, feature, and runtime-readiness checks. A policy or readiness change can therefore stop a later step even when the preview looked valid at execution start.

## Steps And Transitions

Every v2 or v3 step needs a stable `id` and a `cmd`. Step IDs, like parameter and capture IDs, start with a lowercase letter and then use only lowercase letters, numbers, and underscores. `note` is optional and can use the same declared variables as the command.

`next` can define:

- `success`: destination after exit code 0 and successful required captures.
- `failure`: destination after a nonzero exit or capture failure.
- `codes`: exact exit-code destinations. Quote YAML keys such as `"2"`; exact codes take precedence over `success` and `failure`.

A destination is another step id, `complete`, or `stop`. `complete` finishes the execution successfully. `stop` finishes it as failed. If a successful step has no transition, it advances to the next ordered step or completes when it is last. An unhandled failure stops. Unvisited steps are recorded as skipped.

In the workflow editor, use **+ Route** under **Exact exit codes** to add as many code-specific destinations as the step needs. Exit codes must be whole numbers and unique within that step. Renaming a destination updates the visible routes, reordering keeps routes attached to their stable step IDs, and deleting a destination marks it as missing until you choose another destination or remove the route.

Definitions are rejected when they contain duplicate ids, undeclared variables, capture use on any path that can skip its producer, unknown destinations, unreachable steps, or cycles. Operator files with malformed YAML or an unsupported explicit version are also rejected and logged without including their contents.

## Output Captures

Captures read normalized step output after the app's output filters run and never overwrite session variables. A v2 scalar capture stores one small value for later `{{capture_name}}` use. A v3 collection capture adds `kind: collection` and stores a bounded, deduplicated list for one later `for_each` step. Capture names follow the same identifier rule: start with a lowercase letter, followed only by lowercase letters, numbers, and underscores.

| Source | Extra field | Behavior |
| ------ | ----------- | -------- |
| `first_nonempty_line` | None | Saves the first eligible nonempty line for a scalar, or each eligible line for a collection. |
| `first_line_containing` | `contains` | Saves the first eligible matching line for a scalar, or each eligible matching line for a collection. |
| `entity` | `entity_type` | Saves the first matching structured entity for a scalar, or each matching canonical value for a collection. |
| `json_pointer` | `pointer` | Reads one scalar from the first valid JSON or JSONL object. A collection capture reads the bounded scalar items from one array at that pointer. |

Set `required: true` when a missing capture should fail the step and follow its failure transition. App notices, progress rows, status rows, exit rows, and known output noise don't satisfy line captures. Control characters and oversized values are rejected.

Each step accepts up to eight captures. One scalar or collection item is limited to 2 KiB, scalar values for one execution are limited to 8 KiB total, and all collection captures share a separate 8 KiB ceiling. One collection keeps at most 32 unique items; `item_limit` can lower that bound. Capture names and collection counts appear in execution summaries, but values stay inside the owner-scoped execution record and are omitted from workflow routes, logs, audit details, metric labels, and notifications.

Regular-expression captures, arbitrary expressions, executable transforms, and general loops aren't supported. Existing safe command pipe helpers can shape output before a bounded capture sees it.

## Collection Fan-Out

A v3 `for_each` step names exactly one collection captured on every path leading to it. The command must reference that collection, and it can't also substitute another collection or a scalar value. The server substitutes one item at a time, so every child goes through the normal command policy, target scope, team permission, workspace, runtime readiness, History, and Project-link behavior.

```yaml
- version: 3
  id: probe_discovered_hosts
  title: Probe discovered hosts
  inputs: []
  steps:
    - id: collect
      cmd: "printf '%s\\n' one.example two.example"
      captures:
        - name: hosts
          kind: collection
          source: first_nonempty_line
          item_limit: 16
          required: true
    - id: probe
      cmd: "httpx -u {{hosts}} -silent"
      for_each:
        collection: hosts
        failure_mode: continue
        retries: 1
        max_parallel: 4
        max_failures: 8
```

`failure_mode: fail_fast` stops after the first terminal child failure and therefore always uses `max_failures: 1`. `failure_mode: continue` can keep launching until the saved `max_failures` threshold is reached. `retries` accepts 0 through 3, `max_parallel` accepts 1 through 8, and `max_failures` accepts 0 through 32 for continue mode. Scope, permission, and cancellation failures aren't retried. An optional empty collection completes the fan-out step without starting a child; an empty required collection follows the producer's failure transition.

The private execution record holds the collection. Durable child rows hold only an ordinal, attempt number, linked run id, status, exit code, and bounded error code. Public execution and event responses show totals and outcomes but never include collection items or rendered child commands.

## Durable Execution

Starting a v2 or v3 playbook saves an immutable normalized definition snapshot plus the resolved inputs and current execution variables. Editing or deleting the source workflow doesn't change an execution already in progress or its historical detail.

Completed personal execution history moves with session-token migration and rotation. Migration is blocked while the current identity has an active workflow execution; wait for it to finish or cancel it before trying again. Team-owned execution history stays with the team.

The server claims one scalar step or one bounded collection batch at a time and starts each command through the normal run broker. Every launched command remains a standard History run with its own output, findings, Atlas entities, artifacts, Project links, and exit code. Finalization saves the run before it advances the playbook, and transaction guards prevent a duplicate callback from launching the next step or child twice. Cancellation also stops runs that become active during a transition.

At startup, recovery reconciles all active executions in bounded pages. It retries a scalar step interrupted before run binding, advances a completed linked run from saved output, leaves a live run alone, and fails an execution whose active run disappeared. For collection work, it initializes a claimed parent that stopped before child creation, returns only unbound launching children to pending, reconciles completed linked children, leaves active children alone, applies the saved policy to vanished runs, and fills only the available parallel slots. The initiating team's state, member permission, and personal or team session token are checked again before each new step or child.

Interactive PTY modes aren't workflow steps. A command containing a registry-declared PTY trigger, such as an interactive monitor flag, is rejected before broker launch with a clear execution failure. Run interactive commands directly from the terminal instead.

## Observability

Prometheus exposes bounded workflow counters and durations for execution outcomes, step outcomes, capture failures, cancellations, and recovery actions. These metrics use fixed outcome, reason, and action labels; they don't include workflow names, commands, input values, capture names or values, targets, paths, or output text. Workflow-specific logs, audit details, events, and notifications follow the same value-free rule.

## HTTP Surface

The browser uses owner-scoped routes under `/workflow-executions`:

| Method | Route | Purpose |
| ------ | ----- | ------- |
| `POST` | `/workflow-executions` | Validate inputs, snapshot context, and start a v2 scalar or v3 collection execution. |
| `GET` | `/workflow-executions` | List recent executions for the active personal/team scope, optionally filtered by `workflow_id`. |
| `GET` | `/workflow-executions/<id>` | Read public execution and ordered step state. |
| `GET` | `/workflow-executions/<id>/events` | Replay bounded value-free lifecycle events after an integer cursor. |
| `POST` | `/workflow-executions/<id>/cancel` | Cancel pending steps and signal the active run. |

Create, list, detail, and cancel responses contain only the status fields the Workflows panel and terminal need. They omit the immutable definition snapshot, supplied inputs, execution-local variables, workspace context, session/team ownership fields, actor details, and browser ownership hints. The same public shape is returned to owners, operators, and viewers who can read a team execution.

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
| Collection items | 32 per collection, or a lower `item_limit` |
| Collection bytes | 8 KiB across collection captures |
| Fan-out retries | 3 after the first attempt |
| Parallel children | 8 per fan-out step |
| Terminal child failures | 32 per continue-mode fan-out step |

These are application validation limits, not operator settings. Deployment-file playbooks use the same strict identifier, graph, input, transition, and capture validation, while the title, description, step-count, command, and note limits above apply when saving personal or team definitions through the app.

When a playbook stops, open its row in the **Executions** tab for the failed step and linked run. Common causes are a normal command-policy denial, missing secret or tool, unavailable Files path, required capture miss, command exit failure, changed team permission, revoked initiating token, runtime limit, or an interactive PTY trigger. The saved run remains the source of truth for command output; the execution row explains the orchestration outcome and selected transition. If session-token migration or rotation reports an active workflow execution, let that execution finish or cancel it from this tab before retrying.

## Related Docs

- [schedules.md](schedules.md) - scheduled workflow execution
- [notifications.md](notifications.md) - completion notification delivery
- [api.md](api.md) - workflow API and CLI usage
- [../CONFIGURATION.md](../CONFIGURATION.md) - worker and workflow settings
- [../FEATURES.md](../FEATURES.md) - user-facing workflow behavior
