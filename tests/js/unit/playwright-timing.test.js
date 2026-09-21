// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, it } from 'vitest'
import TimingReporter, { summarizeSamples } from '../../../.tooling/playwright.timing-reporter.js'

describe('browser timing evidence', () => {
  it('preserves samples while computing percentiles and empty results', () => {
    const samples = [20, 10, 30]
    expect(summarizeSamples(samples)).toEqual({ count: 3, p50_ms: 20, p95_ms: 30 })
    expect(samples).toEqual([20, 10, 30])
    expect(summarizeSamples([])).toEqual({ count: 0, p50_ms: null, p95_ms: null })
  })

  it('counts failed attempts separately and never stores titles or attachments', () => {
    const reporter = new TimingReporter()
    const test = { parent: { project: () => ({ name: 'chromium-w1' }) }, location: { file: '/private/tests/theme.spec.js' }, title: 'private credential' }
    reporter.onTestEnd(test, { status: 'failed', duration: 100, retry: 0, attachments: ['private credential'] })
    reporter.onTestEnd(test, { status: 'passed', duration: 50, retry: 1 })
    expect([...reporter.rows.values()]).toEqual([{
      project: 'chromium-w1', file: 'theme.spec.js', attempts: 2, retries: 1, seconds: expect.any(Number),
      outcomes: { failed: 1, passed: 1 },
    }])
    expect([...reporter.rows.values()][0].seconds).toBeCloseTo(0.15)
    reporter.onStepEnd(test, {}, { category: 'pw:api', title: 'Navigate to private URL', duration: 90 })
    reporter.onStepEnd(test, {}, { category: 'pw:api', title: 'page.goto(private URL)', duration: 500, error: {} })
    expect(reporter.navigation).toEqual([90])
    expect(JSON.stringify([...reporter.rows.values()])).not.toContain('private')
  })
})
