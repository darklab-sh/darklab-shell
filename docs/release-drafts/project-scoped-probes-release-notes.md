# Project-scoped probes release notes

Projects can now run a reviewed one-off check without creating or changing an Assessment cycle. This is useful when you need to verify one host or URL, collect fresh evidence, or try a recommended tool without rebuilding its safety flags by hand.

## Plan before you run

Use `probe list` to see the actions available for a Project, `probe plan` to review one exact command, and `probe run` when you're ready to launch it. The same flow is available in the browser terminal, API v1, and the `darklab` CLI.

Every plan shows:

- the confirmed Project target;
- the exact command and policy level;
- request, time, concurrency, and fan-out limits;
- expected evidence and credential use;
- unavailable features or profiles; and
- a digest that must still match when the run starts.

The launch checks the target, Project, permissions, settings, profiles, and digest again. A changed or unlinked target, stale profile, disabled feature, or missing permission stops before a process starts. Successful probes are ordinary Project-linked runs, so they appear in History and can contribute structured evidence to a compatible Assessment check later.

## Faster terminal use

Project slugs work anywhere a probe accepts `--project`, and autocomplete offers active Projects, compatible targets, and enabled HTTP profiles. HTTP profiles can be selected by their saved name or stable id. The browser keeps confirmation and streaming in the tab where the probe started, and valid `probe run` commands remain in History for repeat work.

For example:

```text
probe list --project example-project
probe plan httpx --project example-project https://app.example.test
probe run httpx --project example-project https://app.example.test
```

## Protected HTTP profiles

Curl, HTTPx, Katana, Dalfox parameter discovery, and detection-only SQLmap can use an enabled Project HTTP profile when its saved scope and references are available. The plan shows the public role and request boundary but never prints headers, Secret values, private file paths, or generated private arguments.

Nuclei stays anonymous. Its templates can generate requests beyond a single saved path, so combining Nuclei with an HTTP profile returns an unavailable plan instead of risking credentials outside the reviewed boundary. Safe, standard, and enabled intrusive Nuclei profiles still work without an HTTP profile.

## Managed Nuclei templates

Fresh Compose deployments keep Nuclei templates in a named volume and make one bounded update when that cache is empty. An installed snapshot isn't refreshed in the background. If the download fails, the app still starts and Nuclei plans remain unavailable until the cache is ready.

Set `NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED=false` when container startup must not contact ProjectDiscovery. Startup logs show only fixed skipped, started, succeeded, or failed records; Nuclei's own updater output isn't copied into the container log.

## Safety boundaries

- Targets must already be confirmed and linked to the selected Project.
- Intrusive probes are off by default and still require fresh confirmation when enabled.
- Probe launches never write Assessment state directly.
- ZAP, OAST, Schemathesis, takeover confirmation, intrusive Dalfox payloads, and evidence-only actions remain cycle-specific.
- Protected values stay outside browser storage, public responses, saved commands, logs, metrics, and audit records.

## Learn more

- [Project probes](../../FEATURES.md#project-probes)
- [Configuration](../../CONFIGURATION.md)
- [API and CLI reference](../api.md#project-probes)
