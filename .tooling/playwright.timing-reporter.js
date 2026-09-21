// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve, basename } from 'node:path'

export function summarizeSamples(samples) {
  const sorted = [...samples].sort((a, b) => a - b)
  const percentile = (fraction) => sorted.length ? sorted[Math.ceil(sorted.length * fraction) - 1] : null
  return { count: sorted.length, p50_ms: percentile(0.5), p95_ms: percentile(0.95) }
}

export default class TimingReporter {
  constructor() {
    this.started = performance.now()
    this.rows = new Map()
    this.navigation = []
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

  onTestEnd(test, result) {
    const project = test.parent.project().name
    const file = basename(test.location.file)
    const key = `${project}/${file}`
    const row = this.rows.get(key) || { project, file, attempts: 0, retries: 0, seconds: 0, outcomes: {} }
    row.attempts += 1
    row.retries += result.retry > 0 ? 1 : 0
    row.seconds += result.duration / 1000
    row.outcomes[result.status] = (row.outcomes[result.status] || 0) + 1
    this.rows.set(key, row)
  }

  onEnd(result) {
    if (!this.rows.size) return
    const mode = process.env.ASSET_BUNDLE_MODE === 'source' ? 'source' : 'bundle'
    const summary = {
      schema_version: 1,
      revision: process.env.CI_COMMIT_SHA || 'local',
      node: process.version,
      platform: process.platform,
      architecture: process.arch,
      mode,
      status: result.status,
      workers: this.config?.workers,
      configured_servers: this.config?.metadata?.configuredServerCount || 0,
      selected_projects: this.projects || [],
      preparation_ms: this.preparationMs,
      duration_ms: result.duration,
      navigation: summarizeSamples(this.navigation),
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
