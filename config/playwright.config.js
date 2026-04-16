import { defineConfig, devices } from '@playwright/test'
import { buildIsolatedWebServer, testDir } from './playwright.shared.js'

export default defineConfig({
  testDir,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
  ],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:5001',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium' },
  ],
  webServer: buildIsolatedWebServer(5001, 'vscode'),
})
