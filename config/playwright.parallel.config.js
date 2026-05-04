import { defineConfig, devices } from '@playwright/test'
import { readdirSync } from 'fs'
import { resolve } from 'path'
import { __dirname, buildIsolatedWebServer, testDir } from './playwright.shared.js'

const projectCount = Math.max(
  1,
  Number.parseInt(process.env.PLAYWRIGHT_PROJECT_COUNT || '5', 10) || 5,
)
const basePort = Math.max(
  1,
  Number.parseInt(process.env.PLAYWRIGHT_BASE_PORT || '5001', 10) || 5001,
)

const allSpecFiles = readdirSync(resolve(__dirname, 'tests/js/e2e'))
  .filter((name) => name.endsWith('.spec.js'))
  .sort()

// Wall-clock weights from local runs so projects are balanced by elapsed time,
// not by file count. Split welcome flows are weighted separately so the old
// 70s+ long pole can be distributed across multiple workers.
const specWeights = {
  'welcome.spec.js': 25,
  'welcome-interactions.spec.js': 24,
  'welcome-context.spec.js': 17,
  'mobile.spec.js': 21,
  'share.spec.js': 11,
  'session-token.spec.js': 7,
  'history.spec.js': 10,
  'timestamps.spec.js': 10,
  'tabs.spec.js': 8,
  'shortcuts.spec.js': 8,
  'output.spec.js': 7,
  'search.spec.js': 5,
  'autocomplete.spec.js': 5,
  'kill.spec.js': 5,
  'commands.spec.js': 4,
  'runner-stall.spec.js': 4,
  'rate-limit.spec.js': 4,
  'boot-resilience.spec.js': 4,
  'ui.spec.js': 5,
  'failure-paths.spec.js': 6,
  // Demo recording specs skip immediately unless RUN_DEMO=1 is set.
  'demo.spec.js': 1,
  'demo.mobile.spec.js': 1,
}

const weightedSpecs = [...allSpecFiles]
  .map((name) => ({ name, weight: specWeights[name] || 5 }))
  .sort((a, b) => {
    if (b.weight !== a.weight) return b.weight - a.weight
    return a.name.localeCompare(b.name)
  })

const buckets = Array.from({ length: projectCount }, (_, index) => ({
  index,
  totalWeight: 0,
  specs: [],
}))

for (const spec of weightedSpecs) {
  buckets.sort((a, b) => {
    if (a.totalWeight !== b.totalWeight) return a.totalWeight - b.totalWeight
    return a.index - b.index
  })
  buckets[0].specs.push(spec.name)
  buckets[0].totalWeight += spec.weight
}

const specGroups = buckets.sort((a, b) => a.index - b.index).map((bucket) => bucket.specs.sort())

const projects = specGroups
  .map((specs, index) => {
    if (!specs.length) return null
    return {
      name: `chromium-w${index + 1}`,
      testMatch: specs,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: `http://localhost:${basePort + index}`,
        trace: 'on-first-retry',
      },
    }
  })
  .filter(Boolean)

export default defineConfig({
  testDir,
  fullyParallel: false,
  workers: projects.length,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  projects,
  webServer: projects.map((project, index) =>
    buildIsolatedWebServer(basePort + index, `w${index + 1}`),
  ),
})
