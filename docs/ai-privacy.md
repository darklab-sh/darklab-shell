# AI Privacy Posture

darklab_shell has optional AI assists for run summaries and next-command drafts. It is off by default. When enabled, it is designed for self-hosted providers first, such as the bundled llama.cpp sidecar or another OpenAI-compatible endpoint on private infrastructure.

## What can be sent

AI assists are built from completed run context, not live terminal input. The context includes the command, exit code, runtime, findings, warnings, extracted entities, project targets, structured output summaries, and a bounded transcript tail. When `AI_ALLOW_FULL_OUTPUT` is enabled, the app can read the complete persisted output as source material for those bounded sections. It still sends compact prompt sections, not an unbounded full transcript.

Before provider calls, the app applies the same share/export redaction rules used for snapshots. Prompt boundary tokens are stripped from source text so command output cannot break out of the untrusted-output section. Suggestion validation treats model output as untrusted data, runs draft commands through normal command policy checks, and rejects network suggestions whose targets are not already present in the source run or active project context. The UI offers Copy actions for accepted suggestions. When the run-suggestions feature flag is enabled, accepted suggestions also get a Run action that submits through the normal composer path, so command policy is checked again before anything starts.

## What is stored

AI assist rows are stored separately from terminal output. They do not become transcript lines, findings, Atlas source text, search text, or comparison input. The storage tables keep assist status, model, prompt version, context hash, bounded payload data, redaction counts, and suggestion validation audit rows. While a provider request is running, the row can also hold short-lived progress metadata such as elapsed time, output characters seen, and token counts when the provider reports usage. Completed and failed assists clear that progress field.

Stored raw model payloads are size-capped for troubleshooting, but they are the provider's raw response text and are not redacted again after the provider returns them. Use a provider you trust with the redacted prompt context, and treat raw model payloads as sensitive operational data. Retention follows the parent run: when a run is deleted or expires through normal retention cleanup, its AI assist rows and suggestion validation rows are deleted too.

## What is logged

Logs should contain operational metadata only: status, error code, model, prompt version, context hash, duration, input/output sizes, estimated tokens, provider token timings, redaction counts, suggestion counts, and rejection counts. Prompt bodies, raw transcript bodies, provider stack traces, and secret values should not be logged.

## Provider and key handling

The provider contract is OpenAI-compatible `/v1/chat/completions`. Run assists request streamed responses so the UI can show elapsed progress and token counts while local models are still generating. The diagnostics page also probes `/v1/models` and can send a tiny JSON-only test prompt when AI is enabled.

When the bundled llama.cpp sidecar is used, assist requests ask the provider to reuse matching prompt prefixes so repeated local requests spend less time on identical system and developer prompt text. The bundled profile uses one llama-server slot by default because the app already serializes local AI calls, which keeps prompt reuse more predictable on CPU-only hosts. This cache lives inside the local model server process. It is enabled only for the bundled local llama.cpp profile, not for arbitrary OpenAI-compatible endpoints.

`AI_API_KEY_SECRET_NAME` uses the existing encrypted session vault when an AI request has a session context. `AI_API_KEY` is the process/config fallback for deployments that prefer environment-managed credentials. The client sends an `Authorization` header only when a non-empty key is available, so local unauthenticated providers do not receive an empty bearer token.

By default, `AI_REQUIRE_PRIVATE_BASE_URL=true` requires the provider host to resolve to loopback, private, link-local, or explicitly allowed CIDR ranges. Hosted providers require an explicit configuration change.

AI write actions use Redis-backed per-session and global rate limits, a short enqueue lock, and a heartbeat-backed global worker slot before a provider call starts. If Redis is unavailable, new AI writes fail closed instead of letting multiple web or worker processes fan out against a local model. Cached read routes remain scoped to the owning session.

## Operator checks

Use `/diag` from an allowed diagnostics CIDR to see whether AI is disabled, misconfigured, reachable, and whether the configured model appears in `/v1/models`. The **Test prompt** action is rate-limited and returns latency plus the raw small test response so operators can debug provider setup without sending run output.
