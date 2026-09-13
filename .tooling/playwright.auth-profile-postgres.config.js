// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { defineConfig, devices } from '@playwright/test'
import { buildIsolatedWebServer, testDir } from './playwright.shared.js'

if (!process.env.PW_E2E_POSTGRES_DSN) {
  throw new Error('PW_E2E_POSTGRES_DSN is required; use scripts/run_postgres_tests.sh --browser')
}

const basePort = Number.parseInt(process.env.PLAYWRIGHT_BASE_PORT || '5201', 10)
const profiles = [
  ['chromium-w1', 'pg-open', 'open', false],
  ['chromium-restricted', 'pg-restricted', 'token_required', false],
  ['chromium-oidc', 'pg-mixed', 'mixed', true],
  ['chromium-oidc-required', 'pg-oidc-required', 'oidc_required', true],
]

export default defineConfig({
  testDir,
  fullyParallel: false,
  workers: profiles.length,
  retries: process.env.CI ? 1 : 0,
  failOnFlakyTests: Boolean(process.env.CI),
  forbidOnly: Boolean(process.env.CI),
  reporter: [['list'], ['html', { open: 'never' }]],
  projects: profiles.map(([name, , , tls], index) => ({
    name,
    testMatch: ['auth-profile-qualification.spec.js'],
    use: {
      ...devices['Desktop Chrome'],
      baseURL: `${tls ? 'https' : 'http'}://127.0.0.1:${basePort + index}`,
      ignoreHTTPSErrors: tls,
      trace: 'on-first-retry',
    },
  })),
  webServer: profiles.map(([, slot, profile, tls], index) =>
    buildIsolatedWebServer(basePort + index, slot, profile, tls)),
})
