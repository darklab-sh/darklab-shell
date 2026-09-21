// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { defineConfig, devices } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { buildIsolatedWebServer, testDir } from './playwright.shared.js'
import { selectedWebServers } from './playwright.project-selection.js'

if (!process.env.PW_E2E_POSTGRES_DSN) {
  throw new Error('PW_E2E_POSTGRES_DSN is required; use scripts/run_postgres_tests.sh --browser')
}

const basePort = Number.parseInt(process.env.PLAYWRIGHT_BASE_PORT || '5201', 10)
const profiles = JSON.parse(readFileSync(new URL('./playwright.postgres-profiles.json', import.meta.url), 'utf8'))

const webServer = selectedWebServers(profiles.map(([name, slot, profile, tls], index) => [
  name, buildIsolatedWebServer(basePort + index, slot, profile, tls),
]))

export default defineConfig({
  testDir,
  metadata: { configuredServerCount: webServer.length },
  fullyParallel: false,
  workers: profiles.length,
  retries: process.env.CI ? 1 : 0,
  failOnFlakyTests: Boolean(process.env.CI),
  forbidOnly: Boolean(process.env.CI),
  reporter: [['list'], ['html', { open: 'never' }], ['./playwright.timing-reporter.js']],
  projects: profiles.map(([name, , , tls], index) => ({
    name,
    workers: 1,
    testMatch: ['auth-profile-qualification.spec.js', 'operator-console.spec.js'],
    use: {
      ...devices['Desktop Chrome'],
      baseURL: `${tls ? 'https' : 'http'}://127.0.0.1:${basePort + index}`,
      ignoreHTTPSErrors: tls,
      trace: 'retain-on-failure',
    },
  })),
  webServer,
})
