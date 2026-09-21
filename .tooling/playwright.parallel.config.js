// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { defineConfig, devices } from '@playwright/test'
import { readdirSync } from 'fs'
import { resolve } from 'path'
import { __dirname, buildIsolatedWebServer, testDir } from './playwright.shared.js'
import { selectedWebServers } from './playwright.project-selection.js'

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
  .filter((name) => !['restricted-access.spec.js', 'oidc-access.spec.js', 'auth-profile-qualification.spec.js', 'operator-console.spec.js'].includes(name))
  .sort()

// Rounded per-spec seconds from successful CI job 16620146718 (2026-09-21).
// Refresh from DARKLAB_PLAYWRIGHT_TIMINGS; skipped demo specs keep a small weight.
const specWeights = {
  'access.spec.js': 67,
  'assessment.spec.js': 96,
  'autocomplete.spec.js': 26,
  'boot-resilience.spec.js': 9,
  'commands.spec.js': 23,
  'compare.spec.js': 33,
  'demo.mobile.spec.js': 1,
  'demo.spec.js': 1,
  'failure-paths.spec.js': 24,
  'history.spec.js': 91,
  'interaction-contract.spec.js': 59,
  'kill.spec.js': 26,
  'mobile.spec.js': 180,
  'output.spec.js': 59,
  'probes.spec.js': 21,
  'project-list-layout.spec.js': 15,
  'project-overview.spec.js': 14,
  'rate-limit.spec.js': 3,
  'runner-stall.spec.js': 6,
  'search.spec.js': 20,
  'share.spec.js': 47,
  'shortcuts.spec.js': 99,
  'source-lazy-smoke.spec.js': 25,
  'tabs.spec.js': 71,
  'team-mode.spec.js': 29,
  'theme-audit.spec.js': 8,
  'timestamps.spec.js': 17,
  'ui.spec.js': 344,
  'welcome-context.spec.js': 24,
  'welcome-interactions.spec.js': 33,
  'welcome.spec.js': 36,
}
const missingWeights = allSpecFiles.filter((name) => !(name in specWeights))
if (missingWeights.length) console.warn(`[e2e] fallback spec weight (5 seconds): ${missingWeights.join(', ')}`)

const weightedSpecs = [...allSpecFiles]
  .map((name) => ({ name, weight: specWeights[name] || 5 }))
  .sort((a, b) => {
    if (b.weight !== a.weight) return b.weight - a.weight
    return a.name.localeCompare(b.name)
  })

const buckets = Array.from({ length: projectCount }, (_, index) => ({
  index,
  // The first open project also owns access-profile and operator qualification.
  totalWeight: index === 0 ? 27 : 0,
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

const openProjects = specGroups
  .map((specs, index) => {
    if (!specs.length && index !== 0) return null
    return {
      name: `chromium-w${index + 1}`,
      testMatch: index === 0 ? [...specs, 'auth-profile-qualification.spec.js', 'operator-console.spec.js'] : specs,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: `http://127.0.0.1:${basePort + index}`,
        trace: 'retain-on-failure',
      },
    }
  })
  .filter(Boolean)

const restrictedPort = basePort + projectCount
const restrictedProject = {
  name: 'chromium-restricted',
  testMatch: ['restricted-access.spec.js'],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://127.0.0.1:${restrictedPort}`,
    trace: 'retain-on-failure',
  },
}
const oidcPort = restrictedPort + 1
const oidcProject = {
  name: 'chromium-oidc',
  testMatch: ['oidc-access.spec.js'],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `https://127.0.0.1:${oidcPort}`,
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
  },
}
const oidcRequiredPort = oidcPort + 1
const oidcRequiredProject = {
  name: 'chromium-oidc-required',
  testMatch: ['auth-profile-qualification.spec.js', 'operator-console.spec.js'],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `https://127.0.0.1:${oidcRequiredPort}`,
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
  },
}
const restrictedQualificationPort = oidcRequiredPort + 1
const restrictedQualificationProject = {
  name: 'chromium-restricted-qualification',
  testMatch: ['auth-profile-qualification.spec.js', 'operator-console.spec.js'],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://127.0.0.1:${restrictedQualificationPort}`,
    trace: 'retain-on-failure',
  },
}
const oidcQualificationPort = restrictedQualificationPort + 1
const oidcQualificationProject = {
  name: 'chromium-oidc-qualification',
  testMatch: ['auth-profile-qualification.spec.js', 'operator-console.spec.js'],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `https://127.0.0.1:${oidcQualificationPort}`,
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
  },
}
// Tests in one project share an app process and database. Keep parallelism
// between isolated servers instead of letting one project use every worker.
const projects = [
  ...openProjects, restrictedProject, oidcProject, oidcRequiredProject,
  restrictedQualificationProject, oidcQualificationProject,
].map((project) => ({ ...project, workers: 1 }))

const webServer = selectedWebServers([
  ...openProjects.map((project, index) => [
    project.name, buildIsolatedWebServer(basePort + index, `w${index + 1}`),
  ]),
  [restrictedProject.name, buildIsolatedWebServer(restrictedPort, 'restricted', 'token_required')],
  [oidcProject.name, buildIsolatedWebServer(oidcPort, 'oidc', 'mixed', true)],
  [oidcRequiredProject.name, buildIsolatedWebServer(oidcRequiredPort, 'oidc-required', 'oidc_required', true)],
  [restrictedQualificationProject.name, buildIsolatedWebServer(restrictedQualificationPort, 'restricted-qualification', 'token_required')],
  [oidcQualificationProject.name, buildIsolatedWebServer(oidcQualificationPort, 'oidc-qualification', 'mixed', true)],
])

export default defineConfig({
  testDir,
  metadata: { configuredServerCount: webServer.length },
  fullyParallel: false,
  // Auth-profile projects share this total budget with the open-profile shards.
  workers: Math.min(process.env.CI ? 3 : 7, projects.length),
  retries: process.env.CI ? 1 : 0,
  failOnFlakyTests: Boolean(process.env.CI),
  forbidOnly: Boolean(process.env.CI),
  reporter: [['list'], ['html', { open: 'never' }], ['./playwright.timing-reporter.js']],
  projects,
  webServer,
})
