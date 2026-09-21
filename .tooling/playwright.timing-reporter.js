// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve, basename } from 'node:path'
import { execFileSync, spawnSync } from 'node:child_process'
import { availableParallelism, totalmem } from 'node:os'

function revisionMetadata() {
  try {
    return {
      revision: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(),
      working_tree_dirty: spawnSync('git', ['diff', '--quiet', 'HEAD'], { stdio: 'ignore' }).status !== 0,
    }
  } catch { return { revision: 'unknown', working_tree_dirty: null } }
}

export function summarizeSamples(samples) {
  const sorted = [...samples].sort((a, b) => a - b)
  const percentile = (fraction) => sorted.length ? sorted[Math.ceil(sorted.length * fraction) - 1] : null
  return { count: sorted.length, p50_ms: percentile(0.5), p95_ms: percentile(0.95) }
}

export function readStartupSample(attachment) {
  if (attachment?.name !== 'startup-timing' || !attachment.body || attachment.body.length > 8192) return null
  try {
    const value = JSON.parse(attachment.body.toString())
    const bounded = (number, max = 600000) => Number.isFinite(number) && number >= 0 && number <= max
    if (!['fresh-context', 'reload'].includes(value.cache) || !['desktop', 'mobile'].includes(value.viewport)
        || !bounded(value.prompt_ms) || !bounded(value.navigation_ms)) return null
    const requests = {}
    for (const key of ['config', 'preferences', 'active', 'recall', 'catalogs', 'other', 'static', 'cached_static']) {
      if (Number.isInteger(value.requests?.[key]) && bounded(value.requests[key], 10000)) requests[key] = value.requests[key]
    }
    return {
      cache: value.cache, viewport: value.viewport, prompt_ms: value.prompt_ms, navigation_ms: value.navigation_ms,
      first_paint_ms: bounded(value.first_paint_ms) ? value.first_paint_ms : null,
      requests,
    }
  } catch { return null }
}

export default class TimingReporter {
  constructor() {
    this.started = performance.now()
    this.rows = new Map()
    this.navigation = []
    this.startup = []
    this.busyWorkers = new Set()
    this.peakBusyWorkers = 0
  }

  onBegin(config, suite) {
    this.config = config
    this.preparationMs = performance.now() - this.started
    this.projects = suite.suites.map((project) => project.title)
  }

  onStepEnd(test, result, step) {
    if (step.category === 'pw:api' && /^(?:page\.goto\b|Navigate to )/.test(step.title) && !step.error) {
      this.navigation.push(step.duration)
    }
  }

  onTestBegin(test, result) {
    this.busyWorkers.add(result.workerIndex)
    this.peakBusyWorkers = Math.max(this.peakBusyWorkers, this.busyWorkers.size)
  }

  onTestEnd(test, result) {
    this.busyWorkers.delete(result.workerIndex)
    const project = test.parent.project().name
    const file = basename(test.location.file)
    const key = `${project}/${file}`
    const row = this.rows.get(key) || { project, file, attempts: 0, retries: 0, seconds: 0, outcomes: {} }
    row.attempts += 1
    row.retries += result.retry > 0 ? 1 : 0
    row.seconds += result.duration / 1000
    row.outcomes[result.status] = (row.outcomes[result.status] || 0) + 1
    this.rows.set(key, row)
    if (result.status === 'passed') {
      for (const attachment of result.attachments || []) {
        const sample = readStartupSample(attachment)
        if (sample) this.startup.push({ project, ...sample })
      }
    }
  }

  onEnd(result) {
    if (!this.rows.size) return
    const mode = process.env.ASSET_BUNDLE_MODE === 'source' ? 'source' : 'bundle'
    const summary = {
      schema_version: 1,
      ...revisionMetadata(),
      node: process.version,
      platform: process.platform,
      architecture: process.arch,
      available_cpus: availableParallelism(),
      host_memory_bytes: totalmem(),
      ci_runner_id: /^\d+$/.test(process.env.CI_RUNNER_ID || '') ? Number(process.env.CI_RUNNER_ID) : null,
      mode,
      status: result.status,
      workers: this.config?.workers,
      peak_busy_workers: this.peakBusyWorkers,
      configured_servers: this.config?.metadata?.configuredServerCount || 0,
      selected_projects: this.projects || [],
      preparation_ms: this.preparationMs,
      duration_ms: result.duration,
      navigation: summarizeSamples(this.navigation),
      startup: this.startup,
      specs: [...this.rows.values()].sort((a, b) => `${a.project}/${a.file}`.localeCompare(`${b.project}/${b.file}`)),
    }
    const directory = resolve('test-results/timings')
    mkdirSync(directory, { recursive: true })
    writeFileSync(resolve(directory, `playwright-${mode}.json`), `${JSON.stringify(summary, null, 2)}\n`)
    // Successful CI jobs retain this small summary in their trace; full browser
    // reports, logs and attachments continue to be uploaded only on failure.
    console.log(`DARKLAB_PLAYWRIGHT_TIMINGS ${JSON.stringify(summary)}`)
  }
}
